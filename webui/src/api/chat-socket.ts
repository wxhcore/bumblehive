import { WS_URL } from "./config";
import type { ApprovalMode, ChatFrame } from "../types/api";

interface ChatSocketCallbacks {
  onFrame: (frame: ChatFrame) => void | Promise<void>;
  onDisconnect: () => void;
}

export class ChatSocket {
  private socket: WebSocket | null = null;
  private connectPromise: Promise<void> | null = null;
  private closedByClient = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private dispatch = Promise.resolve();

  constructor(
    private readonly sessionId: string,
    private readonly callbacks: ChatSocketCallbacks,
  ) {}

  get connected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  connect(): Promise<void> {
    if (this.connectPromise) return this.connectPromise;
    if (this.connected) return Promise.resolve();

    this.closedByClient = false;
    this.connectPromise = new Promise((resolve, reject) => {
      const socket = new WebSocket(
        `${WS_URL}/ws/v1/chat/${encodeURIComponent(this.sessionId)}`,
      );
      let ready = false;
      this.socket = socket;

      socket.onmessage = (event) => {
        let frame: ChatFrame;
        try {
          frame = JSON.parse(String(event.data)) as ChatFrame;
        } catch {
          reject(new Error("服务端返回了无效消息"));
          socket.close();
          return;
        }

        this.dispatch = this.dispatch
          .then(async () => {
            await this.callbacks.onFrame(frame);
            if (frame.type === "ready") {
              ready = true;
              resolve();
            }
          })
          .catch(reject);
      };

      socket.onerror = () => {
        if (!ready) reject(new Error("无法连接聊天服务"));
      };

      socket.onclose = () => {
        this.socket = null;
        this.connectPromise = null;
        if (!ready) reject(new Error("聊天服务连接已关闭"));
        if (!this.closedByClient) {
          this.callbacks.onDisconnect();
          this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            if (!this.closedByClient) void this.connect().catch(() => undefined);
          }, 1000);
        }
      };
    });

    return this.connectPromise;
  }

  whenSynced(): Promise<void> {
    return this.dispatch;
  }

  send(
    content: string,
    workspace: string | null,
    approvalMode: ApprovalMode,
    messageId: string = crypto.randomUUID(),
  ): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error("聊天服务尚未连接");
    }
    this.socket.send(
      JSON.stringify({
        type: "message",
        message_id: messageId,
        content,
        approval_mode: approvalMode,
        ...(workspace?.trim()
          ? { config: { runtime: { workspace: workspace.trim() } } }
          : {}),
      }),
    );
  }

  updatePending(type: "steer" | "remove_pending", messageId: string): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error("聊天服务尚未连接");
    }
    this.socket.send(JSON.stringify({ type, message_id: messageId }));
  }

  decideApproval(approvalId: string, approved: boolean): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error("聊天服务尚未连接");
    }
    this.socket.send(JSON.stringify({
      type: "approval_decision",
      approval_id: approvalId,
      approved,
    }));
  }

  cancel(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error("聊天服务尚未连接");
    }
    this.socket.send(JSON.stringify({ type: "cancel" }));
  }

  close(): void {
    this.closedByClient = true;
    if (this.reconnectTimer !== null) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.socket?.close();
    this.socket = null;
    this.connectPromise = null;
  }
}

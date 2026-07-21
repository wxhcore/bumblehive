import { WS_URL } from "./config";
import type { ChatFrame } from "../types/api";

interface ChatSocketCallbacks {
  onFrame: (frame: ChatFrame) => void;
  onDisconnect: () => void;
}

export class ChatSocket {
  private socket: WebSocket | null = null;
  private connectPromise: Promise<void> | null = null;
  private closedByClient = false;

  constructor(
    private readonly sessionId: string,
    private readonly callbacks: ChatSocketCallbacks,
  ) {}

  get connected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  connect(): Promise<void> {
    if (this.connected) return Promise.resolve();
    if (this.connectPromise) return this.connectPromise;

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

        if (frame.type === "ready") {
          ready = true;
          resolve();
          return;
        }
        this.callbacks.onFrame(frame);
      };

      socket.onerror = () => {
        if (!ready) reject(new Error("无法连接聊天服务"));
      };

      socket.onclose = () => {
        this.socket = null;
        this.connectPromise = null;
        if (!ready) reject(new Error("聊天服务连接已关闭"));
        if (!this.closedByClient) this.callbacks.onDisconnect();
      };
    });

    return this.connectPromise;
  }

  send(content: string): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error("聊天服务尚未连接");
    }
    this.socket.send(JSON.stringify({ type: "message", content }));
  }

  cancel(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error("聊天服务尚未连接");
    }
    this.socket.send(JSON.stringify({ type: "cancel" }));
  }

  close(): void {
    this.closedByClient = true;
    this.socket?.close();
    this.socket = null;
    this.connectPromise = null;
  }
}

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  deleteSession,
  getSession,
  getSessions,
  updateSettings,
} from "./api/http";
import { ChatView } from "./components/ChatView";
import { Composer } from "./components/Composer";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { DesktopTitlebar } from "./components/DesktopTitlebar";
import { HomeView } from "./components/HomeView";
import { SettingsView } from "./components/SettingsView";
import { Sidebar } from "./components/Sidebar";
import { useChatRuntime } from "./hooks/useChatRuntime";
import { useBlankSessions } from "./hooks/useBlankSessions";
import { useModels } from "./hooks/useModels";
import { useServerBootstrap } from "./hooks/useServerBootstrap";
import { historyMessages } from "./lib/chat-events";
import {
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  useSidebarWidth,
} from "./hooks/useSidebarWidth";
import { useStableCallback } from "./hooks/useStableCallback";
import { useToast } from "./hooks/useToast";
import {
  isMacDesktop,
  pickWorkspaceDirectory,
} from "./lib/platform";
import {
  sessionBranchIds,
  type PendingSessionInfo,
} from "./lib/session-tree";
import {
  mergeDiscoveredWorkspaces,
  readSelectedWorkspace,
  readWorkspaceRegistry,
  removeKnownWorkspace,
  workspaceKey,
  workspaceLabel,
  writeSelectedWorkspace,
  writeWorkspaceRegistry,
} from "./lib/workspaces";
import type {
  SessionSummary,
  Settings,
  SettingsUpdate,
} from "./types/api";

function isProviderConfigured(settings: Settings): boolean {
  return (
    settings.provider.api_key_configured &&
    Boolean(settings.provider.model?.trim())
  );
}

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [workspaceRegistry, setWorkspaceRegistry] = useState(
    readWorkspaceRegistry,
  );
  const [selectedWorkspace, setSelectedWorkspace] = useState<string | null>(
    readSelectedWorkspace,
  );
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [pendingSessionInfo, setPendingSessionInfo] = useState<
    ReadonlyMap<string, PendingSessionInfo>
  >(() => new Map());
  const [input, setInput] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const [focusSettingsWorkspace, setFocusSettingsWorkspace] =
    useState(false);
  const [deleteSessionId, setDeleteSessionId] = useState<string | null>(null);
  const [removeWorkspacePath, setRemoveWorkspacePath] = useState<string | null>(
    null,
  );
  const { message: toast, notify } = useToast();
  const sidebar = useSidebarWidth();

  const sessionsLoadVersionRef = useRef(0);
  const sessionSelectionVersionRef = useRef(0);
  const loadSessions = useCallback(async () => {
    const version = ++sessionsLoadVersionRef.current;
    const loaded = await getSessions();
    if (version !== sessionsLoadVersionRef.current) return;
    setSessions(loaded);
    setWorkspaceRegistry((current) =>
      mergeDiscoveredWorkspaces(
        current,
        loaded.map((session) => ({
          path: session.workspace,
          createdAt: session.created_at,
        })),
      ),
    );
    const persistedIds = new Set(loaded.map((session) => session.session_id));
    setPendingSessionInfo((pending) => {
      const next = new Map(pending);
      persistedIds.forEach((sessionId) => next.delete(sessionId));
      return next;
    });
  }, []);

  const {
    activeSessionId,
    displaySession,
    forgetSessions,
    getSessionMessages,
    isSessionRunning,
    messages,
    runningSessionIds,
    setCachedSessionMessages,
    startRun,
    stopActiveRun,
    stoppingSessionIds,
  } = useChatRuntime({
    onNotify: notify,
    onSessionCreated: (sessionId, session) => {
      setPendingSessionInfo((current) =>
        new Map(current).set(sessionId, session),
      );
    },
    onSessionSettled: () => {
      void loadSessions().catch(() => notify("会话列表刷新失败"));
    },
  });
  const {
    load: loadAvailableModels,
    select: selectModel,
    selectable: selectableModels,
    switching: modelSwitching,
  } = useModels({
    settings,
    setSettings,
    hasRunningSessions: runningSessionIds.size > 0,
    notify,
  });
  const { retry: retryBootstrap, status: bootstrapStatus } =
    useServerBootstrap({
      onReady: (loadedSettings, loadedSessions) => {
        const currentWorkspace = loadedSettings.runtime.workspace?.trim();
        const discoveredRegistry = mergeDiscoveredWorkspaces(
          readWorkspaceRegistry(),
          [
            ...loadedSessions.map((session) => ({
              path: session.workspace,
              createdAt: session.created_at,
            })),
            ...(currentWorkspace
              ? [
                  {
                    path: currentWorkspace,
                    createdAt: Date.now() / 1000,
                  },
                ]
              : []),
          ],
        );
        const storedSelection = readSelectedWorkspace();
        const nextSelection =
          discoveredRegistry.items.find(
            (workspace) =>
              workspaceKey(workspace.path) === workspaceKey(storedSelection),
          )?.path ??
          discoveredRegistry.items.find(
            (workspace) =>
              workspaceKey(workspace.path) === workspaceKey(currentWorkspace),
          )?.path ??
          discoveredRegistry.items[0]?.path ??
          null;
        setSettings(loadedSettings);
        setWorkspaceRegistry(discoveredRegistry);
        setSelectedWorkspace(nextSelection);
        void loadAvailableModels(loadedSettings);
        setSessions(loadedSessions);
        setShowSettings(!isProviderConfigured(loadedSettings));
      },
    });

  useEffect(() => {
    writeWorkspaceRegistry(workspaceRegistry);
  }, [workspaceRegistry]);

  useEffect(() => {
    writeSelectedWorkspace(selectedWorkspace);
  }, [selectedWorkspace]);

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        document.getElementById("newChat")?.click();
      }
    }
    document.addEventListener("keydown", handleShortcut);
    return () => document.removeEventListener("keydown", handleShortcut);
  }, []);

  function workspaceForSession(sessionId: string | null): string | null {
    if (!sessionId) return null;
    return (
      pendingSessionInfo.get(sessionId)?.workspace ??
      sessions.find((session) => session.session_id === sessionId)
        ?.workspace ??
      null
    );
  }

  const blankSessions = useBlankSessions({
    sessions,
    pendingSessions: pendingSessionInfo,
    workspaceForSession,
    getSessionMessages,
    isSessionRunning,
  });

  function rememberWorkspace(
    workspace: string | null | undefined,
    createdAt = Date.now() / 1000,
    restore = true,
  ) {
    const path = workspace?.trim();
    if (!path) return;
    setWorkspaceRegistry((current) =>
      mergeDiscoveredWorkspaces(
        current,
        [{ path, createdAt }],
        restore,
      ),
    );
  }

  function newChatWorkspace(): string | null {
    return (
      workspaceForSession(activeSessionId) ??
      selectedWorkspace?.trim() ??
      null
    );
  }

  async function newChat(requestedWorkspace?: string | null) {
    if (!settings || !isProviderConfigured(settings)) {
      setShowSettings(true);
      notify("请先完成 API Key 和模型设置");
      return;
    }
    const workspace = requestedWorkspace?.trim() || newChatWorkspace();
    if (!workspace) {
      setShowSettings(true);
      notify("请先在设置中添加工作空间");
      return;
    }
    rememberWorkspace(workspace);
    setSelectedWorkspace(workspace);
    try {
      const selectionVersion = ++sessionSelectionVersionRef.current;
      const reusableSessionId = blankSessions.reusableSession(workspace);
      if (reusableSessionId) {
        if (reusableSessionId !== activeSessionId) {
          displaySession(reusableSessionId, []);
          setInput("");
        }
        setShowSettings(false);
        return;
      }

      const created = await blankSessions.create(workspace);
      setCachedSessionMessages(created.session_id, []);
      setPendingSessionInfo((current) =>
        new Map(current).set(created.session_id, {
          workspace: created.workspace,
        }),
      );
      rememberWorkspace(created.workspace, Date.now() / 1000);
      if (selectionVersion !== sessionSelectionVersionRef.current) return;
      displaySession(created.session_id, []);
      setInput("");
      setShowSettings(false);
    } catch (error) {
      notify(error instanceof Error ? error.message : "新建会话失败");
    }
  }

  async function selectSession(sessionId: string) {
    const selectionVersion = ++sessionSelectionVersionRef.current;
    const sessionWorkspace = workspaceForSession(sessionId);
    if (sessionWorkspace) {
      rememberWorkspace(sessionWorkspace);
      setSelectedWorkspace(sessionWorkspace);
    }
    if (sessionId === activeSessionId) {
      setShowSettings(false);
      return;
    }

    if (
      isSessionRunning(sessionId) ||
      pendingSessionInfo.has(sessionId)
    ) {
      displaySession(
        sessionId,
        getSessionMessages(sessionId) ?? [],
      );
      setShowSettings(false);
      return;
    }

    try {
      const detail = await getSession(sessionId);
      if (selectionVersion !== sessionSelectionVersionRef.current) return;
      rememberWorkspace(detail.workspace, detail.created_at);
      setSelectedWorkspace(detail.workspace);
      displaySession(sessionId, historyMessages(detail.messages));
      setShowSettings(false);
    } catch (error) {
      notify(error instanceof Error ? error.message : "会话加载失败");
    }
  }

  function requestDeleteSession(sessionId: string) {
    const branchIds = sessionBranchIds(
      sessionId,
      sessions,
      pendingSessionInfo,
    );
    if (
      [...branchIds].some((branchId) =>
        isSessionRunning(branchId),
      )
    ) {
      notify("请先停止这个会话及其 Bee 子会话中的任务");
      return;
    }
    setDeleteSessionId(sessionId);
  }

  async function confirmDeleteSession() {
    const sessionId = deleteSessionId;
    if (!sessionId) return;
    setDeleteSessionId(null);
    try {
      const deletedSessionIds = new Set(await deleteSession(sessionId));
      for (const deletedId of deletedSessionIds) {
        blankSessions.release(deletedId);
      }
      forgetSessions(deletedSessionIds);
      setSessions((current) =>
        current.filter(
          (session) => !deletedSessionIds.has(session.session_id),
        ),
      );
      setPendingSessionInfo((current) => {
        const next = new Map(current);
        deletedSessionIds.forEach((deletedId) => next.delete(deletedId));
        return next;
      });
      if (activeSessionId && deletedSessionIds.has(activeSessionId)) {
        displaySession(null, []);
      }
    } catch (error) {
      notify(error instanceof Error ? error.message : "会话删除失败");
    }
  }

  function requestRemoveWorkspace(workspace: string) {
    const key = workspaceKey(workspace);
    const sessionIds = [
      ...sessions
        .filter((session) => workspaceKey(session.workspace) === key)
        .map((session) => session.session_id),
      ...[...pendingSessionInfo]
        .filter(([, pending]) => workspaceKey(pending.workspace) === key)
        .map(([sessionId]) => sessionId),
    ];
    if (
      sessionIds.some((sessionId) =>
        isSessionRunning(sessionId),
      )
    ) {
      notify("请先停止这个工作空间中正在运行的任务");
      return;
    }
    setRemoveWorkspacePath(workspace);
  }

  async function addWorkspace() {
    try {
      const workspace = await pickWorkspaceDirectory();
      if (workspace === undefined) {
        setFocusSettingsWorkspace(true);
        setShowSettings(true);
        notify("请在设置中填写工作区路径");
        return;
      }
      if (!workspace) return;

      rememberWorkspace(workspace, Date.now() / 1000, true);
      setSelectedWorkspace(workspace);
      displaySession(null, []);
      setInput("");
      setShowSettings(false);
    } catch (error) {
      notify(
        error instanceof Error ? error.message : "工作空间目录选择失败",
      );
    }
  }

  function confirmRemoveWorkspace() {
    const workspace = removeWorkspacePath;
    if (!workspace) return;
    setRemoveWorkspacePath(null);
    const key = workspaceKey(workspace);
    const remaining = workspaceRegistry.items.filter(
      (candidate) => workspaceKey(candidate.path) !== key,
    );
    setWorkspaceRegistry((current) =>
      removeKnownWorkspace(current, workspace),
    );
    if (workspaceKey(workspaceForSession(activeSessionId)) === key) {
      displaySession(null, []);
      setInput("");
    }
    if (workspaceKey(selectedWorkspace) === key) {
      setSelectedWorkspace(remaining[0]?.path ?? null);
    }
    if (remaining.length === 0) setShowSettings(true);
    notify(`${workspaceLabel(workspace)} 已从侧栏移除`);
  }

  async function sendMessage() {
    const task = input.trim();
    if (!task) return;
    if (!settings || !isProviderConfigured(settings)) {
      setShowSettings(true);
      notify("请先完成 API Key 和模型设置");
      return;
    }

    let sessionId = activeSessionId;
    let taskWorkspace =
      workspaceForSession(sessionId) ??
      selectedWorkspace ??
      settings.runtime.workspace ??
      null;
    if (sessionId && isSessionRunning(sessionId)) return;
    try {
      if (!sessionId) {
        const workspace = newChatWorkspace();
        if (!workspace) {
          setShowSettings(true);
          notify("请先在设置中添加工作空间");
          return;
        }
        const created = await blankSessions.create(
          workspace,
        );
        sessionId = created.session_id;
        taskWorkspace = created.workspace;
        rememberWorkspace(created.workspace, Date.now() / 1000);
        setSelectedWorkspace(created.workspace);
        displaySession(created.session_id, []);
        setPendingSessionInfo((current) =>
          new Map(current).set(created.session_id, {
            workspace: created.workspace,
          }),
        );
      }

      blankSessions.release(sessionId);
      setInput("");
      await startRun({
        sessionId,
        task,
        workspace: taskWorkspace,
        fallbackMessages: messages,
      });
    } catch (error) {
      notify(error instanceof Error ? error.message : "消息发送失败");
    }
  }

  async function saveSettings(update: SettingsUpdate): Promise<Settings> {
    const saved = await updateSettings(update);
    const savedWorkspace = saved.runtime.workspace?.trim() ?? null;
    const workspaceChanged =
      workspaceKey(savedWorkspace) !== workspaceKey(selectedWorkspace);
    setSettings(saved);
    if (savedWorkspace) {
      rememberWorkspace(savedWorkspace, Date.now() / 1000, true);
      setSelectedWorkspace(savedWorkspace);
    }
    if (workspaceChanged) {
      displaySession(null, []);
      setInput("");
    }
    void loadAvailableModels(saved);
    setFocusSettingsWorkspace(false);
    setShowSettings(false);
    notify("设置已保存");
    return saved;
  }

  const isViewingRunningSession = Boolean(
    activeSessionId && runningSessionIds.has(activeSessionId),
  );
  const isViewingStoppingSession = Boolean(
    activeSessionId && stoppingSessionIds.has(activeSessionId),
  );
  const hasRunningSessions = runningSessionIds.size > 0;
  const deleteSessionTitle = deleteSessionId
    ? sessions.find((session) => session.session_id === deleteSessionId)?.title
    : null;
  const deleteSessionChildCount = deleteSessionId
    ? sessionBranchIds(deleteSessionId, sessions, pendingSessionInfo).size - 1
    : 0;
  const activeFirstUserTitle =
    messages.find((message) => message.role === "user")?.content.trim() ?? "";
  const pendingSessions = useMemo(
    () =>
      [...pendingSessionInfo].map(([sessionId, pending]) => {
        const firstUserMessage = getSessionMessages(sessionId)
          ?.find((message) => message.role === "user");
        const messageTitle =
          typeof firstUserMessage?.content === "string"
            ? firstUserMessage.content.trim()
            : "";
        return {
          sessionId,
          workspace: pending.workspace,
          title: pending.title || messageTitle || "新对话",
          parentSessionId: pending.parentSessionId,
        };
      }),
    [activeFirstUserTitle, activeSessionId, pendingSessionInfo],
  );
  const activeSessionTitle = activeSessionId
    ? sessions.find((session) => session.session_id === activeSessionId)
        ?.title ??
      pendingSessions.find((session) => session.sessionId === activeSessionId)
        ?.title ??
      "新对话"
    : "新对话";
  const activeWorkspace =
    selectedWorkspace?.trim() ??
    workspaceForSession(activeSessionId) ??
    null;
  const isBlankChat =
    isMacDesktop &&
    bootstrapStatus === "ready" &&
    !showSettings &&
    messages.length === 0;
  const handleSidebarNewChat = useStableCallback(() => void newChat());
  const handleSidebarAddWorkspace = useStableCallback(
    () => void addWorkspace(),
  );
  const handleSidebarNewChatInWorkspace = useStableCallback(
    (workspace: string) => void newChat(workspace),
  );
  const handleSidebarRemoveWorkspace = useStableCallback(
    requestRemoveWorkspace,
  );
  const handleSidebarSelectSession = useStableCallback(
    (sessionId: string) => void selectSession(sessionId),
  );
  const handleSidebarDeleteSession = useStableCallback(requestDeleteSession);
  const handleSidebarOpenSettings = useStableCallback(() => {
    setFocusSettingsWorkspace(false);
    setShowSettings(true);
  });
  const handleComposerSubmit = useStableCallback(() => void sendMessage());
  const handleComposerStop = useStableCallback(stopActiveRun);
  const handleComposerSelectModel = useStableCallback(selectModel);
  const handleComposerOpenSettings = useStableCallback(() => {
    setFocusSettingsWorkspace(false);
    setShowSettings(true);
  });
  const settingsMode =
    bootstrapStatus === "ready" && settings !== null && showSettings;

  return (
    <main
      className={`app-shell${isMacDesktop ? " platform-macos" : ""}${
        isBlankChat ? " blank-chat" : ""
      }${settingsMode ? " settings-mode" : ""}`}
      aria-label="BumbleHive 对话工作台"
      style={sidebar.style}
    >
      {isMacDesktop ? (
        <DesktopTitlebar
          title={settingsMode ? "设置" : activeSessionTitle}
        />
      ) : null}

      {settingsMode && settings ? (
        <SettingsView
          settings={settings}
          mode="settings"
          focusWorkspace={focusSettingsWorkspace}
          hasRunningSessions={hasRunningSessions}
          onCancel={() => {
            setFocusSettingsWorkspace(false);
            setShowSettings(false);
          }}
          onSave={saveSettings}
        />
      ) : (
        <>
          <Sidebar
            workspaces={workspaceRegistry.items}
            sessions={sessions}
            activeSessionId={activeSessionId}
            currentWorkspace={activeWorkspace}
            pendingSessions={pendingSessions}
            runningSessionIds={runningSessionIds}
            disabled={bootstrapStatus !== "ready"}
            settingsDisabled={bootstrapStatus !== "ready"}
            sessionSelectionDisabled={bootstrapStatus !== "ready"}
            onNewChat={handleSidebarNewChat}
            onAddWorkspace={handleSidebarAddWorkspace}
            onNewChatInWorkspace={handleSidebarNewChatInWorkspace}
            onRemoveWorkspace={handleSidebarRemoveWorkspace}
            onSelectSession={handleSidebarSelectSession}
            onDeleteSession={handleSidebarDeleteSession}
            onOpenSettings={handleSidebarOpenSettings}
          />

          <div
            className="sidebar-resizer"
            role="separator"
            aria-label="调整侧栏宽度"
            aria-orientation="vertical"
            aria-valuemin={MIN_SIDEBAR_WIDTH}
            aria-valuemax={MAX_SIDEBAR_WIDTH}
            aria-valuenow={Math.round(sidebar.width)}
            tabIndex={0}
            onDoubleClick={sidebar.reset}
            {...sidebar.resizerProps}
          />

          <section
            className={`main-panel${messages.length ? " chat-active" : ""}`}
          >
            {bootstrapStatus === "loading" ? (
              <div className="connection-state">
                <span className="connection-spinner" aria-hidden="true" />
                <h1>正在连接 BumbleHive</h1>
                <p>桌面服务启动后会自动进入工作台</p>
              </div>
            ) : null}

            {bootstrapStatus === "error" ? (
              <div className="connection-state">
                <h1>无法连接桌面服务</h1>
                <p>请确认 BumbleHive Server 已经启动</p>
                <button
                  className="primary-button"
                  type="button"
                  onClick={retryBootstrap}
                >
                  重新连接
                </button>
              </div>
            ) : null}

            {bootstrapStatus === "ready" && settings ? (
              <>
                {messages.length ? (
                  <ChatView
                    key={activeSessionId ?? "active-chat"}
                    messages={messages}
                    isStreaming={isViewingRunningSession}
                  />
                ) : (
                  <HomeView onSelectPrompt={setInput} />
                )}
                <Composer
                  value={input}
                  model={settings.provider.model ?? ""}
                  models={selectableModels}
                  workspace={workspaceLabel(activeWorkspace)}
                  disabled={bootstrapStatus !== "ready"}
                  isStreaming={isViewingRunningSession}
                  isStopping={isViewingStoppingSession}
                  modelSwitchDisabled={hasRunningSessions || modelSwitching}
                  onChange={setInput}
                  onSubmit={handleComposerSubmit}
                  onStop={handleComposerStop}
                  onSelectModel={handleComposerSelectModel}
                  onOpenSettings={handleComposerOpenSettings}
                />
              </>
            ) : null}
          </section>
        </>
      )}

      {deleteSessionId ? (
        <ConfirmDialog
          title="删除会话？"
          titleId="deleteSessionTitle"
          confirmLabel="删除"
          onCancel={() => setDeleteSessionId(null)}
          onConfirm={() => void confirmDeleteSession()}
        >
          {deleteSessionChildCount > 0
            ? `${
                deleteSessionTitle ? `“${deleteSessionTitle}”` : "该会话"
              }及其 ${deleteSessionChildCount} 个 Bee 子会话将被永久删除。`
            : deleteSessionTitle
              ? `“${deleteSessionTitle}”将被永久删除。`
              : "该会话将被永久删除。"}
        </ConfirmDialog>
      ) : null}

      {removeWorkspacePath ? (
        <ConfirmDialog
          title="移除工作空间？"
          titleId="removeWorkspaceTitle"
          confirmLabel="移除"
          onCancel={() => setRemoveWorkspacePath(null)}
          onConfirm={confirmRemoveWorkspace}
        >
          “{workspaceLabel(removeWorkspacePath)}”将从侧栏移除。本地文件夹和
          历史会话不会被删除；重新选择同一文件夹即可恢复。
        </ConfirmDialog>
      ) : null}

      <div
        className={`toast${toast ? " show" : ""}`}
        role="status"
        aria-live="polite"
      >
        {toast}
      </div>
    </main>
  );
}

import {
  PanelRightOpen,
  Pause,
  Play,
  Send,
  Settings,
  Square,
  Workflow,
} from "lucide-react";
import { useEffect, useMemo, useState, type KeyboardEvent, type PointerEvent } from "react";
import ReactMarkdown from "react-markdown";
import {
  bindCodeProject,
  createProject,
  createSession,
  getCodeProjectTree,
  getContextUsage,
  getSettings,
  listCodeProjects,
  listDocuments,
  listSessions,
  listSkills,
  openProject,
  previewDocument,
  saveSettings,
  selectCodeFiles,
  type AppSettings,
  type CodeFile,
  type CodeProject,
  type ContextUsage,
  type DocumentItem,
  type DocumentPreview,
  type Project,
  type Session,
  type SkillSummary,
} from "./api/client";
import { createRuntimeSocket, type RuntimeSocket } from "./api/ws";
import { ApprovalDialog } from "./components/ApprovalDialog";
import { RunDetails } from "./components/RunDetails";
import { Sidebar, type SidebarSectionsState } from "./components/Sidebar";
import { SettingsPanel } from "./components/SettingsPanel";
import type { ChatMessage, RunStatus, RuntimeEvent } from "./types";

const WELCOME_MESSAGE = "打开或创建论文项目后，可以开始连续会话。";

const DEFAULT_CONTEXT_USAGE: ContextUsage | null = null;

export function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: WELCOME_MESSAGE },
  ]);
  const [input, setInput] = useState("");
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [projectAction, setProjectAction] = useState<{
    status: "idle" | "busy" | "error";
    message: string;
  }>({ status: "idle", message: "" });
  const [settings, setSettings] = useState<AppSettings>({
    model: "",
    base_url: "",
    has_api_key: false,
  });
  const [resourceAction, setResourceAction] = useState<{
    status: "idle" | "busy" | "error" | "saved";
    message: string;
  }>({ status: "idle", message: "" });
  const [socket, setSocket] = useState<RuntimeSocket | null>(null);
  const [activeRunId, setActiveRunId] = useState("");
  const [documentPreview, setDocumentPreview] = useState<DocumentPreview | null>(null);
  const [activeCodeProject, setActiveCodeProject] = useState<CodeProject | null>(null);
  const [codeFiles, setCodeFiles] = useState<CodeFile[]>([]);
  const [selectedCodeFiles, setSelectedCodeFiles] = useState<string[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([
    {
      name: "idea.md",
      relative_path: "documents/notes/idea.md",
      extension: ".md",
      size: 0,
    },
  ]);
  const [skills, setSkills] = useState<SkillSummary[]>([
    { name: "literature-review", description: "" },
    { name: "opening-report", description: "" },
    { name: "thesis-system-design", description: "" },
  ]);
  const [codeProjects, setCodeProjects] = useState<CodeProject[]>([
    {
      id: "local-code",
      name: "yc-agents",
      path: "",
      mode: "read_only",
      selected_files: [],
    },
  ]);
  const [sessions, setSessions] = useState<Session[]>([
    {
      id: "local-session",
      title: "开题报告准备",
      messages: [],
      run_ids: [],
    },
  ]);
  const [activeSessionId, setActiveSessionId] = useState("local-session");
  const [contextUsage, setContextUsage] = useState<ContextUsage | null>(
    DEFAULT_CONTEXT_USAGE,
  );
  const [collapsedSections, setCollapsedSections] = useState<SidebarSectionsState>({
    documents: false,
    skills: false,
    sessions: false,
  });
  const [detailsVisible, setDetailsVisible] = useState(true);
  const [columnWidths, setColumnWidths] = useState({ left: 270, right: 340 });
  const [approval, setApproval] = useState<{
    approvalId: string;
    title: string;
    summary: string;
  } | null>(null);

  useEffect(() => {
    void refreshSkills();
  }, []);

  const workbenchColumns = useMemo(() => {
    if (!detailsVisible) {
      return `${columnWidths.left}px 6px minmax(360px, 1fr)`;
    }

    return `${columnWidths.left}px 6px minmax(360px, 1fr) 6px ${columnWidths.right}px`;
  }, [columnWidths.left, columnWidths.right, detailsVisible]);

  function sendMessage() {
    const content = input.trim();
    if (!content) return;

    setMessages((current) => [...current, { role: "user", content }]);
    setInput("");

    if (!project || !socket) {
      showChatFailure("请先打开或创建论文项目，再开始聊天。");
      return;
    }

    if (socket.getState() === "failed" || socket.getState() === "closed") {
      showChatFailure("聊天未连接，请重新打开项目后再发送。");
      return;
    }

    if (runStatus === "running" && activeRunId) {
      socket.redirectRun(activeRunId, content);
      return;
    }

    socket.sendUserMessage(content);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;

    event.preventDefault();
    sendMessage();
  }

  async function handleCreateProject() {
    await runProjectAction("正在选择项目文件夹...", async () => {
      const root = await selectProjectDirectory();
      if (!root) return;

      setProjectAction({ status: "busy", message: "正在创建项目..." });
      const createdProject = await createProject(root, projectNameFromRoot(root));
      await activateProject(createdProject);
    });
  }

  async function handleOpenProject() {
    await runProjectAction("正在选择项目文件夹...", async () => {
      const root = await selectProjectDirectory();
      if (!root) return;

      setProjectAction({ status: "busy", message: "正在打开项目..." });
      const openedProject = await openProject(root);
      await activateProject(openedProject);
    });
  }

  async function handleOpenSettings() {
    const nextOpen = !settingsOpen;
    setSettingsOpen(nextOpen);
    if (!nextOpen) return;

    setResourceAction({ status: "busy", message: "正在加载设置..." });
    try {
      const loadedSettings = await getSettings();
      setSettings(loadedSettings);
      setResourceAction({ status: "idle", message: "" });
    } catch (error) {
      setResourceAction({
        status: "error",
        message: userFacingResourceError(error),
      });
    }
  }

  async function handleSaveSettings(nextSettings: {
    model: string;
    base_url: string;
    api_key: string;
  }) {
    setResourceAction({ status: "busy", message: "正在保存设置..." });
    try {
      const savedSettings = await saveSettings(nextSettings);
      setSettings(savedSettings);
      setSettingsOpen(false);
      setResourceAction({ status: "saved", message: "设置已保存" });
    } catch (error) {
      setResourceAction({
        status: "error",
        message: userFacingResourceError(error),
      });
    }
  }

  async function handlePreviewDocument(path: string) {
    if (!project) {
      setResourceAction({ status: "error", message: "请先打开论文项目" });
      return;
    }

    setResourceAction({ status: "busy", message: "正在预览资料..." });
    try {
      const preview = await previewDocument(project.root, path);
      setDocumentPreview(preview);
      setResourceAction({ status: "idle", message: "" });
    } catch (error) {
      setResourceAction({
        status: "error",
        message: userFacingResourceError(error),
      });
    }
  }

  async function handleBindCodeProject() {
    if (!project) {
      setResourceAction({ status: "error", message: "请先打开论文项目" });
      return;
    }

    setResourceAction({ status: "busy", message: "正在选择代码项目文件夹..." });
    try {
      const path = await selectProjectDirectory();
      if (!path) {
        setResourceAction({ status: "idle", message: "" });
        return;
      }

      await bindCodeProject(project.root, projectNameFromRoot(path), path);
      const nextCodeProjects = await listCodeProjects(project.root);
      setCodeProjects(nextCodeProjects);
      setResourceAction({ status: "saved", message: "代码项目已绑定" });
    } catch (error) {
      setResourceAction({
        status: "error",
        message: userFacingResourceError(error),
      });
    }
  }

  async function handleOpenCodeProject(codeProjectId: string) {
    if (!project) {
      setResourceAction({ status: "error", message: "请先打开论文项目" });
      return;
    }

    const codeProject = codeProjects.find((item) => item.id === codeProjectId);
    if (!codeProject) return;

    setResourceAction({ status: "busy", message: "正在读取代码文件..." });
    try {
      const files = await getCodeProjectTree(project.root, codeProjectId);
      setActiveCodeProject(codeProject);
      setCodeFiles(files);
      setSelectedCodeFiles(codeProject.selected_files);
      setResourceAction({ status: "idle", message: "" });
    } catch (error) {
      setResourceAction({
        status: "error",
        message: userFacingResourceError(error),
      });
    }
  }

  async function handleSaveCodeFileSelection() {
    if (!project || !activeCodeProject) return;

    setResourceAction({ status: "busy", message: "正在保存代码文件选择..." });
    try {
      const updatedProject = await selectCodeFiles(
        project.root,
        activeCodeProject.id,
        selectedCodeFiles,
      );
      setActiveCodeProject(updatedProject);
      setCodeProjects((current) =>
        current.map((item) => (item.id === updatedProject.id ? updatedProject : item)),
      );
      setResourceAction({ status: "saved", message: "代码文件选择已保存" });
    } catch (error) {
      setResourceAction({
        status: "error",
        message: userFacingResourceError(error),
      });
    }
  }

  async function handleCreateSession() {
    if (!project) {
      setResourceAction({ status: "error", message: "请先打开论文项目" });
      return;
    }

    setResourceAction({ status: "busy", message: "正在创建新会话..." });
    try {
      const session = await createSession(project.root, "新会话");
      setSessions((current) => [session, ...current]);
      connectSession(project, session);
      setResourceAction({ status: "idle", message: "" });
    } catch (error) {
      setResourceAction({
        status: "error",
        message: userFacingResourceError(error),
      });
    }
  }

  async function runProjectAction(message: string, action: () => Promise<void>) {
    setProjectAction({ status: "busy", message });
    try {
      await action();
      setProjectAction({ status: "idle", message: "" });
    } catch (error) {
      setProjectAction({
        status: "error",
        message: userFacingProjectError(error),
      });
    }
  }

  async function activateProject(nextProject: Project) {
    const [nextDocuments, nextSessions, nextCodeProjects] = await Promise.all([
      listDocuments(nextProject.root),
      listSessions(nextProject.root),
      listCodeProjects(nextProject.root),
      refreshSkills(),
    ]).then(([loadedDocuments, loadedSessions, loadedCodeProjects]) => [
      loadedDocuments,
      loadedSessions,
      loadedCodeProjects,
    ]);
    const activeSession =
      nextSessions[0] ?? (await createSession(nextProject.root, "新会话"));
    const refreshedSessions =
      nextSessions.length > 0 ? nextSessions : [activeSession];
    connectSession(nextProject, activeSession);

    setProject(nextProject);
    setDocuments(nextDocuments);
    setSessions(refreshedSessions);
    setCodeProjects(nextCodeProjects);
    setEvents([]);
    setDocumentPreview(null);
    setActiveCodeProject(null);
    setCodeFiles([]);
    setSelectedCodeFiles([]);
    setResourceAction({ status: "idle", message: "" });
  }

  async function refreshSkills() {
    try {
      const loadedSkills = await listSkills();
      if (loadedSkills.length > 0) {
        setSkills(loadedSkills);
      }
      return loadedSkills;
    } catch {
      return skills;
    }
  }

  async function refreshContextUsage(root: string, sessionId: string) {
    try {
      const usage = await getContextUsage(root, sessionId);
      setContextUsage(isContextUsage(usage) ? usage : null);
    } catch {
      setContextUsage(null);
    }
  }

  function handleOpenSession(sessionId: string) {
    if (!project) return;

    const nextSession = sessions.find((item) => item.id === sessionId);
    if (!nextSession) return;

    connectSession(project, nextSession);
  }

  function connectSession(nextProject: Project, nextSession: Session) {
    socket?.close();
    setResourceAction({ status: "busy", message: "正在连接聊天..." });
    const nextSocket = createRuntimeSocket({
      root: nextProject.root,
      projectId: nextProject.id,
      sessionId: nextSession.id,
      onEvent: handleRuntimeEvent,
      onOpen: () => {
        setResourceAction({ status: "idle", message: "" });
      },
      onConnectionError: showChatFailure,
    });

    setSocket(nextSocket);
    setActiveSessionId(nextSession.id);
    setActiveRunId("");
    setRunStatus("idle");
    setMessages(messagesFromSession(nextSession));
    void refreshContextUsage(nextProject.root, nextSession.id);
  }

  function handleRuntimeEvent(event: RuntimeEvent) {
    setEvents((current) => [...current, event]);

    if (event.run_id) {
      setActiveRunId(event.run_id);
    }
    if (event.type === "run_started") {
      setRunStatus("running");
      setMessages((current) => [
        ...current,
        { role: "assistant", content: "已收到，正在运行..." },
      ]);
    }
    if (event.type === "run_completed") {
      setRunStatus("completed");
      setActiveRunId("");
      if (project) {
        void refreshContextUsage(project.root, event.session_id);
      }
    }
    if (event.type === "output_delta" && typeof event.payload.content === "string") {
      setMessages((current) => [
        ...current,
        { role: "assistant", content: event.payload.content },
      ]);
    }
    if (event.type === "approval_required") {
      setApproval({
        approvalId:
          typeof event.payload.approval_id === "string"
            ? event.payload.approval_id
            : "",
        title:
          typeof event.payload.title === "string"
            ? event.payload.title
            : "需要确认工具调用",
        summary:
          typeof event.payload.summary === "string" ? event.payload.summary : "",
      });
    }
    if (event.type === "run_failed") {
      setRunStatus("failed");
      setActiveRunId("");
      setMessages((current) => [
        ...current,
        { role: "assistant", content: `运行失败：${runtimeEventError(event)}` },
      ]);
    }
    if (event.type === "run_cancelled") {
      setRunStatus("cancelled");
      setActiveRunId("");
    }
  }

  function pauseRun() {
    if (socket && activeRunId) {
      socket.pauseRun(activeRunId);
    }
    setRunStatus("paused");
  }

  function resumeRun() {
    if (socket && activeRunId) {
      socket.resumeRun(activeRunId);
    }
    setRunStatus("running");
  }

  function cancelRun() {
    if (socket && activeRunId) {
      socket.cancelRun(activeRunId);
    }
    setRunStatus("cancelled");
  }

  function showChatFailure(message: string) {
    setRunStatus("failed");
    setActiveRunId("");
    setMessages((current) => [
      ...current,
      { role: "assistant", content: message },
    ]);
  }

  function toggleSection(section: keyof SidebarSectionsState) {
    setCollapsedSections((current) => ({
      ...current,
      [section]: !current[section],
    }));
  }

  function startColumnResize(
    side: "left" | "right",
    event: PointerEvent<HTMLDivElement>,
  ) {
    event.currentTarget.setPointerCapture(event.pointerId);
    const startX = event.clientX;
    const startWidths = { ...columnWidths };

    function handleMove(moveEvent: globalThis.PointerEvent) {
      const delta = moveEvent.clientX - startX;
      setColumnWidths(() => {
        if (side === "left") {
          return {
            ...startWidths,
            left: clamp(startWidths.left + delta, 220, 420),
          };
        }

        return {
          ...startWidths,
          right: clamp(startWidths.right - delta, 260, 520),
        };
      });
    }

    function handleUp() {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    }

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
  }

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div className="brand">
          <Workflow size={18} />
          <span>YC Agents</span>
        </div>
        <div className="project-label">{project ? project.name : "未打开论文项目"}</div>
        <div className={`status status-${runStatus}`}>{runStatus}</div>
        {!detailsVisible ? (
          <button
            aria-label="显示右侧栏"
            className="icon-button"
            onClick={() => setDetailsVisible(true)}
            title="显示右侧栏"
          >
            <PanelRightOpen size={18} />
          </button>
        ) : null}
        <button
          className="icon-button"
          aria-label="Settings"
          onClick={handleOpenSettings}
        >
          <Settings size={18} />
        </button>
      </header>

      {projectAction.status !== "idle" ? (
        <div
          className={`project-action project-action-${projectAction.status}`}
          role={projectAction.status === "error" ? "alert" : "status"}
        >
          {projectAction.message}
        </div>
      ) : null}

      {resourceAction.status !== "idle" ? (
        <div
          className={`project-action project-action-${resourceAction.status}`}
          role={resourceAction.status === "error" ? "alert" : "status"}
        >
          {resourceAction.message}
        </div>
      ) : null}

      <main className="workbench" style={{ gridTemplateColumns: workbenchColumns }}>
        <Sidebar
          collapsedSections={collapsedSections}
          documents={documents.map((item) => ({
            id: item.relative_path,
            label: item.relative_path,
          }))}
          skills={skills.map((item) => ({
            id: item.name,
            label: item.name,
          }))}
          codeProjects={codeProjects.map((item) => ({
            id: item.id,
            label: item.name,
          }))}
          sessions={sessions.map((item) => ({
            id: item.id,
            label: item.title,
          }))}
          activeSessionId={activeSessionId}
          onToggleSection={toggleSection}
          onOpenProject={handleOpenProject}
          onCreateProject={handleCreateProject}
          onPreviewDocument={handlePreviewDocument}
          onBindCodeProject={handleBindCodeProject}
          onCreateSession={project ? handleCreateSession : undefined}
          onOpenCodeProject={project ? handleOpenCodeProject : undefined}
          onOpenSession={project ? handleOpenSession : undefined}
        />

        <div
          aria-label="调整左栏宽度"
          aria-orientation="vertical"
          className="column-resizer"
          role="separator"
          onPointerDown={(event) => startColumnResize("left", event)}
        />

        <section className="chat-panel">
          <div className="resource-panel-slot">
            <ResourcePanel
              documentPreview={documentPreview}
              activeCodeProject={activeCodeProject}
              codeFiles={codeFiles}
              selectedCodeFiles={selectedCodeFiles}
              onToggleCodeFile={(path) =>
                setSelectedCodeFiles((current) =>
                  current.includes(path)
                    ? current.filter((item) => item !== path)
                    : [...current, path],
                )
              }
              onSaveCodeFileSelection={handleSaveCodeFileSelection}
            />
          </div>

          <div className="messages">
            {messages.map((message, index) => (
              <article
                className={`message message-${message.role}`}
                key={`${message.role}-${index}-${message.content.slice(0, 12)}`}
              >
                {message.role === "assistant" ? (
                  <MarkdownMessage content={message.content} />
                ) : (
                  message.content
                )}
              </article>
            ))}
          </div>

          <div className="composer">
            <div className="composer-box">
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                placeholder="输入你的论文任务..."
              />
              <div className="composer-footer">
                <span className="composer-context">{formatContextUsage(contextUsage)}</span>
                <div className="composer-actions">
                  <button
                    className="icon-button"
                    aria-label="Pause"
                    onClick={pauseRun}
                    title="暂停"
                  >
                    <Pause size={18} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label="Resume"
                    onClick={resumeRun}
                    title="恢复"
                  >
                    <Play size={18} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label="Cancel"
                    onClick={cancelRun}
                    title="取消"
                  >
                    <Square size={18} />
                  </button>
                  <button className="send-button" onClick={sendMessage}>
                    <Send size={18} />
                    发送
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        {detailsVisible ? (
          <>
            <div
              aria-label="调整右栏宽度"
              aria-orientation="vertical"
              className="column-resizer"
              role="separator"
              onPointerDown={(event) => startColumnResize("right", event)}
            />
            <RunDetails
              status={runStatus}
              events={events}
              onHide={() => setDetailsVisible(false)}
            />
          </>
        ) : null}
      </main>

      {settingsOpen ? (
        <div className="side-sheet">
          <SettingsPanel
            initialModel={settings.model}
            initialBaseUrl={settings.base_url}
            hasApiKey={settings.has_api_key}
            onSave={handleSaveSettings}
          />
        </div>
      ) : null}

      {approval ? (
        <ApprovalDialog
          title={approval.title}
          summary={approval.summary}
          onDecision={(decision) => {
            if (approval.approvalId) {
              socket?.sendApprovalDecision(approval.approvalId, decision);
            }
            setApproval(null);
          }}
        />
      ) : null}
    </div>
  );
}

function ResourcePanel({
  documentPreview,
  activeCodeProject,
  codeFiles,
  selectedCodeFiles,
  onToggleCodeFile,
  onSaveCodeFileSelection,
}: {
  documentPreview: DocumentPreview | null;
  activeCodeProject: CodeProject | null;
  codeFiles: CodeFile[];
  selectedCodeFiles: string[];
  onToggleCodeFile: (path: string) => void;
  onSaveCodeFileSelection: () => void;
}) {
  if (!documentPreview && !activeCodeProject) {
    return null;
  }

  return (
    <div className="resource-panel">
      {documentPreview ? (
        <section>
          <h2>{documentPreview.relative_path}</h2>
          {documentPreview.kind === "text" ? (
            <div className="document-preview">
              {documentPreview.content.split(/\r?\n/).map((line, index) => (
                <p key={`${line}-${index}`}>{line || " "}</p>
              ))}
            </div>
          ) : (
            <p>当前文件暂不支持文本预览</p>
          )}
        </section>
      ) : null}

      {activeCodeProject ? (
        <section>
          <div className="resource-panel-header">
            <h2>{activeCodeProject.name}</h2>
            <button aria-label="Save code file selection" onClick={onSaveCodeFileSelection}>
              保存代码文件选择
            </button>
          </div>
          {codeFiles.length === 0 ? (
            <p>暂无可选择代码文件</p>
          ) : (
            <div className="code-file-list">
              {codeFiles.map((file) => (
                <label className="code-file-row" key={file.relative_path}>
                  <input
                    aria-label={file.relative_path}
                    checked={selectedCodeFiles.includes(file.relative_path)}
                    onChange={() => onToggleCodeFile(file.relative_path)}
                    type="checkbox"
                  />
                  <span>{file.relative_path}</span>
                  <small>{file.size} B</small>
                </label>
              ))}
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}

function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="markdown-message">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}

function messagesFromSession(session: Session): ChatMessage[] {
  const savedMessages = Array.isArray(session.messages) ? session.messages : [];

  if (savedMessages.length === 0) {
    return [{ role: "assistant", content: WELCOME_MESSAGE }];
  }

  return savedMessages.map((message) => ({
    role: chatRole(message.role),
    content: message.content,
  }));
}

function chatRole(role: string): ChatMessage["role"] {
  if (role === "user" || role === "assistant" || role === "system") {
    return role;
  }

  return "assistant";
}

async function selectProjectDirectory(): Promise<string | null> {
  if (!window.ycAgentsDesktop?.selectProjectDirectory) {
    throw new Error("Electron directory picker bridge is unavailable.");
  }

  return window.ycAgentsDesktop.selectProjectDirectory();
}

function projectNameFromRoot(root: string): string {
  const normalized = root.replace(/\\/g, "/").replace(/\/$/, "");
  return normalized.split("/").pop() || "YC Agents Project";
}

function userFacingProjectError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);

  if (message.includes("Electron directory picker bridge is unavailable")) {
    return "请通过 Electron 桌面窗口使用文件夹选择功能";
  }

  if (message.includes("Create project failed")) {
    return "创建项目失败，请确认后端服务已启动";
  }

  if (message.includes("Open project failed")) {
    return "打开项目失败，请选择包含 project.json 的项目目录";
  }

  return `项目操作失败：${message}`;
}

function userFacingResourceError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return `资源操作失败：${message}`;
}

function runtimeEventError(event: RuntimeEvent): string {
  if (typeof event.payload.error === "string" && event.payload.error.trim()) {
    return event.payload.error;
  }

  return "请查看右侧 Run 详情";
}

function formatContextUsage(usage: ContextUsage | null): string {
  if (!usage) {
    return "上下文：未统计";
  }

  return `上下文：${formatPercent(usage.percent_used)} 已用，${formatTokenCount(
    usage.used_tokens,
  )}/${formatTokenCount(usage.max_tokens)}`;
}

function isContextUsage(value: unknown): value is ContextUsage {
  if (!value || typeof value !== "object") return false;
  const usage = value as Partial<ContextUsage>;
  return (
    typeof usage.used_tokens === "number" &&
    typeof usage.max_tokens === "number" &&
    typeof usage.percent_used === "number"
  );
}

function formatPercent(value: number): string {
  if (Number.isInteger(value)) {
    return `${value}%`;
  }

  return `${value.toFixed(1).replace(/\.0$/, "")}%`;
}

function formatTokenCount(value: number): string {
  if (value >= 1000) {
    return `${Math.round(value / 1000)}k`;
  }

  return String(value);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

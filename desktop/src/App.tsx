import { Pause, Play, Send, Settings, Square, Workflow } from "lucide-react";
import { useMemo, useState } from "react";
import { ApprovalDialog } from "./components/ApprovalDialog";
import { Sidebar } from "./components/Sidebar";
import { SettingsPanel } from "./components/SettingsPanel";
import type { ChatMessage, RunStatus, RuntimeEvent } from "./types";

export function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: "打开或创建论文项目后，可以开始连续会话。" },
  ]);
  const [input, setInput] = useState("");
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [approval, setApproval] = useState<{ title: string; summary: string } | null>(
    null,
  );

  const latestEvent = useMemo(() => events[events.length - 1], [events]);
  const documents = ["documents/notes/idea.md"];
  const codeProjects = ["yc-agents"];
  const sessions = ["开题报告准备"];

  function sendMessage() {
    const content = input.trim();
    if (!content) return;
    setMessages((current) => [...current, { role: "user", content }]);
    setEvents((current) => [
      ...current,
      {
        message_id: `local_${Date.now()}`,
        type: "user_message",
        project_id: "local",
        session_id: "local",
        run_id: "",
        created_at: new Date().toISOString(),
        payload: { content },
      },
    ]);
    setInput("");
    setRunStatus("running");
  }

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div className="brand">
          <Workflow size={18} />
          <span>YC Agents</span>
        </div>
        <div className="project-label">未打开论文项目</div>
        <div className={`status status-${runStatus}`}>{runStatus}</div>
        <button
          className="icon-button"
          aria-label="Settings"
          onClick={() => setSettingsOpen((open) => !open)}
        >
          <Settings size={18} />
        </button>
      </header>

      <main className="workbench">
        <Sidebar
          documents={documents}
          codeProjects={codeProjects}
          sessions={sessions}
          onOpenProject={() => undefined}
          onCreateProject={() => undefined}
        />

        <section className="chat-panel">
          <div className="messages">
            {messages.map((message, index) => (
              <article
                className={`message message-${message.role}`}
                key={`${message.role}-${index}`}
              >
                {message.content}
              </article>
            ))}
          </div>

          <div className="composer">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="输入你的论文任务..."
            />
            <div className="composer-actions">
              <button
                className="icon-button"
                aria-label="Pause"
                onClick={() => setRunStatus("paused")}
              >
                <Pause size={18} />
              </button>
              <button
                className="icon-button"
                aria-label="Resume"
                onClick={() => setRunStatus("running")}
              >
                <Play size={18} />
              </button>
              <button
                className="icon-button"
                aria-label="Cancel"
                onClick={() => setRunStatus("cancelled")}
              >
                <Square size={18} />
              </button>
              <button className="send-button" onClick={sendMessage}>
                <Send size={18} />
                发送
              </button>
            </div>
          </div>
        </section>

        <aside className="details-panel">
          <h2>当前 Run</h2>
          <p>状态：{runStatus}</p>
          <h3>事件</h3>
          <pre>{latestEvent ? JSON.stringify(latestEvent, null, 2) : "暂无事件"}</pre>
        </aside>
      </main>

      {settingsOpen ? (
        <div className="side-sheet">
          <SettingsPanel onSave={() => setSettingsOpen(false)} />
        </div>
      ) : null}

      {approval ? (
        <ApprovalDialog
          title={approval.title}
          summary={approval.summary}
          onDecision={() => setApproval(null)}
        />
      ) : null}
    </div>
  );
}

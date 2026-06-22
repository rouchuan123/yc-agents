import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import type React from "react";

export interface SidebarResource {
  id: string;
  label: string;
}

export interface SidebarSectionsState {
  documents: boolean;
  skills: boolean;
  sessions: boolean;
}

export interface SidebarProps {
  documents: SidebarResource[];
  skills: SidebarResource[];
  codeProjects: SidebarResource[];
  sessions: SidebarResource[];
  collapsedSections: SidebarSectionsState;
  activeSessionId?: string;
  onToggleSection: (section: keyof SidebarSectionsState) => void;
  onOpenProject: () => void;
  onCreateProject: () => void;
  onPreviewDocument: (path: string) => void;
  onBindCodeProject: () => void;
  onCreateSession?: () => void;
  onOpenCodeProject?: (id: string) => void;
  onOpenSession?: (id: string) => void;
}

export function Sidebar({
  documents,
  skills,
  codeProjects,
  sessions,
  collapsedSections,
  activeSessionId,
  onToggleSection,
  onOpenProject,
  onCreateProject,
  onPreviewDocument,
  onBindCodeProject,
  onCreateSession,
  onOpenCodeProject,
  onOpenSession,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <section>
        <h2>论文项目</h2>
        <button onClick={onOpenProject}>打开项目</button>
        <button onClick={onCreateProject}>创建项目</button>
      </section>

      <CollapsibleSection
        collapsed={collapsedSections.documents}
        id="documents"
        title="资料"
        onToggle={() => onToggleSection("documents")}
      >
        {documents.length === 0 ? (
          <p>暂无资料</p>
        ) : (
          documents.map((item) => (
            <button
              className="sidebar-link"
              key={item.id}
              onClick={() => onPreviewDocument(item.id)}
            >
              {item.label}
            </button>
          ))
        )}
      </CollapsibleSection>

      <CollapsibleSection
        collapsed={collapsedSections.skills}
        id="skills"
        title="可用技能"
        onToggle={() => onToggleSection("skills")}
      >
        {skills.length === 0 ? (
          <p>暂无技能</p>
        ) : (
          skills.map((item) => <p key={item.id}>{item.label}</p>)
        )}
      </CollapsibleSection>

      <section>
        <h2>代码项目</h2>
        <button aria-label="Bind code project" onClick={onBindCodeProject}>
          绑定代码项目
        </button>
        {codeProjects.length === 0 ? (
          <p>未绑定</p>
        ) : (
          codeProjects.map((item) =>
            onOpenCodeProject ? (
              <button
                className="sidebar-link"
                key={item.id}
                onClick={() => onOpenCodeProject(item.id)}
              >
                {item.label}
              </button>
            ) : (
              <p key={item.id}>{item.label}</p>
            ),
          )
        )}
      </section>

      <CollapsibleSection
        action={
          onCreateSession ? (
            <button
              aria-label="新增会话"
              className="section-action"
              onClick={onCreateSession}
              title="新增会话"
            >
              <Plus size={15} />
            </button>
          ) : null
        }
        collapsed={collapsedSections.sessions}
        id="sessions"
        title="会话"
        onToggle={() => onToggleSection("sessions")}
      >
        {sessions.length === 0 ? (
          <p>暂无会话</p>
        ) : (
          sessions.map((item) =>
            onOpenSession ? (
              <button
                className={`sidebar-link ${
                  item.id === activeSessionId ? "sidebar-link-active" : ""
                }`}
                key={`session-${item.id}-${item.label}`}
                onClick={() => onOpenSession(item.id)}
              >
                {item.label}
              </button>
            ) : (
              <p key={`session-${item.id}-${item.label}`}>{item.label}</p>
            ),
          )
        )}
      </CollapsibleSection>
    </aside>
  );
}

function CollapsibleSection({
  id,
  title,
  collapsed,
  action,
  children,
  onToggle,
}: {
  id: keyof SidebarSectionsState;
  title: string;
  collapsed: boolean;
  action?: React.ReactNode;
  children: React.ReactNode;
  onToggle: () => void;
}) {
  const actionText = collapsed ? "展开" : "折叠";

  return (
    <section>
      <div className="section-header">
        <button
          aria-label={`${actionText}${title}`}
          className="section-heading"
          data-testid={`section-toggle-${id}`}
          onClick={onToggle}
          title={`${actionText}${title}`}
        >
          <span>{title}</span>
          <span
            className={`section-chevron ${
              collapsed ? "" : "section-chevron-hover"
            }`}
            data-direction={collapsed ? "right" : "down"}
            data-testid={`section-chevron-${id}`}
          >
            {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
          </span>
        </button>
        {action}
      </div>
      {collapsed ? null : children}
    </section>
  );
}

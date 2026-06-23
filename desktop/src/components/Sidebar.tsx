export interface SidebarProps {
  documents: string[];
  codeProjects: string[];
  sessions: string[];
  onOpenProject: () => void;
  onCreateProject: () => void;
}

export function Sidebar({
  documents,
  codeProjects,
  sessions,
  onOpenProject,
  onCreateProject,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <section>
        <h2>论文项目</h2>
        <button onClick={onOpenProject}>打开项目</button>
        <button onClick={onCreateProject}>创建项目</button>
      </section>
      <section>
        <h2>资料</h2>
        {documents.length === 0 ? (
          <p>暂无资料</p>
        ) : (
          documents.map((item) => <p key={item}>{item}</p>)
        )}
      </section>
      <section>
        <h2>技能</h2>
        <p>开题报告</p>
        <p>文献综述</p>
        <p>系统设计</p>
      </section>
      <section>
        <h2>代码项目</h2>
        {codeProjects.length === 0 ? (
          <p>未绑定</p>
        ) : (
          codeProjects.map((item) => <p key={item}>{item}</p>)
        )}
      </section>
      <section>
        <h2>会话</h2>
        {sessions.length === 0 ? (
          <p>暂无会话</p>
        ) : (
          sessions.map((item) => <p key={item}>{item}</p>)
        )}
      </section>
    </aside>
  );
}

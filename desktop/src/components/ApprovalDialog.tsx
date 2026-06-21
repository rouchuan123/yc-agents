export interface ApprovalDialogProps {
  title: string;
  summary: string;
  onDecision: (decision: "allow_once" | "allow_for_project" | "deny") => void;
}

export function ApprovalDialog({ title, summary, onDecision }: ApprovalDialogProps) {
  return (
    <div className="approval-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="approval-dialog">
        <h2>{title}</h2>
        <p>{summary}</p>
        <div className="approval-actions">
          <button onClick={() => onDecision("allow_once")}>允许一次</button>
          <button onClick={() => onDecision("allow_for_project")}>本项目以后允许</button>
          <button onClick={() => onDecision("deny")}>拒绝</button>
        </div>
      </div>
    </div>
  );
}

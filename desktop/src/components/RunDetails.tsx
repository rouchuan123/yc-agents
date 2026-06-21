import type { RunStatus, RuntimeEvent } from "../types";

export interface RunDetailsProps {
  status: RunStatus;
  events: RuntimeEvent[];
}

function eventTitle(event: RuntimeEvent): string {
  if (typeof event.payload.title === "string") return event.payload.title;
  if (event.type === "skill_selected") return "已选择技能";
  if (event.type === "run_started") return "运行已开始";
  if (event.type === "run_completed") return "运行已完成";
  return event.type;
}

function eventSummary(event: RuntimeEvent): string {
  if (typeof event.payload.summary === "string") return event.payload.summary;
  if (event.type === "skill_selected" && typeof event.payload.selected_skill === "string") {
    return `本次使用：${event.payload.selected_skill}`;
  }
  return "";
}

export function RunDetails({ status, events }: RunDetailsProps) {
  const latestEvent = events[events.length - 1];

  return (
    <aside className="details-panel">
      <h2>当前 Run</h2>
      <p>状态：{status}</p>
      <h3>事件</h3>
      {events.length === 0 ? (
        <p>暂无事件</p>
      ) : (
        <ol className="event-list">
          {events.map((event) => (
            <li key={event.message_id}>
              <strong>{eventTitle(event)}</strong>
              {eventSummary(event) ? <p>{eventSummary(event)}</p> : null}
            </li>
          ))}
        </ol>
      )}
      <h3>Raw</h3>
      <pre>{latestEvent ? JSON.stringify(latestEvent, null, 2) : "暂无事件"}</pre>
    </aside>
  );
}

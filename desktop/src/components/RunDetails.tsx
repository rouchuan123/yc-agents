import type { RunState, RunStatus, RuntimeEvent } from "../types";

export interface RunDetailsProps {
  status: RunStatus;
  state?: RunState;
  events: RuntimeEvent[];
}

function eventType(event: RuntimeEvent): string {
  return event.event_type ?? event.type;
}

function eventTitle(event: RuntimeEvent): string {
  const type = eventType(event);
  if (typeof event.payload.title === "string") return event.payload.title;
  if (type === "skill_selected") return "已选择技能";
  if (type === "run_started") return "运行已开始";
  if (type === "run_completed") return "运行已完成";
  return type;
}

function eventSummary(event: RuntimeEvent): string {
  const type = eventType(event);
  if (typeof event.payload.summary === "string") return event.payload.summary;
  if (type === "skill_selected" && typeof event.payload.selected_skill === "string") {
    return `本次使用：${event.payload.selected_skill}`;
  }
  if (type.startsWith("tool_") && typeof event.payload.ok === "boolean") {
    return `ok=${event.payload.ok}`;
  }
  if (type === "tool_needs_approval" && typeof event.payload.reason === "string") return event.payload.reason;
  return "";
}

export function RunDetails({ status, state, events }: RunDetailsProps) {
  const latestEvent = events[events.length - 1];

  return (
    <aside className="details-panel">
      <h2>当前 Run</h2>
      <p>
        状态：<span>{status}</span>
      </p>
      {state ? (
        <div>
          <p>
            运行状态：<span>{state.status}</span>
          </p>
          {state.current_step ? <p>当前步骤：{state.current_step}</p> : null}
        </div>
      ) : null}
      <h3>事件</h3>
      {events.length === 0 ? (
        <p>暂无事件</p>
      ) : (
        <ol className="event-list">
          {events.map((event) => (
            <li key={event.message_id}>
              <strong>{eventTitle(event)}</strong>
              {typeof event.payload.tool_name === "string" ? <code>{event.payload.tool_name}</code> : null}
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

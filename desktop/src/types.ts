export type RunStatus =
  | "idle"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled";

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface RuntimeEvent {
  message_id: string;
  type: string;
  project_id: string;
  session_id: string;
  run_id: string;
  created_at: string;
  payload: Record<string, unknown>;
}

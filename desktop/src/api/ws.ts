import type { RuntimeEvent } from "../types";

const DEFAULT_WS_BASE = "ws://127.0.0.1:8765";

export interface RuntimeSocket {
  sendUserMessage(content: string): void;
  pauseRun(runId: string): void;
  resumeRun(runId: string): void;
  cancelRun(runId: string): void;
  redirectRun(runId: string, content: string): void;
  sendApprovalDecision(
    approvalId: string,
    decision: "allow_once" | "allow_for_project" | "deny",
  ): void;
  getState(): RuntimeSocketState;
  close(): void;
}

export type RuntimeSocketState = "connecting" | "open" | "failed" | "closed";

const CONNECTION_ERROR_MESSAGE = "聊天连接失败，请确认桌面后端正在运行";
const NOT_CONNECTED_MESSAGE = "Chat WebSocket is not connected.";

export function createRuntimeSocket(options: {
  root: string;
  projectId: string;
  sessionId: string;
  onEvent: (event: RuntimeEvent) => void;
  onOpen?: () => void;
  onConnectionError?: (message: string) => void;
  WebSocketImpl?: typeof WebSocket;
}): RuntimeSocket {
  const SocketImpl = options.WebSocketImpl ?? WebSocket;
  const url = `${wsBase()}/ws/projects/${options.projectId}/sessions/${options.sessionId}?root=${encodeURIComponent(options.root)}`;
  const socket = new SocketImpl(url);
  const pendingMessages: string[] = [];
  let intentionallyClosed = false;
  let state: RuntimeSocketState = "connecting";
  let reportedConnectionFailure = false;

  socket.addEventListener("message", (message) => {
    options.onEvent(JSON.parse(message.data));
  });

  socket.addEventListener("open", () => {
    state = "open";
    options.onOpen?.();
    while (pendingMessages.length > 0 && socket.readyState === 1) {
      socket.send(pendingMessages.shift() ?? "");
    }
  });

  socket.addEventListener("error", () => {
    reportConnectionFailure();
  });

  socket.addEventListener("close", () => {
    if (intentionallyClosed) {
      state = "closed";
      return;
    }

    reportConnectionFailure();
  });

  function send(type: string, payload: Record<string, unknown>) {
    const message = JSON.stringify({ type, payload });
    if (state === "failed" || state === "closed") {
      throw new Error(NOT_CONNECTED_MESSAGE);
    }
    if (socket.readyState !== 1) {
      pendingMessages.push(message);
      return;
    }
    socket.send(message);
  }

  function reportConnectionFailure() {
    state = "failed";
    pendingMessages.length = 0;
    if (reportedConnectionFailure) return;

    reportedConnectionFailure = true;
    options.onConnectionError?.(CONNECTION_ERROR_MESSAGE);
  }

  return {
    sendUserMessage(content: string) {
      send("user_message", { content });
    },
    pauseRun(runId: string) {
      send("pause_run", { run_id: runId });
    },
    resumeRun(runId: string) {
      send("resume_run", { run_id: runId });
    },
    cancelRun(runId: string) {
      send("cancel_run", { run_id: runId });
    },
    redirectRun(runId: string, content: string) {
      send("redirect_run", { run_id: runId, content });
    },
    sendApprovalDecision(
      approvalId: string,
      decision: "allow_once" | "allow_for_project" | "deny",
    ) {
      send("approval_decision", { approval_id: approvalId, decision });
    },
    getState() {
      return state;
    },
    close() {
      intentionallyClosed = true;
      state = "closed";
      pendingMessages.length = 0;
      socket.close();
    },
  };
}

function wsBase(): string {
  return window.ycAgentsDesktop?.wsBaseUrl ?? DEFAULT_WS_BASE;
}

import type { RuntimeEvent } from "../types";

export interface RuntimeSocket {
  sendUserMessage(content: string): void;
  pauseRun(runId: string): void;
  resumeRun(runId: string): void;
  cancelRun(runId: string): void;
  redirectRun(runId: string, content: string): void;
  close(): void;
}

export function createRuntimeSocket(options: {
  root: string;
  projectId: string;
  sessionId: string;
  onEvent: (event: RuntimeEvent) => void;
  WebSocketImpl?: typeof WebSocket;
}): RuntimeSocket {
  const SocketImpl = options.WebSocketImpl ?? WebSocket;
  const url = `ws://127.0.0.1:8765/ws/projects/${options.projectId}/sessions/${options.sessionId}?root=${encodeURIComponent(options.root)}`;
  const socket = new SocketImpl(url);

  socket.addEventListener("message", (message) => {
    options.onEvent(JSON.parse(message.data));
  });

  function send(type: string, payload: Record<string, unknown>) {
    socket.send(JSON.stringify({ type, payload }));
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
    close() {
      socket.close();
    },
  };
}

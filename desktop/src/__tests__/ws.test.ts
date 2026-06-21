import { describe, expect, it } from "vitest";
import { createRuntimeSocket } from "../api/ws";

class FakeWebSocket extends EventTarget {
  static sent: string[] = [];
  url: string;

  constructor(url: string) {
    super();
    this.url = url;
  }

  send(message: string) {
    FakeWebSocket.sent.push(message);
  }

  close() {}
}

describe("createRuntimeSocket", () => {
  it("sends user message payloads", () => {
    FakeWebSocket.sent = [];
    const socket = createRuntimeSocket({
      root: "E:/project",
      projectId: "project_001",
      sessionId: "session_001",
      onEvent: () => {},
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    });

    socket.sendUserMessage("hello");

    expect(JSON.parse(FakeWebSocket.sent[0])).toEqual({
      type: "user_message",
      payload: { content: "hello" },
    });
  });
});

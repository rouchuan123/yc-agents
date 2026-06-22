import { afterEach, describe, expect, it } from "vitest";
import { createRuntimeSocket } from "../api/ws";

class FakeWebSocket extends EventTarget {
  static sent: string[] = [];
  static lastUrl = "";
  url: string;
  readyState = 1;

  constructor(url: string) {
    super();
    this.url = url;
    FakeWebSocket.lastUrl = url;
  }

  send(message: string) {
    FakeWebSocket.sent.push(message);
  }

  close() {}
}

class ConnectingWebSocket extends EventTarget {
  static sent: string[] = [];
  static lastInstance: ConnectingWebSocket | null = null;
  url: string;
  readyState = 0;

  constructor(url: string) {
    super();
    this.url = url;
    ConnectingWebSocket.lastInstance = this;
  }

  send(message: string) {
    if (this.readyState !== 1) {
      throw new Error("WebSocket is not open");
    }
    ConnectingWebSocket.sent.push(message);
  }

  open() {
    this.readyState = 1;
    this.dispatchEvent(new Event("open"));
  }

  close() {}
}

class FailingWebSocket extends EventTarget {
  static lastInstance: FailingWebSocket | null = null;
  url: string;
  readyState = 0;

  constructor(url: string) {
    super();
    this.url = url;
    FailingWebSocket.lastInstance = this;
  }

  send() {
    throw new Error("WebSocket is not open");
  }

  fail() {
    this.dispatchEvent(new Event("error"));
  }

  failAndClose() {
    this.dispatchEvent(new Event("error"));
    this.readyState = 3;
    this.dispatchEvent(new Event("close"));
  }

  close() {}
}

class ClosableWebSocket extends EventTarget {
  static lastInstance: ClosableWebSocket | null = null;
  url: string;
  readyState = 1;

  constructor(url: string) {
    super();
    this.url = url;
    ClosableWebSocket.lastInstance = this;
  }

  send() {}

  close() {
    this.readyState = 3;
    this.dispatchEvent(new Event("close"));
  }
}

describe("createRuntimeSocket", () => {
  afterEach(() => {
    delete window.ycAgentsDesktop;
    FakeWebSocket.lastUrl = "";
  });

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

  it("queues messages until the WebSocket connection is open", () => {
    ConnectingWebSocket.sent = [];
    const socket = createRuntimeSocket({
      root: "E:/project",
      projectId: "project_001",
      sessionId: "session_001",
      onEvent: () => {},
      WebSocketImpl: ConnectingWebSocket as unknown as typeof WebSocket,
    });

    socket.sendUserMessage("hello");

    expect(ConnectingWebSocket.sent).toEqual([]);
    ConnectingWebSocket.lastInstance?.open();
    expect(JSON.parse(ConnectingWebSocket.sent[0])).toEqual({
      type: "user_message",
      payload: { content: "hello" },
    });
  });

  it("sends approval decision payloads", () => {
    FakeWebSocket.sent = [];
    const socket = createRuntimeSocket({
      root: "E:/project",
      projectId: "project_001",
      sessionId: "session_001",
      onEvent: () => {},
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    });

    socket.sendApprovalDecision("approval_001", "allow_once");

    expect(JSON.parse(FakeWebSocket.sent[0])).toEqual({
      type: "approval_decision",
      payload: { approval_id: "approval_001", decision: "allow_once" },
    });
  });

  it("uses the Electron-provided WebSocket base URL when available", () => {
    window.ycAgentsDesktop = {
      version: "0.1.0",
      apiBaseUrl: "http://127.0.0.1:8877",
      wsBaseUrl: "ws://127.0.0.1:8877",
      selectProjectDirectory: async () => null,
    };

    const socket = createRuntimeSocket({
      root: "E:/project",
      projectId: "project_001",
      sessionId: "session_001",
      onEvent: () => {},
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    });

    socket.close();
    expect(FakeWebSocket.lastUrl).toBe(
      "ws://127.0.0.1:8877/ws/projects/project_001/sessions/session_001?root=E%3A%2Fproject",
    );
  });

  it("reports WebSocket connection errors", () => {
    let errorMessage = "";
    createRuntimeSocket({
      root: "E:/project",
      projectId: "project_001",
      sessionId: "session_001",
      onEvent: () => {},
      onConnectionError: (message) => {
        errorMessage = message;
      },
      WebSocketImpl: FailingWebSocket as unknown as typeof WebSocket,
    });

    FailingWebSocket.lastInstance?.fail();

    expect(errorMessage).toBe("聊天连接失败，请确认桌面后端正在运行");
  });

  it("reports a failed connection only once when error and close both fire", () => {
    const errors: string[] = [];
    const socket = createRuntimeSocket({
      root: "E:/project",
      projectId: "project_001",
      sessionId: "session_001",
      onEvent: () => {},
      onConnectionError: (message) => {
        errors.push(message);
      },
      WebSocketImpl: FailingWebSocket as unknown as typeof WebSocket,
    });

    FailingWebSocket.lastInstance?.failAndClose();

    expect(errors).toEqual(["聊天连接失败，请确认桌面后端正在运行"]);
    expect(socket.getState()).toBe("failed");
    expect(() => socket.sendUserMessage("hello")).toThrow(
      "Chat WebSocket is not connected.",
    );
  });

  it("does not report an error when the client intentionally closes the socket", () => {
    let errorMessage = "";
    const socket = createRuntimeSocket({
      root: "E:/project",
      projectId: "project_001",
      sessionId: "session_001",
      onEvent: () => {},
      onConnectionError: (message) => {
        errorMessage = message;
      },
      WebSocketImpl: ClosableWebSocket as unknown as typeof WebSocket,
    });

    socket.close();

    expect(errorMessage).toBe("");
  });
});

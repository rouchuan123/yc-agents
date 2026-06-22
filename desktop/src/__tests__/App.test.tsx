import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

const socketInstances: FakeWebSocket[] = [];

class FakeWebSocket extends EventTarget {
  static sent: string[] = [];
  url: string;
  readyState = 1;

  constructor(url: string) {
    super();
    this.url = url;
    socketInstances.push(this);
  }

  send(message: string) {
    FakeWebSocket.sent.push(message);
  }

  close() {}

  emitEvent(event: unknown) {
    this.dispatchEvent(
      new MessageEvent("message", {
        data: JSON.stringify(event),
      }),
    );
  }
}

class ErroringWebSocket extends EventTarget {
  static lastInstance: ErroringWebSocket | null = null;
  url: string;
  readyState = 0;

  constructor(url: string) {
    super();
    this.url = url;
    ErroringWebSocket.lastInstance = this;
  }

  send() {}

  close() {}

  fail() {
    this.dispatchEvent(new Event("error"));
  }

  failAndClose() {
    this.dispatchEvent(new Event("error"));
    this.readyState = 3;
    this.dispatchEvent(new Event("close"));
  }
}

afterEach(() => {
  delete window.ycAgentsDesktop;
  socketInstances.length = 0;
  FakeWebSocket.sent = [];
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("keeps the composer pinned after the messages area when no resource preview is open", () => {
    render(<App />);

    const chatPanel = document.querySelector(".chat-panel");
    const children = Array.from(chatPanel?.children ?? []);

    expect(children[0]?.classList.contains("resource-panel-slot")).toBe(true);
    expect(children[1]?.classList.contains("messages")).toBe(true);
    expect(children[2]?.classList.contains("composer")).toBe(true);
  });

  it("renders context usage inside the composer box", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal("fetch", createProjectFetchMock());
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      const composerBox = document.querySelector(".composer-box");
      expect(composerBox?.textContent).toContain("上下文：25% 已用");
    });
    expect(document.querySelector(".top-bar .context-meter")).toBeNull();
  });

  it("uses Codex-style clickable section titles for sidebar collapse", () => {
    render(<App />);

    const documentsToggle = screen.getByTestId("section-toggle-documents");
    const documentsChevron = screen.getByTestId("section-chevron-documents");

    expect(documentsToggle.textContent).toContain("资料");
    expect(documentsChevron.getAttribute("data-direction")).toBe("down");
    expect(documentsChevron.classList.contains("section-chevron-hover")).toBe(true);

    fireEvent.click(documentsToggle);

    expect(documentsChevron.getAttribute("data-direction")).toBe("right");
    expect(documentsChevron.classList.contains("section-chevron-hover")).toBe(false);
    expect(screen.queryByText("documents/notes/idea.md")).toBeNull();
  });

  it("shows collapsible resources skills and sessions with raw skill names", async () => {
    vi.stubGlobal("fetch", createProjectFetchMock());

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("可用技能")).toBeTruthy();
    });
    expect(screen.getByText("literature-review")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "折叠资料" }));
    expect(screen.queryByText("documents/notes/idea.md")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "折叠可用技能" }));
    expect(screen.queryByText("literature-review")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "折叠会话" }));
    expect(screen.queryByText("开题报告准备")).toBeNull();
  });

  it("uses left and right aligned chat bubbles", () => {
    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "你好" },
    });
    fireEvent.click(screen.getByText("发送"));

    expect(screen.getByText("你好").closest("article")?.className).toContain(
      "message-user",
    );
    expect(
      screen
        .getByText("打开或创建论文项目后，可以开始连续会话。")
        .closest("article")?.className,
    ).toContain("message-assistant");
  });

  it("can hide the run details panel and renders resizable column gutters", () => {
    render(<App />);

    expect(screen.getByLabelText("调整左栏宽度")).toBeTruthy();
    expect(screen.getByLabelText("调整右栏宽度")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "隐藏右侧栏" }));

    expect(screen.queryByText("当前 Run")).toBeNull();
    expect(screen.queryByLabelText("调整右栏宽度")).toBeNull();
  });

  it("creates a fresh session from the sessions section", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/projects/open")) {
        return jsonResponse({ id: "project_001", name: "My Thesis", root: "E:/thesis" });
      }
      if (url.endsWith("/app/skills")) {
        return jsonResponse([]);
      }
      if (url.includes("/context-usage")) {
        return jsonResponse(defaultContextUsage());
      }
      if (url.includes("/projects/current/documents")) {
        return jsonResponse([]);
      }
      if (url.includes("/projects/current/code-projects")) {
        return jsonResponse([]);
      }
      if (url.includes("/projects/current/sessions") && options?.method === "POST") {
        return jsonResponse({
          id: "session_fresh",
          title: "新会话",
          messages: [],
          run_ids: [],
        });
      }
      if (url.includes("/projects/current/sessions")) {
        return jsonResponse([
          {
            id: "session_old",
            title: "旧会话",
            messages: [
              {
                role: "user",
                content: "旧问题",
                created_at: "2026-06-22T00:00:00Z",
              },
            ],
            run_ids: [],
          },
        ]);
      }
      throw new Error(`Unexpected URL: ${url}`);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(screen.getByText("旧会话")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: "新增会话" }));

    await waitFor(() => {
      expect(screen.getByText("新会话")).toBeTruthy();
    });
    expect(socketInstances.at(-1)?.url).toContain("sessions/session_fresh");
    expect(screen.queryByText("旧问题")).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/projects/current/sessions?root=E%3A%2Fthesis",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ title: "新会话" }),
      }),
    );
  });

  it("shows backend context window usage in the top bar", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal("fetch", createProjectFetchMock());
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(screen.getByText("上下文：25% 已用，32k/128k")).toBeTruthy();
    });
  });
  it("renders the workbench shell", () => {
    render(<App />);

    expect(screen.getByText("YC Agents")).toBeTruthy();
    expect(screen.getByText("论文项目")).toBeTruthy();
    expect(screen.getByText("当前 Run")).toBeTruthy();
  });

  it("adds user messages to the chat", () => {
    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "帮我准备开题报告目录" },
    });
    fireEvent.click(screen.getByText("发送"));

    expect(screen.getByText("帮我准备开题报告目录")).toBeTruthy();
  });

  it("sends with Enter and keeps Shift+Enter for a newline", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal("fetch", createProjectFetchMock());
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(socketInstances[0]?.url).toContain("session_001");
    });

    const textarea = screen.getByPlaceholderText("输入你的论文任务...");
    fireEvent.change(textarea, {
      target: { value: "先给我目录" },
    });
    fireEvent.keyDown(textarea, {
      key: "Enter",
      code: "Enter",
      shiftKey: true,
    });

    expect(FakeWebSocket.sent).toEqual([]);

    fireEvent.keyDown(textarea, {
      key: "Enter",
      code: "Enter",
      shiftKey: false,
    });

    expect(JSON.parse(FakeWebSocket.sent[0])).toEqual({
      type: "user_message",
      payload: { content: "先给我目录" },
    });
  });

  it("opens the settings panel", () => {
    render(<App />);

    fireEvent.click(screen.getByLabelText("Settings"));

    expect(screen.getByText("模型设置")).toBeTruthy();
  });

  it("loads and saves app settings through the backend", async () => {
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/app/settings") && options?.method === "PUT") {
        expect(options.body).toBe(
          JSON.stringify({
            model: "gpt-4.1-mini",
            base_url: "https://api.example.test/v1",
            api_key: "sk-test",
          }),
        );
        return jsonResponse({
          model: "gpt-4.1-mini",
          base_url: "https://api.example.test/v1",
          has_api_key: true,
        });
      }
      if (url.endsWith("/app/settings")) {
        return jsonResponse({
          model: "gpt-4.1",
          base_url: "https://api.example.test/v1",
          has_api_key: true,
        });
      }
      throw new Error(`Unexpected URL: ${url}`);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByLabelText("Settings"));

    await waitFor(() => {
      expect(screen.getByDisplayValue("gpt-4.1")).toBeTruthy();
    });

    fireEvent.change(screen.getByDisplayValue("gpt-4.1"), {
      target: { value: "gpt-4.1-mini" },
    });
    fireEvent.change(screen.getByLabelText("API Key"), {
      target: { value: "sk-test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8765/app/settings",
        expect.objectContaining({ method: "PUT" }),
      );
    });
  });

  it("shows documents code projects and sessions in the sidebar", () => {
    render(<App />);

    expect(screen.getByText("documents/notes/idea.md")).toBeTruthy();
    expect(screen.getByText("yc-agents")).toBeTruthy();
    expect(screen.getByText("开题报告准备")).toBeTruthy();
  });

  it("shows a clear error when sending before a project is open", () => {
    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "帮我准备开题报告目录" },
    });
    fireEvent.click(screen.getByText("发送"));

    expect(screen.getByText("请先打开或创建论文项目，再开始聊天。")).toBeTruthy();
    expect(screen.getByText("failed")).toBeTruthy();
  });

  it("creates a project from a selected folder and refreshes sidebar data", async () => {
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/projects/create")) {
        expect(options?.method).toBe("POST");
        expect(options?.body).toBe(JSON.stringify({ root: "E:/thesis", name: "thesis" }));
        return jsonResponse({ id: "project_001", name: "My Thesis", root: "E:/thesis" });
      }
      if (url.includes("/projects/current/documents")) {
        return jsonResponse([
          {
            name: "idea.md",
            relative_path: "documents/notes/idea.md",
            extension: ".md",
            size: 10,
          },
        ]);
      }
      if (url.includes("/projects/current/sessions")) {
        return jsonResponse([
          {
            id: "session_001",
            title: "Opening Report",
            messages: [],
            run_ids: [],
          },
        ]);
      }
      if (url.includes("/projects/current/code-projects")) {
        return jsonResponse([
          {
            id: "code_001",
            name: "yc-agents",
            path: "E:/code/yc-agents",
            mode: "read_only",
            selected_files: [],
          },
        ]);
      }
      throw new Error(`Unexpected URL: ${url}`);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));

    await waitFor(() => {
      expect(screen.getByText("documents/notes/idea.md")).toBeTruthy();
      expect(screen.getByText("Opening Report")).toBeTruthy();
      expect(screen.getByText("yc-agents")).toBeTruthy();
    });
  });

  it("opens a project from a selected folder and refreshes sidebar data", async () => {
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/projects/open")) {
        expect(options?.method).toBe("POST");
        expect(options?.body).toBe(JSON.stringify({ root: "E:/existing-thesis" }));
        return jsonResponse({
          id: "project_002",
          name: "Existing Thesis",
          root: "E:/existing-thesis",
        });
      }
      if (url.includes("/projects/current/documents")) {
        return jsonResponse([]);
      }
      if (url.includes("/projects/current/sessions")) {
        return jsonResponse([]);
      }
      if (url.includes("/projects/current/code-projects")) {
        return jsonResponse([]);
      }
      throw new Error(`Unexpected URL: ${url}`);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/existing-thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(screen.getByText("Existing Thesis")).toBeTruthy();
    });
  });

  it("previews a project document from the sidebar", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/projects/open")) {
        return jsonResponse({
          id: "project_001",
          name: "My Thesis",
          root: "E:/thesis",
        });
      }
      if (url.includes("/projects/current/documents/preview")) {
        return jsonResponse({
          kind: "text",
          relative_path: "documents/notes/idea.md",
          content: "# Idea\nResearch direction",
        });
      }
      if (url.includes("/projects/current/documents")) {
        return jsonResponse([
          {
            name: "idea.md",
            relative_path: "documents/notes/idea.md",
            extension: ".md",
            size: 10,
          },
        ]);
      }
      if (url.includes("/projects/current/sessions")) {
        return jsonResponse([
          {
            id: "session_001",
            title: "Opening Report",
            messages: [],
            run_ids: [],
          },
        ]);
      }
      if (url.includes("/projects/current/code-projects")) {
        return jsonResponse([]);
      }
      throw new Error(`Unexpected URL: ${url}`);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    const documentButton = await screen.findByRole("button", {
      name: "documents/notes/idea.md",
    });
    fireEvent.click(documentButton);

    await waitFor(() => {
      expect(screen.getByText("# Idea")).toBeTruthy();
      expect(screen.getByText("Research direction")).toBeTruthy();
    });
  });

  it("binds a code project through folder selection", async () => {
    let codeProjectsCallCount = 0;
    const boundProject = {
      id: "code_001",
      name: "yc-agents",
      path: "E:/code/yc-agents",
      mode: "read_only",
      selected_files: [],
    };
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/projects/open")) {
        return jsonResponse({
          id: "project_001",
          name: "My Thesis",
          root: "E:/thesis",
        });
      }
      if (url.includes("/projects/current/documents")) {
        return jsonResponse([]);
      }
      if (url.includes("/projects/current/sessions")) {
        return jsonResponse([
          {
            id: "session_001",
            title: "Opening Report",
            messages: [],
            run_ids: [],
          },
        ]);
      }
      if (url.includes("/projects/current/code-projects/bind")) {
        expect(options?.method).toBe("POST");
        expect(options?.body).toBe(
          JSON.stringify({ name: "yc-agents", path: "E:/code/yc-agents" }),
        );
        return jsonResponse(boundProject);
      }
      if (url.includes("/projects/current/code-projects")) {
        codeProjectsCallCount += 1;
        return jsonResponse(codeProjectsCallCount > 1 ? [boundProject] : []);
      }
      throw new Error(`Unexpected URL: ${url}`);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi
        .fn()
        .mockResolvedValueOnce("E:/thesis")
        .mockResolvedValueOnce("E:/code/yc-agents"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(screen.getByText("Opening Report")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: "Bind code project" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "yc-agents" })).toBeTruthy();
    });
  });

  it("loads a code project tree and saves selected files", async () => {
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/projects/open")) {
        return jsonResponse({
          id: "project_001",
          name: "My Thesis",
          root: "E:/thesis",
        });
      }
      if (url.includes("/projects/current/documents")) {
        return jsonResponse([]);
      }
      if (url.includes("/projects/current/sessions")) {
        return jsonResponse([
          {
            id: "session_001",
            title: "Opening Report",
            messages: [],
            run_ids: [],
          },
        ]);
      }
      if (url.includes("/projects/current/code-projects/code_001/select-files")) {
        expect(options?.method).toBe("POST");
        expect(options?.body).toBe(JSON.stringify({ paths: ["main.py"] }));
        return jsonResponse({
          id: "code_001",
          name: "yc-agents",
          path: "E:/code/yc-agents",
          mode: "read_only",
          selected_files: ["main.py"],
        });
      }
      if (url.includes("/projects/current/code-projects/code_001/tree")) {
        return jsonResponse([
          { name: "main.py", relative_path: "main.py", size: 100 },
        ]);
      }
      if (url.includes("/projects/current/code-projects")) {
        return jsonResponse([
          {
            id: "code_001",
            name: "yc-agents",
            path: "E:/code/yc-agents",
            mode: "read_only",
            selected_files: [],
          },
        ]);
      }
      throw new Error(`Unexpected URL: ${url}`);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    const codeProjectButton = await screen.findByRole("button", { name: "yc-agents" });
    fireEvent.click(codeProjectButton);

    const fileCheckbox = await screen.findByLabelText("main.py");
    fireEvent.click(fileCheckbox);
    fireEvent.click(screen.getByRole("button", { name: "Save code file selection" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8765/projects/current/code-projects/code_001/select-files?root=E%3A%2Fthesis",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("shows an error when the desktop folder picker is unavailable", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));

    await waitFor(() => {
      expect(screen.getByText("请通过 Electron 桌面窗口使用文件夹选择功能")).toBeTruthy();
    });
  });

  it("shows progress while waiting for project folder selection", async () => {
    let resolveSelection: (path: string | null) => void = () => {};
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(
        () =>
          new Promise<string | null>((resolve) => {
            resolveSelection = resolve;
          }),
      ),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));

    expect(screen.getByText("正在选择项目文件夹...")).toBeTruthy();

    resolveSelection(null);
  });

  it("connects chat to the selected project session over WebSocket", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/projects/open")) {
        return jsonResponse({
          id: "project_001",
          name: "My Thesis",
          root: "E:/thesis",
        });
      }
      if (url.includes("/projects/current/documents")) {
        return jsonResponse([]);
      }
      if (url.includes("/projects/current/code-projects")) {
        return jsonResponse([]);
      }
      if (url.includes("/projects/current/sessions") && options?.method === "POST") {
        return jsonResponse({
          id: "session_001",
          title: "新会话",
          messages: [],
          run_ids: [],
        });
      }
      if (url.includes("/projects/current/sessions")) {
        return jsonResponse([]);
      }
      throw new Error(`Unexpected URL: ${url}`);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(socketInstances[0]?.url).toBe(
        "ws://127.0.0.1:8765/ws/projects/project_001/sessions/session_001?root=E%3A%2Fthesis",
      );
    });

    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "先给我目录" },
    });
    fireEvent.click(screen.getByText("发送"));

    expect(JSON.parse(FakeWebSocket.sent[0])).toEqual({
      type: "user_message",
      payload: { content: "先给我目录" },
    });

    socketInstances[0].emitEvent({
      message_id: "event_001",
      type: "run_started",
      project_id: "project_001",
      session_id: "session_001",
      run_id: "run_001",
      created_at: "2026-06-21T00:00:00Z",
      payload: { status: "running" },
    });
    await waitFor(() => {
      expect(screen.getByText("已收到，正在运行...")).toBeTruthy();
    });
    socketInstances[0].emitEvent({
      message_id: "event_002",
      type: "output_delta",
      project_id: "project_001",
      session_id: "session_001",
      run_id: "run_001",
      created_at: "2026-06-21T00:00:01Z",
      payload: { content: "一、研究背景" },
    });
    socketInstances[0].emitEvent({
      message_id: "event_003",
      type: "run_completed",
      project_id: "project_001",
      session_id: "session_001",
      run_id: "run_001",
      created_at: "2026-06-21T00:00:02Z",
      payload: { final_output: "一、研究背景" },
    });

    await waitFor(() => {
      expect(screen.getByText("一、研究背景")).toBeTruthy();
      expect(screen.getByText("运行已完成")).toBeTruthy();
    });
  });

  it("renders assistant Markdown as formatted content", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal("fetch", createProjectFetchMock());
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(socketInstances[0]?.url).toContain("session_001");
    });

    socketInstances[0].emitEvent({
      message_id: "event_markdown",
      type: "output_delta",
      project_id: "project_001",
      session_id: "session_001",
      run_id: "run_001",
      created_at: "2026-06-21T00:00:01Z",
      payload: { content: "# 研究计划\n\n**重点**：先整理文献。" },
    });

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "研究计划" })).toBeTruthy();
    });
    expect(screen.getByText("重点").tagName).toBe("STRONG");
  });

  it("loads saved messages and switches between sessions in the sidebar", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/projects/open")) {
        return jsonResponse({
          id: "project_001",
          name: "My Thesis",
          root: "E:/thesis",
        });
      }
      if (url.includes("/projects/current/documents")) {
        return jsonResponse([]);
      }
      if (url.includes("/projects/current/code-projects")) {
        return jsonResponse([]);
      }
      if (url.includes("/projects/current/sessions")) {
        return jsonResponse([
          {
            id: "session_new",
            title: "新会话",
            messages: [
              {
                role: "user",
                content: "继续上次",
                created_at: "2026-06-21T00:00:00Z",
              },
              {
                role: "assistant",
                content: "上次回答",
                created_at: "2026-06-21T00:00:01Z",
              },
            ],
            run_ids: [],
          },
          {
            id: "session_old",
            title: "旧会话",
            messages: [
              {
                role: "user",
                content: "旧问题",
                created_at: "2026-06-20T00:00:00Z",
              },
              {
                role: "assistant",
                content: "旧回答",
                created_at: "2026-06-20T00:00:01Z",
              },
            ],
            run_ids: [],
          },
        ]);
      }
      throw new Error(`Unexpected URL: ${url}`);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetchMock);
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(screen.getByText("上次回答")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: "旧会话" }));

    await waitFor(() => {
      expect(screen.getByText("旧回答")).toBeTruthy();
    });
    expect(socketInstances.at(-1)?.url).toContain("sessions/session_old");
  });

  it("shows backend run failures in the chat", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal("fetch", createProjectFetchMock());
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(socketInstances[0]?.url).toContain("session_001");
    });

    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "你好" },
    });
    fireEvent.click(screen.getByText("发送"));
    socketInstances[0].emitEvent({
      message_id: "event_failed",
      type: "run_failed",
      project_id: "project_001",
      session_id: "session_001",
      run_id: "run_001",
      created_at: "2026-06-21T00:00:00Z",
      payload: { error: "缺少 LLM_MODEL_ID" },
    });

    await waitFor(() => {
      expect(screen.getByText("运行失败：缺少 LLM_MODEL_ID")).toBeTruthy();
    });
  });

  it("shows WebSocket connection failures in the chat", async () => {
    vi.stubGlobal("WebSocket", ErroringWebSocket);
    vi.stubGlobal("fetch", createProjectFetchMock());
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(ErroringWebSocket.lastInstance?.url).toContain("session_001");
    });
    ErroringWebSocket.lastInstance?.fail();

    await waitFor(() => {
      expect(
        screen.getByText("聊天连接失败，请确认桌面后端正在运行"),
      ).toBeTruthy();
      expect(screen.getByText("failed")).toBeTruthy();
    });
  });

  it("does not keep queuing chat messages after the WebSocket connection failed", async () => {
    vi.stubGlobal("WebSocket", ErroringWebSocket);
    vi.stubGlobal("fetch", createProjectFetchMock());
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(ErroringWebSocket.lastInstance?.url).toContain("session_001");
    });
    ErroringWebSocket.lastInstance?.failAndClose();

    await waitFor(() => {
      expect(screen.getAllByText("聊天连接失败，请确认桌面后端正在运行")).toHaveLength(1);
    });

    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "你好，你是谁" },
    });
    fireEvent.click(screen.getByText("发送"));

    expect(screen.getByText("聊天未连接，请重新打开项目后再发送。")).toBeTruthy();
  });

  it("sends run control and redirect messages over WebSocket", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal("fetch", createProjectFetchMock());
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(socketInstances[0]?.url).toContain("session_001");
    });

    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "写一版初稿" },
    });
    fireEvent.click(screen.getByText("发送"));
    socketInstances[0].emitEvent({
      message_id: "event_001",
      type: "run_started",
      project_id: "project_001",
      session_id: "session_001",
      run_id: "run_001",
      created_at: "2026-06-21T00:00:00Z",
      payload: { status: "running" },
    });

    await waitFor(() => {
      expect(screen.getByText("running")).toBeTruthy();
    });

    fireEvent.click(screen.getByLabelText("Pause"));
    fireEvent.click(screen.getByLabelText("Resume"));
    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "先停，不要写正文，只列目录" },
    });
    fireEvent.click(screen.getByText("发送"));
    fireEvent.click(screen.getByLabelText("Cancel"));

    expect(FakeWebSocket.sent.map((item) => JSON.parse(item))).toEqual([
      { type: "user_message", payload: { content: "写一版初稿" } },
      { type: "pause_run", payload: { run_id: "run_001" } },
      { type: "resume_run", payload: { run_id: "run_001" } },
      {
        type: "redirect_run",
        payload: { run_id: "run_001", content: "先停，不要写正文，只列目录" },
      },
      { type: "cancel_run", payload: { run_id: "run_001" } },
    ]);
  });

  it("sends approval decisions back over WebSocket", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.stubGlobal("fetch", createProjectFetchMock());
    window.ycAgentsDesktop = {
      version: "0.1.0",
      selectProjectDirectory: vi.fn(async () => "E:/thesis"),
    };

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开项目" }));

    await waitFor(() => {
      expect(socketInstances[0]?.url).toContain("session_001");
    });

    socketInstances[0].emitEvent({
      message_id: "event_approval",
      type: "approval_required",
      project_id: "project_001",
      session_id: "session_001",
      run_id: "run_001",
      created_at: "2026-06-21T00:00:00Z",
      payload: {
        approval_id: "approval_001",
        title: "需要确认工具调用",
        summary: "Tool requires human approval: script_runner",
      },
    });

    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: "需要确认工具调用" })).toBeTruthy();
    });
    fireEvent.click(screen.getByText("允许一次"));

    expect(FakeWebSocket.sent.map((item) => JSON.parse(item))).toContainEqual({
      type: "approval_decision",
      payload: { approval_id: "approval_001", decision: "allow_once" },
    });
  });
});

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => body,
  } as Response;
}

function defaultContextUsage() {
  return {
    used_tokens: 32000,
    max_tokens: 128000,
    percent_used: 25,
    tokenizer: "cl100k_base",
    sections: {
      messages: 12000,
      documents: 20000,
      memory: 0,
    },
  };
}

function createProjectFetchMock() {
  return vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith("/app/skills")) {
      return jsonResponse([
        { name: "literature-review", description: "Read and summarize papers" },
        { name: "opening-report", description: "Prepare opening reports" },
        { name: "thesis-system-design", description: "Design thesis systems" },
      ]);
    }
    if (url.includes("/context-usage")) {
      return jsonResponse(defaultContextUsage());
    }
    if (url.endsWith("/projects/open")) {
      return jsonResponse({
        id: "project_001",
        name: "My Thesis",
        root: "E:/thesis",
      });
    }
    if (url.includes("/projects/current/documents")) {
      return jsonResponse([]);
    }
    if (url.includes("/projects/current/code-projects")) {
      return jsonResponse([]);
    }
    if (url.includes("/projects/current/sessions") && options?.method === "POST") {
      return jsonResponse({
        id: "session_001",
        title: "新会话",
        messages: [],
        run_ids: [],
      });
    }
    if (url.includes("/projects/current/sessions")) {
      return jsonResponse([]);
    }
    throw new Error(`Unexpected URL: ${url}`);
  }) as unknown as typeof fetch;
}

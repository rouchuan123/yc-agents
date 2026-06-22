import { afterEach, describe, expect, it, vi } from "vitest";

import {
  bindCodeProject,
  createSession,
  getContextUsage,
  getCodeProjectTree,
  getHealth,
  getSettings,
  listCodeProjects,
  listDocuments,
  listSessions,
  listSkills,
  openProject,
  previewDocument,
  saveSettings,
  selectCodeFiles,
} from "../api/client";

function mockFetch(responseBody: unknown) {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    json: async () => responseBody,
  })) as unknown as typeof fetch;
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  delete window.ycAgentsDesktop;
  vi.unstubAllGlobals();
});

describe("desktop API client", () => {
  it("opens an existing project by root path", async () => {
    const fetchMock = mockFetch({ id: "project_001", root: "E:/thesis" });

    const project = await openProject("E:/thesis");

    expect(project.root).toBe("E:/thesis");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/projects/open",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ root: "E:/thesis" }),
      }),
    );
  });

  it("loads project collections with the root query parameter", async () => {
    const fetchMock = mockFetch([]);

    await listDocuments("E:/thesis");
    await listSessions("E:/thesis");
    await listCodeProjects("E:/thesis");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8765/projects/current/documents?root=E%3A%2Fthesis",
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8765/projects/current/sessions?root=E%3A%2Fthesis",
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://127.0.0.1:8765/projects/current/code-projects?root=E%3A%2Fthesis",
    );
  });

  it("creates a session under the current project", async () => {
    const fetchMock = mockFetch({ id: "session_001", title: "Chat" });

    const session = await createSession("E:/thesis", "Chat");

    expect(session.id).toBe("session_001");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/projects/current/sessions?root=E%3A%2Fthesis",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ title: "Chat" }),
      }),
    );
  });

  it("loads available skills with their raw names", async () => {
    const fetchMock = mockFetch([{ name: "literature-review", description: "Read papers" }]);

    const skills = await listSkills();

    expect(skills[0].name).toBe("literature-review");
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8765/app/skills");
  });

  it("loads backend context usage for a session", async () => {
    const fetchMock = mockFetch({
      used_tokens: 12000,
      max_tokens: 128000,
      percent_used: 9.38,
      tokenizer: "cl100k_base",
      sections: { messages: 3000, documents: 9000 },
    });

    const usage = await getContextUsage("E:/thesis", "session_001");

    expect(usage.used_tokens).toBe(12000);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/projects/current/sessions/session_001/context-usage?root=E%3A%2Fthesis",
    );
  });

  it("loads saved app settings", async () => {
    const fetchMock = mockFetch({
      model: "gpt-4.1",
      base_url: "https://api.example.test/v1",
      has_api_key: true,
    });

    const settings = await getSettings();

    expect(settings.model).toBe("gpt-4.1");
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8765/app/settings");
  });

  it("uses the Electron-provided API base URL when available", async () => {
    window.ycAgentsDesktop = {
      version: "0.1.0",
      apiBaseUrl: "http://127.0.0.1:8877",
      wsBaseUrl: "ws://127.0.0.1:8877",
      selectProjectDirectory: async () => null,
    };
    const fetchMock = mockFetch({ status: "ok" });

    await getHealth();

    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8877/health");
  });

  it("saves app settings", async () => {
    const fetchMock = mockFetch({
      model: "gpt-4.1-mini",
      base_url: "https://api.example.test/v1",
      has_api_key: true,
    });

    const settings = await saveSettings({
      model: "gpt-4.1-mini",
      base_url: "https://api.example.test/v1",
      api_key: "sk-test",
    });

    expect(settings.has_api_key).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/app/settings",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          model: "gpt-4.1-mini",
          base_url: "https://api.example.test/v1",
          api_key: "sk-test",
        }),
      }),
    );
  });

  it("previews a project document", async () => {
    const fetchMock = mockFetch({
      kind: "text",
      relative_path: "documents/notes/idea.md",
      content: "# Idea",
    });

    const preview = await previewDocument("E:/thesis", "documents/notes/idea.md");

    expect(preview.content).toBe("# Idea");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/projects/current/documents/preview?root=E%3A%2Fthesis&path=documents%2Fnotes%2Fidea.md",
    );
  });

  it("binds a code project under the current project", async () => {
    const fetchMock = mockFetch({
      id: "code_001",
      name: "yc-agents",
      path: "E:/code/yc-agents",
      mode: "read_only",
      selected_files: [],
    });

    const codeProject = await bindCodeProject(
      "E:/thesis",
      "yc-agents",
      "E:/code/yc-agents",
    );

    expect(codeProject.id).toBe("code_001");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/projects/current/code-projects/bind?root=E%3A%2Fthesis",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "yc-agents", path: "E:/code/yc-agents" }),
      }),
    );
  });

  it("loads a bound code project file tree", async () => {
    const fetchMock = mockFetch([
      { name: "main.py", relative_path: "main.py", size: 100 },
    ]);

    const files = await getCodeProjectTree("E:/thesis", "code_001");

    expect(files[0].relative_path).toBe("main.py");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/projects/current/code-projects/code_001/tree?root=E%3A%2Fthesis",
    );
  });

  it("saves selected code files", async () => {
    const fetchMock = mockFetch({
      id: "code_001",
      name: "yc-agents",
      path: "E:/code/yc-agents",
      mode: "read_only",
      selected_files: ["main.py"],
    });

    const codeProject = await selectCodeFiles("E:/thesis", "code_001", ["main.py"]);

    expect(codeProject.selected_files).toEqual(["main.py"]);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/projects/current/code-projects/code_001/select-files?root=E%3A%2Fthesis",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ paths: ["main.py"] }),
      }),
    );
  });
});

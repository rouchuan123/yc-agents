const DEFAULT_API_BASE = "http://127.0.0.1:8765";

export interface Project {
  id: string;
  name: string;
  root: string;
}

export interface DocumentItem {
  name: string;
  relative_path: string;
  extension: string;
  size: number;
}

export interface CodeProject {
  id: string;
  name: string;
  path: string;
  mode: string;
  selected_files: string[];
}

export interface CodeFile {
  name: string;
  relative_path: string;
  size: number;
}

export interface DocumentPreview {
  kind: "text" | "binary";
  relative_path: string;
  content: string;
}

export interface AppSettings {
  model: string;
  base_url: string;
  has_api_key: boolean;
}

export interface SkillSummary {
  name: string;
  description: string;
  allowed_tools?: string[];
}

export interface ContextUsage {
  used_tokens: number;
  max_tokens: number;
  percent_used: number;
  tokenizer: string;
  exact?: boolean;
  sections: {
    messages: number;
    documents: number;
    memory: number;
  };
}

export interface Session {
  id: string;
  title: string;
  messages: Array<{ role: string; content: string; created_at: string }>;
  run_ids: string[];
}

export async function getHealth(): Promise<{ status: string }> {
  const response = await fetch(`${apiBase()}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json();
}

export async function getSettings(): Promise<AppSettings> {
  return getJson("/app/settings");
}

export async function saveSettings(settings: {
  model: string;
  base_url: string;
  api_key: string;
}): Promise<AppSettings> {
  return sendJson("/app/settings", "PUT", settings);
}

export async function listSkills(): Promise<SkillSummary[]> {
  return getJson("/app/skills");
}

export async function createProject(root: string, name: string): Promise<Project> {
  const response = await fetch(`${apiBase()}/projects/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ root, name }),
  });
  if (!response.ok) {
    throw new Error(`Create project failed: ${response.status}`);
  }
  return response.json();
}

export async function openProject(root: string): Promise<Project> {
  const response = await fetch(`${apiBase()}/projects/open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ root }),
  });
  if (!response.ok) {
    throw new Error(`Open project failed: ${response.status}`);
  }
  return response.json();
}

export async function listDocuments(root: string): Promise<DocumentItem[]> {
  return getJson(`/projects/current/documents?${rootQuery(root)}`);
}

export async function previewDocument(
  root: string,
  path: string,
): Promise<DocumentPreview> {
  return getJson(
    `/projects/current/documents/preview?${new URLSearchParams({
      root,
      path,
    }).toString()}`,
  );
}

export async function listSessions(root: string): Promise<Session[]> {
  return getJson(`/projects/current/sessions?${rootQuery(root)}`);
}

export async function createSession(root: string, title: string): Promise<Session> {
  const response = await fetch(`${apiBase()}/projects/current/sessions?${rootQuery(root)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw new Error(`Create session failed: ${response.status}`);
  }
  return response.json();
}

export async function getContextUsage(
  root: string,
  sessionId: string,
): Promise<ContextUsage> {
  return getJson(
    `/projects/current/sessions/${encodeURIComponent(sessionId)}/context-usage?${rootQuery(root)}`,
  );
}

export async function listCodeProjects(root: string): Promise<CodeProject[]> {
  return getJson(`/projects/current/code-projects?${rootQuery(root)}`);
}

export async function bindCodeProject(
  root: string,
  name: string,
  path: string,
): Promise<CodeProject> {
  return sendJson(
    `/projects/current/code-projects/bind?${rootQuery(root)}`,
    "POST",
    { name, path },
  );
}

export async function getCodeProjectTree(
  root: string,
  codeProjectId: string,
): Promise<CodeFile[]> {
  return getJson(
    `/projects/current/code-projects/${encodeURIComponent(codeProjectId)}/tree?${rootQuery(root)}`,
  );
}

export async function selectCodeFiles(
  root: string,
  codeProjectId: string,
  paths: string[],
): Promise<CodeProject> {
  return sendJson(
    `/projects/current/code-projects/${encodeURIComponent(codeProjectId)}/select-files?${rootQuery(root)}`,
    "POST",
    { paths },
  );
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

async function sendJson<T>(
  path: string,
  method: "POST" | "PUT",
  body: unknown,
): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function rootQuery(root: string): string {
  return new URLSearchParams({ root }).toString();
}

function apiBase(): string {
  return window.ycAgentsDesktop?.apiBaseUrl ?? DEFAULT_API_BASE;
}

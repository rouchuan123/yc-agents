const API_BASE = "http://127.0.0.1:8765";

export async function getHealth(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json();
}

export async function createProject(root: string, name: string) {
  const response = await fetch(`${API_BASE}/projects/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ root, name }),
  });
  if (!response.ok) {
    throw new Error(`Create project failed: ${response.status}`);
  }
  return response.json();
}

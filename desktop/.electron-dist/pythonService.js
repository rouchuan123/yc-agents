import { spawn } from "node:child_process";
import path from "node:path";
export function startPythonService(options) {
    const pythonPath = options.pythonPath ?? path.join(options.repoRoot, ".venv", "Scripts", "python.exe");
    const child = spawn(pythonPath, ["-m", "yc_agents.desktop.server"], {
        cwd: options.repoRoot,
        env: {
            ...process.env,
            YC_AGENTS_DESKTOP_PORT: String(options.port ?? 8765),
        },
        windowsHide: true,
    });
    return {
        process: child,
        stop() {
            if (!child.killed) {
                child.kill();
            }
        },
    };
}
export async function waitForHealth(options = {}) {
    const url = options.url ?? "http://127.0.0.1:8765/health";
    const attempts = options.attempts ?? 20;
    const delayMs = options.delayMs ?? 250;
    const fetchImpl = options.fetchImpl ?? fetch;
    for (let index = 0; index < attempts; index += 1) {
        try {
            const response = await fetchImpl(url);
            if (response.ok)
                return true;
        }
        catch {
            // Try again until attempts are exhausted.
        }
        await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
    return false;
}
//# sourceMappingURL=pythonService.js.map
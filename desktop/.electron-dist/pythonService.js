import { spawn } from "node:child_process";
import net from "node:net";
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
export async function findAvailablePort(startPort, attempts = 50) {
    for (let offset = 0; offset < attempts; offset += 1) {
        const port = startPort + offset;
        if (await isPortAvailable(port)) {
            return port;
        }
    }
    throw new Error(`No available desktop backend port near ${startPort}`);
}
function isPortAvailable(port) {
    return new Promise((resolve) => {
        const server = net.createServer();
        server.once("error", () => {
            resolve(false);
        });
        server.once("listening", () => {
            server.close(() => resolve(true));
        });
        server.listen(port, "127.0.0.1");
    });
}
//# sourceMappingURL=pythonService.js.map
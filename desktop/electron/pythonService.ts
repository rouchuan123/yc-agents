import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import path from "node:path";

export interface PythonService {
  process: ChildProcessWithoutNullStreams;
  stop(): void;
}

export function startPythonService(options: {
  repoRoot: string;
  pythonPath?: string;
  port?: number;
}): PythonService {
  const pythonPath =
    options.pythonPath ?? path.join(options.repoRoot, ".venv", "Scripts", "python.exe");
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

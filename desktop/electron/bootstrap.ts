import {
  findAvailablePort as defaultFindAvailablePort,
  startPythonService as defaultStartPythonService,
  waitForHealth as defaultWaitForHealth,
  type PythonService,
} from "./pythonService.js";

export interface DesktopAppOptions {
  repoRoot: string;
  pythonPath?: string;
  port?: number;
  healthAttempts?: number;
  healthDelayMs?: number;
}

export interface DesktopAppRuntime {
  whenReady(): Promise<void>;
  findAvailablePort?: typeof defaultFindAvailablePort;
  startPythonService: typeof defaultStartPythonService;
  waitForHealth: typeof defaultWaitForHealth;
  createWindow(port: number): void;
}

export interface DesktopAppHandle {
  service: PythonService;
  port: number;
}

export async function startDesktopApp(
  runtime: DesktopAppRuntime,
  options: DesktopAppOptions,
): Promise<DesktopAppHandle> {
  await runtime.whenReady();

  const requestedPort = options.port ?? 8765;
  const port = await (runtime.findAvailablePort ?? defaultFindAvailablePort)(
    requestedPort,
  );
  const serviceOptions = {
    repoRoot: options.repoRoot,
    port,
    ...(options.pythonPath ? { pythonPath: options.pythonPath } : {}),
  };
  const service = runtime.startPythonService(serviceOptions);

  const healthy = await runtime.waitForHealth({
    url: `http://127.0.0.1:${port}/health`,
    attempts: options.healthAttempts ?? 40,
    delayMs: options.healthDelayMs ?? 250,
  });

  if (!healthy) {
    service.stop();
    throw new Error("YC Agents desktop backend did not become healthy");
  }

  runtime.createWindow(port);

  return { service, port };
}

import { describe, expect, it, vi } from "vitest";

import { startDesktopApp } from "../bootstrap";
import type { PythonService } from "../pythonService";

function createService(): PythonService {
  return {
    process: {} as PythonService["process"],
    stop: vi.fn(),
  };
}

describe("startDesktopApp", () => {
  it("waits for backend health before creating the main window", async () => {
    const events: string[] = [];
    const service = createService();
    const startPythonService = vi.fn(() => {
      events.push("start-backend");
      return service;
    });
    const waitForHealth = vi.fn(async () => {
      events.push("wait-health");
      return true;
    });
    const createWindow = vi.fn((_port?: number) => {
      events.push("create-window");
    });
    const findAvailablePort = vi.fn(async () => {
      events.push("find-port");
      return 8877;
    });

    const result = await startDesktopApp(
      {
        whenReady: async () => {
          events.push("electron-ready");
        },
        findAvailablePort,
        startPythonService,
        waitForHealth,
        createWindow,
      },
      {
        repoRoot: "E:/code/yc-agents",
        port: 8765,
        healthAttempts: 3,
        healthDelayMs: 1,
      },
    );

    expect(result.service).toBe(service);
    expect(result.port).toBe(8877);
    expect(events).toEqual([
      "electron-ready",
      "find-port",
      "start-backend",
      "wait-health",
      "create-window",
    ]);
    expect(startPythonService).toHaveBeenCalledWith({
      repoRoot: "E:/code/yc-agents",
      port: 8877,
    });
    expect(waitForHealth).toHaveBeenCalledWith({
      url: "http://127.0.0.1:8877/health",
      attempts: 3,
      delayMs: 1,
    });
    expect(createWindow).toHaveBeenCalledWith(8877);
  });

  it("stops the backend and does not create a window when health never responds", async () => {
    const service = createService();
    const createWindow = vi.fn();

    await expect(
      startDesktopApp(
        {
          whenReady: async () => undefined,
          findAvailablePort: vi.fn(async () => 8877),
          startPythonService: vi.fn(() => service),
          waitForHealth: vi.fn(async () => false),
          createWindow,
        },
        {
          repoRoot: "E:/code/yc-agents",
          port: 8765,
          healthAttempts: 1,
          healthDelayMs: 1,
        },
      ),
    ).rejects.toThrow("YC Agents desktop backend did not become healthy");

    expect(service.stop).toHaveBeenCalledTimes(1);
    expect(createWindow).not.toHaveBeenCalled();
  });
});

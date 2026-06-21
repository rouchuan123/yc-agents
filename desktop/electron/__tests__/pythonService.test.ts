import { describe, expect, it, vi } from "vitest";

const { spawnMock } = vi.hoisted(() => ({
  spawnMock: vi.fn(() => ({
    killed: false,
    kill: vi.fn(),
  })),
}));

vi.mock("node:child_process", () => ({
  spawn: spawnMock,
  default: {
    spawn: spawnMock,
  },
}));

import { spawn } from "node:child_process";
import { startPythonService, waitForHealth } from "../pythonService";

describe("startPythonService", () => {
  it("starts the desktop backend module", () => {
    startPythonService({
      repoRoot: "E:/code/yc-agents",
      pythonPath: "python.exe",
      port: 8765,
    });

    expect(spawn).toHaveBeenCalledWith(
      "python.exe",
      ["-m", "yc_agents.desktop.server"],
      expect.objectContaining({
        cwd: "E:/code/yc-agents",
        windowsHide: true,
      }),
    );
  });
});

describe("waitForHealth", () => {
  it("returns true when health endpoint responds", async () => {
    const ok = await waitForHealth({
      attempts: 1,
      delayMs: 1,
      fetchImpl: vi.fn(async () => ({ ok: true })) as unknown as typeof fetch,
    });

    expect(ok).toBe(true);
  });
});

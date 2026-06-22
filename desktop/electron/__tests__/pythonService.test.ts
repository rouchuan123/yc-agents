import { describe, expect, it, vi } from "vitest";
import net from "node:net";

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
import { findAvailablePort, startPythonService, waitForHealth } from "../pythonService";

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

describe("findAvailablePort", () => {
  it("returns the first free port at or above the requested port", async () => {
    const port = await findAvailablePort(0, 1);

    expect(port).toBeGreaterThanOrEqual(0);
  });

  it("skips a port that is already in use", async () => {
    const busyServer = net.createServer();
    await new Promise<void>((resolve) => busyServer.listen(0, "127.0.0.1", resolve));
    const address = busyServer.address();
    if (!address || typeof address === "string") {
      throw new Error("Expected TCP address");
    }

    const port = await findAvailablePort(address.port, 2);

    expect(port).toBe(address.port + 1);
    await new Promise<void>((resolve) => busyServer.close(() => resolve()));
  });
});

import { describe, expect, it } from "vitest";

import packageJson from "../../package.json";
import tsconfig from "../../tsconfig.electron.json";

describe("Electron package scripts", () => {
  it("builds Electron TypeScript before launching Electron", () => {
    expect(packageJson.main).toBe(".electron-dist/main.js");
    expect(packageJson.scripts["build:electron"]).toBe("tsc -p tsconfig.electron.json");
    expect(packageJson.scripts["electron:start"]).toContain("npm.cmd run build:electron");
    expect(packageJson.scripts["electron:start"]).toContain("electron .");
  });

  it("compiles the preload bridge from a CommonJS TypeScript source", () => {
    expect(packageJson.scripts["build:preload"]).toBeUndefined();
    expect(tsconfig.include).toContain("electron/**/*.cts");
  });

  it("starts the renderer dev server and waits for it before launching Electron", () => {
    expect(packageJson.scripts.dev).toContain("vite");
    expect(packageJson.scripts.dev).toContain("--host 127.0.0.1");
    expect(packageJson.scripts.dev).toContain("--port 5174");
    expect(packageJson.scripts.dev).toContain("--strictPort");
    expect(packageJson.scripts["electron:dev"]).toContain("concurrently");
    expect(packageJson.scripts["electron:dev"]).toContain(
      "wait-on http://127.0.0.1:5174",
    );
    expect(packageJson.scripts["electron:dev"]).toContain("npm.cmd run electron:start");
  });
});

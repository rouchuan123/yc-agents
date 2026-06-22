import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("Electron main process source", () => {
  it("loads the preload bridge from a CommonJS file", () => {
    const mainSource = readFileSync(
      path.join(__dirname, "..", "main.ts"),
      "utf-8",
    );

    expect(mainSource).toContain('path.join(currentDir, "preload.cjs")');
  });

  it("sets a Chinese application menu", () => {
    const mainSource = readFileSync(
      path.join(__dirname, "..", "main.ts"),
      "utf-8",
    );

    expect(mainSource).toContain("Menu");
    expect(mainSource).toContain("文件");
    expect(mainSource).toContain("编辑");
    expect(mainSource).toContain("视图");
    expect(mainSource).toContain("窗口");
    expect(mainSource).toContain("帮助");
    expect(mainSource).toContain("Menu.setApplicationMenu");
  });
});

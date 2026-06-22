import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("desktop layout CSS", () => {
  it("does not reserve empty grid rows below the workbench", () => {
    const css = readFileSync(resolve(__dirname, "../styles.css"), "utf-8");

    expect(css).toContain("grid-template-rows: 48px minmax(0, 1fr);");
    expect(css).not.toContain("grid-template-rows: 48px auto auto 1fr;");
  });
});

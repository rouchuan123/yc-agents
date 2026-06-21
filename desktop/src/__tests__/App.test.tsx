import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "../App";

describe("App", () => {
  it("renders the workbench shell", () => {
    render(<App />);

    expect(screen.getByText("YC Agents")).toBeTruthy();
    expect(screen.getByText("论文项目")).toBeTruthy();
    expect(screen.getByText("当前 Run")).toBeTruthy();
  });
});

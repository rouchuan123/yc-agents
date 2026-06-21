import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "../App";

afterEach(() => {
  cleanup();
});

describe("App", () => {
  it("renders the workbench shell", () => {
    render(<App />);

    expect(screen.getByText("YC Agents")).toBeTruthy();
    expect(screen.getByText("论文项目")).toBeTruthy();
    expect(screen.getByText("当前 Run")).toBeTruthy();
  });

  it("adds user messages to the chat", () => {
    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "帮我准备开题报告目录" },
    });
    fireEvent.click(screen.getByText("发送"));

    expect(screen.getByText("帮我准备开题报告目录")).toBeTruthy();
  });
});

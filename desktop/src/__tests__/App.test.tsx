import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { RunDetails } from "../components/RunDetails";

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

  it("opens the settings panel", () => {
    render(<App />);

    fireEvent.click(screen.getByLabelText("Settings"));

    expect(screen.getByText("模型设置")).toBeTruthy();
  });

  it("shows documents code projects and sessions in the sidebar", () => {
    render(<App />);

    expect(screen.getByText("documents/notes/idea.md")).toBeTruthy();
    expect(screen.getByText("yc-agents")).toBeTruthy();
    expect(screen.getByText("开题报告准备")).toBeTruthy();
  });

  it("shows a readable run event after sending a message", () => {
    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("输入你的论文任务..."), {
      target: { value: "帮我准备开题报告目录" },
    });
    fireEvent.click(screen.getByText("发送"));

    expect(screen.getByText("user_message")).toBeTruthy();
  });

  it("renders run status trace tool and approval details", () => {
    render(
      <RunDetails
        status="running"
        state={{ status: "waiting_approval", current_step: "tool_call", history: [] }}
        events={[
          {
            message_id: "event_1",
            type: "tool_called",
            event_type: "tool_called",
            project_id: "local",
            session_id: "local",
            run_id: "run_1",
            created_at: "2026-06-22T00:00:00Z",
            payload: { tool_name: "rag_search", ok: true },
          },
          {
            message_id: "event_2",
            type: "tool_needs_approval",
            event_type: "tool_needs_approval",
            project_id: "local",
            session_id: "local",
            run_id: "run_1",
            created_at: "2026-06-22T00:00:01Z",
            payload: { tool_name: "markdown_writer", reason: "write file" },
          },
        ]}
      />,
    );

    expect(screen.getByText("running")).toBeTruthy();
    expect(screen.getByText("waiting_approval")).toBeTruthy();
    expect(screen.getByText("tool_called")).toBeTruthy();
    expect(screen.getByText("rag_search")).toBeTruthy();
    expect(screen.getByText("markdown_writer")).toBeTruthy();
  });
});

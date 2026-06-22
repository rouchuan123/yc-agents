import { describe, expect, it, vi } from "vitest";

import { registerProjectDialogIpc } from "../projectDialog";

describe("registerProjectDialogIpc", () => {
  it("returns the selected directory path through IPC", async () => {
    const handlers = new Map<string, (event?: unknown) => Promise<string | null>>();
    const ipcMain = {
      handle: vi.fn((channel: string, handler: (event?: unknown) => Promise<string | null>) => {
        handlers.set(channel, handler);
      }),
    };
    const dialog = {
      showOpenDialog: vi.fn(async () => ({
        canceled: false,
        filePaths: ["E:\\thesis"],
      })),
    };

    registerProjectDialogIpc(ipcMain, dialog);
    const selectedPath = await handlers.get("project:select-directory")?.();

    expect(selectedPath).toBe("E:\\thesis");
    expect(dialog.showOpenDialog).toHaveBeenCalledWith({
      properties: ["openDirectory", "createDirectory"],
      title: "Select YC Agents project folder",
    });
  });

  it("opens the directory picker as a modal child of the current window", async () => {
    const parentWindow = { id: 1 };
    const event = { sender: { id: 99 } };
    const handlers = new Map<string, (event?: unknown) => Promise<string | null>>();
    const ipcMain = {
      handle: vi.fn((channel: string, handler: (event?: unknown) => Promise<string | null>) => {
        handlers.set(channel, handler);
      }),
    };
    const dialog = {
      showOpenDialog: vi.fn(async () => ({
        canceled: true,
        filePaths: [],
      })),
    };
    const browserWindow = {
      fromWebContents: vi.fn(() => parentWindow),
    };

    registerProjectDialogIpc(ipcMain, dialog, browserWindow);
    await handlers.get("project:select-directory")?.(event);

    expect(browserWindow.fromWebContents).toHaveBeenCalledWith(event.sender);
    expect(dialog.showOpenDialog).toHaveBeenCalledWith(parentWindow, {
      properties: ["openDirectory", "createDirectory"],
      title: "Select YC Agents project folder",
    });
  });

  it("returns null when directory selection is cancelled", async () => {
    const handlers = new Map<string, (event?: unknown) => Promise<string | null>>();
    const ipcMain = {
      handle: vi.fn((channel: string, handler: (event?: unknown) => Promise<string | null>) => {
        handlers.set(channel, handler);
      }),
    };
    const dialog = {
      showOpenDialog: vi.fn(async () => ({
        canceled: true,
        filePaths: [],
      })),
    };

    registerProjectDialogIpc(ipcMain, dialog);
    const selectedPath = await handlers.get("project:select-directory")?.();

    expect(selectedPath).toBeNull();
  });
});

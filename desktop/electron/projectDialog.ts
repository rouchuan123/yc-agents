export interface ProjectDialogIpcMain {
  handle(channel: string, listener: (event?: unknown) => Promise<string | null>): void;
}

export interface ProjectDialog {
  showOpenDialog(
    parentOrOptions:
      | unknown
      | {
          properties: Array<"openDirectory" | "createDirectory">;
          title: string;
        },
    options?: {
      properties: Array<"openDirectory" | "createDirectory">;
      title: string;
    },
  ): Promise<{ canceled: boolean; filePaths: string[] }>;
}

export interface BrowserWindowLookup {
  fromWebContents(webContents: unknown): unknown;
}

export function registerProjectDialogIpc(
  ipcMain: ProjectDialogIpcMain,
  dialog: ProjectDialog,
  browserWindow?: BrowserWindowLookup,
) {
  ipcMain.handle("project:select-directory", async (event?: unknown) => {
    const options: {
      properties: Array<"openDirectory" | "createDirectory">;
      title: string;
    } = {
      properties: ["openDirectory", "createDirectory"],
      title: "Select YC Agents project folder",
    };
    const sender = getSender(event);
    const parentWindow =
      sender && browserWindow ? browserWindow.fromWebContents(sender) : null;
    const result = parentWindow
      ? await dialog.showOpenDialog(parentWindow, options)
      : await dialog.showOpenDialog(options);

    if (result.canceled) return null;
    return result.filePaths[0] ?? null;
  });
}

function getSender(event: unknown): unknown | null {
  if (!event || typeof event !== "object" || !("sender" in event)) {
    return null;
  }

  return (event as { sender?: unknown }).sender ?? null;
}

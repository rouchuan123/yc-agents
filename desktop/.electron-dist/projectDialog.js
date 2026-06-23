export function registerProjectDialogIpc(ipcMain, dialog, browserWindow) {
    ipcMain.handle("project:select-directory", async (event) => {
        const options = {
            properties: ["openDirectory", "createDirectory"],
            title: "Select YC Agents project folder",
        };
        const sender = getSender(event);
        const parentWindow = sender && browserWindow ? browserWindow.fromWebContents(sender) : null;
        const result = parentWindow
            ? await dialog.showOpenDialog(parentWindow, options)
            : await dialog.showOpenDialog(options);
        if (result.canceled)
            return null;
        return result.filePaths[0] ?? null;
    });
}
function getSender(event) {
    if (!event || typeof event !== "object" || !("sender" in event)) {
        return null;
    }
    return event.sender ?? null;
}
//# sourceMappingURL=projectDialog.js.map
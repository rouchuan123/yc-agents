import { contextBridge, ipcRenderer } from "electron";
contextBridge.exposeInMainWorld("ycAgentsDesktop", {
    version: "0.1.0",
    selectProjectDirectory: () => ipcRenderer.invoke("project:select-directory"),
});
//# sourceMappingURL=preload.js.map
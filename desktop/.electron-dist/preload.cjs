"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("ycAgentsDesktop", {
    version: "0.1.0",
    apiBaseUrl: process.env.YC_AGENTS_DESKTOP_API_BASE ?? "http://127.0.0.1:8765",
    wsBaseUrl: process.env.YC_AGENTS_DESKTOP_WS_BASE ?? "ws://127.0.0.1:8765",
    selectProjectDirectory: () => ipcRenderer.invoke("project:select-directory"),
});
//# sourceMappingURL=preload.cjs.map
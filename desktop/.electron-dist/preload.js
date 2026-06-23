import { contextBridge } from "electron";
contextBridge.exposeInMainWorld("ycAgentsDesktop", {
    version: "0.1.0",
});
//# sourceMappingURL=preload.js.map
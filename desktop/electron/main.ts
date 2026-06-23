import { app, BrowserWindow } from "electron";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { startPythonService, type PythonService } from "./pythonService.js";

let service: PythonService | null = null;
const currentDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(currentDir, "..", "..");
const userDataDir = path.join(repoRoot, "outputs", "electron-user-data");

mkdirSync(userDataDir, { recursive: true });
app.setPath("userData", userDataDir);
app.disableHardwareAcceleration();
app.commandLine.appendSwitch("disable-gpu");
app.commandLine.appendSwitch("disable-gpu-compositing");
app.commandLine.appendSwitch("disable-gpu-sandbox");

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    webPreferences: {
      preload: path.join(currentDir, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    win.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    win.loadFile(path.join(currentDir, "../dist/index.html"));
  }
}

app.whenReady().then(() => {
  service = startPythonService({ repoRoot });
  createWindow();
});

app.on("window-all-closed", () => {
  service?.stop();
  service = null;
  if (process.platform !== "darwin") {
    app.quit();
  }
});

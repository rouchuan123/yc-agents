import { app, BrowserWindow } from "electron";
import path from "node:path";
import { startPythonService, type PythonService } from "./pythonService";

let service: PythonService | null = null;

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    win.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    win.loadFile(path.join(__dirname, "../dist/index.html"));
  }
}

app.whenReady().then(() => {
  const repoRoot = path.resolve(__dirname, "..", "..");
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

import { app, BrowserWindow, dialog, ipcMain, Menu } from "electron";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { startDesktopApp } from "./bootstrap.js";
import { registerProjectDialogIpc } from "./projectDialog.js";
import { startPythonService, waitForHealth, type PythonService } from "./pythonService.js";

let service: PythonService | null = null;
const currentDir = path.dirname(fileURLToPath(import.meta.url));

function createWindow(port: number) {
  setChineseApplicationMenu();
  process.env.YC_AGENTS_DESKTOP_API_BASE = `http://127.0.0.1:${port}`;
  process.env.YC_AGENTS_DESKTOP_WS_BASE = `ws://127.0.0.1:${port}`;

  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    webPreferences: {
      preload: path.join(currentDir, "preload.cjs"),
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

function setChineseApplicationMenu() {
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      {
        label: "文件",
        submenu: [
          { role: "quit", label: "退出" },
        ],
      },
      {
        label: "编辑",
        submenu: [
          { role: "undo", label: "撤销" },
          { role: "redo", label: "重做" },
          { type: "separator" },
          { role: "cut", label: "剪切" },
          { role: "copy", label: "复制" },
          { role: "paste", label: "粘贴" },
          { role: "selectAll", label: "全选" },
        ],
      },
      {
        label: "视图",
        submenu: [
          { role: "reload", label: "重新加载" },
          { role: "toggleDevTools", label: "开发者工具" },
          { type: "separator" },
          { role: "resetZoom", label: "实际大小" },
          { role: "zoomIn", label: "放大" },
          { role: "zoomOut", label: "缩小" },
          { type: "separator" },
          { role: "togglefullscreen", label: "全屏" },
        ],
      },
      {
        label: "窗口",
        submenu: [
          { role: "minimize", label: "最小化" },
          { role: "close", label: "关闭" },
        ],
      },
      {
        label: "帮助",
        submenu: [
          {
            label: "关于 YC Agents",
            click: () => {
              dialog.showMessageBox({
                type: "info",
                title: "关于 YC Agents",
                message: "YC Agents 桌面版",
              });
            },
          },
        ],
      },
    ]),
  );
}

const repoRoot = path.resolve(currentDir, "..", "..");
const port = Number(process.env.YC_AGENTS_DESKTOP_PORT ?? 8765);

registerProjectDialogIpc(ipcMain, dialog, BrowserWindow);

startDesktopApp(
  {
    whenReady: () => app.whenReady().then(() => undefined),
    startPythonService,
    waitForHealth,
    createWindow,
  },
  { repoRoot, port },
)
  .then((handle) => {
    service = handle.service;
  })
  .catch((error: unknown) => {
    console.error(error);
    app.quit();
  });

app.on("window-all-closed", () => {
  service?.stop();
  service = null;
  if (process.platform !== "darwin") {
    app.quit();
  }
});

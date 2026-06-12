const { app, BrowserWindow, ipcMain, shell, dialog } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");

let mainWindow;
let splashWindow;
let backendProcess;

const isDev = process.env.NODE_ENV === "development";
const isMac = process.platform === "darwin";

const SPLASH_WIDTH = 420;
const SPLASH_HEIGHT = 520;
const BACKEND_PORT = 8000;
const BACKEND_HOST = "127.0.0.1";
const STAGGER_DELAY_MS = 200;

//     Progress State
let progressHistory = [];
let splashReady = false;
let nextFlushIndex = 0;
let staggerTimer = null;

function pushProgress(step, progress, message) {
  const last = progressHistory[progressHistory.length - 1];
  if (last && step <= last.step) return;

  progressHistory.push({ step, progress, message });

  if (splashReady) {
    startStaggeredFlush();
  }
}

// Send one entry every STAGGER_DELAY_MS so CSS transitions play out visibly
function startStaggeredFlush() {
  if (staggerTimer) return;

  const tick = () => {
    if (!splashWindow || splashWindow.isDestroyed()) {
      staggerTimer = null;
      return;
    }

    if (nextFlushIndex >= progressHistory.length) {
      staggerTimer = null;
      return;
    }

    const entry = progressHistory[nextFlushIndex];
    splashWindow.webContents.send("splash-progress", entry);
    nextFlushIndex++;

    staggerTimer = setTimeout(() => {
      staggerTimer = null;
      tick();
    }, STAGGER_DELAY_MS);
  };

  tick();
}

function resolveSplashPath() {
  const candidates = [
    path.join(__dirname, "..", "dist", "splash.html"),
    path.join(__dirname, "..", "public", "splash.html"),
    path.join(__dirname, "..", "splash.html"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return candidates[0];
}

//     Splash Screen
function createSplashWindow() {
  const splashPath = resolveSplashPath();
  progressHistory = [];
  splashReady = false;
  nextFlushIndex = 0;
  if (staggerTimer) {
    clearTimeout(staggerTimer);
    staggerTimer = null;
  }

  splashWindow = new BrowserWindow({
    width: SPLASH_WIDTH,
    height: SPLASH_HEIGHT,
    frame: false,
    alwaysOnTop: true,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    transparent: true,
    backgroundColor: "#00000000",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  splashWindow.loadFile(splashPath);

  splashWindow.webContents.once("did-finish-load", () => {
    splashReady = true;
    startStaggeredFlush();
  });

  splashWindow.once("ready-to-show", () => {
    splashWindow.center();
    splashWindow.show();
  });

  splashWindow.on("closed", () => {
    splashWindow = null;
    splashReady = false;
  });
}

//     Main Window
function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    titleBarStyle: isMac ? "hiddenInset" : undefined,
    frame: isMac,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:3000");
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

//     Backend Health Check
function checkBackendHealth(maxRetries = 60, intervalMs = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    const tryConnect = () => {
      attempts++;
      const req = http.get(
        `http://${BACKEND_HOST}:${BACKEND_PORT}/health`,
        { timeout: 2000 },
        (res) => {
          if (res.statusCode === 200) {
            resolve();
            return;
          }
          retry();
        },
      );
      req.on("error", () => retry());
      req.on("timeout", () => {
        req.destroy();
        retry();
      });
    };

    const retry = () => {
      if (attempts >= maxRetries) {
        reject(new Error(`Backend failed after ${maxRetries} attempts`));
        return;
      }
      setTimeout(tryConnect, intervalMs);
    };

    tryConnect();
  });
}

//     Parse uvicorn output to drive progress
function handleBackendOutput(text) {
  const lines = text.toString().split(/\r?\n/);
  for (const line of lines) {
    const t = line.trim();
    if (!t) continue;

    if (t.includes("Application startup complete")) {
      pushProgress(3, 75, "Warming up API routes...");
    } else if (t.includes("Waiting for application startup")) {
      pushProgress(2, 50, "Initializing database...");
    } else if (t.includes("Started server process")) {
      pushProgress(1, 30, "Loading Python environment...");
    }
  }
}

//     Backend Process
function startBackend() {
  const backendDir = path.join(__dirname, "..", "..", "backend");

  const python =
    process.platform === "win32"
      ? path.join(backendDir, ".venv", "Scripts", "python.exe")
      : path.join(backendDir, ".venv", "bin", "python");

  pushProgress(0, 10, "Starting backend server...");

  backendProcess = spawn(
    python,
    [
      "-m",
      "uvicorn",
      "main:app",
      "--port",
      String(BACKEND_PORT),
      "--host",
      BACKEND_HOST,
    ],
    {
      cwd: backendDir,
      env: { ...process.env, PYTHONPATH: backendDir },
    },
  );

  backendProcess.stdout.on("data", handleBackendOutput);
  backendProcess.stderr.on("data", handleBackendOutput);

  backendProcess.on("close", (code) => {
    console.log(`Backend process exited with code ${code}`);
  });
}

//     Boot Sequence
async function bootSequence() {
  createSplashWindow();

  if (!isDev) {
    startBackend();

    try {
      await checkBackendHealth(60, 500);
    } catch (err) {
      console.error("Backend failed to start:", err);
      pushProgress(4, 100, "Backend failed to start. Check logs.");
      await new Promise((r) => setTimeout(r, 3000));
    }

    const last = progressHistory[progressHistory.length - 1];
    if (!last || last.step < 4) {
      pushProgress(4, 100, "Ready to launch...");
    }

    // Wait for staggered flush to finish + let user see 100%
    while (staggerTimer) {
      await new Promise((r) => setTimeout(r, 100));
    }
    await new Promise((r) => setTimeout(r, 600));
  } else {
    pushProgress(0, 20, "Connecting to development server...");
    try {
      await checkBackendHealth(20, 300);
      pushProgress(4, 100, "Ready to launch...");
      await new Promise((r) => setTimeout(r, 800));
    } catch {
      pushProgress(4, 100, "Backend not detected — proceed to setup");
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  // Transition
  createMainWindow();

  const transition = () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
    }
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.destroy();
    }
  };

  if (mainWindow) {
    mainWindow.once("ready-to-show", transition);
    setTimeout(transition, 2000);
  }
}

//     App Lifecycle
app.whenReady().then(() => {
  bootSequence();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      bootSequence();
    }
  });
});

app.on("window-all-closed", () => {
  if (backendProcess) backendProcess.kill();
  if (process.platform !== "darwin") app.quit();
});

//     IPC Handlers
ipcMain.handle("open-external", async (_, url) => {
  await shell.openExternal(url);
});

ipcMain.handle("select-directory", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory"],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle("select-file", async (_, filters) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile"],
    filters: filters || [{ name: "All Files", extensions: ["*"] }],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle("window-minimize", () => mainWindow?.minimize());
ipcMain.handle("window-maximize", () => {
  if (mainWindow?.isMaximized()) mainWindow?.unmaximize();
  else mainWindow?.maximize();
});
ipcMain.handle("window-close", () => mainWindow?.close());
ipcMain.handle("window-is-maximized", () => mainWindow?.isMaximized() ?? false);

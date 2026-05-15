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

// ─── Progress State ───
let bootProgress = { step: 0, progress: 5, message: "Initializing..." };
let progressTimer = null;
let splashReady = false;
let pendingSplashMessages = [];

function setProgress(step, progress, message) {
  bootProgress = { step, progress, message };
  sendSplashProgress({ step, progress, message });
}

function animateProgressTo(
  targetStep,
  targetProgress,
  message,
  durationMs = 800,
) {
  const startProgress = bootProgress.progress;
  const startTime = Date.now();

  if (progressTimer) clearInterval(progressTimer);

  progressTimer = setInterval(() => {
    const elapsed = Date.now() - startTime;
    const ratio = Math.min(1, elapsed / durationMs);
    const eased = 1 - Math.pow(1 - ratio, 3);
    const current = Math.round(
      startProgress + (targetProgress - startProgress) * eased,
    );

    setProgress(targetStep, current, message);

    if (ratio >= 1) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
  }, 16);
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

// ─── Splash Screen ───
function createSplashWindow() {
  const splashPath = resolveSplashPath();
  splashReady = false;
  pendingSplashMessages = [];

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

  // Single did-finish-load listener — flush queue when ready
  splashWindow.webContents.once("did-finish-load", () => {
    splashReady = true;
    // Send all queued messages
    for (const msg of pendingSplashMessages) {
      splashWindow.webContents.send("splash-progress", msg);
    }
    pendingSplashMessages = [];
  });

  splashWindow.once("ready-to-show", () => {
    splashWindow.center();
    splashWindow.show();
    // If already loaded, send current state
    if (splashReady) {
      splashWindow.webContents.send("splash-progress", bootProgress);
    }
  });

  splashWindow.on("closed", () => {
    splashWindow = null;
    splashReady = false;
  });
}

function sendSplashProgress(data) {
  if (!splashWindow || splashWindow.isDestroyed()) return;

  if (!splashReady) {
    // Queue message instead of adding more listeners
    pendingSplashMessages.push(data);
    return;
  }

  splashWindow.webContents.send("splash-progress", data);
}

// ─── Main Window ───
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

// ─── Backend Health Check ───
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

// ─── Parse uvicorn output to drive progress ───
function handleBackendOutput(text) {
  const t = text.toString();
  console.log(`[Backend] ${t.trim()}`);

  if (t.includes("Application startup complete")) {
    animateProgressTo(3, 85, "Warming up API routes...", 600);
  } else if (t.includes("Uvicorn running on")) {
    animateProgressTo(2, 60, "Initializing database...", 500);
  } else if (t.includes("Started server process")) {
    animateProgressTo(1, 35, "Loading Python environment...", 500);
  } else if (t.includes("Waiting for application startup")) {
    animateProgressTo(1, 25, "Loading Python environment...", 400);
  }
}

// ─── Backend Process ───
function startBackend() {
  const backendDir = path.join(__dirname, "..", "..", "backend");

  const python =
    process.platform === "win32"
      ? path.join(backendDir, ".venv", "Scripts", "python.exe")
      : path.join(backendDir, ".venv", "bin", "python");

  animateProgressTo(0, 15, "Starting backend server...", 400);

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

// ─── Boot Sequence ───
async function bootSequence() {
  createSplashWindow();

  if (!isDev) {
    startBackend();

    try {
      await checkBackendHealth(60, 500);
    } catch (err) {
      console.error("Backend failed to start:", err);
      animateProgressTo(4, 100, "Backend failed to start. Check logs.", 300);
      await new Promise((r) => setTimeout(r, 3000));
    }

    if (bootProgress.step < 4 || bootProgress.progress < 100) {
      animateProgressTo(4, 100, "Ready to launch!", 400);
      await new Promise((r) => setTimeout(r, 600));
    }
  } else {
    animateProgressTo(0, 20, "Connecting to development server...", 300);
    try {
      await checkBackendHealth(20, 300);
      animateProgressTo(4, 100, "Ready to launch!", 400);
      await new Promise((r) => setTimeout(r, 400));
    } catch {
      animateProgressTo(4, 100, "Backend not detected — proceed to setup", 300);
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
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
  };

  if (mainWindow) {
    mainWindow.once("ready-to-show", transition);
    setTimeout(transition, 2000);
  }
}

// ─── App Lifecycle ───
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

// ─── IPC Handlers ───
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

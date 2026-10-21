// electron/main.js — Electron entry point (CommonJS)
const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');

const isDev = process.env.NODE_ENV !== 'production';

// Base resolution 320x180 at 4x scale = 1280x720
const BASE_WIDTH = 1280;
const BASE_HEIGHT = 720;

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: BASE_WIDTH,
    height: BASE_HEIGHT,
    minWidth: 320,
    minHeight: 180,
    resizable: true,
    fullscreenable: true,
    autoHideMenuBar: true,
    frame: true,
    backgroundColor: '#000000',
    title: 'Realm Chips',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    // Lock aspect ratio to 16:9
    aspectRatio: 16 / 9,
  });

  // Load dev server or built dist
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    // Open DevTools in development (comment out if not needed)
    // mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});

// IPC: resize window (called from SettingsScene when resolution changes)
ipcMain.handle('resize-window', (_event, width, height) => {
  if (mainWindow) {
    mainWindow.setSize(Math.round(width), Math.round(height), true);
    mainWindow.center();
  }
});

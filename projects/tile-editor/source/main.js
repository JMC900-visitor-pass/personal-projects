'use strict';

const { app, BrowserWindow, Menu, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');

/** @type {BrowserWindow} */
let mainWindow = null;

/**
 * Create the main application window.
 */
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: 'Tile Map Editor',
    backgroundColor: '#1e1e1e',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  buildMenu();
}

/**
 * Build the application menu with File/Edit/View/Map entries.
 */
function buildMenu() {
  const isMac = process.platform === 'darwin';

  const template = [
    // App menu (macOS only)
    ...(isMac ? [{
      label: app.name,
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'hideOthers' },
        { role: 'unhide' },
        { type: 'separator' },
        { role: 'quit' }
      ]
    }] : []),

    {
      label: 'File',
      submenu: [
        {
          label: 'New Map',
          accelerator: 'CmdOrCtrl+N',
          click() { mainWindow.webContents.send('menu:new-map'); }
        },
        { type: 'separator' },
        {
          label: 'Open Map...',
          accelerator: 'CmdOrCtrl+O',
          click() { mainWindow.webContents.send('menu:open-map'); }
        },
        { type: 'separator' },
        {
          label: 'Save Map',
          accelerator: 'CmdOrCtrl+S',
          click() { mainWindow.webContents.send('menu:save-map'); }
        },
        {
          label: 'Save Map As...',
          accelerator: 'CmdOrCtrl+Shift+S',
          click() { mainWindow.webContents.send('menu:save-map-as'); }
        },
        { type: 'separator' },
        {
          label: 'Export Map...',
          click() { mainWindow.webContents.send('menu:export-json'); }
        },
        { type: 'separator' },
        {
          label: 'Import Tileset...',
          click() { mainWindow.webContents.send('menu:import-tileset'); }
        },
        { type: 'separator' },
        isMac ? { role: 'close' } : { role: 'quit' }
      ]
    },

    {
      label: 'Edit',
      submenu: [
        {
          label: 'Undo',
          accelerator: 'CmdOrCtrl+Z',
          click() { mainWindow.webContents.send('menu:undo'); }
        },
        {
          label: 'Redo',
          accelerator: 'CmdOrCtrl+Y',
          click() { mainWindow.webContents.send('menu:redo'); }
        },
        { type: 'separator' },
        { role: 'copy' },
        { role: 'paste' }
      ]
    },

    {
      label: 'View',
      submenu: [
        {
          label: 'Toggle Grid',
          accelerator: 'G',
          click() { mainWindow.webContents.send('menu:toggle-grid'); }
        },
        {
          label: 'Toggle Collision Overlay',
          accelerator: 'C',
          click() { mainWindow.webContents.send('menu:toggle-collision'); }
        },
        { type: 'separator' },
        {
          label: 'Zoom In',
          accelerator: 'CmdOrCtrl+Equal',
          click() { mainWindow.webContents.send('menu:zoom-in'); }
        },
        {
          label: 'Zoom Out',
          accelerator: 'CmdOrCtrl+Minus',
          click() { mainWindow.webContents.send('menu:zoom-out'); }
        },
        {
          label: 'Reset Zoom',
          accelerator: 'CmdOrCtrl+0',
          click() { mainWindow.webContents.send('menu:zoom-reset'); }
        },
        { type: 'separator' },
        { role: 'toggleDevTools' }
      ]
    },

    {
      label: 'Map',
      submenu: [
        {
          label: 'Resize Map...',
          click() { mainWindow.webContents.send('menu:resize-map'); }
        },
        {
          label: 'Map Properties...',
          click() { mainWindow.webContents.send('menu:map-properties'); }
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

// ---- IPC Handlers ----

/**
 * Show an open file dialog.
 */
ipcMain.handle('dialog:open', async (event, options) => {
  const result = await dialog.showOpenDialog(mainWindow, options);
  return result;
});

/**
 * Show a save file dialog.
 */
ipcMain.handle('dialog:save', async (event, options) => {
  const result = await dialog.showSaveDialog(mainWindow, options);
  return result;
});

/**
 * Read a file from disk, returning its string contents.
 */
ipcMain.handle('fs:readFile', async (event, filePath, encoding) => {
  try {
    const data = fs.readFileSync(filePath, encoding || 'utf8');
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

/**
 * Write a string or buffer to disk.
 */
ipcMain.handle('fs:writeFile', async (event, filePath, content) => {
  try {
    fs.writeFileSync(filePath, content, 'utf8');
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

/**
 * Write a base64-encoded string to disk as binary (used for PNG export).
 */
ipcMain.handle('fs:writeFileBinary', async (event, filePath, base64Data) => {
  try {
    const buffer = Buffer.from(base64Data, 'base64');
    fs.writeFileSync(filePath, buffer);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

/**
 * Create a directory (and any missing parents).
 */
ipcMain.handle('fs:mkdir', async (event, dirPath) => {
  try {
    fs.mkdirSync(dirPath, { recursive: true });
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

/**
 * Read a file as a base64-encoded data URL (for images).
 */
ipcMain.handle('fs:readFileBase64', async (event, filePath) => {
  try {
    const buffer = fs.readFileSync(filePath);
    const ext = path.extname(filePath).toLowerCase().slice(1);
    const mime = ext === 'png' ? 'image/png' : ext === 'jpg' ? 'image/jpeg' : 'image/png';
    const dataUrl = `data:${mime};base64,${buffer.toString('base64')}`;
    return { ok: true, data: dataUrl };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ---- App lifecycle ----

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

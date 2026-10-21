// electron/preload.js — Expose safe APIs to the renderer via contextBridge
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  /**
   * Resize the Electron BrowserWindow.
   * @param {number} width - Target pixel width
   * @param {number} height - Target pixel height
   */
  resizeWindow: (width, height) => ipcRenderer.invoke('resize-window', width, height),
});

'use strict';

const { contextBridge, ipcRenderer } = require('electron');

/**
 * Expose a safe, minimal API to the renderer process via contextBridge.
 * All file I/O and dialog operations are proxied through IPC to the main process.
 */
contextBridge.exposeInMainWorld('electronAPI', {

  // ---- Dialog helpers ----

  /**
   * Show an open-file dialog.
   * @param {Electron.OpenDialogOptions} options
   * @returns {Promise<Electron.OpenDialogReturnValue>}
   */
  showOpenDialog: (options) => ipcRenderer.invoke('dialog:open', options),

  /**
   * Show a save-file dialog.
   * @param {Electron.SaveDialogOptions} options
   * @returns {Promise<Electron.SaveDialogReturnValue>}
   */
  showSaveDialog: (options) => ipcRenderer.invoke('dialog:save', options),

  // ---- File system helpers ----

  /**
   * Read a text file from disk.
   * @param {string} filePath
   * @param {string} [encoding='utf8']
   * @returns {Promise<{ok:boolean, data?:string, error?:string}>}
   */
  readFile: (filePath, encoding) => ipcRenderer.invoke('fs:readFile', filePath, encoding),

  /**
   * Write text content to disk.
   * @param {string} filePath
   * @param {string} content
   * @returns {Promise<{ok:boolean, error?:string}>}
   */
  writeFile: (filePath, content) => ipcRenderer.invoke('fs:writeFile', filePath, content),

  /**
   * Read an image file as a base64 data URL.
   * @param {string} filePath
   * @returns {Promise<{ok:boolean, data?:string, error?:string}>}
   */
  readFileBase64: (filePath) => ipcRenderer.invoke('fs:readFileBase64', filePath),

  /**
   * Write a base64 string to disk as binary data (e.g. PNG).
   * @param {string} filePath
   * @param {string} base64Data
   * @returns {Promise<{ok:boolean, error?:string}>}
   */
  writeFileBinary: (filePath, base64Data) => ipcRenderer.invoke('fs:writeFileBinary', filePath, base64Data),

  /**
   * Create a directory and any missing parent directories.
   * @param {string} dirPath
   * @returns {Promise<{ok:boolean, error?:string}>}
   */
  mkdir: (dirPath) => ipcRenderer.invoke('fs:mkdir', dirPath),

  // ---- Menu event listeners ----

  /**
   * Register a listener for menu-triggered events.
   * @param {string} channel
   * @param {Function} callback
   */
  onMenu: (channel, callback) => {
    const validChannels = [
      'menu:new-map', 'menu:open-map', 'menu:save-map', 'menu:save-map-as',
      'menu:export-json', 'menu:import-tileset',
      'menu:undo', 'menu:redo',
      'menu:toggle-grid', 'menu:toggle-collision',
      'menu:zoom-in', 'menu:zoom-out', 'menu:zoom-reset',
      'menu:resize-map', 'menu:map-properties'
    ];
    if (validChannels.includes(channel)) {
      ipcRenderer.on(channel, (_event, ...args) => callback(...args));
    }
  },

  /**
   * Remove all listeners for a menu channel.
   * @param {string} channel
   */
  offMenu: (channel) => {
    ipcRenderer.removeAllListeners(channel);
  }
});

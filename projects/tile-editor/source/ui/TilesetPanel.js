'use strict';

/**
 * TilesetPanel — renders the loaded tileset in a canvas and lets the user
 * click or drag to select one or more tiles. Exposes the selection as a
 * stamp via state.tileStamp and fires onTileSelected with the top-left ID.
 */
class TilesetPanel {
  /**
   * @param {HTMLElement} container - The DOM element to render into.
   * @param {object} state          - Shared editor state.
   */
  constructor(container, state) {
    this.container = container;
    this.state = state;

    /** @type {HTMLCanvasElement} */
    this.canvas = null;
    /** @type {CanvasRenderingContext2D} */
    this.ctx = null;

    /** @type {HTMLImageElement|null} */
    this.image = null;
    /** @type {number} */
    this.tileSize = 16;
    /** @type {number} */
    this.columns = 0;
    /** @type {number} */
    this.rows = 0;

    /** @type {number} Selected tile ID (top-left of selection) */
    this.selectedTileId = 0;
    /** @type {number} Display scale for the tileset panel */
    this.displayScale = 2;
    /** @type {boolean} Whether to draw tile ID numbers on each tile */
    this.showTileIds = true;
    /** @type {HTMLInputElement|null} The tile ID input field */
    this._idInput = null;

    /** @type {Function|null} */
    this.onTileSelected = null;

    // Multi-select drag state
    /** @type {{col:number,row:number}|null} */
    this._selStart = null;
    /** @type {{col:number,row:number}|null} */
    this._selEnd = null;
    /** @type {boolean} */
    this._selDragging = false;

    this._build();
  }

  /**
   * Build the panel DOM structure.
   */
  _build() {
    this.container.innerHTML = '';

    // Header row
    const header = document.createElement('div');
    header.className = 'panel-header';
    header.innerHTML = '<span>Tileset</span>';

    const importBtn = document.createElement('button');
    importBtn.className = 'btn btn-sm';
    importBtn.textContent = 'Import';
    importBtn.title = 'Import a tileset PNG';
    importBtn.addEventListener('click', () => this._importTileset());
    header.appendChild(importBtn);
    this.container.appendChild(header);

    // Controls: row 1 — tile size + tile ID input
    const controls = document.createElement('div');
    controls.className = 'tileset-controls';

    const row1 = document.createElement('div');
    row1.className = 'tileset-control-row';
    row1.innerHTML = `
      <label>Size:
        <select id="tileSizeSelect">
          <option value="8">8</option>
          <option value="16" selected>16</option>
          <option value="32">32</option>
          <option value="48">48</option>
        </select>
      </label>
      <label>Tile ID:
        <input type="number" id="tileIdInput" value="0" min="0"
               title="Hover to preview tile ID. Type a number + Enter to jump to that tile." />
      </label>
    `;
    controls.appendChild(row1);

    // Controls: row 2 — show IDs toggle
    const row2 = document.createElement('div');
    row2.className = 'tileset-control-row';
    row2.innerHTML = `
      <label class="tileset-check-label">
        <input type="checkbox" id="showTileIds" checked />
        Show tile IDs
      </label>
    `;
    controls.appendChild(row2);
    this.container.appendChild(controls);

    const sel = controls.querySelector('#tileSizeSelect');
    sel.addEventListener('change', () => {
      this.tileSize = parseInt(sel.value, 10);
      this.state.tileMap.tileSize = this.tileSize;
      this._recompute();
      this.render();
    });

    this._idInput = controls.querySelector('#tileIdInput');
    this._idInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); this._selectById(); }
    });
    this._idInput.addEventListener('blur', () => {
      // Revert display to the currently selected tile if user didn't commit
      this._idInput.value = this.selectedTileId;
    });

    controls.querySelector('#showTileIds').addEventListener('change', (e) => {
      this.showTileIds = e.target.checked;
      this.render();
    });

    // Canvas wrapper for scrolling
    const wrapper = document.createElement('div');
    wrapper.className = 'tileset-canvas-wrapper';
    this.container.appendChild(wrapper);

    this.canvas = document.createElement('canvas');
    this.canvas.className = 'tileset-canvas';
    wrapper.appendChild(this.canvas);
    this.ctx = this.canvas.getContext('2d');
    this.ctx.imageSmoothingEnabled = false;

    this.canvas.addEventListener('mousedown', (e) => this._onMouseDown(e));
    this.canvas.addEventListener('mousemove', (e) => this._onMouseMove(e));
    this.canvas.addEventListener('mouseup',   (e) => this._onMouseUp(e));
    this.canvas.addEventListener('mouseleave', () => {
      if (!this._selDragging) {
        if (this._idInput) this._idInput.value = this.selectedTileId;
        this.render();
      }
    });

    // End drag even if mouse releases outside the canvas
    document.addEventListener('mouseup', () => {
      if (this._selDragging) {
        this._selDragging = false;
      }
    });

    // Placeholder text
    this._placeholder = document.createElement('div');
    this._placeholder.className = 'tileset-placeholder';
    this._placeholder.textContent = 'No tileset loaded. Click Import to load a PNG.';
    wrapper.appendChild(this._placeholder);
  }

  /**
   * Open file dialog and load a new tileset.
   */
  async _importTileset() {
    const result = await window.electronAPI.showOpenDialog({
      title: 'Import Tileset',
      filters: [
        { name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'gif', 'bmp'] }
      ],
      properties: ['openFile']
    });

    if (result.canceled || !result.filePaths.length) return;

    const filePath = result.filePaths[0];
    const res = await window.electronAPI.readFileBase64(filePath);
    if (!res.ok) {
      alert('Failed to load tileset: ' + res.error);
      return;
    }

    await this.loadFromDataUrl(res.data, filePath);
    this.state.tileMap.tilesetPath = filePath;
  }

  /**
   * Load a tileset from a data URL.
   * @param {string} dataUrl
   * @param {string} [path='']
   */
  async loadFromDataUrl(dataUrl, path = '') {
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = dataUrl;
    });

    this.image = img;
    this._recompute();
    this._placeholder.style.display = 'none';
    this.render();

    // Push image to renderer
    if (this.state.renderer) {
      await this.state.renderer.loadTileset(dataUrl);
    }

    if (this.onTileSelected) this.onTileSelected(this.selectedTileId);
  }

  /**
   * Recompute columns/rows from current image and tile size.
   * Canvas is sized to the full image at displayScale so no pixels are cropped.
   * Also pushes the column count to the renderer so tile ID → source coordinate
   * mapping is guaranteed to be identical on both sides.
   */
  _recompute() {
    if (!this.image) return;
    this.columns = Math.floor(this.image.naturalWidth / this.tileSize);
    this.rows    = Math.floor(this.image.naturalHeight / this.tileSize);
    // Use the full image dimensions (not the tile-grid area) so the entire
    // source image is visible, including any sub-tile-size remainder pixels.
    const w = this.image.naturalWidth  * this.displayScale;
    const h = this.image.naturalHeight * this.displayScale;
    this.canvas.width  = w;
    this.canvas.height = h;
    this.canvas.style.width  = w + 'px';
    this.canvas.style.height = h + 'px';
    // Keep renderer in sync — it must use the exact same column count
    if (this.state.renderer) {
      this.state.renderer.tilesetColumns = this.columns;
    }
  }

  /**
   * Sync the panel's tile size to match the active map (called when a map is
   * loaded or created with a tileSize different from the current dropdown value).
   * Updates the dropdown UI, this.tileSize, tileMap.tileSize, and recomputes
   * the grid if a tileset image is already loaded.
   * @param {number} size
   */
  setTileSize(size) {
    if (this.tileSize === size) return;
    this.tileSize = size;
    // Sync the dropdown to show the correct value
    const sel = this.container.querySelector('#tileSizeSelect');
    if (sel) sel.value = String(size);
    // Keep tileMap in sync (it may already be set, but be explicit)
    if (this.state.tileMap) this.state.tileMap.tileSize = size;
    if (this.image) {
      this._recompute();
      this.render();
    }
  }

  /**
   * Render the tileset to the panel canvas.
   */
  render() {
    if (!this.image) return;
    const { ctx, tileSize, displayScale, columns, rows } = this;
    const ds = tileSize * displayScale;

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // Draw the full source image at displayScale (preserves native resolution)
    ctx.drawImage(
      this.image,
      0, 0,
      this.image.naturalWidth  * displayScale,
      this.image.naturalHeight * displayScale
    );

    // Overlay grid lines and tile IDs only for complete tiles
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < columns; col++) {
        const tileId = row * columns + col;
        const dx = col * ds;
        const dy = row * ds;

        // Light grid
        ctx.strokeStyle = 'rgba(0,0,0,0.25)';
        ctx.lineWidth = 0.5;
        ctx.strokeRect(dx, dy, ds, ds);

        // Tile ID number overlay — only when tiles are large enough to be readable
        if (this.showTileIds && ds >= 20) {
          const fontSize = Math.max(7, Math.min(11, Math.floor(ds * 0.28)));
          ctx.font = `${fontSize}px monospace`;
          ctx.textAlign = 'left';
          ctx.textBaseline = 'top';
          const label = String(tileId);
          const tw = ctx.measureText(label).width;
          // Dark pill behind the number for contrast
          ctx.fillStyle = 'rgba(0,0,0,0.62)';
          ctx.fillRect(dx + 1, dy + 1, tw + 3, fontSize + 2);
          // White number text
          ctx.fillStyle = 'rgba(255,255,255,0.92)';
          ctx.fillText(label, dx + 2, dy + 2);
        }
      }
    }

    // Selection highlight
    this._drawSelection();
  }

  /**
   * Draw the selection highlight. Covers the full selected rectangle.
   */
  _drawSelection() {
    if (!this._selStart) return;
    const { ctx, tileSize, displayScale, columns } = this;
    const ds = tileSize * displayScale;

    const end = this._selEnd || this._selStart;
    const minCol = Math.min(this._selStart.col, end.col);
    const maxCol = Math.max(this._selStart.col, end.col);
    const minRow = Math.min(this._selStart.row, end.row);
    const maxRow = Math.max(this._selStart.row, end.row);

    const dx   = minCol * ds;
    const dy   = minRow * ds;
    const selW = (maxCol - minCol + 1) * ds;
    const selH = (maxRow - minRow + 1) * ds;

    ctx.strokeStyle = '#007acc';
    ctx.lineWidth = 2;
    ctx.strokeRect(dx + 1, dy + 1, selW - 2, selH - 2);

    ctx.fillStyle = 'rgba(0, 122, 204, 0.20)';
    ctx.fillRect(dx, dy, selW, selH);
  }

  /**
   * Convert a mouse event to a clamped tile {col, row}.
   * @param {MouseEvent} e
   * @returns {{col:number, row:number}|null}
   */
  _tileFromEvent(e) {
    if (!this.image) return null;
    const rect = this.canvas.getBoundingClientRect();
    const ds = this.tileSize * this.displayScale;
    const col = Math.floor((e.clientX - rect.left) / ds);
    const row = Math.floor((e.clientY - rect.top) / ds);
    return { col, row };
  }

  /**
   * Handle mousedown — begin a tile selection drag.
   * @param {MouseEvent} e
   */
  _onMouseDown(e) {
    if (e.button !== 0) return;
    const t = this._tileFromEvent(e);
    if (!t) return;
    const col = Math.max(0, Math.min(t.col, this.columns - 1));
    const row = Math.max(0, Math.min(t.row, this.rows - 1));
    if (t.col < 0 || t.col >= this.columns || t.row < 0 || t.row >= this.rows) return;

    this._selStart   = { col, row };
    this._selEnd     = { col, row };
    this._selDragging = true;

    this._commitStamp();
    this.render();
    if (this.onTileSelected) this.onTileSelected(this.selectedTileId);
  }

  /**
   * Handle mousemove — extend drag selection or show hover highlight.
   * @param {MouseEvent} e
   */
  _onMouseMove(e) {
    if (!this.image) return;
    const t = this._tileFromEvent(e);
    if (!t) return;

    if (this._selDragging && this._selStart) {
      // Clamp to valid tile range
      const col = Math.max(0, Math.min(t.col, this.columns - 1));
      const row = Math.max(0, Math.min(t.row, this.rows - 1));
      this._selEnd = { col, row };
      this._commitStamp();
      this.render();
      return;
    }

    // Hover highlight (no drag)
    this.render();
    const col = t.col;
    const row = t.row;
    if (col >= 0 && col < this.columns && row >= 0 && row < this.rows) {
      if (this._idInput) this._idInput.value = row * this.columns + col;
      const ds = this.tileSize * this.displayScale;
      this.ctx.strokeStyle = 'rgba(255,255,255,0.6)';
      this.ctx.lineWidth = 1;
      this.ctx.strokeRect(col * ds + 0.5, row * ds + 0.5, ds - 1, ds - 1);
    }
  }

  /**
   * Handle mouseup — finalize the selection.
   * @param {MouseEvent} e
   */
  _onMouseUp(e) {
    if (e.button !== 0) return;
    this._selDragging = false;
  }

  /**
   * Compute and push the current selection rectangle as a stamp into state.
   * Also updates selectedTileId to the top-left tile.
   */
  _commitStamp() {
    if (!this._selStart) return;
    const end = this._selEnd || this._selStart;

    const minCol = Math.min(this._selStart.col, end.col);
    const maxCol = Math.max(this._selStart.col, end.col);
    const minRow = Math.min(this._selStart.row, end.row);
    const maxRow = Math.max(this._selStart.row, end.row);

    const cols = maxCol - minCol + 1;
    const rows = maxRow - minRow + 1;

    // Top-left tile is the canonical selectedTileId
    this.selectedTileId      = minRow * this.columns + minCol;
    this.state.selectedTileId = this.selectedTileId;
    if (this._idInput) this._idInput.value = this.selectedTileId;

    // Build the flat tile-ID array for the stamp (row-major)
    const tileIds = [];
    for (let r = minRow; r <= maxRow; r++) {
      for (let c = minCol; c <= maxCol; c++) {
        tileIds.push(r * this.columns + c);
      }
    }

    this.state.tileStamp = { cols, rows, tileIds };
  }

  /**
   * Programmatically select a tile by ID (used by eyedropper).
   * Resets to a 1×1 stamp.
   * @param {number} tileId
   */
  selectTile(tileId) {
    if (this.columns <= 0) return;
    const col = tileId % this.columns;
    const row = Math.floor(tileId / this.columns);
    this._selStart = { col, row };
    this._selEnd   = { col, row };
    this._commitStamp();
    this.render();
  }

  /**
   * Read the ID input field, validate, and select that tile.
   * Called when the user presses Enter in the tile ID input.
   */
  _selectById() {
    if (!this.image) return;
    const id = parseInt(this._idInput.value, 10);
    const maxId = this.columns * this.rows - 1;
    if (isNaN(id) || id < 0 || id > maxId) {
      this._idInput.value = this.selectedTileId; // revert bad input
      return;
    }
    this.selectTile(id);
    if (this.onTileSelected) this.onTileSelected(id);
  }
}

window.TilesetPanel = TilesetPanel;

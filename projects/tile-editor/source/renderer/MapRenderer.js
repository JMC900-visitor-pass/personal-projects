'use strict';

/**
 * Object type visual descriptors: icon character and fill color.
 */
const OBJECT_VISUALS = {
  chest:      { icon: 'C', color: '#f0c040', label: 'Chest' },
  npc:        { icon: 'N', color: '#40a0f0', label: 'NPC' },
  door:       { icon: 'D', color: '#a060e0', label: 'Door' },
  teleporter: { icon: 'T', color: '#40e0a0', label: 'Teleport' },
  sign:       { icon: 'S', color: '#e08040', label: 'Sign' },
  encounter:  { icon: '!', color: '#000000', label: 'Encounter' }
};

/**
 * Renders the tile map, collision overlay, objects, and grid onto a canvas.
 */
class MapRenderer {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {Camera} camera
   * @param {TileMap} tileMap
   */
  constructor(canvas, camera, tileMap) {
    /** @type {HTMLCanvasElement} */
    this.canvas = canvas;
    /** @type {CanvasRenderingContext2D} */
    this.ctx = canvas.getContext('2d');
    this.ctx.imageSmoothingEnabled = false;

    /** @type {Camera} */
    this.camera = camera;
    /** @type {TileMap} */
    this.tileMap = tileMap;

    /** @type {HTMLImageElement|null} */
    this.tilesetImage = null;
    /** @type {HTMLCanvasElement|null} Offscreen canvas pre-loaded with tileset */
    this.tilesetCanvas = null;

    /** @type {boolean} */
    this.showGrid = true;
    /** @type {boolean} */
    this.showCollision = false;
    /** @type {boolean} */
    this.showObjects = true;

    /**
     * Column count set directly by TilesetPanel after _recompute().
     * When non-zero, _drawLayer uses this instead of computing from
     * tsImage.width / tileSize, guaranteeing both sides stay in sync.
     * @type {number}
     */
    this.tilesetColumns = 0;

    /** @type {{x:number,y:number}|null} Highlighted hover tile */
    this.hoverTile = null;
    /** @type {number|null} Selected object ID */
    this.selectedObjectId = null;
  }

  /**
   * Load a tileset image from a data URL or src.
   * @param {string} src - Data URL or image src.
   * @returns {Promise<void>}
   */
  loadTileset(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        this.tilesetImage = img;
        // Build offscreen canvas for fast blitting
        const oc = document.createElement('canvas');
        oc.width = img.naturalWidth;
        oc.height = img.naturalHeight;
        const octx = oc.getContext('2d');
        octx.imageSmoothingEnabled = false;
        octx.drawImage(img, 0, 0);
        this.tilesetCanvas = oc;
        resolve();
      };
      img.onerror = reject;
      img.src = src;
    });
  }

  /**
   * Main render pass. Call once per animation frame.
   */
  render() {
    const { ctx, canvas, camera, tileMap } = this;
    const { width: cw, height: ch } = canvas;

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, cw, ch);

    // Checkerboard background (transparent tile indicator)
    this._drawBackground(ctx, cw, ch);

    ctx.save();

    // Apply camera transform
    ctx.scale(camera.zoom, camera.zoom);
    ctx.translate(-camera.x, -camera.y);

    const bounds = camera.getVisibleTileBounds(cw, ch, tileMap.tileSize);
    const clampedMinX = Math.max(0, bounds.minX);
    const clampedMinY = Math.max(0, bounds.minY);
    const clampedMaxX = Math.min(tileMap.width - 1, bounds.maxX);
    const clampedMaxY = Math.min(tileMap.height - 1, bounds.maxY);

    // Draw tile layers bottom to top
    for (const layer of tileMap.layers) {
      if (!layer.visible) continue;
      ctx.globalAlpha = layer.opacity;
      this._drawLayer(ctx, layer, clampedMinX, clampedMinY, clampedMaxX, clampedMaxY);
    }
    ctx.globalAlpha = 1.0;

    // Draw collision overlay
    if (this.showCollision) {
      this._drawCollision(ctx, clampedMinX, clampedMinY, clampedMaxX, clampedMaxY);
    }

    // Draw objects
    if (this.showObjects) {
      this._drawObjects(ctx);
    }

    // Draw grid
    if (this.showGrid) {
      this._drawGrid(ctx, bounds, cw, ch);
    }

    // Draw hover highlight
    if (this.hoverTile) {
      this._drawHover(ctx, this.hoverTile.x, this.hoverTile.y);
    }

    ctx.restore();
  }

  /**
   * Draw a simple checkerboard pattern as the canvas background.
   * @param {CanvasRenderingContext2D} ctx
   * @param {number} cw
   * @param {number} ch
   */
  _drawBackground(ctx, cw, ch) {
    const sz = 16;
    for (let y = 0; y < Math.ceil(ch / sz); y++) {
      for (let x = 0; x < Math.ceil(cw / sz); x++) {
        ctx.fillStyle = (x + y) % 2 === 0 ? '#2d2d30' : '#252526';
        ctx.fillRect(x * sz, y * sz, sz, sz);
      }
    }
  }

  /**
   * Draw a single tile layer.
   * @param {CanvasRenderingContext2D} ctx
   * @param {TileLayer} layer
   * @param {number} minX
   * @param {number} minY
   * @param {number} maxX
   * @param {number} maxY
   */
  _drawLayer(ctx, layer, minX, minY, maxX, maxY) {
    const ts = this.tileMap.tileSize;

    if (!this.tilesetCanvas) {
      // No tileset loaded: draw placeholder colored tiles
      for (let y = minY; y <= maxY; y++) {
        for (let x = minX; x <= maxX; x++) {
          const id = layer.get(x, y);
          if (id < 0) continue;
          ctx.fillStyle = `hsl(${(id * 37) % 360}, 50%, 40%)`;
          ctx.fillRect(x * ts, y * ts, ts, ts);
        }
      }
      return;
    }

    // Draw tiles from tileset offscreen canvas.
    // Prefer the column count pushed by TilesetPanel._recompute() so both
    // sides always use the identical value, regardless of tileSize sync state.
    const tsImage = this.tilesetCanvas;
    const tilesetCols = this.tilesetColumns > 0
      ? this.tilesetColumns
      : Math.floor(tsImage.width / ts);
    if (tilesetCols <= 0) return;

    for (let y = minY; y <= maxY; y++) {
      for (let x = minX; x <= maxX; x++) {
        const id = layer.get(x, y);
        if (id < 0) continue;

        const srcX = (id % tilesetCols) * ts;
        const srcY = Math.floor(id / tilesetCols) * ts;
        const destX = x * ts;
        const destY = y * ts;

        ctx.drawImage(tsImage, srcX, srcY, ts, ts, destX, destY, ts, ts);
      }
    }
  }

  /**
   * Draw semi-transparent collision overlay.
   * Green = walkable (0), Red = blocked (1).
   * @param {CanvasRenderingContext2D} ctx
   */
  _drawCollision(ctx, minX, minY, maxX, maxY) {
    const ts = this.tileMap.tileSize;
    ctx.save();
    for (let y = minY; y <= maxY; y++) {
      for (let x = minX; x <= maxX; x++) {
        const val = this.tileMap.collision.get(x, y);
        ctx.fillStyle = val === 1 ? 'rgba(220, 50, 50, 0.55)' : 'rgba(50, 200, 80, 0.20)';
        ctx.fillRect(x * ts, y * ts, ts, ts);
      }
    }
    ctx.restore();
  }

  /**
   * Draw all placed objects as colored icon squares.
   * @param {CanvasRenderingContext2D} ctx
   */
  _drawObjects(ctx) {
    const ts = this.tileMap.tileSize;
    const objects = this.tileMap.objectLayer.getAll();

    for (const obj of objects) {
      const visual = OBJECT_VISUALS[obj.type] || { icon: '?', color: '#ffffff', label: obj.type };
      const px = obj.x * ts;
      const py = obj.y * ts;

      const isSelected = obj.id === this.selectedObjectId;

      if (obj.type === 'encounter') {
        // Encounter zone — black transparent overlay with optional selection border
        ctx.fillStyle = isSelected ? 'rgba(0, 0, 0, 0.65)' : 'rgba(0, 0, 0, 0.45)';
        ctx.fillRect(px, py, ts, ts);
        if (isSelected) {
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2 / this.camera.zoom;
          ctx.strokeRect(px + 0.5, py + 0.5, ts - 1, ts - 1);
        }
      } else {
        // Standard object rendering
        ctx.fillStyle = visual.color + (isSelected ? 'ee' : '99');
        ctx.fillRect(px, py, ts, ts);

        ctx.strokeStyle = isSelected ? '#ffffff' : visual.color;
        ctx.lineWidth = isSelected ? 2 / this.camera.zoom : 1 / this.camera.zoom;
        ctx.strokeRect(px + 0.5, py + 0.5, ts - 1, ts - 1);

        const fontSize = Math.max(6, ts * 0.55);
        ctx.fillStyle = '#ffffff';
        ctx.font = `bold ${fontSize}px monospace`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(visual.icon, px + ts / 2, py + ts / 2);

        // Encounter property indicator on non-encounter-type objects
        if (obj.properties && obj.properties.encounter === true) {
          ctx.fillStyle = 'rgba(0, 0, 0, 0.45)';
          ctx.fillRect(px, py, ts, ts);
        }
      }
    }
  }

  /**
   * Draw the tile grid overlay.
   * @param {CanvasRenderingContext2D} ctx
   * @param {{ minX, minY, maxX, maxY }} bounds
   * @param {number} cw
   * @param {number} ch
   */
  _drawGrid(ctx, bounds, cw, ch) {
    const ts = this.tileMap.tileSize;
    const mapW = this.tileMap.width * ts;
    const mapH = this.tileMap.height * ts;

    ctx.save();
    ctx.strokeStyle = 'rgba(80, 80, 100, 0.5)';
    ctx.lineWidth = 0.5 / this.camera.zoom;

    const startX = Math.max(0, bounds.minX) * ts;
    const startY = Math.max(0, bounds.minY) * ts;
    const endX = Math.min(this.tileMap.width, bounds.maxX + 2) * ts;
    const endY = Math.min(this.tileMap.height, bounds.maxY + 2) * ts;

    ctx.beginPath();
    for (let x = startX; x <= endX; x += ts) {
      ctx.moveTo(x, startY);
      ctx.lineTo(x, endY);
    }
    for (let y = startY; y <= endY; y += ts) {
      ctx.moveTo(startX, y);
      ctx.lineTo(endX, y);
    }
    ctx.stroke();

    // Map border
    ctx.strokeStyle = 'rgba(120, 140, 200, 0.8)';
    ctx.lineWidth = 1.5 / this.camera.zoom;
    ctx.strokeRect(0, 0, mapW, mapH);

    ctx.restore();
  }

  /**
   * Draw the hover/cursor tile highlight.
   * @param {CanvasRenderingContext2D} ctx
   * @param {number} tx
   * @param {number} ty
   */
  _drawHover(ctx, tx, ty) {
    if (tx < 0 || tx >= this.tileMap.width || ty < 0 || ty >= this.tileMap.height) return;
    const ts = this.tileMap.tileSize;
    ctx.save();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.85)';
    ctx.lineWidth = 1.5 / this.camera.zoom;
    ctx.strokeRect(tx * ts + 0.5, ty * ts + 0.5, ts - 1, ts - 1);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.10)';
    ctx.fillRect(tx * ts, ty * ts, ts, ts);
    ctx.restore();
  }

  /**
   * Draw a single tile at a destination pixel coordinate.
   * Used by the tileset panel preview.
   * @param {CanvasRenderingContext2D} ctx
   * @param {number} tileId
   * @param {number} destX
   * @param {number} destY
   * @param {number} tileSize
   */
  drawTile(ctx, tileId, destX, destY, tileSize) {
    if (!this.tilesetCanvas || tileId < 0) return;
    const tilesetCols = Math.floor(this.tilesetCanvas.width / tileSize);
    const srcX = (tileId % tilesetCols) * tileSize;
    const srcY = Math.floor(tileId / tilesetCols) * tileSize;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(this.tilesetCanvas, srcX, srcY, tileSize, tileSize, destX, destY, tileSize, tileSize);
  }
}

window.MapRenderer = MapRenderer;

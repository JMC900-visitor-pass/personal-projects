'use strict';

/**
 * Brush Tool — paints the selected tile (or multi-tile stamp) onto the active layer.
 * Supports click-and-drag continuous painting.
 */
class BrushTool {
  /**
   * @param {object} state - Shared editor state reference.
   */
  constructor(state) {
    /** @type {object} */
    this.state = state;
    /** @type {boolean} */
    this.painting = false;
    /** @type {number} */
    this.lastTX = -1;
    /** @type {number} */
    this.lastTY = -1;

    this.name = 'brush';
    this.cursor = 'crosshair';
  }

  /**
   * @param {number} tx - Tile X
   * @param {number} ty - Tile Y
   */
  onMouseDown(tx, ty) {
    this.painting = true;
    this._paint(tx, ty);
  }

  /**
   * @param {number} tx
   * @param {number} ty
   */
  onMouseMove(tx, ty) {
    if (!this.painting) return;
    if (tx === this.lastTX && ty === this.lastTY) return;
    this._paint(tx, ty);
  }

  onMouseUp() {
    if (this.painting) {
      this.state.undoStack.commit();
      this.painting = false;
    }
    this.lastTX = -1;
    this.lastTY = -1;
  }

  /**
   * Paint the selected tile or stamp at (tx, ty).
   * For a multi-tile stamp, (tx, ty) is the top-left anchor.
   * @param {number} tx
   * @param {number} ty
   */
  _paint(tx, ty) {
    const { tileMap, activeLayerIndex, selectedTileId, tileStamp } = this.state;

    if (tileStamp && (tileStamp.cols > 1 || tileStamp.rows > 1)) {
      // Multi-tile stamp: paint all tiles in the stamp relative to (tx, ty)
      for (let row = 0; row < tileStamp.rows; row++) {
        for (let col = 0; col < tileStamp.cols; col++) {
          const cx = tx + col;
          const cy = ty + row;
          if (cx < 0 || cx >= tileMap.width || cy < 0 || cy >= tileMap.height) continue;
          const tileId = tileStamp.tileIds[row * tileStamp.cols + col];
          const prev = tileMap.getTile(activeLayerIndex, cx, cy);
          if (prev !== tileId) {
            this.state.undoStack.pushTilePaint(activeLayerIndex, cx, cy, prev, tileId);
            tileMap.setTile(activeLayerIndex, cx, cy, tileId);
          }
        }
      }
      this.lastTX = tx;
      this.lastTY = ty;
    } else {
      // Single tile
      if (tx < 0 || tx >= tileMap.width || ty < 0 || ty >= tileMap.height) return;
      if (selectedTileId < 0) return;

      const prev = tileMap.getTile(activeLayerIndex, tx, ty);
      if (prev === selectedTileId) return;

      this.state.undoStack.pushTilePaint(activeLayerIndex, tx, ty, prev, selectedTileId);
      tileMap.setTile(activeLayerIndex, tx, ty, selectedTileId);
      this.lastTX = tx;
      this.lastTY = ty;
    }
  }
}

window.BrushTool = BrushTool;

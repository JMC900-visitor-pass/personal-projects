'use strict';

/**
 * Eraser Tool — sets tiles to -1 (empty) on the active layer.
 */
class EraserTool {
  /**
   * @param {object} state - Shared editor state reference.
   */
  constructor(state) {
    this.state = state;
    this.erasing = false;
    this.lastTX = -1;
    this.lastTY = -1;
    this.name = 'eraser';
    this.cursor = 'cell';
  }

  onMouseDown(tx, ty) {
    this.erasing = true;
    this._erase(tx, ty);
  }

  onMouseMove(tx, ty) {
    if (!this.erasing) return;
    if (tx === this.lastTX && ty === this.lastTY) return;
    this._erase(tx, ty);
  }

  onMouseUp() {
    if (this.erasing) {
      this.state.undoStack.commit();
      this.erasing = false;
    }
    this.lastTX = -1;
    this.lastTY = -1;
  }

  /**
   * Erase the tile at (tx, ty).
   * @param {number} tx
   * @param {number} ty
   */
  _erase(tx, ty) {
    const { tileMap, activeLayerIndex } = this.state;
    if (tx < 0 || tx >= tileMap.width || ty < 0 || ty >= tileMap.height) return;

    const prev = tileMap.getTile(activeLayerIndex, tx, ty);
    if (prev === -1) return;

    this.state.undoStack.pushTilePaint(activeLayerIndex, tx, ty, prev, -1);
    tileMap.setTile(activeLayerIndex, tx, ty, -1);
    this.lastTX = tx;
    this.lastTY = ty;
  }
}

window.EraserTool = EraserTool;

'use strict';

/**
 * Collision Paint Tool — left-click paints blocked (1),
 * right-click (or eraser mode) paints walkable (0).
 */
class CollisionTool {
  /**
   * @param {object} state - Shared editor state reference.
   */
  constructor(state) {
    this.state = state;
    this.painting = false;
    this.paintValue = 1; // What value to paint (1=blocked, 0=walkable)
    this.lastTX = -1;
    this.lastTY = -1;
    this.name = 'collision';
    this.cursor = 'crosshair';
  }

  /**
   * @param {number} tx
   * @param {number} ty
   * @param {boolean} [rightButton=false]
   */
  onMouseDown(tx, ty, rightButton = false) {
    this.painting = true;
    this.paintValue = rightButton ? 0 : 1;
    this._paint(tx, ty);
  }

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
   * Paint collision at (tx, ty).
   * @param {number} tx
   * @param {number} ty
   */
  _paint(tx, ty) {
    const { tileMap } = this.state;
    if (tx < 0 || tx >= tileMap.width || ty < 0 || ty >= tileMap.height) return;

    const prev = tileMap.getCollision(tx, ty);
    if (prev === this.paintValue) return;

    this.state.undoStack.pushCollisionPaint(tx, ty, prev, this.paintValue);
    tileMap.setCollision(tx, ty, this.paintValue);
    this.lastTX = tx;
    this.lastTY = ty;
  }
}

window.CollisionTool = CollisionTool;

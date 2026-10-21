'use strict';

/**
 * Flood Fill Tool — replaces all contiguous tiles of the same ID
 * with the selected tile (BFS-based).
 */
class FillTool {
  /**
   * @param {object} state - Shared editor state reference.
   */
  constructor(state) {
    this.state = state;
    this.name = 'fill';
    this.cursor = 'copy';
  }

  onMouseDown(tx, ty) {
    this._fill(tx, ty);
  }

  onMouseMove() {}
  onMouseUp() {}

  /**
   * BFS flood fill starting at (tx, ty).
   * @param {number} startX
   * @param {number} startY
   */
  _fill(startX, startY) {
    const { tileMap, activeLayerIndex, selectedTileId } = this.state;
    if (startX < 0 || startX >= tileMap.width || startY < 0 || startY >= tileMap.height) return;
    if (selectedTileId < 0) return;

    const targetId = tileMap.getTile(activeLayerIndex, startX, startY);
    if (targetId === selectedTileId) return;

    const visited = new Uint8Array(tileMap.width * tileMap.height);
    const queue = [[startX, startY]];
    const painted = []; // [{x, y, prev}]

    while (queue.length > 0) {
      const [x, y] = queue.shift();
      if (x < 0 || x >= tileMap.width || y < 0 || y >= tileMap.height) continue;

      const idx = y * tileMap.width + x;
      if (visited[idx]) continue;
      visited[idx] = 1;

      const current = tileMap.getTile(activeLayerIndex, x, y);
      if (current !== targetId) continue;

      painted.push({ x, y, prev: current });
      tileMap.setTile(activeLayerIndex, x, y, selectedTileId);

      queue.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
    }

    if (painted.length > 0) {
      this.state.undoStack.pushFill(activeLayerIndex, painted, selectedTileId);
    }
  }
}

window.FillTool = FillTool;

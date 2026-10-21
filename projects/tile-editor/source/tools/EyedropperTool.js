'use strict';

/**
 * Eyedropper / Tile Picker Tool — samples the tile ID under the cursor
 * and sets it as the active selected tile.
 */
class EyedropperTool {
  /**
   * @param {object} state - Shared editor state reference.
   */
  constructor(state) {
    this.state = state;
    this.name = 'eyedropper';
    this.cursor = 'crosshair';
  }

  onMouseDown(tx, ty) {
    this._pick(tx, ty);
  }

  onMouseMove() {}
  onMouseUp() {}

  /**
   * Sample the tile at (tx, ty) on the active layer.
   * @param {number} tx
   * @param {number} ty
   */
  _pick(tx, ty) {
    const { tileMap, activeLayerIndex } = this.state;
    const id = tileMap.getTile(activeLayerIndex, tx, ty);
    if (id >= 0) {
      this.state.selectedTileId = id;
      // Notify the tileset panel to update its selection highlight
      if (this.state.onTileSelected) {
        this.state.onTileSelected(id);
      }
    }
  }
}

window.EyedropperTool = EyedropperTool;

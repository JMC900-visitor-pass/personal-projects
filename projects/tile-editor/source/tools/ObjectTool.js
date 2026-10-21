'use strict';

/**
 * Object Placement Tool — click to place the selected object type,
 * or click an existing object to select and inspect it.
 */
class ObjectTool {
  /**
   * @param {object} state - Shared editor state reference.
   */
  constructor(state) {
    this.state = state;
    this.name = 'object';
    this.cursor = 'pointer';
  }

  /**
   * @param {number} tx - Tile X
   * @param {number} ty - Tile Y
   */
  onMouseDown(tx, ty) {
    const { tileMap } = this.state;

    // Check if there's already an object at this tile
    const existing = tileMap.objectLayer.getAt(tx, ty);
    if (existing) {
      // Select it for inspection
      this.state.selectedObjectId = existing.id;
      this.state.renderer.selectedObjectId = existing.id;
      if (this.state.onObjectSelected) {
        this.state.onObjectSelected(existing);
      }
      return;
    }

    // Place a new object if we have a type selected
    const { selectedObjectType } = this.state;
    if (!selectedObjectType) return;

    if (tx < 0 || tx >= tileMap.width || ty < 0 || ty >= tileMap.height) return;

    const obj = tileMap.objectLayer.add(selectedObjectType, tx, ty);
    this.state.undoStack.pushObjectPlace(obj);

    this.state.selectedObjectId = obj.id;
    this.state.renderer.selectedObjectId = obj.id;
    if (this.state.onObjectSelected) {
      this.state.onObjectSelected(obj);
    }
    if (this.state.onObjectsChanged) {
      this.state.onObjectsChanged();
    }
  }

  onMouseMove() {}
  onMouseUp() {}
}

window.ObjectTool = ObjectTool;

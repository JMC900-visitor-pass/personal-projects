'use strict';

/**
 * The collision layer stores per-tile walkability flags.
 * 0 = walkable, 1 = blocked.
 */
class CollisionLayer {
  /**
   * @param {number} width  - Map width in tiles.
   * @param {number} height - Map height in tiles.
   */
  constructor(width, height) {
    /** @type {number} */
    this.width = width;
    /** @type {number} */
    this.height = height;
    /** @type {Uint8Array} */
    this.data = new Uint8Array(width * height); // 0 = walkable
    /** @type {boolean} */
    this.visible = false;
  }

  /**
   * Get the collision value at (x, y).
   * @param {number} x
   * @param {number} y
   * @returns {number} 0 or 1.
   */
  get(x, y) {
    if (x < 0 || x >= this.width || y < 0 || y >= this.height) return 0;
    return this.data[y * this.width + x];
  }

  /**
   * Set the collision value at (x, y).
   * @param {number} x
   * @param {number} y
   * @param {number} value 0 or 1.
   */
  set(x, y, value) {
    if (x < 0 || x >= this.width || y < 0 || y >= this.height) return;
    this.data[y * this.width + x] = value ? 1 : 0;
  }

  /**
   * Toggle the collision value at (x, y).
   * @param {number} x
   * @param {number} y
   */
  toggle(x, y) {
    this.set(x, y, this.get(x, y) ? 0 : 1);
  }

  /**
   * Resize the collision layer, preserving existing data.
   * @param {number} newWidth
   * @param {number} newHeight
   */
  resize(newWidth, newHeight) {
    const newData = new Uint8Array(newWidth * newHeight);
    const copyW = Math.min(this.width, newWidth);
    const copyH = Math.min(this.height, newHeight);
    for (let y = 0; y < copyH; y++) {
      for (let x = 0; x < copyW; x++) {
        newData[y * newWidth + x] = this.data[y * this.width + x];
      }
    }
    this.data = newData;
    this.width = newWidth;
    this.height = newHeight;
  }

  /**
   * Serialize to plain array.
   * @returns {number[][]} 2D array [row][col].
   */
  toJSON() {
    const rows = [];
    for (let y = 0; y < this.height; y++) {
      const row = [];
      for (let x = 0; x < this.width; x++) {
        row.push(this.data[y * this.width + x]);
      }
      rows.push(row);
    }
    return rows;
  }

  /**
   * Deserialize from a 2D array.
   * @param {number[][]} rows
   * @param {number} width
   * @param {number} height
   * @returns {CollisionLayer}
   */
  static fromJSON(rows, width, height) {
    const layer = new CollisionLayer(width, height);
    for (let y = 0; y < Math.min(rows.length, height); y++) {
      const row = rows[y];
      for (let x = 0; x < Math.min(row.length, width); x++) {
        layer.data[y * width + x] = row[x] ? 1 : 0;
      }
    }
    return layer;
  }
}

window.CollisionLayer = CollisionLayer;

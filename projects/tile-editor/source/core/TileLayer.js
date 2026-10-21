'use strict';

/**
 * A single tile layer in the map.
 * Each cell stores a tile ID (index into the tileset), or -1 for empty.
 */
class TileLayer {
  /**
   * @param {string} name   - Human-readable layer name.
   * @param {number} width  - Map width in tiles.
   * @param {number} height - Map height in tiles.
   */
  constructor(name, width, height) {
    /** @type {string} */
    this.name = name;
    /** @type {number} */
    this.width = width;
    /** @type {number} */
    this.height = height;
    /** @type {boolean} */
    this.visible = true;
    /** @type {number} 0.0–1.0 */
    this.opacity = 1.0;
    /** @type {Int16Array} Flat row-major array; -1 = empty */
    this.data = new Int16Array(width * height).fill(-1);
  }

  /**
   * Get the tile ID at (x, y).
   * @param {number} x
   * @param {number} y
   * @returns {number} Tile ID or -1.
   */
  get(x, y) {
    if (x < 0 || x >= this.width || y < 0 || y >= this.height) return -1;
    return this.data[y * this.width + x];
  }

  /**
   * Set the tile ID at (x, y).
   * @param {number} x
   * @param {number} y
   * @param {number} id
   */
  set(x, y, id) {
    if (x < 0 || x >= this.width || y < 0 || y >= this.height) return;
    this.data[y * this.width + x] = id;
  }

  /**
   * Clear the tile at (x, y) by setting it to -1.
   * @param {number} x
   * @param {number} y
   */
  clear(x, y) {
    this.set(x, y, -1);
  }

  /**
   * Resize the layer, preserving existing tile data where possible.
   * New cells are filled with -1.
   * @param {number} newWidth
   * @param {number} newHeight
   */
  resize(newWidth, newHeight) {
    const newData = new Int16Array(newWidth * newHeight).fill(-1);
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
   * Serialize this layer to a plain object.
   * data is exported as a 2D array (one inner array per row) so the
   * exported JSON visually mirrors the actual map shape.
   * @returns {{ name: string, visible: boolean, opacity: number, data: number[][] }}
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
    return {
      name: this.name,
      visible: this.visible,
      opacity: this.opacity,
      data: rows
    };
  }

  /**
   * Deserialize a layer from a plain object.
   * Accepts both the new 2D row format and the legacy flat 1D format.
   * @param {object} json
   * @param {number} width
   * @param {number} height
   * @returns {TileLayer}
   */
  static fromJSON(json, width, height) {
    const layer = new TileLayer(json.name, width, height);
    layer.visible = json.visible !== undefined ? json.visible : true;
    layer.opacity = json.opacity !== undefined ? json.opacity : 1.0;
    if (json.data) {
      if (Array.isArray(json.data[0])) {
        // New 2D row format — flatten to a single Int16Array
        const flat = json.data.flat();
        if (flat.length === width * height) {
          layer.data = new Int16Array(flat);
        }
      } else if (json.data.length === width * height) {
        // Legacy flat 1D format
        layer.data = new Int16Array(json.data);
      }
    }
    return layer;
  }
}

// Global export for script-tag loading
window.TileLayer = TileLayer;

'use strict';

/**
 * The central data model for a tile map.
 * Owns layers, collision data, and placed objects.
 */
class TileMap {
  /**
   * @param {number} width    - Map width in tiles.
   * @param {number} height   - Map height in tiles.
   * @param {number} tileSize - Tile size in pixels (default 16).
   */
  constructor(width, height, tileSize = 16) {
    /** @type {number} */
    this.width = width;
    /** @type {number} */
    this.height = height;
    /** @type {number} */
    this.tileSize = tileSize;
    /** @type {string} Tileset filename/path */
    this.tilesetPath = '';
    /** @type {string} Map name */
    this.name = 'Untitled Map';

    /** @type {TileLayer[]} */
    this.layers = [];

    /** @type {CollisionLayer} */
    this.collision = new CollisionLayer(width, height);

    /** @type {ObjectLayer} */
    this.objectLayer = new ObjectLayer();

    // Create default layers
    this.addLayer('Ground');
    this.addLayer('Decorations');
    this.addLayer('Top');
  }

  // ---- Layer management ----

  /**
   * Add a new layer with the given name.
   * @param {string} name
   * @returns {TileLayer}
   */
  addLayer(name) {
    const layer = new TileLayer(name, this.width, this.height);
    this.layers.push(layer);
    return layer;
  }

  /**
   * Remove the layer at the given index.
   * @param {number} index
   */
  removeLayer(index) {
    if (this.layers.length <= 1) return; // Keep at least one layer
    this.layers.splice(index, 1);
  }

  /**
   * Move a layer from one index to another.
   * @param {number} from
   * @param {number} to
   */
  moveLayer(from, to) {
    if (from < 0 || from >= this.layers.length) return;
    if (to < 0 || to >= this.layers.length) return;
    const [layer] = this.layers.splice(from, 1);
    this.layers.splice(to, 0, layer);
  }

  // ---- Tile access ----

  /**
   * Set a tile on a layer.
   * @param {number} layerIndex
   * @param {number} x
   * @param {number} y
   * @param {number} tileId
   */
  setTile(layerIndex, x, y, tileId) {
    if (layerIndex < 0 || layerIndex >= this.layers.length) return;
    this.layers[layerIndex].set(x, y, tileId);
  }

  /**
   * Get a tile from a layer.
   * @param {number} layerIndex
   * @param {number} x
   * @param {number} y
   * @returns {number}
   */
  getTile(layerIndex, x, y) {
    if (layerIndex < 0 || layerIndex >= this.layers.length) return -1;
    return this.layers[layerIndex].get(x, y);
  }

  // ---- Collision access ----

  /**
   * Set collision value at (x, y).
   * @param {number} x
   * @param {number} y
   * @param {number} value 0 or 1.
   */
  setCollision(x, y, value) {
    this.collision.set(x, y, value);
  }

  /**
   * Get collision value at (x, y).
   * @param {number} x
   * @param {number} y
   * @returns {number}
   */
  getCollision(x, y) {
    return this.collision.get(x, y);
  }

  // ---- Resize ----

  /**
   * Resize the map, preserving existing tile and collision data.
   * @param {number} newWidth
   * @param {number} newHeight
   */
  resize(newWidth, newHeight) {
    if (newWidth < 1 || newHeight < 1) return;
    for (const layer of this.layers) {
      layer.resize(newWidth, newHeight);
    }
    this.collision.resize(newWidth, newHeight);
    this.width = newWidth;
    this.height = newHeight;
  }

  // ---- Serialization ----

  /**
   * Serialize the entire map to a plain object (JSON-safe).
   * @returns {object}
   */
  toJSON() {
    return {
      name: this.name,
      width: this.width,
      height: this.height,
      tileSize: this.tileSize,
      tileset: this.tilesetPath,
      layers: this.layers.map(l => l.toJSON()),
      collision: this.collision.toJSON(),
      objects: this.objectLayer.toJSON()
    };
  }

  /**
   * Deserialize a TileMap from a plain object.
   * @param {object} data
   * @returns {TileMap}
   */
  static fromJSON(data) {
    const map = new TileMap(data.width, data.height, data.tileSize || 16);
    map.name = data.name || 'Untitled Map';
    map.tilesetPath = data.tileset || '';

    // Replace default layers with serialized ones
    map.layers = [];
    if (data.layers && data.layers.length > 0) {
      for (const layerData of data.layers) {
        map.layers.push(TileLayer.fromJSON(layerData, data.width, data.height));
      }
    } else {
      map.addLayer('Ground');
    }

    if (data.collision) {
      map.collision = CollisionLayer.fromJSON(data.collision, data.width, data.height);
    }

    if (data.objects && data.objects.length > 0) {
      map.objectLayer = ObjectLayer.fromJSON(data.objects);
    }

    return map;
  }
}

window.TileMap = TileMap;

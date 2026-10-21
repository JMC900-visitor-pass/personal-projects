'use strict';

/**
 * Manages placed map objects (NPCs, doors, chests, etc.).
 * Objects are stored in a Map keyed by auto-incremented integer ID.
 */
class ObjectLayer {
  constructor() {
    /** @type {Map<number, MapObject>} */
    this.objects = new Map();
    /** @type {number} */
    this._nextId = 1;
  }

  /**
   * Add a new object to the layer.
   * @param {string} type  - Object type: 'npc' | 'chest' | 'door' | 'teleporter' | 'sign'
   * @param {number} x     - Tile column.
   * @param {number} y     - Tile row.
   * @param {object} [props={}] - Custom properties.
   * @returns {MapObject} The newly created object.
   */
  add(type, x, y, props = {}) {
    const id = this._nextId++;
    const obj = { id, type, x, y, properties: Object.assign({}, props) };
    this.objects.set(id, obj);
    return obj;
  }

  /**
   * Remove an object by ID.
   * @param {number} id
   */
  remove(id) {
    this.objects.delete(id);
  }

  /**
   * Get an object by ID.
   * @param {number} id
   * @returns {MapObject|undefined}
   */
  get(id) {
    return this.objects.get(id);
  }

  /**
   * Get the first object at tile coordinates (x, y).
   * @param {number} x
   * @param {number} y
   * @returns {MapObject|undefined}
   */
  getAt(x, y) {
    for (const obj of this.objects.values()) {
      if (obj.x === x && obj.y === y) return obj;
    }
    return undefined;
  }

  /**
   * Return all objects as an array.
   * @returns {MapObject[]}
   */
  getAll() {
    return Array.from(this.objects.values());
  }

  /**
   * Update a property on an object.
   * @param {number} id
   * @param {string} key
   * @param {*} value
   */
  setProperty(id, key, value) {
    const obj = this.objects.get(id);
    if (obj) obj.properties[key] = value;
  }

  /**
   * Remove a property from an object.
   * @param {number} id
   * @param {string} key
   */
  removeProperty(id, key) {
    const obj = this.objects.get(id);
    if (obj) delete obj.properties[key];
  }

  /**
   * Serialize to array of plain objects.
   * @returns {object[]}
   */
  toJSON() {
    return this.getAll();
  }

  /**
   * Deserialize from array of plain objects.
   * @param {object[]} arr
   * @returns {ObjectLayer}
   */
  static fromJSON(arr) {
    const layer = new ObjectLayer();
    let maxId = 0;
    for (const item of arr) {
      const obj = {
        id: item.id,
        type: item.type,
        x: item.x,
        y: item.y,
        properties: Object.assign({}, item.properties || {})
      };
      layer.objects.set(obj.id, obj);
      if (obj.id >= maxId) maxId = obj.id;
    }
    layer._nextId = maxId + 1;
    return layer;
  }
}

window.ObjectLayer = ObjectLayer;

'use strict';

/**
 * MapExporter — handles serialization and deserialization of TileMap data
 * to/from JSON strings.
 */
class MapExporter {
  /**
   * Serialize a TileMap to a formatted JSON string.
   * @param {TileMap} tileMap
   * @param {string} [tilesetPath=''] - Override tileset path in the output.
   * @returns {string}
   */
  static exportToJSON(tileMap, tilesetPath) {
    const data = tileMap.toJSON();
    if (tilesetPath !== undefined) data.tileset = tilesetPath;

    // Produce pretty-printed JSON, then collapse arrays that contain only
    // numbers onto a single line so layer rows and collision rows are
    // human-readable as actual map shapes.
    const raw = JSON.stringify(data, null, 2);
    return raw.replace(/\[\n([ \t]+-?\d+,?\n)+[ \t]+\]/g, (match) => {
      const nums = match.match(/-?\d+/g);
      return '[' + nums.join(', ') + ']';
    });
  }

  /**
   * Deserialize a JSON string to a TileMap instance.
   * @param {string} jsonString
   * @returns {TileMap}
   */
  static importFromJSON(jsonString) {
    let data;
    try {
      data = JSON.parse(jsonString);
    } catch (e) {
      throw new Error('Invalid JSON: ' + e.message);
    }

    if (!data.width || !data.height) {
      throw new Error('Map JSON missing width/height fields.');
    }

    return TileMap.fromJSON(data);
  }

  /**
   * Get the tileset path from a JSON string without fully parsing the map.
   * @param {string} jsonString
   * @returns {string}
   */
  static getTilesetPath(jsonString) {
    try {
      const data = JSON.parse(jsonString);
      return data.tileset || '';
    } catch (e) {
      return '';
    }
  }
}

window.MapExporter = MapExporter;

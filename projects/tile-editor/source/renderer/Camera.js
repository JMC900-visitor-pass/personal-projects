'use strict';

/**
 * Camera — manages pan and zoom for the map viewport.
 * Coordinates: camera.x/y are the world-space position of the top-left corner
 * of the visible area (in pixels, before zoom).
 */
class Camera {
  /**
   * @param {number} [x=0]    - Initial world X offset.
   * @param {number} [y=0]    - Initial world Y offset.
   * @param {number} [zoom=1] - Initial zoom factor.
   */
  constructor(x = 0, y = 0, zoom = 1) {
    /** @type {number} */
    this.x = x;
    /** @type {number} */
    this.y = y;
    /** @type {number} */
    this.zoom = zoom;

    /** @type {number} Minimum zoom */
    this.minZoom = 0.25;
    /** @type {number} Maximum zoom */
    this.maxZoom = 8;
  }

  /**
   * Pan the camera by (dx, dy) in screen pixels.
   * @param {number} dx
   * @param {number} dy
   */
  pan(dx, dy) {
    this.x -= dx / this.zoom;
    this.y -= dy / this.zoom;
  }

  /**
   * Zoom toward a point on screen.
   * @param {number} factor     - Multiplicative zoom factor (e.g. 1.1 to zoom in).
   * @param {number} screenX    - Screen X coordinate to zoom toward.
   * @param {number} screenY    - Screen Y coordinate to zoom toward.
   */
  zoomAt(factor, screenX, screenY) {
    const newZoom = Math.max(this.minZoom, Math.min(this.maxZoom, this.zoom * factor));
    if (newZoom === this.zoom) return;

    // Convert screen point to world before zoom change
    const worldX = this.screenToWorldX(screenX);
    const worldY = this.screenToWorldY(screenY);

    this.zoom = newZoom;

    // Adjust pan so the world point stays under the mouse
    this.x = worldX - screenX / this.zoom;
    this.y = worldY - screenY / this.zoom;
  }

  /**
   * Set zoom to an exact value, centering on canvas center.
   * @param {number} zoom
   * @param {number} canvasW
   * @param {number} canvasH
   */
  setZoom(zoom, canvasW, canvasH) {
    this.zoomAt(zoom / this.zoom, canvasW / 2, canvasH / 2);
  }

  /**
   * Convert a world X coordinate to a screen X coordinate.
   * @param {number} worldX
   * @returns {number}
   */
  worldToScreenX(worldX) {
    return (worldX - this.x) * this.zoom;
  }

  /**
   * Convert a world Y coordinate to a screen Y coordinate.
   * @param {number} worldY
   * @returns {number}
   */
  worldToScreenY(worldY) {
    return (worldY - this.y) * this.zoom;
  }

  /**
   * Convert screen coordinates to world coordinates.
   * @param {number} sx
   * @param {number} sy
   * @returns {{x: number, y: number}}
   */
  screenToWorld(sx, sy) {
    return {
      x: this.screenToWorldX(sx),
      y: this.screenToWorldY(sy)
    };
  }

  /**
   * Convert world coordinates to screen coordinates.
   * @param {number} wx
   * @param {number} wy
   * @returns {{x: number, y: number}}
   */
  worldToScreen(wx, wy) {
    return {
      x: this.worldToScreenX(wx),
      y: this.worldToScreenY(wy)
    };
  }

  /** @param {number} sx @returns {number} */
  screenToWorldX(sx) {
    return sx / this.zoom + this.x;
  }

  /** @param {number} sy @returns {number} */
  screenToWorldY(sy) {
    return sy / this.zoom + this.y;
  }

  /**
   * Convert a screen position to tile grid coordinates.
   * @param {number} sx
   * @param {number} sy
   * @param {number} tileSize
   * @returns {{tx: number, ty: number}}
   */
  screenToTile(sx, sy, tileSize) {
    const wx = this.screenToWorldX(sx);
    const wy = this.screenToWorldY(sy);
    return {
      tx: Math.floor(wx / tileSize),
      ty: Math.floor(wy / tileSize)
    };
  }

  /**
   * Get the range of tile coordinates currently visible.
   * @param {number} canvasW
   * @param {number} canvasH
   * @param {number} tileSize
   * @returns {{ minX: number, minY: number, maxX: number, maxY: number }}
   */
  getVisibleTileBounds(canvasW, canvasH, tileSize) {
    const topLeft = this.screenToTile(0, 0, tileSize);
    const botRight = this.screenToTile(canvasW, canvasH, tileSize);
    return {
      minX: topLeft.tx - 1,
      minY: topLeft.ty - 1,
      maxX: botRight.tx + 1,
      maxY: botRight.ty + 1
    };
  }

  /**
   * Clamp the camera so it doesn't scroll too far outside the map.
   * @param {number} mapPixelW  - Total map width in pixels.
   * @param {number} mapPixelH  - Total map height in pixels.
   * @param {number} canvasW
   * @param {number} canvasH
   */
  clampToBounds(mapPixelW, mapPixelH, canvasW, canvasH) {
    const visW = canvasW / this.zoom;
    const visH = canvasH / this.zoom;
    const margin = 200; // Allow some overdraw
    this.x = Math.max(-margin, Math.min(this.x, mapPixelW - visW + margin));
    this.y = Math.max(-margin, Math.min(this.y, mapPixelH - visH + margin));
  }
}

window.Camera = Camera;

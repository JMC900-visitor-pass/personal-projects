import Phaser from 'phaser';

export interface MapLayer {
  name: string;
  visible: boolean;
  opacity: number;
  data: number[][];
}

export interface MapData {
  name: string;
  width: number;
  height: number;
  tileSize: number;
  tileset: string;
  layers: MapLayer[];
  collision: number[][];
  objects: any[];
}

export interface RenderedMap {
  width: number;
  height: number;
  tileSize: number;
  collision: number[][];
}

const LAYER_DEPTH: Record<string, number> = {
  Ground: 0,
  Decorations: 2,
  Top: 50,   // above player (depth 10) so "roof" tiles draw over the player
};

/**
 * Convert a dotted map key into a folder path + file name.
 *
 * 'home'       → { folderPath: 'home',      fileName: 'home' }
 * 'home.wild'  → { folderPath: 'home/wild', fileName: 'wild' }
 * 'home.cave.deep' → { folderPath: 'home/cave/deep', fileName: 'deep' }
 */
function keyToPath(mapKey: string): { folderPath: string; fileName: string } {
  const parts = mapKey.split('.');
  return {
    folderPath: parts.join('/'),
    fileName:   parts[parts.length - 1],
  };
}

/**
 * Queue map assets for loading. Call from scene preload().
 * Assets are cached so repeated calls on scene restart are instant.
 *
 * mapKey supports dot notation for subfolders:
 *   'home'      → assets/maps/home/home.json  +  home.png
 *   'home.wild' → assets/maps/home/wild/wild.json  +  wild.png
 *
 * Tileset convention: <mapname>.png lives in the same folder as the JSON.
 */
export function preloadMap(scene: Phaser.Scene, mapKey: string): void {
  const { folderPath, fileName } = keyToPath(mapKey);
  scene.load.json(`map_${mapKey}`, `assets/maps/${folderPath}/${fileName}.json`);
  scene.load.image(`tileset_${mapKey}`, `assets/maps/${folderPath}/${fileName}.png`);
}

/**
 * Render a cached map into the scene. Call from scene create().
 * Returns map metadata (dimensions + collision grid), or null if the
 * map data wasn't loaded (e.g. no export exists yet — caller should
 * fall back to procedural rendering).
 *
 * Tile indices in the export format are 0-based with -1 = empty.
 * Phaser's addTilesetImage gid is set to 0 so indices match directly.
 */
export function renderMap(scene: Phaser.Scene, mapKey: string): RenderedMap | null {
  const mapData: MapData | null = scene.cache.json.get(`map_${mapKey}`);
  if (!mapData) return null;

  const tilesetKey = `tileset_${mapKey}`;
  if (!scene.textures.exists(tilesetKey)) return null;

  for (const layer of mapData.layers) {
    if (!layer.visible) continue;

    const tilemap = scene.make.tilemap({
      data: layer.data,
      tileWidth: mapData.tileSize,
      tileHeight: mapData.tileSize,
      width: mapData.width,
      height: mapData.height,
    });

    // gid=0 → our 0-based tile indices map 1-to-1 to tileset positions.
    // -1 in the data array is Phaser's built-in "empty tile" sentinel.
    const tileset = tilemap.addTilesetImage(
      tilesetKey, tilesetKey,
      mapData.tileSize, mapData.tileSize,
      0, 0, // margin, spacing
      0,    // firstgid = 0 (0-based format)
    );
    if (!tileset) continue;

    const tileLayer = tilemap.createLayer(0, tileset, 0, 0);
    if (!tileLayer) continue;

    tileLayer.setAlpha(layer.opacity);
    tileLayer.setDepth(LAYER_DEPTH[layer.name] ?? 1);
  }

  return {
    width: mapData.width,
    height: mapData.height,
    tileSize: mapData.tileSize,
    collision: mapData.collision,
  };
}

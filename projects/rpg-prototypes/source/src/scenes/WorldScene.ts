import Phaser from 'phaser';
import { State, GameState } from '../core/State';
import { preloadMap, renderMap } from '../systems/MapLoader';
import { txt } from '../core/TextStyle';

// Encounter rate: chance per step on grass tiles
const ENCOUNTER_RATE = 0.125;
const ENCOUNTER_STEP_MIN = 4;

/**
 * Overworld / exploration scene.
 *
 * Movement: WASD only, strict 4-way (no diagonal).
 *   - Velocity-based movement with 4-directional facing.
 *   - Tab / left-click on non-interactive area → open MenuScene overlay.
 *
 * Falls back to procedural coloured-rectangle tilemap if no map JSON is found.
 */
export default class WorldScene extends Phaser.Scene {
  // ── Sprites ────────────────────────────────────────────────────────────────
  private player!: Phaser.GameObjects.Rectangle;

  // ── Input ─────────────────────────────────────────────────────────────────
  private keyW!: Phaser.Input.Keyboard.Key;
  private keyA!: Phaser.Input.Keyboard.Key;
  private keyS!: Phaser.Input.Keyboard.Key;
  private keyD!: Phaser.Input.Keyboard.Key;
  private keyTab!: Phaser.Input.Keyboard.Key;
  private keyK!: Phaser.Input.Keyboard.Key;
  // Track which of WASD was pressed most recently for single-axis priority
  private lastHorizontal: 'a' | 'd' | null = null;
  private lastVertical:   'w' | 's' | null = null;
  private lastAxisTime: { h: number; v: number } = { h: 0, v: 0 };

  // ── Encounter ──────────────────────────────────────────────────────────────
  private stepCounter: number = 0;
  private inEncounterZone: boolean = false;
  private encounterCooldown: boolean = false;

  // ── Auto-save tracking ─────────────────────────────────────────────────────
  private lastSaveTime: number = 0;

  // ── Map / world data ───────────────────────────────────────────────────────
  private SPEED = 60;        // pixels/sec in 320×180 space
  private TILE  = 16;        // tile size in virtual pixels
  private MAP_W = 20;        // tiles wide  (overridden by loaded map)
  private MAP_H = 11;        // tiles tall  (overridden by loaded map)

  // Collision grid from the tile-editor export (1=solid, 0=walkable).
  // When set, getTileType() uses this instead of the procedural tileMap.
  private collisionData: number[][] | null = null;

  // Procedural fallback layout: 0=path, 1=grass (encounter), 2=wall
  private tileMap: number[][] = [];
  private worldWidth!: number;
  private worldHeight!: number;

  // ── NPCs ───────────────────────────────────────────────────────────────────
  private npcRects: Phaser.GameObjects.Rectangle[] = [];
  private npcDefs: any[] = [];
  private keyInteract!: Phaser.Input.Keyboard.Key;

  // ── Door / warp zones ──────────────────────────────────────────────────────
  private doorZones: Array<{ x: number; y: number; w: number; h: number; targetMap: string; targetX: number; targetY: number }> = [];

  // ── Pause flag (set while menu/battle scene is active) ────────────────────
  private paused: boolean = false;

  constructor() {
    super({ key: State.OVERWORLD });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Lifecycle
  // ──────────────────────────────────────────────────────────────────────────

  preload() {
    // Load the current map's JSON + tileset from the external Maps folder.
    // Phaser caches assets so restarting the scene (map warp) is instant.
    preloadMap(this, GameState.currentMap);
  }

  create() {
    GameState.ensureDefaultParty();
    this.paused = false;
    this.collisionData = null;

    // Try to render the tile-editor map; fall back to procedural if absent.
    const rendered = renderMap(this, GameState.currentMap);
    if (rendered) {
      this.TILE          = rendered.tileSize;
      this.MAP_W         = rendered.width;
      this.MAP_H         = rendered.height;
      this.collisionData = rendered.collision;
    }

    this.worldWidth  = this.MAP_W * this.TILE;
    this.worldHeight = this.MAP_H * this.TILE;

    this.tileMap = this.buildTileMap();         // procedural fallback data
    if (!rendered) this.renderProceduralMap();  // only draw rectangles when no real map

    this.createPlayer();
    this.setupInput();
    this.setupCamera();
    this.addHUD();
    this.spawnNPCs();
    this.setupDoors();

    // Listen for menu closure
    this.scene.get(State.MENU)?.events.on('menu-closed', this.onMenuClosed, this);

      // (No world click handler — mouse only supported on main menu)
  }

  update(_time: number, delta: number) {
    if (this.paused) return;
    this.handleMovement(delta);
    this.checkEncounterZone();
    this.checkDoors();
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Procedural map (placeholder — replace with Tiled JSON when ready)
  // ──────────────────────────────────────────────────────────────────────────

  private buildTileMap(): number[][] {
    const map: number[][] = [];
    for (let row = 0; row < this.MAP_H; row++) {
      map[row] = [];
      for (let col = 0; col < this.MAP_W; col++) {
        // Border = wall
        if (row === 0 || row === this.MAP_H - 1 || col === 0 || col === this.MAP_W - 1) {
          map[row][col] = 2;
        }
        // A rectangular "town" in the middle = path
        else if (row >= 3 && row <= 7 && col >= 4 && col <= 15) {
          map[row][col] = 0;
        }
        // Remaining inner tiles = encounter grass
        else {
          map[row][col] = 1;
        }
      }
    }
    return map;
  }

  private renderProceduralMap() {
    const COLORS: Record<number, number> = {
      0: 0x4a7c59,  // path — medium green
      1: 0x2d5a1b,  // tall grass — dark green
      2: 0x555577,  // wall — blue-grey
    };

    for (let row = 0; row < this.MAP_H; row++) {
      for (let col = 0; col < this.MAP_W; col++) {
        const type = this.tileMap[row][col];
        const color = COLORS[type] ?? 0x000000;
        const rect = this.add.rectangle(
          col * this.TILE + this.TILE / 2,
          row * this.TILE + this.TILE / 2,
          this.TILE - 1, this.TILE - 1,
          color
        );
        rect.setDepth(0);

        // Highlight grass with a slightly lighter fleck
        if (type === 1) {
          this.add.rectangle(
            col * this.TILE + 3,
            row * this.TILE + 3,
            2, 2,
            0x5aaa30
          ).setDepth(1);
        }
      }
    }
  }

  private createPlayer() {
    const startX = GameState.playerX;
    const startY = GameState.playerY;

    // Coloured rectangle as player stand-in (replace with sprite when art exists)
    this.player = this.add.rectangle(startX, startY, 10, 12, 0xff4444);
    this.player.setDepth(10);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Input
  // ──────────────────────────────────────────────────────────────────────────

  private setupInput() {
    const kb = this.input.keyboard!;
    this.keyW   = kb.addKey(Phaser.Input.Keyboard.KeyCodes.W);
    this.keyA   = kb.addKey(Phaser.Input.Keyboard.KeyCodes.A);
    this.keyS   = kb.addKey(Phaser.Input.Keyboard.KeyCodes.S);
    this.keyD   = kb.addKey(Phaser.Input.Keyboard.KeyCodes.D);
    this.keyTab      = kb.addKey(Phaser.Input.Keyboard.KeyCodes.TAB);
    this.keyK        = kb.addKey(Phaser.Input.Keyboard.KeyCodes.K);
    this.keyInteract = this.keyK;

    // Track most-recently-pressed axis for single-axis priority
    this.keyA.on('down', () => { this.lastHorizontal = 'a'; this.lastAxisTime.h = this.time.now; });
    this.keyD.on('down', () => { this.lastHorizontal = 'd'; this.lastAxisTime.h = this.time.now; });
    this.keyW.on('down', () => { this.lastVertical   = 'w'; this.lastAxisTime.v = this.time.now; });
    this.keyS.on('down', () => { this.lastVertical   = 's'; this.lastAxisTime.v = this.time.now; });
    this.keyA.on('up',   () => { if (this.lastHorizontal === 'a') this.lastHorizontal = null; });
    this.keyD.on('up',   () => { if (this.lastHorizontal === 'd') this.lastHorizontal = null; });
    this.keyW.on('up',   () => { if (this.lastVertical   === 'w') this.lastVertical   = null; });
    this.keyS.on('up',   () => { if (this.lastVertical   === 's') this.lastVertical   = null; });
  }

  private handleMovement(delta: number) {
    const hDown = this.keyA.isDown || this.keyD.isDown;
    const vDown = this.keyW.isDown || this.keyS.isDown;

    let vx = 0;
    let vy = 0;

    // Single-axis priority: whichever axis was pressed most recently wins
    if (hDown && vDown) {
      if (this.lastAxisTime.h >= this.lastAxisTime.v) {
        // horizontal axis wins
        vx = this.lastHorizontal === 'a' ? -1 : 1;
      } else {
        vy = this.lastVertical   === 'w' ? -1 : 1;
      }
    } else if (hDown) {
      vx = (this.lastHorizontal === 'a' || this.keyA.isDown) && !this.keyD.isDown ? -1 : 1;
    } else if (vDown) {
      vy = (this.lastVertical   === 'w' || this.keyW.isDown) && !this.keyS.isDown ? -1 : 1;
    }

    const speed = this.SPEED * (delta / 1000);
    let nx = this.player.x + vx * speed;
    let ny = this.player.y + vy * speed;

    // World bounds clamp
    const hw = this.player.width  / 2;
    const hh = this.player.height / 2;
    nx = Phaser.Math.Clamp(nx, this.TILE + hw, this.worldWidth  - this.TILE - hw);
    ny = Phaser.Math.Clamp(ny, this.TILE + hh, this.worldHeight - this.TILE - hh);

    // Tile-based wall collision (check the tile the player centre lands in)
    const tileCol = Math.floor(nx / this.TILE);
    const tileRow = Math.floor(ny / this.TILE);
    if (this.getTileType(tileCol, tileRow) !== 2) {
      this.player.setPosition(nx, ny);

      // Count a "step" once per ~tile traversal (simple frame counting below)
      if (vx !== 0 || vy !== 0) {
        this.stepCounter += speed;
        if (this.stepCounter >= this.TILE) {
          this.stepCounter -= this.TILE;
          this.onStep();
        }
      }
    }

    // Save player position every second
    GameState.playerX = this.player.x;
    GameState.playerY = this.player.y;

    // Tab → open settings
    if (Phaser.Input.Keyboard.JustDown(this.keyTab)) {
      this.openSettings();
    }

    // K → interact with nearby NPC
    if (Phaser.Input.Keyboard.JustDown(this.keyInteract)) {
      this.checkNPCInteract();
    }
  }

  private getTileType(col: number, row: number): number {
    if (row < 0 || row >= this.MAP_H || col < 0 || col >= this.MAP_W) return 2;
    if (this.collisionData) {
      // collision export: 1=solid→wall(2), 0=walkable→path(0)
      return (this.collisionData[row]?.[col] ?? 0) === 1 ? 2 : 0;
    }
    return this.tileMap[row][col];
  }

  // ──────────────────────────────────────────────────────────────────────────
  // NPC system
  // ──────────────────────────────────────────────────────────────────────────

  private spawnNPCs() {
    const raw = this.cache.json.get('npcs');
    if (!raw) return;

    const defs: any[] = Array.isArray(raw) ? raw : (Array.isArray(raw.npcs) ? raw.npcs : []);

    for (const npc of defs) {
      const rect = this.add.rectangle(npc.x, npc.y, 10, 14, 0x4488ff).setDepth(5);
      this.npcRects.push(rect);
      this.npcDefs.push(npc);

      // First letter of name as a floating label
      this.add.text(
        npc.x - 4,
        npc.y - 10,
        npc.name[0],
        txt({ fontSize: '5px', color: '#ffffff' })
      ).setDepth(6);
    }
  }

  private checkNPCInteract() {
    for (let i = 0; i < this.npcRects.length; i++) {
      const dist = Phaser.Math.Distance.Between(
        this.player.x, this.player.y,
        this.npcRects[i].x, this.npcRects[i].y
      );
      if (dist < 20) {
        this.triggerNPCDialog(this.npcDefs[i]);
        return;
      }
    }
  }

  private triggerNPCDialog(npc: any) {
    if (this.paused) return;
    this.paused = true;

    const dialogText = `${npc.name}: ${npc.dialog[0]}`;

    // Dialog box — fixed to camera via setScrollFactor(0)
    const box = this.add.rectangle(160, 162, 300, 24, 0x000000, 0.85)
      .setScrollFactor(0)
      .setDepth(200);

    const label = this.add.text(160, 162, dialogText, txt({
      fontSize: '5px',
      color: '#ffffff',
      wordWrap: { width: 290 },
    }))
      .setOrigin(0.5)
      .setScrollFactor(0)
      .setDepth(201);

    // Auto-dismiss after 2 seconds
    this.time.delayedCall(2000, () => {
      box.destroy();
      label.destroy();
      this.paused = false;
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Door / warp zone system
  // ──────────────────────────────────────────────────────────────────────────

  private setupDoors() {
    // Add door zones here, e.g.:
    // this.doorZones.push({ x: 160, y: 8, w: 16, h: 8, targetMap: 'town', targetX: 160, targetY: 150 });

    for (const door of this.doorZones) {
      // Visual indicator
      this.add.rectangle(door.x, door.y, door.w, door.h, 0xffdd44, 0.7).setDepth(3);

      // Up-arrow label
      this.add.text(door.x, door.y - 6, '▲', txt({
        fontSize: '5px',
        color: '#ffdd44',
      })).setOrigin(0.5).setDepth(4);
    }
  }

  private checkDoors() {
    const px = this.player.x;
    const py = this.player.y;

    for (const door of this.doorZones) {
      const halfW = door.w / 2;
      const halfH = door.h / 2;
      if (px >= door.x - halfW && px <= door.x + halfW &&
          py >= door.y - halfH && py <= door.y + halfH) {
        this.paused = true;
        GameState.save(this.player.x, this.player.y);
        GameState.currentMap = door.targetMap;
        GameState.playerX    = door.targetX;
        GameState.playerY    = door.targetY;

        this.cameras.main.fadeOut(300, 0, 0, 0);
        this.time.delayedCall(350, () => {
          this.scene.restart();
        });
        return;
      }
    }
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Encounter system
  // ──────────────────────────────────────────────────────────────────────────

  private checkEncounterZone() {
    const col = Math.floor(this.player.x / this.TILE);
    const row = Math.floor(this.player.y / this.TILE);
    this.inEncounterZone = this.getTileType(col, row) === 1;
  }

  private onStep() {
    if (!this.inEncounterZone || this.encounterCooldown) return;
    if (Math.random() < ENCOUNTER_RATE) {
      this.triggerEncounter();
    }
  }

  private triggerEncounter() {
    this.encounterCooldown = true;
    // Auto-save before battle
    GameState.save(this.player.x, this.player.y);

    // Brief flash then transition
    this.cameras.main.flash(200, 255, 255, 255, true);
    this.time.delayedCall(220, () => {
      this.paused = true;
      this.scene.start(State.BATTLE, {
        party: GameState.party,
        returnScene: State.OVERWORLD,
        encounterType: 'grass',
      });
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Camera
  // ──────────────────────────────────────────────────────────────────────────

  private setupCamera() {
    const cam   = this.cameras.main;
    const viewW = cam.width;   // 320
    const viewH = cam.height;  // 180

    const fitsW = this.worldWidth  <= viewW;
    const fitsH = this.worldHeight <= viewH;

    if (fitsW && fitsH) {
      // Map smaller than viewport — center it, no follow needed
      cam.setScroll(
        (this.worldWidth  - viewW) / 2,
        (this.worldHeight - viewH) / 2,
      );
      return;
    }

    // Map overflows at least one axis — follow player within bounds
    cam.setBounds(0, 0, this.worldWidth, this.worldHeight);
    cam.startFollow(this.player, true, 0.1, 0.1);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // HUD
  // ──────────────────────────────────────────────────────────────────────────

  private hudHP!: Phaser.GameObjects.Text;
  private hudGold!: Phaser.GameObjects.Text;

  private addHUD() {
    // HUD is fixed to camera so we use setScrollFactor(0)
    this.hudHP = this.add.text(4, 4, '', txt({
      fontSize: '5px',
      color: '#ffffff',
      backgroundColor: '#00000088',
      padding: { x: 2, y: 1 },
    })).setScrollFactor(0).setDepth(100);

    this.hudGold = this.add.text(4, 14, '', txt({
      fontSize: '5px',
      color: '#ffee44',
      backgroundColor: '#00000088',
      padding: { x: 2, y: 1 },
    })).setScrollFactor(0).setDepth(100);

    this.events.on('postupdate', this.refreshHUD, this);
  }

  private refreshHUD() {
    const hero = GameState.party[0];
    if (hero) {
      this.hudHP.setText(`HP ${hero.currentHP}/${hero.maxHP}`);
    }
    this.hudGold.setText(`G ${GameState.gold}`);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Menu
  // ──────────────────────────────────────────────────────────────────────────

  private openSettings() {
    this.paused = true;
    GameState.save(this.player.x, this.player.y);
    this.scene.start(State.SETTINGS, { from: State.OVERWORLD });
  }

  onMenuClosed() {
    this.paused = false;
    this.encounterCooldown = false;
  }

  // Called when returning from BattleScene
  onBattleReturn() {
    this.paused = false;
    this.encounterCooldown = false;
    this.cameras.main.fadeIn(300);
  }
}

import { Character } from '../entities/Character';

/**
 * Scene key constants — every scene is registered under one of these keys.
 */
export enum State {
  BOOT      = 'BOOT',
  LOADING   = 'LOADING',
  TITLE     = 'TITLE',
  OVERWORLD = 'OVERWORLD',
  BATTLE    = 'BATTLE',
  MENU      = 'MENU',
  SETTINGS  = 'SETTINGS',
}

// ─── Save data shape ──────────────────────────────────────────────────────────

export interface SaveData {
  playerX: number;
  playerY: number;
  mapKey: string;
  partyStats: Array<{
    id: string;
    name: string;
    maxHP: number;
    currentHP: number;
    maxMP: number;
    currentMP: number;
    atk: number;
    def: number;
    spd: number;
    spAtk: number;
    spDef: number;
    sprite: string;
    frames: number[];
    level: number;
    xp: number;
  }>;
  inventory: Record<string, number>;
  gold: number;
  playtime: number;
}

const SAVE_KEY     = 'realmchips_save';
const SETTINGS_KEY = 'realmchips_settings';

export interface GameSettings {
  soundEnabled: boolean;
  zoom: number; // 1 | 2 | 3 | 4
}

// ─── Persistent cross-scene game state ───────────────────────────────────────

export class GameState {
  private static _party: Character[] = [];
  private static _gold: number = 0;
  private static _inventory: Record<string, number> = {};
  private static _playtime: number = 0;
  private static _playtimeStart: number = Date.now();
  private static _currentMap: string = 'home';
  private static _playerX: number = 100;
  private static _playerY: number = 100;
  private static _settings: GameSettings = { soundEnabled: true, zoom: 4 };

  // ── Party ──────────────────────────────────────────────────────────────────

  static get party(): Character[] { return GameState._party; }
  static set party(value: Character[]) { GameState._party = value; }

  // ── Gold ───────────────────────────────────────────────────────────────────

  static get gold(): number { return GameState._gold; }
  static set gold(value: number) { GameState._gold = value; }

  // ── Inventory ─────────────────────────────────────────────────────────────

  static get inventory(): Record<string, number> { return GameState._inventory; }

  static addItem(id: string, qty: number = 1): void {
    GameState._inventory[id] = (GameState._inventory[id] ?? 0) + qty;
  }

  static removeItem(id: string, qty: number = 1): boolean {
    if ((GameState._inventory[id] ?? 0) < qty) return false;
    GameState._inventory[id] -= qty;
    if (GameState._inventory[id] <= 0) delete GameState._inventory[id];
    return true;
  }

  // ── Player position / map ─────────────────────────────────────────────────

  static get currentMap(): string { return GameState._currentMap; }
  static set currentMap(v: string) { GameState._currentMap = v; }

  static get playerX(): number { return GameState._playerX; }
  static set playerX(v: number) { GameState._playerX = v; }

  static get playerY(): number { return GameState._playerY; }
  static set playerY(v: number) { GameState._playerY = v; }

  // ── Settings ──────────────────────────────────────────────────────────────

  static get settings(): GameSettings { return GameState._settings; }

  static loadSettings(): void {
    try {
      const raw = localStorage.getItem(SETTINGS_KEY);
      if (raw) GameState._settings = { ...GameState._settings, ...JSON.parse(raw) };
    } catch { /* ignore */ }
  }

  static saveSettings(): void {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(GameState._settings));
  }

  // ── Default party ─────────────────────────────────────────────────────────

  static ensureDefaultParty(): void {
    if (GameState._party.length === 0) {
      GameState._party = [
        new Character('hero', 'Hero', 100, 50, 20, 10, 15, 18, 8, 'player', [0, 1, 2, 3], 1, 0)
      ];
      GameState._gold = 50;
      GameState._inventory = { potion: 3 };
    }
  }

  // ── XP / Gold helpers ─────────────────────────────────────────────────────

  static awardXP(amount: number): void {
    for (const member of GameState._party) {
      if (!member.isDead()) member.xp += amount;
    }
  }

  static addGold(amount: number): void { GameState._gold += amount; }

  static spendGold(amount: number): boolean {
    if (GameState._gold < amount) return false;
    GameState._gold -= amount;
    return true;
  }

  // ── Save / Load ───────────────────────────────────────────────────────────

  static save(playerX?: number, playerY?: number): void {
    const elapsed = (Date.now() - GameState._playtimeStart) / 1000;
    GameState._playtime += elapsed;
    GameState._playtimeStart = Date.now();

    const data: SaveData = {
      playerX: playerX ?? GameState._playerX,
      playerY: playerY ?? GameState._playerY,
      mapKey: GameState._currentMap,
      partyStats: GameState._party.map(c => ({
        id: c.id, name: c.name,
        maxHP: c.maxHP, currentHP: c.currentHP,
        maxMP: c.maxMP, currentMP: c.currentMP,
        atk: c.atk, def: c.def, spd: c.spd, spAtk: c.spAtk, spDef: c.spDef,
        sprite: c.sprite, frames: c.frames,
        level: c.level, xp: c.xp,
      })),
      inventory: { ...GameState._inventory },
      gold: GameState._gold,
      playtime: GameState._playtime,
    };
    localStorage.setItem(SAVE_KEY, JSON.stringify(data));
  }

  static load(): SaveData | null {
    try {
      const raw = localStorage.getItem(SAVE_KEY);
      if (!raw) return null;
      return JSON.parse(raw) as SaveData;
    } catch { return null; }
  }

  static applySave(data: SaveData): void {
    GameState._playerX = data.playerX;
    GameState._playerY = data.playerY;
    GameState._currentMap = data.mapKey;
    GameState._gold = data.gold;
    GameState._inventory = { ...data.inventory };
    GameState._playtime = data.playtime;
    GameState._playtimeStart = Date.now();
    GameState._party = data.partyStats.map(s =>
      new Character(s.id, s.name, s.maxHP, s.maxMP, s.atk, s.def, s.spd, s.spAtk ?? s.atk, s.spDef ?? s.def, s.sprite, s.frames, s.level, s.xp)
    );
    // Restore currentHP (it was serialised separately from maxHP)
    GameState._party.forEach((c, i) => {
      c.currentHP = data.partyStats[i].currentHP;
      c.currentMP = data.partyStats[i].currentMP;
    });
  }

  static hasSave(): boolean {
    return localStorage.getItem(SAVE_KEY) !== null;
  }
}

import Phaser from 'phaser';
import { State } from '../core/State';
import { txt } from '../core/TextStyle';

export default class LoadingScene extends Phaser.Scene {
  constructor() {
    super({ key: State.LOADING });
  }

  preload() {
    const { width, height } = this.cameras.main;

    // ── Progress bar (sized for 320×180 canvas) ─────────────────────────────
    const barW = 200;
    const barH = 10;
    const barX = (width - barW) / 2;
    const barY = height / 2 + 10;

    const progressBox = this.add.graphics();
    progressBox.fillStyle(0x333333, 0.9);
    progressBox.fillRect(barX - 2, barY - 2, barW + 4, barH + 4);

    const progressBar = this.add.graphics();

    this.add.text(width / 2, height / 2 - 12, 'LOADING...', txt({
      fontSize: '8px',
      color: '#ffffff',
    })).setOrigin(0.5);

    // ── Loader callbacks ─────────────────────────────────────────────────────
    this.load.on('progress', (value: number) => {
      progressBar.clear();
      progressBar.fillStyle(0x4488ff, 1);
      progressBar.fillRect(barX, barY, barW * value, barH);
    });

    this.load.on('loaderror', (file: { key: string }) => {
      console.warn(`Asset not found (skipping): ${file.key}`);
    });

    // ── Required JSON data ────────────────────────────────────────────────────
    this.load.json('enemies',    'assets/data/enemies/slime.json');
    this.load.json('enemy_grass','assets/data/enemies/wildmon_grass.json');
    this.load.json('enemy_cave', 'assets/data/enemies/wildmon_cave.json');
    this.load.json('items',      'assets/data/items/potion_heal.json');
    this.load.json('characters', 'assets/data/characters/hero.json');
    this.load.json('npcs',       'assets/data/npcs/npcs.json');
    this.load.json('doors',      'assets/data/maps/doors.json');

    // ── Sprites (generated at runtime if files absent) ────────────────────────
    // Real PNGs can be dropped in; the game falls back to coloured rectangles.
    this.load.image('player', 'assets/sprites/player.png');
    this.load.image('slime',  'assets/sprites/slime.png');
  }

  create() {
    this.scene.start(State.TITLE);
  }
}

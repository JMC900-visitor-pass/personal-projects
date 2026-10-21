import Phaser from 'phaser';
import { State, GameState } from '../core/State';
import { txt } from '../core/TextStyle';

// Declare the electronAPI interface injected by preload.js
declare global {
  interface Window {
    electronAPI?: {
      resizeWindow: (w: number, h: number) => Promise<void>;
    };
  }
}

/**
 * Settings screen.  Back to TitleScene on Escape / B.
 */
export default class SettingsScene extends Phaser.Scene {
  private rows!: SettingRow[];
  private cursor: number = 0;
  private keys!: {
    up: Phaser.Input.Keyboard.Key;
    down: Phaser.Input.Keyboard.Key;
    left: Phaser.Input.Keyboard.Key;
    right: Phaser.Input.Keyboard.Key;
    w: Phaser.Input.Keyboard.Key;
    s: Phaser.Input.Keyboard.Key;
    a: Phaser.Input.Keyboard.Key;
    d: Phaser.Input.Keyboard.Key;
    k: Phaser.Input.Keyboard.Key;
    l: Phaser.Input.Keyboard.Key;
  };
  private arrowGfx!: Phaser.GameObjects.Text;
  // Source scene that launched settings (TITLE or MENU)
  private fromScene: string = State.TITLE;

  constructor() {
    super({ key: State.SETTINGS });
  }

  init(data: { from?: string }) {
    this.fromScene = data?.from ?? State.TITLE;
  }

  create() {
    this.cursor = 0;
    const { width, height } = this.cameras.main;

    this.add.rectangle(0, 0, width, height, 0x111133).setOrigin(0);

    this.add.text(width / 2, 14, 'SETTINGS', txt({
      fontSize: '10px',
      color: '#ffee44',
    })).setOrigin(0.5);

    // ── Setting rows ──────────────────────────────────────────────────────────
    const startY = 50;
    const rowH   = 20;

    this.rows = [
      new ToggleSetting(this, 'Sound', startY,          GameState.settings.soundEnabled),
      new ZoomSetting  (this, 'Zoom',  startY + rowH,   GameState.settings.zoom),
    ];

    this.rows.forEach(r => r.render(width));

    // ── Arrow ─────────────────────────────────────────────────────────────────
    this.arrowGfx = this.add.text(0, 0, '>', txt({
      fontSize: '8px',
      color: '#ffee44',
    })).setOrigin(0, 0.5);
    this.updateArrow();

    // ── Back hint ─────────────────────────────────────────────────────────────
    this.add.text(width / 2, height - 8, '[L] Back', txt({
      fontSize: '6px',
      color: '#888888',
    })).setOrigin(0.5);

    // ── Keys ──────────────────────────────────────────────────────────────────
    const kb = this.input.keyboard!;
    this.keys = {
      up:    kb.addKey(Phaser.Input.Keyboard.KeyCodes.UP),
      down:  kb.addKey(Phaser.Input.Keyboard.KeyCodes.DOWN),
      left:  kb.addKey(Phaser.Input.Keyboard.KeyCodes.LEFT),
      right: kb.addKey(Phaser.Input.Keyboard.KeyCodes.RIGHT),
      w:     kb.addKey(Phaser.Input.Keyboard.KeyCodes.W),
      s:     kb.addKey(Phaser.Input.Keyboard.KeyCodes.S),
      a:     kb.addKey(Phaser.Input.Keyboard.KeyCodes.A),
      d:     kb.addKey(Phaser.Input.Keyboard.KeyCodes.D),
      k: kb.addKey(Phaser.Input.Keyboard.KeyCodes.K),
      l: kb.addKey(Phaser.Input.Keyboard.KeyCodes.L),
    };
  }

  update() {
    const up    = Phaser.Input.Keyboard.JustDown(this.keys.up)    || Phaser.Input.Keyboard.JustDown(this.keys.w);
    const down  = Phaser.Input.Keyboard.JustDown(this.keys.down)  || Phaser.Input.Keyboard.JustDown(this.keys.s);
    const left  = Phaser.Input.Keyboard.JustDown(this.keys.left)  || Phaser.Input.Keyboard.JustDown(this.keys.a);
    const right = Phaser.Input.Keyboard.JustDown(this.keys.right) || Phaser.Input.Keyboard.JustDown(this.keys.d);
    const ok   = Phaser.Input.Keyboard.JustDown(this.keys.k);
    const back = Phaser.Input.Keyboard.JustDown(this.keys.l);

    if (up)         { this.cursor = Math.max(0, this.cursor - 1); this.updateArrow(); }
    if (down)       { this.cursor = Math.min(this.rows.length - 1, this.cursor + 1); this.updateArrow(); }
    if (left)       { this.rows[this.cursor].decrement(); this.applySettings(); }
    if (right || ok){ this.rows[this.cursor].increment(); this.applySettings(); }
    if (back)       { this.goBack(); }
  }

  private updateArrow() {
    const row = this.rows[this.cursor];
    this.arrowGfx.setPosition(8, row.y);
    this.rows.forEach((r, i) => r.setHighlight(i === this.cursor));
  }

  private applySettings() {
    // Collect values back from rows
    const sound = (this.rows[0] as ToggleSetting).value;
    const zoom  = (this.rows[1] as ZoomSetting).value;

    const prevZoom = GameState.settings.zoom;

    GameState.settings.soundEnabled = sound;
    GameState.settings.zoom         = zoom;
    GameState.saveSettings();

    // Update Phaser zoom
    this.scale.setZoom(zoom);

    // Resize Electron window if API available
    const w = 320 * zoom;
    const h = 180 * zoom;
    if (window.electronAPI) {
      window.electronAPI.resizeWindow(w, h).catch(() => {});
    }

    this.rows.forEach(r => r.refresh());

    // Flash "Applied!" when zoom changes
    if (zoom !== prevZoom) {
      const { width, height } = this.cameras.main;
      const appliedMsg = this.add.text(width / 2, height - 20, 'Applied!', txt({
        fontSize: '6px',
        color: '#88ffaa',
      })).setOrigin(0.5).setAlpha(1);

      this.time.delayedCall(1000, () => {
        this.tweens.add({
          targets: appliedMsg,
          alpha: 0,
          duration: 300,
          onComplete: () => { appliedMsg.destroy(); },
        });
      });
    }
  }

  private goBack() {
    if (this.fromScene === State.MENU) {
      this.scene.start(State.MENU, { from: State.SETTINGS });
    } else if (this.fromScene === State.OVERWORLD) {
      this.scene.start(State.OVERWORLD);
    } else {
      this.scene.start(State.TITLE);
    }
  }
}

// ─── Setting row helpers ──────────────────────────────────────────────────────

abstract class SettingRow {
  protected scene: SettingsScene;
  protected label: string;
  readonly y: number;
  protected labelTxt!: Phaser.GameObjects.Text;
  protected valueTxt!: Phaser.GameObjects.Text;

  constructor(scene: SettingsScene, label: string, y: number) {
    this.scene = scene;
    this.label = label;
    this.y     = y;
  }

  abstract render(width: number): void;
  abstract increment(): void;
  abstract decrement(): void;
  abstract refresh(): void;

  setHighlight(on: boolean) {
    this.labelTxt?.setColor(on ? '#ffee44' : '#cccccc');
  }
}

class ToggleSetting extends SettingRow {
  value: boolean;

  constructor(scene: SettingsScene, label: string, y: number, initial: boolean) {
    super(scene, label, y);
    this.value = initial;
  }

  render(width: number) {
    this.labelTxt = this.scene.add.text(24, this.y, this.label, txt({
      fontSize: '8px', color: '#cccccc',
    })).setOrigin(0, 0.5);

    this.valueTxt = this.scene.add.text(width - 8, this.y, this.valueLabel(), txt({
      fontSize: '8px', color: '#88ffaa',
    })).setOrigin(1, 0.5);
  }

  increment() { this.value = !this.value; this.refresh(); }
  decrement() { this.value = !this.value; this.refresh(); }

  refresh() {
    this.valueTxt?.setText(this.valueLabel());
  }

  private valueLabel(): string { return this.value ? 'ON' : 'OFF'; }
}

class ZoomSetting extends SettingRow {
  private readonly OPTIONS = [1, 2, 3, 4];
  private idx: number;

  get value(): number { return this.OPTIONS[this.idx]; }

  constructor(scene: SettingsScene, label: string, y: number, initial: number) {
    super(scene, label, y);
    this.idx = Math.max(0, this.OPTIONS.indexOf(initial));
  }

  render(width: number) {
    this.labelTxt = this.scene.add.text(24, this.y, this.label, txt({
      fontSize: '8px', color: '#cccccc',
    })).setOrigin(0, 0.5);

    this.valueTxt = this.scene.add.text(width - 8, this.y, this.valueLabel(), txt({
      fontSize: '8px', color: '#88ffaa',
    })).setOrigin(1, 0.5);
  }

  increment() { this.idx = Math.min(this.OPTIONS.length - 1, this.idx + 1); this.refresh(); }
  decrement() { this.idx = Math.max(0, this.idx - 1); this.refresh(); }

  refresh() { this.valueTxt?.setText(this.valueLabel()); }

  private valueLabel(): string {
    const z = this.OPTIONS[this.idx];
    return `${z}x  (${320 * z}x${180 * z})`;
  }
}

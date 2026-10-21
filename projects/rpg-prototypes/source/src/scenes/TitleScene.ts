import Phaser from 'phaser';
import { State, GameState } from '../core/State';
import { txt } from '../core/TextStyle';

/**
 * Pokemon-style title screen.
 * Canvas is 320×180.  Menu items are selectable with W/S, arrow keys,
 * mouse click, or touch.  Enter/Z confirms.
 */
export default class TitleScene extends Phaser.Scene {
  private menuItems!: Phaser.GameObjects.Text[];
  private cursor: number = 0;
  private keys!: {
    up: Phaser.Input.Keyboard.Key;
    down: Phaser.Input.Keyboard.Key;
    w: Phaser.Input.Keyboard.Key;
    s: Phaser.Input.Keyboard.Key;
    k: Phaser.Input.Keyboard.Key;
  };
  private arrow!: Phaser.GameObjects.Text;
  private blocked: boolean = false;
  private titleText!: Phaser.GameObjects.Text;
  private lastNavTime: number = 0;

  private readonly LABELS = ['NEW GAME', 'LOAD GAME', 'SETTINGS'];

  constructor() {
    super({ key: State.TITLE });
  }

  create() {
    this.blocked = false;
    this.cursor  = 0;

    const { width, height } = this.cameras.main;

    // ── Background ────────────────────────────────────────────────────────────
    this.add.rectangle(0, 0, width, height, 0x000000).setOrigin(0);

    // Decorative star-like pixel pattern
    const graphics = this.add.graphics();
    graphics.fillStyle(0x223366, 1);
    graphics.fillRect(0, 0, width, height);
    // Horizontal gradient bands
    graphics.fillStyle(0x112244, 1);
    graphics.fillRect(0, 0, width, height / 2);

    // ── Title text ────────────────────────────────────────────────────────────
    this.titleText = this.add.text(width / 2, 40, 'REALM CHIPS', txt({
      fontSize: '18px',
      color: '#ffee44',
      stroke: '#885500',
      strokeThickness: 3,
    })).setOrigin(0.5);

    // Idle animation: every 2000ms, briefly scale to 1.05 and back
    this.time.addEvent({
      delay: 2000,
      loop: true,
      callback: () => {
        this.tweens.add({
          targets: this.titleText,
          scaleX: 1.05,
          scaleY: 1.05,
          duration: 120,
          yoyo: true,
          ease: 'Sine.easeInOut',
        });
      },
    });

    this.add.text(width / 2, 56, 'An Epic Pixel Adventure', txt({
      fontSize: '6px',
      color: '#aaaacc',
    })).setOrigin(0.5);

    // ── Menu items ────────────────────────────────────────────────────────────
    const menuStartY = 100;
    const menuSpacing = 18;

    this.menuItems = this.LABELS.map((label, i) => {
      const item = this.add.text(width / 2 + 8, menuStartY + i * menuSpacing, label, txt({
        fontSize: '8px',
        color: '#ffffff',
      })).setOrigin(0.5);

      // Click / tap to select
      item.setInteractive({ useHandCursor: true });
      item.on('pointerdown', () => {
        if (this.blocked) return;
        this.cursor = i;
        this.updateArrow();
        this.confirm();
      });
      item.on('pointerover', () => {
        if (this.blocked) return;
        this.cursor = i;
        this.updateArrow();
      });

      return item;
    });

    // ── Cursor arrow ─────────────────────────────────────────────────────────
    this.arrow = this.add.text(0, 0, '>', txt({
      fontSize: '8px',
      color: '#ffee44',
    })).setOrigin(0.5);
    this.updateArrow();

    // ── Keyboard bindings ─────────────────────────────────────────────────────
    const kb = this.input.keyboard!;
    this.keys = {
      up:   kb.addKey(Phaser.Input.Keyboard.KeyCodes.UP),
      down: kb.addKey(Phaser.Input.Keyboard.KeyCodes.DOWN),
      w:    kb.addKey(Phaser.Input.Keyboard.KeyCodes.W),
      s:    kb.addKey(Phaser.Input.Keyboard.KeyCodes.S),
      k:    kb.addKey(Phaser.Input.Keyboard.KeyCodes.K),
    };

    // ── Version watermark ─────────────────────────────────────────────────────
    this.add.text(width - 2, height - 2, 'v1.0', txt({
      fontSize: '5px',
      color: '#555577',
    })).setOrigin(1, 1);
  }

  update() {
    if (this.blocked) return;

    const now = this.time.now;
    const pressedUp   = Phaser.Input.Keyboard.JustDown(this.keys.up)   || Phaser.Input.Keyboard.JustDown(this.keys.w);
    const pressedDown = Phaser.Input.Keyboard.JustDown(this.keys.down) || Phaser.Input.Keyboard.JustDown(this.keys.s);
    const pressedOk   = Phaser.Input.Keyboard.JustDown(this.keys.k);

    if (pressedUp || pressedDown) {
      if (now - this.lastNavTime < 150) return;
      this.lastNavTime = now;
      if (pressedUp) {
        this.cursor = (this.cursor - 1 + this.LABELS.length) % this.LABELS.length;
      } else {
        this.cursor = (this.cursor + 1) % this.LABELS.length;
      }
      this.updateArrow(true);
    }

    if (pressedOk) {
      this.confirm();
    }
  }

  private updateArrow(withTween: boolean = false) {
    const item = this.menuItems[this.cursor];
    const targetX = item.x - item.width / 2 - 8;
    // Place arrow to left of the selected text
    this.arrow.setPosition(targetX, item.y);

    if (withTween) {
      // Nudge: move 2px right and back over 80ms
      this.tweens.add({
        targets: this.arrow,
        x: targetX + 2,
        duration: 40,
        yoyo: true,
        ease: 'Linear',
      });
    }

    this.menuItems.forEach((t, i) => {
      t.setColor(i === this.cursor ? '#ffee44' : '#ffffff');
    });
  }

  private confirm() {
    this.blocked = true;
    switch (this.cursor) {
      case 0: // NEW GAME
        this.startNewGame();
        break;
      case 1: // LOAD GAME
        this.loadGame();
        break;
      case 2: // SETTINGS
        this.scene.start(State.SETTINGS);
        break;
    }
  }

  private startNewGame() {
    // Wipe any existing party so ensureDefaultParty creates fresh
    GameState.party = [];
    GameState.gold  = 0;
    GameState.ensureDefaultParty();
    
    // Set the starting map to home
    GameState.currentMap = 'home';

    this.cameras.main.fadeOut(300, 0, 0, 0, (_cam: Phaser.Cameras.Scene2D.Camera, progress: number) => {
      if (progress === 1) this.scene.start(State.OVERWORLD);
    });
  }

  private loadGame() {
    const save = GameState.load();
    if (!save) {
      // Do NOT navigate — flash "LOAD GAME" text red once and show message
      const loadItem = this.menuItems[1];
      const originalColor = '#ffee44'; // it's currently highlighted
      this.tweens.add({
        targets: loadItem,
        alpha: 0.3,
        duration: 80,
        yoyo: true,
        repeat: 1,
        onStart: () => { loadItem.setColor('#ff4444'); },
        onComplete: () => { loadItem.setColor(originalColor); },
      });

      // Show "No save data!" above the menu items, then fade out after 1 second
      const { width } = this.cameras.main;
      const menuStartY = 100;
      const msg = this.add.text(width / 2, menuStartY - 18, 'No save data!', txt({
        fontSize: '6px',
        color: '#ff4444',
      })).setOrigin(0.5).setAlpha(1);

      this.time.delayedCall(1000, () => {
        this.tweens.add({
          targets: msg,
          alpha: 0,
          duration: 300,
          onComplete: () => { msg.destroy(); },
        });
        this.blocked = false;
      });
      return;
    }

    GameState.applySave(save);
    this.cameras.main.fadeOut(300, 0, 0, 0, (_cam: Phaser.Cameras.Scene2D.Camera, progress: number) => {
      if (progress === 1) this.scene.start(State.OVERWORLD);
    });
  }
}

import Phaser from 'phaser';
import { State, GameState } from '../core/State';
import { txt } from '../core/TextStyle';

/**
 * In-game menu overlay.  Launched on top of WorldScene via scene.launch().
 * Pokemon-style panel on the right side of the screen.
 *
 * Items: PARTY | ITEMS | SAVE | SETTINGS | QUIT TO TITLE
 */
export default class MenuScene extends Phaser.Scene {
  private cursor: number = 0;
  private labels: string[] = ['PARTY', 'ITEMS', 'SAVE', 'SETTINGS', 'QUIT TO TITLE'];
  private itemTexts: Phaser.GameObjects.Text[] = [];
  private arrow!: Phaser.GameObjects.Text;
  private feedbackText!: Phaser.GameObjects.Text;
  private feedbackTimer?: Phaser.Time.TimerEvent;
  private panel!: Phaser.GameObjects.Rectangle;
  private panelFinalX: number = 0;
  private hoverHighlight?: Phaser.GameObjects.Rectangle;
  private quitConfirmPending: boolean = false;
  private quitConfirmTimer?: Phaser.Time.TimerEvent;
  private closing: boolean = false;

  private keys!: {
    up: Phaser.Input.Keyboard.Key;
    down: Phaser.Input.Keyboard.Key;
    w: Phaser.Input.Keyboard.Key;
    s: Phaser.Input.Keyboard.Key;
    k: Phaser.Input.Keyboard.Key;
    l: Phaser.Input.Keyboard.Key;
  };

  // Which scene opened us
  private fromScene: string = State.OVERWORLD;

  constructor() {
    super({ key: State.MENU });
  }

  init(data: { from?: string }) {
    this.fromScene = data?.from ?? State.OVERWORLD;
  }

  create() {
    this.cursor = 0;
    this.closing = false;
    this.quitConfirmPending = false;
    const { width, height } = this.cameras.main;

    // ── Semi-transparent dark overlay (full screen, low alpha) ───────────────
    this.add.rectangle(0, 0, width, height, 0x000000, 0.35).setOrigin(0).setDepth(0);

    // ── Menu panel (right side) ───────────────────────────────────────────────
    const panelW = 100;
    const panelFinalX = width - panelW - 4;
    const panelY = 4;
    const panelH = this.labels.length * 16 + 20;
    this.panelFinalX = panelFinalX;

    // Start off-screen at x=320, tween to final position
    this.panel = this.add.rectangle(width, panelY, panelW, panelH, 0x112244, 0.95).setOrigin(0).setDepth(1);
    this.add.rectangle(panelFinalX, panelY, panelW, 1, 0x4488ff).setOrigin(0).setDepth(2); // top border

    // Slide in from right over 120ms
    this.tweens.add({
      targets: this.panel,
      x: panelFinalX,
      duration: 120,
      ease: 'Sine.easeOut',
    });

    // ── Menu items ────────────────────────────────────────────────────────────
    const itemStartX = panelFinalX + 14;
    const itemStartY = panelY + 12;
    const itemSpacing = 16;

    this.itemTexts = this.labels.map((label, i) => {
      const item = this.add.text(itemStartX, itemStartY + i * itemSpacing, label, txt({
        fontSize: '7px',
        color: '#ffffff',
      })).setOrigin(0, 0.5).setDepth(3);

      item.setInteractive({ useHandCursor: true });
      item.on('pointerdown', () => {
        if (this.closing) return;
        this.cursor = i; this.updateArrow(); this.confirm();
      });
      item.on('pointerover', () => {
        if (this.closing) return;
        this.cursor = i; this.updateArrow();
        this.setHoverHighlight(i, itemStartX, itemSpacing, panelY, panelW, panelFinalX);
      });
      item.on('pointerout', () => {
        this.clearHoverHighlight();
      });
      return item;
    });

    // ── Arrow ─────────────────────────────────────────────────────────────────
    this.arrow = this.add.text(panelFinalX + 4, 0, '>', txt({
      fontSize: '7px',
      color: '#ffee44',
    })).setOrigin(0, 0.5).setDepth(4);
    this.updateArrow();

    // ── Feedback text (e.g. "Saved!") ─────────────────────────────────────────
    this.feedbackText = this.add.text(panelFinalX + panelW / 2, panelY + panelH + 6, '', txt({
      fontSize: '6px',
      color: '#88ffaa',
    })).setOrigin(0.5, 0).setDepth(5);

    // ── Party HP summary on left ───────────────────────────────────────────────
    this.renderPartyPanel(4, 4);

    // ── Keys ──────────────────────────────────────────────────────────────────
    const kb = this.input.keyboard!;
    this.keys = {
      up:   kb.addKey(Phaser.Input.Keyboard.KeyCodes.UP),
      down: kb.addKey(Phaser.Input.Keyboard.KeyCodes.DOWN),
      w:    kb.addKey(Phaser.Input.Keyboard.KeyCodes.W),
      s:    kb.addKey(Phaser.Input.Keyboard.KeyCodes.S),
      k:    kb.addKey(Phaser.Input.Keyboard.KeyCodes.K),
      l:    kb.addKey(Phaser.Input.Keyboard.KeyCodes.L),
    };
  }

  update() {
    if (this.closing) return;
    const up    = Phaser.Input.Keyboard.JustDown(this.keys.up)    || Phaser.Input.Keyboard.JustDown(this.keys.w);
    const down  = Phaser.Input.Keyboard.JustDown(this.keys.down)  || Phaser.Input.Keyboard.JustDown(this.keys.s);
    const ok    = Phaser.Input.Keyboard.JustDown(this.keys.k);
    const close = Phaser.Input.Keyboard.JustDown(this.keys.l);

    if (up)    { this.cursor = Math.max(0, this.cursor - 1); this.updateArrow(); }
    if (down)  { this.cursor = Math.min(this.labels.length - 1, this.cursor + 1); this.updateArrow(); }
    if (ok)    { this.confirm(); }
    if (close) { this.close(); }
  }

  private updateArrow() {
    const item = this.itemTexts[this.cursor];
    this.arrow.setY(item.y);
    this.itemTexts.forEach((t, i) => t.setColor(i === this.cursor ? '#ffee44' : '#ffffff'));
  }

  private confirm() {
    switch (this.cursor) {
      case 0: // PARTY
        this.showFeedback('Party: ' + GameState.party.map(c => `${c.name} HP:${c.currentHP}`).join(', '));
        break;
      case 1: // ITEMS
        this.showItemList();
        break;
      case 2: // SAVE
        GameState.save();
        this.showFeedback('Game Saved!');
        break;
      case 3: // SETTINGS
        this.scene.start(State.SETTINGS, { from: State.MENU });
        break;
      case 4: // QUIT TO TITLE — requires second press to confirm
        if (!this.quitConfirmPending) {
          // First press: show confirmation prompt and start 3-second timer
          this.quitConfirmPending = true;
          this.itemTexts[4].setText('QUIT? (confirm)');
          this.quitConfirmTimer?.destroy();
          this.quitConfirmTimer = this.time.delayedCall(3000, () => {
            this.quitConfirmPending = false;
            this.itemTexts[4].setText('QUIT TO TITLE');
          });
        } else {
          // Second press: confirmed — quit
          this.quitConfirmTimer?.destroy();
          this.quitConfirmPending = false;
          this.close();
          this.scene.stop(State.OVERWORLD);
          this.scene.start(State.TITLE);
        }
        break;
    }
  }

  private showItemList() {
    const inv = GameState.inventory;
    const entries = Object.entries(inv);
    if (entries.length === 0) {
      this.showFeedback('Bag is empty!');
    } else {
      this.showFeedback(entries.map(([id, qty]) => `${id} x${qty}`).join('  '));
    }
  }

  private showFeedback(msg: string) {
    this.feedbackText.setText(msg);
    this.feedbackTimer?.destroy();
    this.feedbackTimer = this.time.delayedCall(2000, () => {
      this.feedbackText.setText('');
    });
  }

  private renderPartyPanel(x: number, y: number) {
    const party = GameState.party;
    this.add.text(x, y, 'PARTY', txt({
      fontSize: '6px',
      color: '#aaaacc',
    })).setDepth(3);

    party.forEach((c, i) => {
      const py = y + 10 + i * 20;
      this.add.text(x, py, c.name, txt({
        fontSize: '6px',
        color: '#ffffff',
      })).setDepth(3);

      // HP bar
      const barW = 50;
      const pct = c.currentHP / c.maxHP;
      const barColor = pct > 0.5 ? 0x44bb44 : pct > 0.25 ? 0xeecc00 : 0xee3333;

      this.add.rectangle(x, py + 8, barW, 4, 0x333333).setOrigin(0).setDepth(3);
      this.add.rectangle(x, py + 8, Math.max(1, barW * pct), 4, barColor).setOrigin(0).setDepth(4);

      this.add.text(x + barW + 2, py + 8, `${c.currentHP}/${c.maxHP}`, txt({
        fontSize: '5px',
        color: '#cccccc',
      })).setOrigin(0, 0).setDepth(4);
    });
  }

  private close() {
    if (this.closing) return;
    this.closing = true;
    const { width } = this.cameras.main;
    // Slide panel back off to the right over 100ms, then finish closing
    this.tweens.add({
      targets: this.panel,
      x: width,
      duration: 100,
      ease: 'Sine.easeIn',
      onComplete: () => {
        // Notify WorldScene it can resume
        const world = this.scene.get(State.OVERWORLD) as any;
        if (world?.onMenuClosed) world.onMenuClosed();
        this.events.emit('menu-closed');
        this.scene.stop();
      },
    });
  }

  private setHoverHighlight(
    idx: number,
    itemStartX: number,
    itemSpacing: number,
    panelY: number,
    panelW: number,
    panelFinalX: number,
  ) {
    this.clearHoverHighlight();
    const item = this.itemTexts[idx];
    const highlightH = 9; // 1px taller than the 8px text row
    this.hoverHighlight = this.add.rectangle(
      panelFinalX,
      item.y,
      panelW,
      highlightH,
      0xddccaa,
      0.25,
    ).setOrigin(0, 0.5).setDepth(2);
  }

  private clearHoverHighlight() {
    if (this.hoverHighlight) {
      this.hoverHighlight.destroy();
      this.hoverHighlight = undefined;
    }
  }
}

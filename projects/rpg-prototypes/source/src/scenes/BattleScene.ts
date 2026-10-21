import Phaser from 'phaser';
import { State, GameState } from '../core/State';
import { CombatSystem } from '../systems/CombatSystem';
import { Character } from '../entities/Character';
import { txt } from '../core/TextStyle';

// ─── Move definition ──────────────────────────────────────────────────────────
interface Move {
  name: string;
  power: number;
  type: 'physical' | 'special' | 'status';
  pp: number;
  maxPP: number;
  description: string;
}

const HERO_MOVES: Move[] = [
  { name: 'Tackle',    power: 40, type: 'physical', pp: 35, maxPP: 35, description: 'A basic charge attack.' },
  { name: 'Scratch',   power: 45, type: 'physical', pp: 30, maxPP: 30, description: 'Sharp claw swipe.' },
  { name: 'Ember',     power: 55, type: 'special',  pp: 25, maxPP: 25, description: 'A small flame burst.' },
  { name: 'Growl',     power:  0, type: 'status',   pp: 40, maxPP: 40, description: 'Lowers enemy ATK by 3.' },
  { name: 'Harden',    power:  0, type: 'status',   pp: 30, maxPP: 30, description: 'Raises your DEF by 3.' },
  { name: 'Potion',    power:  0, type: 'status',   pp:  3, maxPP:  3, description: 'Restores 20 HP.' },
];

type BattlePhase = 'ACTION' | 'MOVE_SELECT' | 'ITEM_SELECT' | 'ANIMATING' | 'RESULT' | 'DONE';

/**
 * Pokemon-style turn-based battle scene.
 *
 * Layout (320×180):
 *   - Background fill
 *   - Enemy sprite/rectangle top-centre
 *   - Enemy HP bar below enemy name (top)
 *   - Player sprite bottom-left
 *   - Player stat box bottom-right
 *   - Action menu (FIGHT / ITEM / RUN) bottom-right when ACTION phase
 *   - Move list when MOVE_SELECT phase
 */
export default class BattleScene extends Phaser.Scene {
  // ── Data ───────────────────────────────────────────────────────────────────
  private combatSystem!: CombatSystem;
  private enemy!: Character;
  private hero!: Character;
  private moves: Move[] = [...HERO_MOVES];

  // ── Layout constants (virtual 320×180) ────────────────────────────────────
  private readonly W  = 320;
  private readonly H  = 180;
  private readonly BOX_Y   = 116; // y where the message/action box starts
  private readonly BOX_H   = 64;  // height of bottom UI area

  // ── UI objects ─────────────────────────────────────────────────────────────
  private enemyRect!: Phaser.GameObjects.Rectangle;
  private playerRect!: Phaser.GameObjects.Rectangle;

  private enemyNameTxt!: Phaser.GameObjects.Text;
  private enemyLvlTxt!:  Phaser.GameObjects.Text;
  private enemyHPBar!:   Phaser.GameObjects.Rectangle;
  private enemyHPFill!:  Phaser.GameObjects.Rectangle;

  private playerNameTxt!: Phaser.GameObjects.Text;
  private playerHPTxt!:   Phaser.GameObjects.Text;
  private playerHPBar!:   Phaser.GameObjects.Rectangle;
  private playerHPFill!:  Phaser.GameObjects.Rectangle;

  private messageTxt!: Phaser.GameObjects.Text;

  // Action menu items
  private actionGroup!: Phaser.GameObjects.Group;
  private moveGroup!:   Phaser.GameObjects.Group;
  private itemGroup!:   Phaser.GameObjects.Group;

  // ── State ──────────────────────────────────────────────────────────────────
  private phase: BattlePhase = 'ACTION';
  private actionCursor: number = 0;
  private moveCursor:   number = 0;
  private itemCursor:   number = 0;

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

  // ── Scene init data ────────────────────────────────────────────────────────
  private encounterType: string = 'grass';
  private returnScene:   string = State.OVERWORLD;

  constructor() {
    super({ key: State.BATTLE });
  }

  init(data: { party?: Character[]; returnScene?: string; encounterType?: string }) {
    if (data?.party && data.party.length > 0) GameState.party = data.party;
    this.returnScene   = data?.returnScene ?? State.OVERWORLD;
    this.encounterType = data?.encounterType ?? 'grass';
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Lifecycle
  // ──────────────────────────────────────────────────────────────────────────

  create() {
    this.phase  = 'ACTION';
    this.actionCursor = 0;
    this.moveCursor   = 0;
    this.itemCursor   = 0;

    // Reset PP for this battle
    this.moves = HERO_MOVES.map(m => ({ ...m }));

    GameState.ensureDefaultParty();
    this.hero  = GameState.party[0];
    this.enemy = this.buildEnemy();

    this.combatSystem = new CombatSystem();
    this.combatSystem.init([this.hero], [this.enemy]);

    this.buildBackground();
    this.buildEnemyUI();
    this.buildPlayerUI();
    this.buildMessageBox();
    this.buildActionMenu();
    this.buildMoveMenu();
    this.buildItemMenu();
    this.setupKeys();

    this.setMessage(`A wild ${this.enemy.name} appeared!`);
    this.showPhase('ACTION');
  }

  update() {
    if (this.phase === 'ANIMATING' || this.phase === 'DONE') return;

    const up    = Phaser.Input.Keyboard.JustDown(this.keys.up)    || Phaser.Input.Keyboard.JustDown(this.keys.w);
    const down  = Phaser.Input.Keyboard.JustDown(this.keys.down)  || Phaser.Input.Keyboard.JustDown(this.keys.s);
    const left  = Phaser.Input.Keyboard.JustDown(this.keys.left)  || Phaser.Input.Keyboard.JustDown(this.keys.a);
    const right = Phaser.Input.Keyboard.JustDown(this.keys.right) || Phaser.Input.Keyboard.JustDown(this.keys.d);
    const ok   = Phaser.Input.Keyboard.JustDown(this.keys.k);
    const back = Phaser.Input.Keyboard.JustDown(this.keys.l);

    if (this.phase === 'ACTION') {
      const numActions = 3;
      // 2-column grid: FIGHT ITEM / RUN
      if (left || up)  { this.actionCursor = (this.actionCursor - 1 + numActions) % numActions; this.refreshActionMenu(); }
      if (right || down) { this.actionCursor = (this.actionCursor + 1) % numActions; this.refreshActionMenu(); }
      if (ok) this.selectAction();
    }
    else if (this.phase === 'MOVE_SELECT') {
      const numMoves = this.moves.length;
      if (up || left)   { this.moveCursor = (this.moveCursor - 1 + numMoves) % numMoves; this.refreshMoveMenu(); }
      if (down || right) { this.moveCursor = (this.moveCursor + 1) % numMoves; this.refreshMoveMenu(); }
      if (ok)   this.selectMove(this.moveCursor);
      if (back) { this.showPhase('ACTION'); }
    }
    else if (this.phase === 'ITEM_SELECT') {
      const items = Object.entries(GameState.inventory);
      if (items.length > 0) {
        if (up)   { this.itemCursor = Math.max(0, this.itemCursor - 1); this.refreshItemMenu(); }
        if (down) { this.itemCursor = Math.min(items.length - 1, this.itemCursor + 1); this.refreshItemMenu(); }
        if (ok)   this.selectItem(this.itemCursor);
      }
      if (back) { this.showPhase('ACTION'); }
    }
    else if (this.phase === 'RESULT') {
      if (ok) {
        this.endBattle();
      }
    }
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Enemy builder
  // ──────────────────────────────────────────────────────────────────────────

  private buildEnemy(): Character {
    const key = this.encounterType === 'cave' ? 'enemy_cave' : 'enemy_grass';
    const data = this.cache.json.get(key) ?? this.cache.json.get('enemies');

    if (data && data.id) {
      // Support both nested stats block (template) and flat legacy fields
      const s = data.stats ?? data;
      const lvlRange = data.level ?? {};
      const lvl   = Phaser.Math.Between(lvlRange.min ?? 3, lvlRange.max ?? 5);
      const scale = 1 + (lvl - 1) * 0.15;
      return new Character(
        data.id,
        data.name,
        Math.round((s.maxHP        ?? 30) * scale),
        0,
        Math.round((s.atk          ?? 8)  * scale),
        Math.round((s.def          ?? 3)  * scale),
        s.spd ?? 5,
        Math.round((s['sp.atk']    ?? s.spAtk ?? s.atk ?? 8) * scale),
        Math.round((s['sp.def']    ?? s.spDef ?? s.def ?? 3) * scale),
        data.sprite?.key ?? data.sprite ?? 'slime',
        data.frames ?? [0],
        lvl,
      );
    }
    return new Character('slime', 'Slime', 30, 0, 8, 3, 5, 8, 3, 'slime', [0], 3);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Background
  // ──────────────────────────────────────────────────────────────────────────

  private buildBackground() {
    // Sky-ish gradient via two rectangles
    this.add.rectangle(0, 0, this.W, this.BOX_Y, 0x88bbff).setOrigin(0);
    this.add.rectangle(0, this.BOX_Y - 20, this.W, 20, 0x558833).setOrigin(0); // grass strip
    this.add.rectangle(0, this.BOX_Y - 8, this.W, 8, 0x4a7c59).setOrigin(0);  // darker strip
    // Battle UI background
    this.add.rectangle(0, this.BOX_Y, this.W, this.BOX_H, 0xf0e8c8).setOrigin(0);
    // divider line
    this.add.rectangle(0, this.BOX_Y, this.W, 1, 0x999999).setOrigin(0);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Enemy UI (top-right area)
  // ──────────────────────────────────────────────────────────────────────────

  private buildEnemyUI() {
    const ex = 200; // enemy rect centre-x
    const ey = 52;  // enemy rect centre-y

    // Placeholder sprite — large-ish coloured block
    this.enemyRect = this.add.rectangle(ex, ey, 48, 40, 0x6644aa);

    // Name + level box (top-left of battle area)
    const nameBoxX = 8;
    const nameBoxY = 8;
    this.add.rectangle(nameBoxX, nameBoxY, 110, 28, 0xffffff, 0.9).setOrigin(0);
    this.add.rectangle(nameBoxX, nameBoxY, 110, 1, 0x333333).setOrigin(0);

    this.enemyNameTxt = this.add.text(nameBoxX + 4, nameBoxY + 4, this.enemy.name, txt({
      fontSize: '7px', color: '#222222',
    })).setOrigin(0);

    this.enemyLvlTxt = this.add.text(nameBoxX + 90, nameBoxY + 4, `Lv${this.enemy.level}`, txt({
      fontSize: '6px', color: '#555555',
    })).setOrigin(0);

    const lvlDiff = this.enemy.level - this.hero.level;
    const lvlColor = lvlDiff >= 3 ? '#ee3333' : lvlDiff <= -3 ? '#33aa33' : '#555555';
    this.enemyLvlTxt.setColor(lvlColor);

    // HP bar track
    const hpBarX = nameBoxX + 4;
    const hpBarY = nameBoxY + 14;
    const hpBarW = 100;
    this.add.text(hpBarX, hpBarY, 'HP', txt({ fontSize: '5px', color: '#333333' }));
    this.enemyHPBar  = this.add.rectangle(hpBarX + 10, hpBarY + 1, hpBarW, 5, 0xaaaaaa).setOrigin(0);
    this.enemyHPFill = this.add.rectangle(hpBarX + 10, hpBarY + 1, hpBarW, 5, 0x44bb44).setOrigin(0);
    this.updateEnemyHPBar();
  }

  private updateEnemyHPBar() {
    const pct = Math.max(0, this.enemy.currentHP / this.enemy.maxHP);
    const W   = 100;
    const color = pct > 0.5 ? 0x44bb44 : pct > 0.25 ? 0xeecc00 : 0xee3333;
    this.enemyHPFill.setSize(Math.max(1, W * pct), 5);
    this.enemyHPFill.setFillStyle(color);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Player UI (bottom-left sprite + bottom-right stat box)
  // ──────────────────────────────────────────────────────────────────────────

  private buildPlayerUI() {
    // Player sprite bottom-left
    this.playerRect = this.add.rectangle(56, 96, 32, 40, 0xff4444);

    // Stat box bottom-right
    const sbX = 160;
    const sbY = this.BOX_Y + 2;
    const sbW = this.W - sbX - 4;

    this.add.rectangle(sbX, sbY, sbW, 60, 0xffffff, 0.95).setOrigin(0);
    this.add.rectangle(sbX, sbY, sbW, 1, 0x333333).setOrigin(0);

    this.playerNameTxt = this.add.text(sbX + 4, sbY + 4, this.hero.name, txt({
      fontSize: '7px', color: '#222222',
    })).setOrigin(0);

    this.add.text(sbX + 4, sbY + 16, 'HP', txt({
      fontSize: '6px', color: '#333333',
    }));

    const hpBarX = sbX + 14;
    const hpBarY = sbY + 18;
    const hpBarW = sbW - 20;
    this.playerHPBar  = this.add.rectangle(hpBarX, hpBarY, hpBarW, 5, 0xaaaaaa).setOrigin(0);
    this.playerHPFill = this.add.rectangle(hpBarX, hpBarY, hpBarW, 5, 0x44bb44).setOrigin(0);

    this.playerHPTxt = this.add.text(sbX + 4, sbY + 28, '', txt({
      fontSize: '6px', color: '#222222',
    })).setOrigin(0);

    this.updatePlayerHPBar();
  }

  private updatePlayerHPBar() {
    const pct = Math.max(0, this.hero.currentHP / this.hero.maxHP);
    const W   = (this.W - 160 - 4) - 20;
    const color = pct > 0.5 ? 0x44bb44 : pct > 0.25 ? 0xeecc00 : 0xee3333;
    this.playerHPFill.setSize(Math.max(1, W * pct), 5);
    this.playerHPFill.setFillStyle(color);
    this.playerHPTxt.setText(`${this.hero.currentHP} / ${this.hero.maxHP}`);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Message box
  // ──────────────────────────────────────────────────────────────────────────

  private buildMessageBox() {
    const msgX = 4;
    const msgY = this.BOX_Y + 4;

    this.messageTxt = this.add.text(msgX, msgY, '', txt({
      fontSize: '7px',
      color: '#222222',
      wordWrap: { width: 150 },
      lineSpacing: 2,
    })).setOrigin(0).setDepth(10);
  }

  private setMessage(msg: string) {
    this.messageTxt.setText(msg);
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Action menu: FIGHT / ITEM / RUN
  // ──────────────────────────────────────────────────────────────────────────

  private actionLabels = ['FIGHT', 'ITEM', 'RUN'];
  private actionTextObjs: Phaser.GameObjects.Text[] = [];

  private buildActionMenu() {
    this.actionGroup = this.add.group();

    const menuX  = 168;
    const menuY  = this.BOX_Y + 2;
    const menuW  = this.W - menuX - 4;
    const menuH  = this.BOX_H - 4;

    const bg = this.add.rectangle(menuX, menuY, menuW, menuH, 0xfaf0e6, 0.95).setOrigin(0).setDepth(9);
    this.add.rectangle(menuX, menuY, menuW, 1, 0x666666).setOrigin(0).setDepth(9);
    this.actionGroup.add(bg);

    // 3 items in a 2-col layout
    this.actionTextObjs = this.actionLabels.map((lbl, i) => {
      const col = i % 2;
      const row = Math.floor(i / 2);
      const tx = menuX + 8 + col * 60;
      const ty = menuY + 10 + row * 16;

      const item = this.add.text(tx, ty, lbl, txt({
        fontSize: '7px', color: '#333333',
      })).setOrigin(0, 0.5).setDepth(10);

      item.setInteractive({ useHandCursor: true });
      item.on('pointerdown', () => { this.actionCursor = i; this.selectAction(); });
      item.on('pointerover', () => { this.actionCursor = i; this.refreshActionMenu(); });
      this.actionGroup.add(item);
      return item;
    });

    this.refreshActionMenu();
  }

  private refreshActionMenu() {
    this.actionTextObjs.forEach((t, i) => {
      t.setColor(i === this.actionCursor ? '#cc2200' : '#333333');
      t.setText((i === this.actionCursor ? '> ' : '  ') + this.actionLabels[i]);
    });
  }

  private selectAction() {
    switch (this.actionCursor) {
      case 0: this.showPhase('MOVE_SELECT'); break;
      case 1: this.showPhase('ITEM_SELECT'); break;
      case 2: this.runAway(); break;
    }
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Move menu
  // ──────────────────────────────────────────────────────────────────────────

  private moveTextObjs: Phaser.GameObjects.Text[] = [];
  private movePPObjs:   Phaser.GameObjects.Text[] = [];

  private buildMoveMenu() {
    this.moveGroup = this.add.group();

    const menuX = 4;
    const menuY = this.BOX_Y + 2;
    const menuW = 310;
    const menuH = this.BOX_H - 4;

    const bg = this.add.rectangle(menuX, menuY, menuW, menuH, 0xfaf0e6, 0.95).setOrigin(0).setDepth(9);
    this.add.rectangle(menuX, menuY, menuW, 1, 0x666666).setOrigin(0).setDepth(9);
    this.moveGroup.add(bg);

    this.moveTextObjs = [];
    this.movePPObjs   = [];

    for (let i = 0; i < this.moves.length; i++) {
      const col = i % 2;
      const row = Math.floor(i / 2);
      const tx = menuX + 8  + col * 152;
      const ty = menuY + 12 + row * 20;

      const moveTxt = this.add.text(tx, ty, '', txt({
        fontSize: '7px', color: '#333333',
      })).setOrigin(0, 0.5).setDepth(10);

      const ppTxt = this.add.text(tx + 100, ty, '', txt({
        fontSize: '6px', color: '#777777',
      })).setOrigin(0, 0.5).setDepth(10);

      moveTxt.setInteractive({ useHandCursor: true });
      const idx = i;
      moveTxt.on('pointerdown', () => { this.moveCursor = idx; this.selectMove(idx); });
      moveTxt.on('pointerover', () => { this.moveCursor = idx; this.refreshMoveMenu(); });

      this.moveGroup.add(moveTxt);
      this.moveGroup.add(ppTxt);
      this.moveTextObjs.push(moveTxt);
      this.movePPObjs.push(ppTxt);
    }

    this.refreshMoveMenu();
    this.moveGroup.setVisible(false);
  }

  private refreshMoveMenu() {
    this.moves.forEach((m, i) => {
      const selected = i === this.moveCursor;
      this.moveTextObjs[i].setText((selected ? '> ' : '  ') + m.name);
      this.moveTextObjs[i].setColor(selected ? '#cc2200' : '#333333');
      this.movePPObjs[i].setText(`PP ${m.pp}/${m.maxPP}`);
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Item menu
  // ──────────────────────────────────────────────────────────────────────────

  private itemTextObjs: Phaser.GameObjects.Text[] = [];

  private buildItemMenu() {
    this.itemGroup = this.add.group();

    const menuX = 4;
    const menuY = this.BOX_Y + 2;
    const menuW = 310;
    const menuH = this.BOX_H - 4;

    const bg = this.add.rectangle(menuX, menuY, menuW, menuH, 0xfaf0e6, 0.95).setOrigin(0).setDepth(9);
    this.itemGroup.add(bg);
    this.itemGroup.setVisible(false);
  }

  private refreshItemMenu() {
    // Destroy old texts
    this.itemTextObjs.forEach(t => t.destroy());
    this.itemTextObjs = [];

    const items = Object.entries(GameState.inventory);
    const menuX = 4;
    const menuY = this.BOX_Y + 2;

    if (items.length === 0) {
      const t = this.add.text(menuX + 8, menuY + 16, 'Bag is empty!', txt({
        fontSize: '7px', color: '#666666',
      })).setDepth(11);
      this.itemTextObjs.push(t);
      return;
    }

    items.forEach(([id, qty], i) => {
      const ty = menuY + 10 + i * 14;
      const selected = i === this.itemCursor;
      const t = this.add.text(menuX + 8, ty, `${selected ? '>' : ' '} ${id} x${qty}`, txt({
        fontSize: '7px', color: selected ? '#cc2200' : '#333333',
      })).setDepth(11).setOrigin(0, 0.5);

      t.setInteractive({ useHandCursor: true });
      const idx = i;
      t.on('pointerdown', () => { this.itemCursor = idx; this.selectItem(idx); });
      t.on('pointerover', () => { this.itemCursor = idx; this.refreshItemMenu(); });
      this.itemTextObjs.push(t);
    });
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Phase switching
  // ──────────────────────────────────────────────────────────────────────────

  private showPhase(phase: BattlePhase) {
    this.phase = phase;

    const showAction = phase === 'ACTION';
    const showMove   = phase === 'MOVE_SELECT';
    const showItem   = phase === 'ITEM_SELECT';

    this.actionGroup.setVisible(showAction);
    this.moveGroup.setVisible(showMove);
    this.itemGroup.setVisible(showItem);

    if (showMove) {
      this.setMessage('Choose a move:');
      this.refreshMoveMenu();
    }
    if (showItem) {
      this.setMessage('Choose an item:');
      this.refreshItemMenu();
    }
    if (showAction) {
      this.setMessage(`What will\n${this.hero.name} do?`);
      this.refreshActionMenu();
    }
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Combat resolution
  // ──────────────────────────────────────────────────────────────────────────

  private setupKeys() {
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

  private selectMove(index: number) {
    const move = this.moves[index];
    if (move.pp <= 0) {
      this.phase = 'ANIMATING';
      this.setMessage(`${move.name} has no PP left!`);
      this.time.delayedCall(800, () => {
        if (this.phase === 'ANIMATING') {
          this.showPhase('MOVE_SELECT');
        }
      });
      return;
    }
    move.pp--;

    this.phase = 'ANIMATING';
    this.actionGroup.setVisible(false);
    this.moveGroup.setVisible(false);

    if (move.type === 'status' && move.name === 'Growl') {
      this.setMessage(`${this.hero.name} used Growl!\nEnemy ATK fell!`);
      this.enemy.atk = Math.max(1, this.enemy.atk - 2);
      this.time.delayedCall(1000, () => this.enemyTurn());
    }
    else if (move.name === 'Harden') {
      this.hero.def = Math.min(this.hero.def + 3, 99);
      this.setMessage(`${this.hero.name} hardened!\nDEF rose!`);
      this.time.delayedCall(1000, () => this.enemyTurn());
    }
    else if (move.type === 'status' && move.name === 'Potion') {
      const heal = 20;
      this.hero.heal(heal);
      this.setMessage(`${this.hero.name} used a Potion!\nRestored ${heal} HP!`);
      this.updatePlayerHPBar();
      this.time.delayedCall(1000, () => this.enemyTurn());
    }
    else {
      // Physical uses atk/def; special uses spAtk/spDef
      const atkStat = move.type === 'special' ? this.hero.spAtk : this.hero.atk;
      const defStat = move.type === 'special' ? this.enemy.spDef : this.enemy.def;
      const damage = this.calcDamage(atkStat, defStat, move.power);
      this.enemy.takeDamage(damage);
      this.updateEnemyHPBar();

      // Shake enemy
      this.tweens.add({
        targets: this.enemyRect,
        x: { from: this.enemyRect.x - 4, to: this.enemyRect.x },
        duration: 100, yoyo: true, repeat: 2,
      });

      this.setMessage(`${this.hero.name} used ${move.name}!\nDealt ${damage} damage!`);

      if (this.enemy.isDead()) {
        this.time.delayedCall(800, () => this.victory());
      } else {
        this.time.delayedCall(1000, () => this.enemyTurn());
      }
    }
  }

  private enemyTurn() {
    const roll = Math.random();

    if (roll < 0.10) {
      // 10% chance: enemy focuses — raises its own ATK by 2, no damage
      this.enemy.atk = Math.min(this.enemy.atk + 2, 99);
      this.setMessage(`${this.enemy.name} focused!\nATK rose!`);
      this.time.delayedCall(900, () => this.showPhase('ACTION'));
    } else {
      // 70% normal physical attack (power 35), 20% special strike (power 55)
      const strong = roll < 0.30;
      const power  = strong ? 55 : 35;
      // Strong attack is special-based; normal is physical
      const atkStat = strong ? this.enemy.spAtk : this.enemy.atk;
      const defStat = strong ? this.hero.spDef  : this.hero.def;
      const damage = this.calcDamage(atkStat, defStat, power);
      this.hero.takeDamage(damage);
      this.updatePlayerHPBar();

      // Shake player rect
      this.tweens.add({
        targets: this.playerRect,
        x: { from: this.playerRect.x + 4, to: this.playerRect.x },
        duration: 100, yoyo: true, repeat: 2,
      });

      if (strong) {
        this.setMessage(`${this.enemy.name} used a powerful strike!\nDealt ${damage} damage!`);
      } else {
        this.setMessage(`${this.enemy.name} attacked!\nDealt ${damage} damage!`);
      }

      if (this.hero.isDead()) {
        this.time.delayedCall(800, () => this.defeat());
      } else {
        this.time.delayedCall(900, () => this.showPhase('ACTION'));
      }
    }
  }

  private selectItem(index: number) {
    const items = Object.entries(GameState.inventory);
    if (index >= items.length) return;

    const [id] = items[index];
    this.phase = 'ANIMATING';
    this.itemGroup.setVisible(false);
    this.itemTextObjs.forEach(t => t.destroy());
    this.itemTextObjs = [];

    if (id === 'potion') {
      const healed = 20;
      this.hero.heal(healed);
      GameState.removeItem('potion');
      this.updatePlayerHPBar();
      this.setMessage(`Used Potion!\n${this.hero.name} recovered ${healed} HP!`);
      this.time.delayedCall(1000, () => this.enemyTurn());
    } else {
      this.setMessage(`Can't use ${id} here!`);
      this.time.delayedCall(800, () => this.showPhase('ACTION'));
    }
  }

  private runAway() {
    this.phase = 'ANIMATING';
    this.actionGroup.setVisible(false);

    const fleeChance = Math.min(0.99, Math.max(0.3, 0.75 + (this.hero.spd - this.enemy.spd) * 0.02));

    if (Math.random() < fleeChance) {
      this.setMessage('Got away safely!');
      this.time.delayedCall(1000, () => this.endBattle());
    } else {
      this.setMessage("Can't escape!");
      this.time.delayedCall(800, () => this.enemyTurn());
    }
  }

  private calcDamage(atkStat: number, defStat: number, power: number): number {
    const base = Math.max(1, Math.floor((atkStat / Math.max(1, defStat)) * (power / 50) * 10));
    return Math.max(1, base + Phaser.Math.Between(-Math.floor(base * 0.1), Math.floor(base * 0.1)));
  }

  // ──────────────────────────────────────────────────────────────────────────
  // Victory / Defeat
  // ──────────────────────────────────────────────────────────────────────────

  private victory() {
    this.phase = 'RESULT';
    const xp   = this.enemy.level * 12;
    const gold = this.enemy.level * 6;
    GameState.awardXP(xp);
    GameState.addGold(gold);
    GameState.save();

    // Fade out enemy
    this.tweens.add({ targets: this.enemyRect, alpha: 0, duration: 500 });

    // Flash player rect to indicate XP gained
    this.tweens.add({
      targets: this.playerRect,
      fillColor: { from: 0xffff00, to: 0xff4444 },
      duration: 400,
      yoyo: false,
      onComplete: () => { this.playerRect.setFillStyle(0xff4444); }
    });

    this.setMessage(`${this.enemy.name} fainted!\n+${xp} XP  +${gold} Gold\n[Press Enter]`);
  }

  private defeat() {
    this.phase = 'RESULT';
    // Restore to 1 HP so game is playable
    this.hero.currentHP = 1;
    GameState.save();
    this.setMessage(`${this.hero.name} blacked out!\n[Press Enter]`);
  }

  private endBattle() {
    if (this.phase === 'DONE') return;
    this.phase = 'DONE';

    this.cameras.main.fadeOut(300, 0, 0, 0, (_cam: Phaser.Cameras.Scene2D.Camera, progress: number) => {
      if (progress === 1) {
        // Resume / restart WorldScene
        const world = this.scene.get(this.returnScene) as any;
        if (world?.scene?.isActive()) {
          world.onBattleReturn?.();
          this.scene.stop();
        } else {
          this.scene.start(this.returnScene);
        }
      }
    });
  }
}

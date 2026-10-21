/**
 * Base Character class — stats match the enemy/character JSON template:
 *   maxHP, atk, def, spd, spAtk (sp.atk), spDef (sp.def)
 */
export class Character {
  id: string;
  name: string;
  maxHP: number;
  currentHP: number;
  maxMP: number;
  currentMP: number;
  atk: number;
  def: number;
  spd: number;
  spAtk: number;   // special attack
  spDef: number;   // special defence
  sprite: string;
  frames: number[];
  level: number;
  xp: number;

  constructor(
    id: string,
    name: string,
    maxHP: number,
    maxMP: number,
    atk: number,
    def: number,
    spd: number,
    spAtk: number,
    spDef: number,
    sprite: string,
    frames: number[],
    level: number = 1,
    xp: number = 0,
  ) {
    this.id       = id;
    this.name     = name;
    this.maxHP    = maxHP;
    this.currentHP = maxHP;
    this.maxMP    = maxMP;
    this.currentMP = maxMP;
    this.atk      = atk;
    this.def      = def;
    this.spd      = spd;
    this.spAtk    = spAtk;
    this.spDef    = spDef;
    this.sprite   = sprite;
    this.frames   = frames;
    this.level    = level;
    this.xp       = xp;
  }

  isDead(): boolean {
    return this.currentHP <= 0;
  }

  isAlive(): boolean {
    return !this.isDead();
  }

  takeDamage(damage: number): number {
    const actual = Math.min(this.currentHP, damage);
    this.currentHP = Math.max(0, this.currentHP - damage);
    return actual;
  }

  heal(amount: number) {
    this.currentHP = Math.min(this.maxHP, this.currentHP + amount);
  }

  restoreMP(amount: number) {
    this.currentMP = Math.min(this.maxMP, this.currentMP + amount);
  }

  fullHeal() {
    this.currentHP = this.maxHP;
    this.currentMP = this.maxMP;
  }

  hpPercent(): number {
    return Math.min(1, Math.max(0, this.currentHP / this.maxHP));
  }

  mpPercent(): number {
    return Math.min(1, Math.max(0, this.currentMP / this.maxMP));
  }

  toString(): string {
    return `${this.name} (HP:${this.currentHP}/${this.maxHP} Lv${this.level})`;
  }
}

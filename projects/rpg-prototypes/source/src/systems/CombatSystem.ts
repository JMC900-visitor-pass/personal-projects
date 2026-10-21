import { Character } from '../entities/Character';

/**
 * Combat system for turn-based battles
 */
export class CombatSystem {
  private currentState: 'PLAYER_TURN' | 'ENEMY_TURN' | 'RESOLVING' | 'VICTORY' | 'DEFEAT';
  private playerParty: Character[];
  private enemyParty: Character[];
  private battleLog: string[];

  constructor() {
    this.currentState = 'PLAYER_TURN';
    this.playerParty = [];
    this.enemyParty = [];
    this.battleLog = [];
  }

  /**
   * Initialize combat with parties
   */
  init(playerParty: Character[], enemyParty: Character[]) {
    this.playerParty = playerParty;
    this.enemyParty = enemyParty;
    this.currentState = 'PLAYER_TURN';
    this.battleLog = [];
  }

  /**
   * Player attacks an enemy
   */
  playerAttack(enemyIndex: number) {
    if (this.currentState !== 'PLAYER_TURN' || enemyIndex >= this.enemyParty.length) {
      return;
    }
    
    const player = this.playerParty[0]; // For simplicity, assume first party member
    const enemy = this.enemyParty[enemyIndex];
    
    // Calculate damage: base is atk - def (floored at 0), minimum 1 dealt
    const baseDamage = Math.max(0, player.atk - enemy.def);
    const damage = Math.max(1, baseDamage);
    enemy.takeDamage(damage);

    // Update battle log
    this.battleLog.push(`${player.name} attacks ${enemy.name} for ${damage} damage!`);

    // Check if enemy is defeated
    if (enemy.isDead()) {
      this.battleLog.push(`${enemy.name} is defeated!`);
      this.currentState = 'VICTORY';
      return;
    }

    // Switch to enemy turn
    this.currentState = 'ENEMY_TURN';
  }

  /**
   * Enemy attacks player
   */
  enemyAttack(playerIndex: number) {
    if (this.currentState !== 'ENEMY_TURN' || playerIndex >= this.playerParty.length) {
      return;
    }
    
    const enemy = this.enemyParty[0]; // For simplicity, assume first enemy
    const player = this.playerParty[playerIndex];
    
    // Calculate damage: base is atk - def (floored at 0), minimum 1 dealt
    const baseDamage = Math.max(0, enemy.atk - player.def);
    const damage = Math.max(1, baseDamage);
    player.takeDamage(damage);
    
    // Update battle log
    this.battleLog.push(`${enemy.name} attacks ${player.name} for ${damage} damage!`);
    
    // Check if player is defeated
    if (player.isDead()) {
      this.battleLog.push(`${player.name} is defeated!`);
    }
    
    // Resolve victory/defeat conditions synchronously
    if (this.checkVictory()) {
      this.currentState = 'VICTORY';
    } else if (this.checkDefeat()) {
      this.currentState = 'DEFEAT';
    } else {
      this.currentState = 'PLAYER_TURN';
    }
  }

  /**
   * Use an item on a target
   */
  useItem(itemName: string, targetIndex: number): boolean {
    if (targetIndex >= this.playerParty.length) {
      return false;
    }
    
    // In a real implementation, this would look up the item and apply its effect
    // For now we just simulate a healing effect
    const target = this.playerParty[targetIndex];
    const healAmount = 10;
    target.heal(healAmount);
    this.battleLog.push(`${target.name} is healed for ${healAmount} HP!`);
    
    return true;
  }

  /**
   * Check if victory conditions are met. Updates state to VICTORY if so.
   */
  checkVictory(): boolean {
    const victory = this.enemyParty.every(enemy => enemy.isDead());
    if (victory) this.currentState = 'VICTORY';
    return victory;
  }

  /**
   * Check if defeat conditions are met. Updates state to DEFEAT if so.
   */
  checkDefeat(): boolean {
    const defeat = this.playerParty.every(player => player.isDead());
    if (defeat) this.currentState = 'DEFEAT';
    return defeat;
  }

  /**
   * Get current battle state
   */
  getState(): string {
    return this.currentState;
  }

  /**
   * Get battle log
   */
  getLog(): string[] {
    return this.battleLog;
  }

  /**
   * Get player party
   */
  getPlayerParty(): Character[] {
    return this.playerParty;
  }

  /**
   * Get enemy party
   */
  getEnemyParty(): Character[] {
    return this.enemyParty;
  }
}
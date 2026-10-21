/**
 * Time-related utilities for the game
 *
 * Use for non-Phaser async flows only.
 * Inside Phaser scenes, prefer this.time.delayedCall() instead.
 */
export class Time {
  /**
   * Simple delay function using Promises
   * @param ms - milliseconds to wait
   * @returns Promise that resolves after ms milliseconds
   */
  static delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}
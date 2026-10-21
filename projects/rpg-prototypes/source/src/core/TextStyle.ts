import Phaser from 'phaser';

/**
 * Global pixel-text style helper.
 *
 * Merges caller overrides with the shared base:
 *   fontFamily: 'monospace'
 *   resolution: 4   ← renders text at native size then scales up, giving crisp pixel edges
 *
 * Usage in any scene:
 *   this.add.text(x, y, 'Hello', txt({ fontSize: '8px', color: '#ffffff' }))
 */
export function txt(
  overrides: Phaser.Types.GameObjects.Text.TextStyle,
): Phaser.Types.GameObjects.Text.TextStyle {
  return {
    fontFamily: '"Press Start 2P", monospace',
    ...overrides,
  };
}

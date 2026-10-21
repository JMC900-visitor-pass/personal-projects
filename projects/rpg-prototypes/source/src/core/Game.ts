import Phaser from 'phaser';
import { State, GameState } from './State';
import BootScene    from '../scenes/BootScene';
import LoadingScene from '../scenes/LoadingScene';
import TitleScene   from '../scenes/TitleScene';
import WorldScene   from '../scenes/WorldScene';
import BattleScene  from '../scenes/BattleScene';
import MenuScene    from '../scenes/MenuScene';
import SettingsScene from '../scenes/SettingsScene';

/**
 * Main Phaser Game class.
 *
 * Base resolution: 320x180 (16:9).
 * Default zoom: 4x → displayed at 1280x720.
 * All sprites are rendered nearest-neighbour (pixelArt: true).
 */
export class Game extends Phaser.Game {
  constructor() {
    // Mount element
    if (!document.getElementById('game-container')) {
      const container = document.createElement('div');
      container.id = 'game-container';
      document.body.appendChild(container);
    }

    // Load persisted settings before constructing so zoom is correct
    GameState.loadSettings();
    const zoom = GameState.settings.zoom ?? 4;

    super({
      width:  320,
      height: 180,
      zoom,
      parent: 'game-container',
      backgroundColor: '#000000',
      render: {
        pixelArt: true,
        antialias: false,
        antialiasGL: false,
        roundPixels: true,
      },
      physics: {
        default: 'arcade',
        arcade: {
          gravity: { x: 0, y: 0 },
          debug: false,
        },
      },
      scale: {
        mode: Phaser.Scale.NONE,
        autoCenter: Phaser.Scale.CENTER_BOTH,
      },
      scene: [
        BootScene,
        LoadingScene,
        TitleScene,
        WorldScene,
        BattleScene,
        MenuScene,
        SettingsScene,
      ],
    });
  }
}

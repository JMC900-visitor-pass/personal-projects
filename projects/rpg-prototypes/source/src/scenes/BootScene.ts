import Phaser from 'phaser';
import { State } from '../core/State';

export default class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: State.BOOT });
  }

  preload() {
    // Nothing essential to load before the loading screen.
  }

  create() {
    this.scene.start(State.LOADING);
  }
}

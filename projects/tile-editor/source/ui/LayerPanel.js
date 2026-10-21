'use strict';

/**
 * LayerPanel — displays all tile layers, lets the user toggle visibility,
 * adjust opacity, add/remove/reorder layers, and switch the active layer.
 */
class LayerPanel {
  /**
   * @param {HTMLElement} container
   * @param {object} state
   */
  constructor(container, state) {
    this.container = container;
    this.state = state;

    /** @type {Function|null} Called when active layer changes. */
    this.onLayerChanged = null;

    this._build();
  }

  /**
   * Build the static header + dynamic list area.
   */
  _build() {
    this.container.innerHTML = '';

    const header = document.createElement('div');
    header.className = 'panel-header';
    header.innerHTML = '<span>Layers</span>';

    // Add layer button
    const addBtn = document.createElement('button');
    addBtn.className = 'btn btn-sm';
    addBtn.textContent = '+';
    addBtn.title = 'Add new layer';
    addBtn.addEventListener('click', () => this._addLayer());
    header.appendChild(addBtn);
    this.container.appendChild(header);

    this._listEl = document.createElement('div');
    this._listEl.className = 'layer-list';
    this.container.appendChild(this._listEl);
    this.refresh();
  }

  /**
   * Re-render the layer list from current state.
   */
  refresh() {
    const { tileMap, activeLayerIndex } = this.state;
    this._listEl.innerHTML = '';

    // Render layers in reverse order (top layer shown at top of list)
    for (let i = tileMap.layers.length - 1; i >= 0; i--) {
      const layer = tileMap.layers[i];
      const isActive = i === activeLayerIndex;

      const item = document.createElement('div');
      item.className = 'layer-item' + (isActive ? ' active' : '');
      item.dataset.index = i;

      // Visibility toggle
      const eyeBtn = document.createElement('button');
      eyeBtn.className = 'layer-eye-btn';
      eyeBtn.title = 'Toggle visibility';
      eyeBtn.textContent = layer.visible ? '●' : '○';
      eyeBtn.style.opacity = layer.visible ? '1' : '0.4';
      eyeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        layer.visible = !layer.visible;
        this.refresh();
      });

      // Name label
      const nameSpan = document.createElement('span');
      nameSpan.className = 'layer-name';
      nameSpan.textContent = layer.name;
      nameSpan.contentEditable = true;
      nameSpan.spellcheck = false;
      nameSpan.addEventListener('blur', () => {
        layer.name = nameSpan.textContent.trim() || layer.name;
        this.refresh();
      });
      nameSpan.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); nameSpan.blur(); }
      });

      // Opacity slider
      const opacitySlider = document.createElement('input');
      opacitySlider.type = 'range';
      opacitySlider.min = '0';
      opacitySlider.max = '100';
      opacitySlider.value = Math.round(layer.opacity * 100);
      opacitySlider.className = 'layer-opacity';
      opacitySlider.title = `Opacity: ${Math.round(layer.opacity * 100)}%`;
      opacitySlider.addEventListener('input', (e) => {
        e.stopPropagation();
        layer.opacity = parseInt(opacitySlider.value, 10) / 100;
        opacitySlider.title = `Opacity: ${Math.round(layer.opacity * 100)}%`;
      });

      // Controls: move up, move down, delete
      const ctrlDiv = document.createElement('div');
      ctrlDiv.className = 'layer-controls';

      const upBtn = document.createElement('button');
      upBtn.textContent = '↑';
      upBtn.title = 'Move layer up';
      upBtn.disabled = i >= tileMap.layers.length - 1;
      upBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        tileMap.moveLayer(i, i + 1);
        if (this.state.activeLayerIndex === i) this.state.activeLayerIndex = i + 1;
        else if (this.state.activeLayerIndex === i + 1) this.state.activeLayerIndex = i;
        this.refresh();
        if (this.onLayerChanged) this.onLayerChanged();
      });

      const downBtn = document.createElement('button');
      downBtn.textContent = '↓';
      downBtn.title = 'Move layer down';
      downBtn.disabled = i <= 0;
      downBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        tileMap.moveLayer(i, i - 1);
        if (this.state.activeLayerIndex === i) this.state.activeLayerIndex = i - 1;
        else if (this.state.activeLayerIndex === i - 1) this.state.activeLayerIndex = i;
        this.refresh();
        if (this.onLayerChanged) this.onLayerChanged();
      });

      const delBtn = document.createElement('button');
      delBtn.textContent = '✕';
      delBtn.title = 'Delete layer';
      delBtn.disabled = tileMap.layers.length <= 1;
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!confirm(`Delete layer "${layer.name}"?`)) return;
        tileMap.removeLayer(i);
        if (this.state.activeLayerIndex >= tileMap.layers.length) {
          this.state.activeLayerIndex = tileMap.layers.length - 1;
        }
        this.refresh();
        if (this.onLayerChanged) this.onLayerChanged();
      });

      ctrlDiv.appendChild(upBtn);
      ctrlDiv.appendChild(downBtn);
      ctrlDiv.appendChild(delBtn);

      item.appendChild(eyeBtn);
      item.appendChild(nameSpan);
      item.appendChild(opacitySlider);
      item.appendChild(ctrlDiv);

      // Click row to select layer
      item.addEventListener('click', () => {
        this.state.activeLayerIndex = i;
        this.refresh();
        if (this.onLayerChanged) this.onLayerChanged();
      });

      this._listEl.appendChild(item);
    }
  }

  /**
   * Add a new layer with a generated name.
   */
  _addLayer() {
    const name = `Layer ${this.state.tileMap.layers.length + 1}`;
    this.state.tileMap.addLayer(name);
    this.state.activeLayerIndex = this.state.tileMap.layers.length - 1;
    this.refresh();
    if (this.onLayerChanged) this.onLayerChanged();
  }
}

window.LayerPanel = LayerPanel;

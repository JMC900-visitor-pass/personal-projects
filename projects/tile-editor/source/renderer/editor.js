'use strict';

// ============================================================
//  UNDO/REDO COMMAND STACK
// ============================================================

/**
 * Manages the undo/redo history as batched command groups.
 */
class UndoStack {
  constructor(state) {
    this.state = state;
    /** @type {Array<object[]>} Committed batches */
    this._history = [];
    /** @type {object[]} Uncommitted batch being built */
    this._pending = [];
    /** @type {number} Position in history (for redo) */
    this._cursor = -1; // points to last committed item
  }

  /**
   * Push a tile paint change into the pending batch.
   * @param {number} layerIdx
   * @param {number} x
   * @param {number} y
   * @param {number} prevId
   * @param {number} newId
   */
  pushTilePaint(layerIdx, x, y, prevId, newId) {
    this._pending.push({ type: 'tile', layerIdx, x, y, prevId, newId });
  }

  /**
   * Push a collision change into the pending batch.
   */
  pushCollisionPaint(x, y, prevVal, newVal) {
    this._pending.push({ type: 'collision', x, y, prevVal, newVal });
  }

  /**
   * Push a flood-fill operation (committed immediately as one batch).
   */
  pushFill(layerIdx, painted, newId) {
    const batch = painted.map(({ x, y, prev }) => ({
      type: 'tile', layerIdx, x, y, prevId: prev, newId
    }));
    this._commit(batch);
  }

  /**
   * Push an object placement.
   */
  pushObjectPlace(obj) {
    this._commit([{ type: 'obj-place', obj: Object.assign({}, obj, { properties: Object.assign({}, obj.properties) }) }]);
  }

  /**
   * Push an object deletion.
   */
  pushObjectDelete(obj) {
    this._commit([{ type: 'obj-delete', obj: Object.assign({}, obj, { properties: Object.assign({}, obj.properties) }) }]);
  }

  /**
   * Commit the current pending batch to history.
   */
  commit() {
    if (this._pending.length === 0) return;
    this._commit(this._pending);
    this._pending = [];
  }

  _commit(batch) {
    if (batch.length === 0) return;
    // Discard any redo history beyond current cursor
    if (this._cursor < this._history.length - 1) {
      this._history = this._history.slice(0, this._cursor + 1);
    }
    this._history.push(batch);
    this._cursor = this._history.length - 1;
    // Limit history to 200 batches
    if (this._history.length > 200) {
      this._history.shift();
      this._cursor = this._history.length - 1;
    }
  }

  /**
   * Undo the last committed batch.
   */
  undo() {
    this._pending = []; // Discard any in-progress stroke
    if (this._cursor < 0) return;
    const batch = this._history[this._cursor];
    this._cursor--;
    this._applyBatch(batch, true);
  }

  /**
   * Redo the next batch.
   */
  redo() {
    if (this._cursor >= this._history.length - 1) return;
    this._cursor++;
    const batch = this._history[this._cursor];
    this._applyBatch(batch, false);
  }

  /**
   * Apply a batch of changes in forward or reverse direction.
   * @param {object[]} batch
   * @param {boolean} reverse - If true, apply the "undo" of each command.
   */
  _applyBatch(batch, reverse) {
    const { tileMap } = this.state;
    const items = reverse ? [...batch].reverse() : batch;
    for (const cmd of items) {
      if (cmd.type === 'tile') {
        tileMap.setTile(cmd.layerIdx, cmd.x, cmd.y, reverse ? cmd.prevId : cmd.newId);
      } else if (cmd.type === 'collision') {
        tileMap.setCollision(cmd.x, cmd.y, reverse ? cmd.prevVal : cmd.newVal);
      } else if (cmd.type === 'obj-place') {
        if (reverse) {
          tileMap.objectLayer.remove(cmd.obj.id);
        } else {
          tileMap.objectLayer.objects.set(cmd.obj.id, Object.assign({}, cmd.obj, { properties: Object.assign({}, cmd.obj.properties) }));
        }
        if (this.state.onObjectsChanged) this.state.onObjectsChanged();
      } else if (cmd.type === 'obj-delete') {
        if (reverse) {
          tileMap.objectLayer.objects.set(cmd.obj.id, Object.assign({}, cmd.obj, { properties: Object.assign({}, cmd.obj.properties) }));
        } else {
          tileMap.objectLayer.remove(cmd.obj.id);
        }
        if (this.state.onObjectsChanged) this.state.onObjectsChanged();
      }
    }
  }

  get canUndo() { return this._cursor >= 0; }
  get canRedo() { return this._cursor < this._history.length - 1; }
}

// ============================================================
//  MAIN EDITOR CONTROLLER
// ============================================================

/**
 * Editor — wires all modules together and drives the application.
 */
class Editor {
  constructor() {
    // Shared mutable state object passed to all subsystems
    this.state = {
      tileMap: null,
      activeLayerIndex: 0,
      selectedTileId: 0,
      tileStamp: null,
      selectedObjectId: null,
      selectedObjectType: 'npc',
      activeTool: 'brush',
      showGrid: true,
      showCollision: false,
      renderer: null,
      undoStack: null,
      onObjectSelected: null,
      onObjectsChanged: null,
      onTileSelected: null
    };

    /** @type {string|null} Current save file path */
    this.currentFilePath = null;
    /** @type {boolean} */
    this.dirty = false;

    // Canvas + mouse tracking
    this._mouseDown = false;
    this._middleDown = false;
    this._lastMouseX = 0;
    this._lastMouseY = 0;
    this._rightButtonDown = false;

    // requestAnimationFrame handle
    this._rafHandle = null;
  }

  /**
   * Bootstrap everything. Called once the DOM is ready.
   */
  async init() {
    // Create initial map
    const map = new TileMap(50, 50, 16);
    this.state.tileMap = map;

    // Undo stack
    this.state.undoStack = new UndoStack(this.state);

    // Canvas setup
    this._canvas = document.getElementById('mapCanvas');
    this._resizeCanvas();

    // Camera
    this._camera = new Camera(0, 0, 2);
    this.state.camera = this._camera;

    // Renderer
    const renderer = new MapRenderer(this._canvas, this._camera, map);
    this.state.renderer = renderer;
    renderer.showGrid = this.state.showGrid;
    renderer.showCollision = this.state.showCollision;

    // Tools
    this._tools = {
      brush:      new BrushTool(this.state),
      eraser:     new EraserTool(this.state),
      fill:       new FillTool(this.state),
      eyedropper: new EyedropperTool(this.state),
      object:     new ObjectTool(this.state),
      collision:  new CollisionTool(this.state)
    };
    this._activeTool = this._tools['brush'];

    // Build UI panels
    this._buildTilesetPanel();
    this._buildLayerPanel();
    this._buildInspectorPanel();
    this._buildObjectPanel();
    this._buildToolbar();

    // Wire state callbacks
    this.state.onObjectSelected = (obj) => {
      this._inspector.showObject(obj);
    };
    this.state.onObjectsChanged = () => {
      this._refreshObjectList();
    };
    this.state.onTileSelected = (id) => {
      this._tilesetPanel.selectTile(id);
    };

    // Event listeners
    this._bindCanvasEvents();
    this._bindKeyboard();
    this._bindWindowEvents();
    this._bindMenuEvents();

    // Start render loop
    this._loop();

    // Try to load the bundled sample tileset automatically
    this._loadBuiltinTileset();

    // Autosave timer
    setInterval(() => this._autoSave(), 30000);

    // Restore autosaved data (after tileset load attempt)
    setTimeout(() => this._loadAutoSave(), 300);

    this._updateTitle();
  }

  /**
   * Load the built-in sample tileset from the assets folder at startup.
   * This gives users an immediate visual to work with.
   */
  async _loadBuiltinTileset() {
    try {
      // __dirname is not available in the renderer, so we resolve
      // relative to the current document URL.
      const tilesetUrl = new URL('../assets/tileset.png', document.location.href).href;
      await this._tilesetPanel.loadFromDataUrl(tilesetUrl, '');
      this.state.tileMap.tilesetPath = '';
    } catch (e) {
      // Silently ignore — user can import their own tileset
    }
  }

  // ---- Panel builders ----

  _buildTilesetPanel() {
    const container = document.getElementById('tilesetPanel');
    this._tilesetPanel = new TilesetPanel(container, this.state);
    this._tilesetPanel.onTileSelected = (id) => {
      this.state.selectedTileId = id;
      // Switch back to brush when picking from tileset
      if (this.state.activeTool !== 'brush' && this.state.activeTool !== 'fill') {
        this._setTool('brush');
      }
    };
  }

  _buildLayerPanel() {
    const container = document.getElementById('layerPanel');
    this._layerPanel = new LayerPanel(container, this.state);
    this._layerPanel.onLayerChanged = () => {
      this._updateStatus();
    };
  }

  _buildInspectorPanel() {
    const container = document.getElementById('inspectorPanel');
    this._inspector = new InspectorPanel(container, this.state);
    this._inspector.onObjectDeleted = () => {
      this._refreshObjectList();
    };
    this._inspector.onObjectChanged = () => {
      this._markDirty();
    };
  }

  _buildObjectPanel() {
    const container = document.getElementById('objectPanel');
    container.innerHTML = '';

    const header = document.createElement('div');
    header.className = 'panel-header';
    header.innerHTML = '<span>Objects</span>';
    container.appendChild(header);

    // Object type selector
    const typeDiv = document.createElement('div');
    typeDiv.className = 'object-type-selector';
    const types = ['npc', 'chest', 'door', 'teleporter', 'sign', 'encounter'];
    for (const t of types) {
      const btn = document.createElement('button');
      btn.className = 'obj-type-btn' + (t === this.state.selectedObjectType ? ' active' : '');
      btn.textContent = t.charAt(0).toUpperCase() + t.slice(1);
      btn.dataset.type = t;
      btn.addEventListener('click', () => {
        document.querySelectorAll('.obj-type-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.state.selectedObjectType = t;
        this._setTool('object');
      });
      typeDiv.appendChild(btn);
    }
    container.appendChild(typeDiv);

    // Object list
    this._objectListEl = document.createElement('div');
    this._objectListEl.className = 'object-list';
    container.appendChild(this._objectListEl);

    this._refreshObjectList();
  }

  _refreshObjectList() {
    if (!this._objectListEl) return;
    this._objectListEl.innerHTML = '';
    const objects = this.state.tileMap.objectLayer.getAll();
    if (objects.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'inspector-empty';
      empty.textContent = 'No objects placed';
      this._objectListEl.appendChild(empty);
      return;
    }

    for (const obj of objects) {
      const item = document.createElement('div');
      item.className = 'object-list-item' + (obj.id === this.state.selectedObjectId ? ' active' : '');
      item.textContent = `#${obj.id} ${obj.type} (${obj.x}, ${obj.y})`;
      item.addEventListener('click', () => {
        this.state.selectedObjectId = obj.id;
        this.state.renderer.selectedObjectId = obj.id;
        this._inspector.showObject(obj);
        this._refreshObjectList();
      });
      this._objectListEl.appendChild(item);
    }
  }

  _buildToolbar() {
    const toolbar = document.getElementById('toolbar');

    // Tool buttons
    const toolDefs = [
      { id: 'brush',      icon: '✏',  title: 'Brush (B)' },
      { id: 'eraser',     icon: '⌫',  title: 'Eraser (E)' },
      { id: 'fill',       icon: '⬛',  title: 'Fill (F)' },
      { id: 'eyedropper', icon: '🔍', title: 'Eyedropper (I)' },
      { id: 'collision',  icon: '⛔',  title: 'Collision Paint (X)' },
      { id: 'object',     icon: '📍',  title: 'Object Tool (O)' }
    ];

    this._toolButtons = {};

    for (const def of toolDefs) {
      const btn = document.createElement('button');
      btn.className = 'toolbar-btn' + (def.id === this.state.activeTool ? ' active' : '');
      btn.title = def.title;
      btn.textContent = def.icon;
      btn.dataset.tool = def.id;
      btn.addEventListener('click', () => this._setTool(def.id));
      toolbar.appendChild(btn);
      this._toolButtons[def.id] = btn;
    }

    // Separator
    const sep = document.createElement('span');
    sep.className = 'toolbar-sep';
    toolbar.appendChild(sep);

    // Grid toggle
    const gridBtn = document.createElement('button');
    gridBtn.id = 'gridToggleBtn';
    gridBtn.className = 'toolbar-btn' + (this.state.showGrid ? ' active' : '');
    gridBtn.title = 'Toggle Grid (G)';
    gridBtn.textContent = '⊞';
    gridBtn.addEventListener('click', () => this._toggleGrid());
    toolbar.appendChild(gridBtn);

    // Collision toggle
    const collBtn = document.createElement('button');
    collBtn.id = 'collisionToggleBtn';
    collBtn.className = 'toolbar-btn' + (this.state.showCollision ? ' active' : '');
    collBtn.title = 'Toggle Collision Overlay (C)';
    collBtn.textContent = '⛔';
    collBtn.addEventListener('click', () => this._toggleCollision());
    toolbar.appendChild(collBtn);

    // Separator
    const sep2 = document.createElement('span');
    sep2.className = 'toolbar-sep';
    toolbar.appendChild(sep2);

    // Zoom controls
    const zoomOutBtn = document.createElement('button');
    zoomOutBtn.className = 'toolbar-btn';
    zoomOutBtn.title = 'Zoom Out (-)';
    zoomOutBtn.textContent = '−';
    zoomOutBtn.addEventListener('click', () => this._zoom(1 / 1.25));
    toolbar.appendChild(zoomOutBtn);

    this._zoomLabel = document.createElement('span');
    this._zoomLabel.className = 'zoom-label';
    this._zoomLabel.id = 'zoomLabel';
    this._zoomLabel.textContent = '200%';
    toolbar.appendChild(this._zoomLabel);

    const zoomInBtn = document.createElement('button');
    zoomInBtn.className = 'toolbar-btn';
    zoomInBtn.title = 'Zoom In (+)';
    zoomInBtn.textContent = '+';
    zoomInBtn.addEventListener('click', () => this._zoom(1.25));
    toolbar.appendChild(zoomInBtn);

    const zoomResetBtn = document.createElement('button');
    zoomResetBtn.className = 'toolbar-btn';
    zoomResetBtn.title = 'Reset Zoom';
    zoomResetBtn.textContent = '1:1';
    zoomResetBtn.addEventListener('click', () => {
      this._camera.setZoom(1, this._canvas.width, this._canvas.height);
      this._updateZoomLabel();
    });
    toolbar.appendChild(zoomResetBtn);
  }

  // ---- Tool management ----

  _setTool(name) {
    if (!this._tools[name]) return;
    this.state.activeTool = name;
    this._activeTool = this._tools[name];

    // Update button states
    for (const [id, btn] of Object.entries(this._toolButtons)) {
      btn.classList.toggle('active', id === name);
    }

    // Cursor
    this._canvas.style.cursor = this._activeTool.cursor || 'default';
    this._updateStatus();
  }

  // ---- Canvas event binding ----

  _bindCanvasEvents() {
    const canvas = this._canvas;

    canvas.addEventListener('mousedown', (e) => {
      e.preventDefault();
      canvas.focus();

      if (e.button === 1) {
        // Middle button: pan
        this._middleDown = true;
        this._lastMouseX = e.clientX;
        this._lastMouseY = e.clientY;
        canvas.style.cursor = 'grabbing';
        return;
      }

      this._mouseDown = true;
      this._rightButtonDown = e.button === 2;

      const { tx, ty } = this._getMouseTile(e);

      if (e.button === 2 && this.state.activeTool === 'collision') {
        this._activeTool.onMouseDown(tx, ty, true);
      } else if (e.button !== 2) {
        this._activeTool.onMouseDown(tx, ty);
      }
      this._markDirty();
    });

    canvas.addEventListener('mousemove', (e) => {
      const { tx, ty } = this._getMouseTile(e);

      // Update hover
      this.state.renderer.hoverTile = { x: tx, y: ty };

      // Middle-drag pan
      if (this._middleDown) {
        const dx = e.clientX - this._lastMouseX;
        const dy = e.clientY - this._lastMouseY;
        this._camera.pan(dx, dy);
        this._lastMouseX = e.clientX;
        this._lastMouseY = e.clientY;
      }

      if (this._mouseDown) {
        this._activeTool.onMouseMove(tx, ty);
        this._markDirty();
      }

      this._updateStatus(tx, ty);
    });

    const onMouseUp = (e) => {
      if (e.button === 1) {
        this._middleDown = false;
        canvas.style.cursor = this._activeTool ? this._activeTool.cursor : 'default';
        return;
      }
      if (this._mouseDown) {
        this._activeTool.onMouseUp();
        this._mouseDown = false;
      }
    };

    canvas.addEventListener('mouseup', onMouseUp);
    window.addEventListener('mouseup', onMouseUp);

    canvas.addEventListener('mouseleave', () => {
      this.state.renderer.hoverTile = null;
    });

    // Context menu: suppress
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());

    // Mouse wheel zoom
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      const rect = canvas.getBoundingClientRect();
      this._camera.zoomAt(factor, e.clientX - rect.left, e.clientY - rect.top);
      this._updateZoomLabel();
    }, { passive: false });
  }

  /**
   * Get the tile coordinates under the mouse event.
   * @param {MouseEvent} e
   * @returns {{ tx: number, ty: number }}
   */
  _getMouseTile(e) {
    const rect = this._canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    const { tx, ty } = this._camera.screenToTile(sx, sy, this.state.tileMap.tileSize);
    return { tx, ty };
  }

  // ---- Keyboard ----

  _bindKeyboard() {
    window.addEventListener('keydown', (e) => {
      // Don't intercept if typing in an input
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;

      const ctrl = e.ctrlKey || e.metaKey;

      if (ctrl && e.key === 'z') { e.preventDefault(); this.state.undoStack.undo(); return; }
      if (ctrl && (e.key === 'y' || (e.shiftKey && e.key === 'Z'))) { e.preventDefault(); this.state.undoStack.redo(); return; }
      if (ctrl && e.key === 's') { e.preventDefault(); this._saveMap(); return; }
      if (ctrl && e.key === 'n') { e.preventDefault(); this._newMap(); return; }
      if (ctrl && e.key === 'o') { e.preventDefault(); this._openMap(); return; }

      // Tool shortcuts (no modifier)
      if (!ctrl) {
        switch (e.key.toLowerCase()) {
          case 'b': this._setTool('brush'); break;
          case 'e': this._setTool('eraser'); break;
          case 'f': this._setTool('fill'); break;
          case 'i': this._setTool('eyedropper'); break;
          case 'o': this._setTool('object'); break;
          case 'x': this._setTool('collision'); break;
          case 'g': this._toggleGrid(); break;
          case 'c': this._toggleCollision(); break;
          case '+': case '=': this._zoom(1.25); break;
          case '-': case '_': this._zoom(1 / 1.25); break;

          // Arrow key pan
          case 'arrowleft':  this._camera.pan(16, 0); break;
          case 'arrowright': this._camera.pan(-16, 0); break;
          case 'arrowup':    this._camera.pan(0, 16); break;
          case 'arrowdown':  this._camera.pan(0, -16); break;
        }
      }
    });
  }

  // ---- Window resize ----

  _bindWindowEvents() {
    window.addEventListener('resize', () => this._resizeCanvas());
  }

  // ---- Menu events from Electron ----

  _bindMenuEvents() {
    if (!window.electronAPI) return;

    window.electronAPI.onMenu('menu:new-map',       () => this._newMap());
    window.electronAPI.onMenu('menu:open-map',      () => this._openMap());
    window.electronAPI.onMenu('menu:save-map',      () => this._saveMap());
    window.electronAPI.onMenu('menu:save-map-as',   () => this._saveMapAs());
    window.electronAPI.onMenu('menu:export-json',   () => this._exportJSON());
    window.electronAPI.onMenu('menu:import-tileset',() => this._tilesetPanel._importTileset());
    window.electronAPI.onMenu('menu:undo',          () => this.state.undoStack.undo());
    window.electronAPI.onMenu('menu:redo',          () => this.state.undoStack.redo());
    window.electronAPI.onMenu('menu:toggle-grid',   () => this._toggleGrid());
    window.electronAPI.onMenu('menu:toggle-collision', () => this._toggleCollision());
    window.electronAPI.onMenu('menu:zoom-in',       () => this._zoom(1.25));
    window.electronAPI.onMenu('menu:zoom-out',      () => this._zoom(1 / 1.25));
    window.electronAPI.onMenu('menu:zoom-reset',    () => {
      this._camera.setZoom(1, this._canvas.width, this._canvas.height);
      this._updateZoomLabel();
    });
    window.electronAPI.onMenu('menu:resize-map',    () => this._showResizeDialog());
    window.electronAPI.onMenu('menu:map-properties',() => this._showMapPropertiesDialog());
  }

  // ---- Render loop ----

  _loop() {
    this.state.renderer.render();
    this._rafHandle = requestAnimationFrame(() => this._loop());
  }

  // ---- Canvas resize ----

  _resizeCanvas() {
    const canvas = this._canvas;
    const container = canvas.parentElement;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    canvas.width = Math.floor(rect.width);
    canvas.height = Math.floor(rect.height);
  }

  // ---- View toggles ----

  _toggleGrid() {
    this.state.showGrid = !this.state.showGrid;
    this.state.renderer.showGrid = this.state.showGrid;
    const btn = document.getElementById('gridToggleBtn');
    if (btn) btn.classList.toggle('active', this.state.showGrid);
  }

  _toggleCollision() {
    this.state.showCollision = !this.state.showCollision;
    this.state.renderer.showCollision = this.state.showCollision;
    const btn = document.getElementById('collisionToggleBtn');
    if (btn) btn.classList.toggle('active', this.state.showCollision);
  }

  _zoom(factor) {
    this._camera.zoomAt(factor, this._canvas.width / 2, this._canvas.height / 2);
    this._updateZoomLabel();
  }

  _updateZoomLabel() {
    const pct = Math.round(this._camera.zoom * 100);
    if (this._zoomLabel) this._zoomLabel.textContent = pct + '%';
    const el = document.getElementById('statusZoom');
    if (el) el.textContent = pct + '%';
  }

  // ---- File operations ----

  async _newMap() {
    if (this.dirty && !confirm('Unsaved changes will be lost. Continue?')) return;

    // BUG-1/2 fix: use HTML <dialog> instead of prompt() which is unreliable in Electron
    const result = await this._showNewMapDialog();
    if (!result) return; // user cancelled

    const { name, width, height, tileSize } = result;

    this.state.tileMap = new TileMap(width, height, tileSize);
    this.state.tileMap.name = name;
    this.state.activeLayerIndex = 0;
    this.state.selectedObjectId = null;
    this.state.renderer.selectedObjectId = null; // BUG-4 fix: clear stale renderer selection
    this.currentFilePath = null;
    // Sync panel tileSize so _recompute() uses the correct grid on next import
    this._tilesetPanel.setTileSize(tileSize);

    this.state.renderer.tileMap = this.state.tileMap;
    this.state.renderer.tilesetCanvas = null;
    this.state.renderer.tilesetImage = null;

    // Reset undo
    this.state.undoStack = new UndoStack(this.state);
    for (const tool of Object.values(this._tools)) tool.state = this.state;

    this._tilesetPanel.image = null;
    this._tilesetPanel.canvas.width = 0;
    this._tilesetPanel.canvas.height = 0;
    this._tilesetPanel._placeholder.style.display = '';

    this._layerPanel.refresh();
    this._inspector.clear();
    this._refreshObjectList();

    this.dirty = false;
    this._updateTitle();
  }

  /**
   * Show a styled HTML <dialog> to collect new map settings.
   * Returns { name, width, height, tileSize } or null if cancelled.
   * @returns {Promise<{name:string,width:number,height:number,tileSize:number}|null>}
   */
  _showNewMapDialog() {
    return new Promise((resolve) => {
      const existing = document.getElementById('newMapDialog');
      if (existing) existing.remove();

      const dlg = document.createElement('dialog');
      dlg.id = 'newMapDialog';
      dlg.innerHTML = `
        <form class="new-map-form">
          <h3 class="dialog-title">New Map</h3>
          <div class="dialog-field">
            <label>Map Name <input type="text" name="mapName" value="Untitled Map" /></label>
          </div>
          <div class="dialog-field">
            <label>Width (tiles) <input type="number" name="width" value="50" min="1" max="500" /></label>
          </div>
          <div class="dialog-field">
            <label>Height (tiles) <input type="number" name="height" value="50" min="1" max="500" /></label>
          </div>
          <div class="dialog-field">
            <label>Tile Size (px)
              <select name="tileSize">
                <option value="8">8</option>
                <option value="16" selected>16</option>
                <option value="32">32</option>
                <option value="48">48</option>
              </select>
            </label>
          </div>
          <div class="dialog-buttons">
            <button type="button" id="newMapCancel">Cancel</button>
            <button type="submit">Create Map</button>
          </div>
        </form>
      `;

      document.body.appendChild(dlg);

      const done = (val) => { dlg.close(); dlg.remove(); resolve(val); };

      dlg.querySelector('#newMapCancel').addEventListener('click', () => done(null));

      dlg.querySelector('form').addEventListener('submit', (e) => {
        e.preventDefault();
        const f = dlg.querySelector('form');
        done({
          name:     f.querySelector('[name=mapName]').value.trim() || 'Untitled Map',
          width:    Math.max(1, Math.min(500, parseInt(f.querySelector('[name=width]').value, 10) || 50)),
          height:   Math.max(1, Math.min(500, parseInt(f.querySelector('[name=height]').value, 10) || 50)),
          tileSize: parseInt(f.querySelector('[name=tileSize]').value, 10) || 16
        });
      });

      // Click the backdrop (outside the form) to cancel
      dlg.addEventListener('click', (e) => { if (e.target === dlg) done(null); });

      dlg.showModal();
      dlg.querySelector('[name=mapName]').select();
    });
  }

  async _openMap() {
    if (this.dirty && !confirm('Unsaved changes will be lost. Continue?')) return;

    const result = await window.electronAPI.showOpenDialog({
      title: 'Open Map',
      filters: [{ name: 'Map JSON', extensions: ['json'] }],
      properties: ['openFile']
    });
    if (result.canceled || !result.filePaths.length) return;

    const filePath = result.filePaths[0];
    const res = await window.electronAPI.readFile(filePath);
    if (!res.ok) { alert('Failed to open: ' + res.error); return; }

    try {
      const newMap = MapExporter.importFromJSON(res.data);
      this.state.tileMap = newMap;
      this.state.activeLayerIndex = 0;
      this.state.selectedObjectId = null;
      this.currentFilePath = filePath;

      this.state.renderer.tileMap = newMap;
      this.state.undoStack = new UndoStack(this.state);
      for (const tool of Object.values(this._tools)) tool.state = this.state;

      this._layerPanel.refresh();
      this._inspector.clear();
      this._refreshObjectList();

      // Sync panel tileSize BEFORE reloading the tileset so _recompute() uses
      // the correct grid column count that matches the loaded map's tileSize.
      this._tilesetPanel.setTileSize(newMap.tileSize);

      // Load tileset if path is saved
      if (newMap.tilesetPath) {
        const imgRes = await window.electronAPI.readFileBase64(newMap.tilesetPath);
        if (imgRes.ok) {
          await this._tilesetPanel.loadFromDataUrl(imgRes.data, newMap.tilesetPath);
        }
      }

      this.dirty = false;
      this._updateTitle();
    } catch (e) {
      alert('Failed to parse map file: ' + e.message);
    }
  }

  async _saveMap() {
    if (this.currentFilePath) {
      await this._writemap(this.currentFilePath);
    } else {
      await this._saveMapAs();
    }
  }

  async _saveMapAs() {
    const result = await window.electronAPI.showSaveDialog({
      title: 'Save Map',
      filters: [{ name: 'Map JSON', extensions: ['json'] }],
      defaultPath: 'map.json'
    });
    if (result.canceled || !result.filePath) return;
    this.currentFilePath = result.filePath;
    await this._writemap(result.filePath);
  }

  async _writemap(filePath) {
    const json = MapExporter.exportToJSON(this.state.tileMap, this.state.tileMap.tilesetPath);
    const res = await window.electronAPI.writeFile(filePath, json);
    if (!res.ok) { alert('Failed to save: ' + res.error); return; }
    this.dirty = false;
    this._updateTitle();
  }

  async _exportJSON() {
    // Let the user choose a parent directory; we create Maps/<mapName>/ inside it.
    const result = await window.electronAPI.showOpenDialog({
      title: 'Choose Export Parent Folder',
      properties: ['openDirectory']
    });
    if (result.canceled || !result.filePaths.length) return;

    const mapName   = (this.state.tileMap.name || 'untitled').replace(/[/\\:*?"<>|]/g, '_');
    const mapFolder = `${result.filePaths[0]}/Maps/${mapName}`;

    // Create the folder (and Maps/ parent if needed)
    const mkRes = await window.electronAPI.mkdir(mapFolder);
    if (!mkRes.ok) { alert('Could not create export folder: ' + mkRes.error); return; }

    // Save JSON — tileset path is stored as a relative filename so the bundle is portable
    const jsonPath = `${mapFolder}/${mapName}.json`;
    const json = MapExporter.exportToJSON(this.state.tileMap, 'tileset.png');
    const jsonRes = await window.electronAPI.writeFile(jsonPath, json);
    if (!jsonRes.ok) { alert('Failed to write JSON: ' + jsonRes.error); return; }

    // Save tileset PNG if one is loaded
    if (this._tilesetPanel.image) {
      const img = this._tilesetPanel.image;
      const offscreen = document.createElement('canvas');
      offscreen.width  = img.naturalWidth;
      offscreen.height = img.naturalHeight;
      const offCtx = offscreen.getContext('2d');
      offCtx.imageSmoothingEnabled = false;
      offCtx.drawImage(img, 0, 0);
      const dataUrl  = offscreen.toDataURL('image/png');
      const base64   = dataUrl.split(',')[1];
      const pngPath  = `${mapFolder}/tileset.png`;
      const pngRes   = await window.electronAPI.writeFileBinary(pngPath, base64);
      if (!pngRes.ok) { alert('Failed to write tileset PNG: ' + pngRes.error); return; }
    }

    alert(`Exported to:\n${mapFolder}`);
  }

  // ---- Dialogs ----

  _showResizeDialog() {
    const w = prompt('New width (tiles):', this.state.tileMap.width);
    const h = prompt('New height (tiles):', this.state.tileMap.height);
    const nw = parseInt(w, 10);
    const nh = parseInt(h, 10);
    if (!nw || !nh || nw < 1 || nh < 1) return;
    this.state.tileMap.resize(nw, nh);
    this._markDirty();
  }

  _showMapPropertiesDialog() {
    const name = prompt('Map name:', this.state.tileMap.name);
    if (name !== null) {
      this.state.tileMap.name = name.trim() || this.state.tileMap.name;
      this._updateTitle();
    }
  }

  // ---- AutoSave ----

  _autoSave() {
    if (!this.dirty) return;
    try {
      const json = MapExporter.exportToJSON(this.state.tileMap);
      localStorage.setItem('tile-editor-autosave', json);
      localStorage.setItem('tile-editor-autosave-path', this.currentFilePath || '');
    } catch (e) { /* localStorage may be full */ }
  }

  async _loadAutoSave() {
    try {
      const saved = localStorage.getItem('tile-editor-autosave');
      if (!saved) return;
      const savedPath = localStorage.getItem('tile-editor-autosave-path') || '';
      if (confirm('An autosaved map was found. Restore it?')) {
        const newMap = MapExporter.importFromJSON(saved);
        this.state.tileMap = newMap;
        this.state.renderer.tileMap = newMap;
        this.currentFilePath = savedPath || null;
        this._layerPanel.refresh();
        this._refreshObjectList();
        this._markDirty();

        // Sync panel tileSize BEFORE reloading the tileset so _recompute() uses
        // the correct column count matching the restored map's tileSize.
        this._tilesetPanel.setTileSize(newMap.tileSize);

        // BUG-5 fix: reload tileset image so tiles render as art, not coloured placeholders
        if (newMap.tilesetPath && window.electronAPI) {
          const imgRes = await window.electronAPI.readFileBase64(newMap.tilesetPath);
          if (imgRes.ok) {
            await this._tilesetPanel.loadFromDataUrl(imgRes.data, newMap.tilesetPath);
          }
        }
      }
    } catch (e) { /* ignore */ }
  }

  // ---- Status bar ----

  _updateStatus(tx, ty) {
    const tileEl = document.getElementById('statusTile');
    const toolEl = document.getElementById('statusTool');
    const layerEl = document.getElementById('statusLayer');

    if (tileEl && tx !== undefined) {
      tileEl.textContent = `Tile: (${tx}, ${ty})`;
    }
    if (toolEl) {
      toolEl.textContent = `Tool: ${this.state.activeTool}`;
    }
    if (layerEl) {
      const layer = this.state.tileMap.layers[this.state.activeLayerIndex];
      layerEl.textContent = `Layer: ${layer ? layer.name : '-'}`;
    }
    this._updateZoomLabel();
  }

  _updateTitle() {
    const name = this.state.tileMap.name || 'Untitled';
    const dirty = this.dirty ? ' *' : '';
    const file = this.currentFilePath ? ` — ${this.currentFilePath.split('/').pop()}` : '';
    document.title = `Tile Map Editor — ${name}${file}${dirty}`;
  }

  _markDirty() {
    this.dirty = true;
    this._updateTitle();
  }
}

// ---- Bootstrap ----

window.addEventListener('DOMContentLoaded', async () => {
  const editor = new Editor();
  await editor.init();
  window._editor = editor; // Debug access
});

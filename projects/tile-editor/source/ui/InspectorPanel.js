'use strict';

/**
 * InspectorPanel — shows and edits the properties of the selected map object.
 */
class InspectorPanel {
  /**
   * @param {HTMLElement} container
   * @param {object} state
   */
  constructor(container, state) {
    this.container = container;
    this.state = state;

    /** @type {object|null} Currently displayed object */
    this._currentObj = null;

    /** @type {Function|null} */
    this.onObjectDeleted = null;
    /** @type {Function|null} */
    this.onObjectChanged = null;

    this._build();
  }

  _build() {
    this.container.innerHTML = '';
    const header = document.createElement('div');
    header.className = 'panel-header';
    header.innerHTML = '<span>Inspector</span>';
    this.container.appendChild(header);

    this._body = document.createElement('div');
    this._body.className = 'inspector-body';
    this.container.appendChild(this._body);

    this._showEmpty();
  }

  _showEmpty() {
    this._body.innerHTML = '<div class="inspector-empty">No object selected</div>';
  }

  /**
   * Show the properties of a placed object.
   * @param {object} obj
   */
  showObject(obj) {
    this._currentObj = obj;
    this._render();
  }

  /**
   * Clear the inspector.
   */
  clear() {
    this._currentObj = null;
    this._showEmpty();
  }

  /**
   * Re-render the inspector for the current object.
   */
  _render() {
    const obj = this._currentObj;
    if (!obj) { this._showEmpty(); return; }

    this._body.innerHTML = '';

    // Type badge
    const typeBadge = document.createElement('div');
    typeBadge.className = 'inspector-type-badge';
    typeBadge.textContent = obj.type.toUpperCase();
    this._body.appendChild(typeBadge);

    // Basic fields (read-only display)
    const basicFields = [
      { label: 'ID', value: obj.id },
      { label: 'Type', value: obj.type },
      { label: 'X', value: obj.x },
      { label: 'Y', value: obj.y }
    ];

    const basicTable = document.createElement('div');
    basicTable.className = 'inspector-fields';

    for (const field of basicFields) {
      const row = document.createElement('div');
      row.className = 'inspector-field';
      const label = document.createElement('span');
      label.className = 'field-label';
      label.textContent = field.label;
      const val = document.createElement('span');
      val.className = 'field-value';
      val.textContent = field.value;
      row.appendChild(label);
      row.appendChild(val);
      basicTable.appendChild(row);
    }
    this._body.appendChild(basicTable);

    // Encounter toggle
    const encounterRow = document.createElement('div');
    encounterRow.className = 'inspector-encounter-row';
    const isEncounter = obj.properties && obj.properties.encounter === true;
    const encounterBtn = document.createElement('button');
    encounterBtn.className = 'btn btn-sm btn-block' + (isEncounter ? ' btn-encounter-on' : ' btn-encounter-off');
    encounterBtn.textContent = isEncounter ? '⚔ Encounter Zone: ON' : '⚔ Encounter Zone: OFF';
    encounterBtn.addEventListener('click', () => {
      if (!obj.properties) obj.properties = {};
      obj.properties.encounter = !obj.properties.encounter;
      if (!obj.properties.encounter) delete obj.properties.encounter;
      if (this.onObjectChanged) this.onObjectChanged(obj);
      this._render();
    });
    encounterRow.appendChild(encounterBtn);
    this._body.appendChild(encounterRow);

    // Custom properties
    const propsHeader = document.createElement('div');
    propsHeader.className = 'inspector-section-title';
    propsHeader.textContent = 'Properties';
    this._body.appendChild(propsHeader);

    this._propsContainer = document.createElement('div');
    this._propsContainer.className = 'inspector-props';
    this._body.appendChild(this._propsContainer);
    this._renderProps();

    // Add property button
    const addBtn = document.createElement('button');
    addBtn.className = 'btn btn-sm btn-block';
    addBtn.textContent = '+ Add Property';
    addBtn.addEventListener('click', () => this._addProperty());
    this._body.appendChild(addBtn);

    // Delete object button
    const delBtn = document.createElement('button');
    delBtn.className = 'btn btn-sm btn-block btn-danger';
    delBtn.textContent = 'Delete Object';
    delBtn.addEventListener('click', () => this._deleteObject());
    this._body.appendChild(delBtn);
  }

  /**
   * Render the editable custom property rows.
   */
  _renderProps() {
    const obj = this._currentObj;
    this._propsContainer.innerHTML = '';

    const keys = Object.keys(obj.properties || {});
    if (keys.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'inspector-empty';
      empty.textContent = 'No properties';
      this._propsContainer.appendChild(empty);
      return;
    }

    for (const key of keys) {
      const row = document.createElement('div');
      row.className = 'prop-row';

      const keyInput = document.createElement('input');
      keyInput.className = 'prop-key-input';
      keyInput.value = key;
      keyInput.title = 'Property name';
      keyInput.addEventListener('blur', () => {
        const newKey = keyInput.value.trim();
        if (newKey && newKey !== key) {
          const val = obj.properties[key];
          delete obj.properties[key];
          obj.properties[newKey] = val;
          if (this.onObjectChanged) this.onObjectChanged(obj);
          this._renderProps();
        }
      });

      const valInput = document.createElement('input');
      valInput.className = 'prop-val-input';
      valInput.value = obj.properties[key];
      valInput.title = 'Property value';
      valInput.addEventListener('blur', () => {
        obj.properties[key] = valInput.value;
        if (this.onObjectChanged) this.onObjectChanged(obj);
      });

      const removeBtn = document.createElement('button');
      removeBtn.className = 'btn btn-sm prop-remove';
      removeBtn.textContent = '✕';
      removeBtn.title = 'Remove property';
      removeBtn.addEventListener('click', () => {
        delete obj.properties[key];
        if (this.onObjectChanged) this.onObjectChanged(obj);
        this._renderProps();
      });

      row.appendChild(keyInput);
      row.appendChild(valInput);
      row.appendChild(removeBtn);
      this._propsContainer.appendChild(row);
    }
  }

  /**
   * Add a new empty property.
   */
  _addProperty() {
    const obj = this._currentObj;
    if (!obj) return;
    let key = 'property';
    let n = 1;
    while (key in obj.properties) key = `property${n++}`;
    obj.properties[key] = '';
    this._renderProps();
    if (this.onObjectChanged) this.onObjectChanged(obj);
  }

  /**
   * Delete the current object from the map.
   */
  _deleteObject() {
    const obj = this._currentObj;
    if (!obj) return;
    if (!confirm(`Delete ${obj.type} #${obj.id}?`)) return;

    this.state.undoStack.pushObjectDelete(obj);
    this.state.tileMap.objectLayer.remove(obj.id);
    this.state.selectedObjectId = null;
    this.state.renderer.selectedObjectId = null;
    this._currentObj = null;
    this._showEmpty();

    if (this.onObjectDeleted) this.onObjectDeleted(obj.id);
  }
}

window.InspectorPanel = InspectorPanel;

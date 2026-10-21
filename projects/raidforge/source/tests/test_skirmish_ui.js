const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'web/skirmish.js'), 'utf8');
const packet = JSON.parse(fs.readFileSync(path.join(root, 'data/skirmish-v0.4.json'), 'utf8'));

// Exercise the card renderer without starting a server or making model requests.
function page() {
  const elements = new Map();
  const element = () => ({
    innerHTML: '', textContent: '', style: {setProperty() {}},
    classList: {toggle() {}}, addEventListener() {}, append() {},
  });
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
    createElement: element,
    addEventListener() {},
  };
  const context = vm.createContext({document, fetch: () => new Promise(() => {})});
  vm.runInContext(source, context);
  return {context, elements};
}

test('a Vampire displays its own Target TN separately from its attack test', () => {
  const {context} = page();
  const vampire = packet.monsters.find(monster => monster.name === 'Vampire');
  const html = context.renderMonster(vampire);
  assert.match(html, /<dt>Target TN<\/dt><dd>6<\/dd>/);
  assert.match(html, /Hit: 1D6 \+ ATK ≥ target TN/);
  assert.doesNotMatch(html, /1D6 \+ ATK ≥ TN 6/);
  assert.match(html, /On hit: roll D12 − target DEF = HP lost \(minimum 0\)/);
});

test('the character view explains ATK and DEF and renders a separate damage roll', () => {
  const {context, elements} = page();
  context.render(packet);
  assert.match(elements.get('base-stats').innerHTML, /Target TN<\/span><strong>4<\/strong>/);
  assert.match(elements.get('basic-attack').innerHTML, /Hit: 1D6 \+ ATK ≥ target TN/);
  assert.match(elements.get('basic-attack').innerHTML, /On hit: roll D3 − target DEF = HP lost \(minimum 0\)/);
  assert.match(elements.get('combat-rules').innerHTML, /It does not increase damage/);
  assert.match(elements.get('combat-rules').innerHTML, /No defence roll; DEF does not change TN/);
  assert.match(elements.get('level-rule').textContent, /including Down or removed characters/);
  assert.match(elements.get('level-rule').textContent, /Level caps at 5; Build Points continue/);
  assert.match(elements.get('level-rule').textContent, /A loss grants neither/);
});

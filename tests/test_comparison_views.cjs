const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('three views switch exclusively and independently for each tool', () => {
  const source = fs.readFileSync(path.join(__dirname,
    '../src/docling_poc/comparison_report.py'), 'utf8');
  const script = source.match(/TOGGLE_SCRIPT = """\s*<script>([\s\S]*?)<\/script>/)[1];
  const panels = {};
  const buttons = [];
  for (const id of ['docling', 'tika']) {
    const panes = ['raw', 'styled', 'json'].map(view => ({
      dataset: {viewPane: view}, hidden: view !== 'raw'
    }));
    const options = panes.map(pane => ({
      dataset: {view: pane.dataset.viewPane}, pressed: pane.dataset.viewPane === 'raw',
      getAttribute: () => id,
      setAttribute(name, value) { this.pressed = value === 'true'; },
      addEventListener(name, fn) { this.click = fn; }
    }));
    options.forEach(option => option.parentElement = {querySelectorAll: () => options});
    panels[id] = {panes, querySelectorAll: () => panes};
    buttons.push(...options);
  }
  vm.runInNewContext(script, {document: {
    querySelectorAll: () => buttons, getElementById: id => panels[id]
  }});
  for (const index of [2, 1, 0, 0]) {
    buttons[index].click();
    assert.deepEqual(panels.docling.panes.map(p => p.hidden),
      [0, 1, 2].map(i => i !== index));
    assert.deepEqual(buttons.slice(0, 3).map(b => b.pressed),
      [0, 1, 2].map(i => i === index));
    assert.deepEqual(panels.tika.panes.map(p => p.hidden), [false, true, true]);
  }
});

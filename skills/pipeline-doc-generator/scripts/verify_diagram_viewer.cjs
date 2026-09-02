// Deterministic tests execute the actual shipped viewer, with no network/browser driver.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
let document;
class Element extends EventTarget {
  constructor() {
    super(); this.dataset = {}; this.style = {}; this.isConnected = true;
    this.captures = new Set(); this.attributes = []; this.children = [];
    this.rect = { left: 24, top: 80, width: 1000, height: 620, right: 1024, bottom: 700 };
  }
  getBoundingClientRect() { return this.rect; }
  focus() { document.activeElement = this; }
  setPointerCapture(id) { this.captures.add(id); }
  releasePointerCapture(id) { this.captures.delete(id); }
  hasPointerCapture(id) { return this.captures.has(id); }
  replaceChildren(...items) { this.children = items; }
  showModal() { this.open = true; }
  close() { this.open = false; this.dispatchEvent(new Event('close')); }
  setAttribute(name, value) {
    this.attributes = this.attributes.filter(a => a.name !== name).concat({name, value});
  }
}
const root = new Element(), dialog = new Element(), stage = new Element(), art = new Element();
const plus = new Element(), minus = new Element(), fit = new Element(), close = new Element(), output = new Element(), title = new Element();
function svg(width, height) {
  const result = new Element(), marker = new Element(), edge = new Element();
  marker.id = 'marker'; edge.setAttribute('marker-end', 'url(#marker)');
  result.setAttribute('aria-labelledby', 'marker');
  result.viewBox = {baseVal: {width, height}};
  result.cloneNode = () => svg(width, height);
  result.querySelectorAll = selector => selector === '[id]' ? [marker] : [marker, edge];
  result.marker = marker; result.edge = edge;
  return result;
}
const simple = new Element(), complex = new Element();
const simpleSvg = svg(1150, 350), complexSvg = svg(1500, 900);
simple.dataset.caption = '简单同步'; complex.dataset.caption = '复杂报表';
simple.querySelector = () => simpleSvg; complex.querySelector = () => complexSvg;
const lookup = {
  '.wl-dialog': dialog, '.wl-stage': stage, '.wl-art': art, '.wl-zoom': output,
  '[data-action="zoom-in"]': plus, '[data-action="zoom-out"]': minus,
  '[data-action="fit"]': fit, '[data-action="close"]': close, '#wl-dialog-title': title,
};
root.querySelector = selector => { assert.ok(lookup[selector], selector); return lookup[selector]; };
document = {
  getElementById: id => { assert.equal(id, 'waterline-diagram-viewer'); return root; },
  querySelectorAll: selector => { assert.equal(selector, '.waterline-diagram-open'); return [simple, complex]; },
  activeElement: null,
};
const observers = [];
const context = vm.createContext({ document, Map, Math, String, Array, requestAnimationFrame: callback => callback(), ResizeObserver: class { constructor(callback) { observers.push(callback); } observe() {} } });
vm.runInContext(fs.readFileSync(path.join(__dirname, '../assets/diagram-viewer.js'), 'utf8'), context);
function fire(el, type, data = {}) {
  const event = new Event(type, {cancelable: true});
  for (const [key, value] of Object.entries(data)) Object.defineProperty(event, key, {value});
  el.dispatchEvent(event); return event;
}
function current() { return {x: Number(stage.dataset.panX), y: Number(stage.dataset.panY), scale: Number(stage.dataset.scale)}; }
function near(a, b) { assert.ok(Math.abs(a-b) < .00001, `${a} != ${b}`); }
fire(complex, 'click'); assert.equal(dialog.open, true); assert.equal(title.textContent, '复杂报表');
assert.equal(art.children[0].marker.id, 'focus-marker');
assert.equal(art.children[0].edge.attributes[0].value, 'url(#focus-marker)');
assert.equal(complexSvg.marker.id, 'marker');
const initial = current();
fire(plus, 'click'); near(current().scale, initial.scale*1.25);
fire(minus, 'click'); near(current().scale, initial.scale);
const start = current();
fire(stage, 'pointerdown', {pointerType:'mouse', button:0, pointerId:1, clientX:400, clientY:330});
fire(stage, 'pointermove', {pointerId:1, clientX:550, clientY:420});
near(current().x, start.x+150); near(current().y, start.y+90);
fire(stage, 'pointerup', {pointerId:1}); assert.equal(stage.captures.size, 0);
const before = current(), anchor = {x:450-stage.rect.left, y:350-stage.rect.top};
assert.ok(fire(stage, 'wheel', {deltaY:-200, deltaMode:0, clientX:450, clientY:350}).defaultPrevented);
const after = current(); assert.ok(after.scale > before.scale);
near((anchor.x-before.x)/before.scale, (anchor.x-after.x)/after.scale);
near((anchor.y-before.y)/before.scale, (anchor.y-after.y)/after.scale);
fire(fit, 'click'); near(current().scale, initial.scale); near(current().x, initial.x);
fire(stage, 'pointerdown', {pointerType:'touch', button:0, pointerId:2, clientX:300, clientY:300});
fire(stage, 'pointerdown', {pointerType:'touch', button:0, pointerId:3, clientX:500, clientY:300});
fire(stage, 'pointermove', {pointerId:3, clientX:700, clientY:300}); near(current().scale, initial.scale*2);
fire(stage, 'pointerup', {pointerId:3});
const one = current(); fire(stage, 'pointermove', {pointerId:2, clientX:350, clientY:320}); near(current().x, one.x+50);
fire(stage, 'pointercancel', {pointerId:2}); assert.equal(stage.dataset.dragging, 'false');
for (let i=0; i<50; i++) fire(plus, 'click'); near(current().scale, 5); assert.equal(plus.disabled, true);
for (let i=0; i<100; i++) fire(minus, 'click'); near(current().scale, .05); assert.equal(minus.disabled, true);
fire(dialog, 'keydown', {key:'0'}); near(current().scale, initial.scale);
fire(close, 'click'); assert.equal(document.activeElement, complex); assert.equal(art.children.length, 0);
fire(simple, 'click'); assert.equal(art.children[0].viewBox.baseVal.width, 1150);
stage.rect.width=290; observers[0](); assert.ok(current().scale > .05 && current().scale < 1);
fire(close, 'click'); assert.equal(document.activeElement, simple);
console.log(JSON.stringify({passed:true, checks:['focus','zoom','drag','wheel_anchor','fit','pinch','one_finger_pan','pointer_cancel','limits','keyboard','focus_restore','switch','resize','unique_svg_ids','original_unchanged']}, null, 2));

'use strict';
// Execute the shipped script against deterministic DOM geometry, without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function scenario(mobile) {
  const handlers = new Map(), frames = [];
  const listen = (name, callback) => handlers.set(name, callback);
  const links = [0, 1, 2].map(index => ({
    attrs: { href: '#section-' + index },
    handlers: {},
    getAttribute(key) { return this.attrs[key]; },
    setAttribute(key, value) { this.attrs[key] = value; },
    removeAttribute(key) { delete this.attrs[key]; },
    addEventListener(name, callback) { this.handlers[name] = callback; },
    closest() { return null; },
    getBoundingClientRect() { return { top: index * 100, bottom: index * 100 + 50 }; },
  }));
  let tops = [0, 800, 2400];
  const headings = links.map((_, index) => ({ getBoundingClientRect: () => ({ top: tops[index] }) }));
  const toggle = { checked: true, attrs: {}, addEventListener: listen,
    setAttribute(key, value) { this.attrs[key] = value; }, focus() { this.focused = true; } };
  const label = {};
  const nav = { scrollTop: 0, scrollLeft: 0, dataset: {}, children: [], handlers: {},
    classList: { add() {} },
    appendChild(child) { this.children.push(child); child.parentElement = this; },
    addEventListener(name, callback) { this.handlers[name] = callback; },
    querySelectorAll: selector => selector === 'a[href^="#"]' ? links : [],
    getBoundingClientRect: () => ({ top: 0, bottom: 180, left: 0, right: 220, width: 220, height: 180 }) };
  const document = { documentElement: { scrollHeight: 4000 }, addEventListener: listen,
    getElementById: id => id === 'toc-toggle' ? toggle : headings[Number(id.split('-')[1])],
    querySelector: selector => selector === '.toc-toggle-label' ? label : selector === '.toc-chapters' ? nav : null,
    createElement: tag => ({ tag, attrs: {}, style: {}, handlers: {}, setAttribute(key, value) { this.attrs[key] = value; },
      addEventListener(name, callback) { this.handlers[name] = callback; }, hasPointerCapture() { return false; } }) };
  const window = { innerHeight: 800, scrollY: 0, location: { pathname: '/test.html', hash: '' }, matchMedia: () => ({ matches: mobile }),
    addEventListener: listen, requestAnimationFrame: callback => frames.push(callback) };
  const runFrame = () => { handlers.get('scroll')(); frames.splice(0).forEach(callback => callback()); };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../assets/document-navigation.js'), 'utf8'), { window, document });
  assert.equal(toggle.checked, !mobile);
  assert.equal(links[0].attrs['aria-current'], 'location');
  tops = [-1000, -200, 1400]; window.scrollY = 1000; runFrame();
  assert.equal(links[1].attrs['aria-current'], 'location'); // Long-table reading keeps its section.
  tops = [-2100, -1300, 300]; window.scrollY = 2100; runFrame();
  assert.equal(links[1].attrs['aria-current'], 'location');
  tops = [-2400, -1600, 0]; window.scrollY = 2400; runFrame();
  assert.equal(links[2].attrs['aria-current'], 'location');
  assert.equal(links.filter(link => link.attrs['aria-current']).length, 1);
  toggle.checked = true; handlers.get('change')();
  assert(nav.scrollTop > 0); // Reopening reveals the active item.
  handlers.get('keydown')({ key: 'Escape' });
  assert.equal(toggle.checked, false); assert.equal(toggle.focused, true);
  assert.equal(toggle.attrs['aria-expanded'], 'false');
  tops = [0, 800, 2400]; window.scrollY = 0; runFrame();
  assert.equal(links[0].attrs['aria-current'], 'location'); // Backward scrolling.
  tops = [-3200, -2400, 600]; window.scrollY = 3200; runFrame();
  assert.equal(links[2].attrs['aria-current'], 'location'); // Last short section at page bottom.
}
scenario(false); scenario(true);
function themeScenario(saved, systemDark, storageBlocked) {
  const attrs = {}, rootAttrs = {}, listeners = {};
  let stored = saved;
  const button = { setAttribute: (key, value) => { attrs[key] = value; },
    addEventListener: (name, action) => { listeners[name] = action; } };
  const document = { documentElement: { setAttribute: (key, value) => { rootAttrs[key] = value; } },
    getElementById: id => id === 'theme-toggle' ? button : null, querySelector: () => null };
  const window = { matchMedia: () => ({ matches: systemDark }), localStorage: {
    getItem: key => { assert.equal(key, 'waterline-theme'); if (storageBlocked) throw Error('disabled'); return stored; },
    setItem: (key, value) => { assert.equal(key, 'waterline-theme'); if (storageBlocked) throw Error('disabled'); stored = value; },
  } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../assets/document-navigation.js'), 'utf8'), { document, window });
  const initial = !storageBlocked && ['light', 'dark'].includes(saved) ? saved : systemDark ? 'dark' : 'light';
  assert.equal(rootAttrs['data-theme'], initial);
  listeners.click();
  assert.equal(rootAttrs['data-theme'], initial === 'dark' ? 'light' : 'dark');
  assert.equal(attrs['aria-pressed'], String(rootAttrs['data-theme'] === 'dark'));
  assert(attrs['aria-label'].includes('切换'));
  if (!storageBlocked) assert.equal(stored, rootAttrs['data-theme']);
  listeners.click(); assert.equal(rootAttrs['data-theme'], initial);
}
themeScenario(null, false, false); themeScenario(null, true, false);
themeScenario('light', true, false); themeScenario('dark', false, false);
themeScenario('invalid', true, false); themeScenario('dark', false, true);

// Nested headings exercise the actual shipped controller, including reloads.
class Element {
  constructor(tag, classes = '') {
    this.tag = tag; this.className = classes; this.children = []; this.attrs = {};
    this.handlers = {}; this.dataset = {}; this.style = {}; this.hidden = false; this.textContent = '';
    this.scrollTop = 0; this.scrollLeft = 0;
    this.classList = {
      add: name => { if (!this.classList.contains(name)) this.className = (this.className + ' ' + name).trim(); },
      contains: name => this.className.split(/\s+/).includes(name),
    };
  }
  append(child) { return this.appendChild(child); }
  appendChild(child) {
    if (child.parentElement) child.parentElement.removeChild(child);
    this.children.push(child); child.parentElement = this; return child;
  }
  removeChild(child) {
    const index = this.children.indexOf(child); if (index >= 0) this.children.splice(index, 1);
    child.parentElement = null; return child;
  }
  insertBefore(child, before) {
    if (child.parentElement) child.parentElement.removeChild(child);
    this.children.splice(this.children.indexOf(before), 0, child); child.parentElement = this;
  }
  matches(selector) {
    if (selector === 'li') return this.tag === 'li';
    if (selector === 'ul.toc-children') return this.tag === 'ul' && this.className.includes('toc-children');
    if (selector === 'a[href^="#"]') return this.tag === 'a' && this.attrs.href?.startsWith('#');
    return false;
  }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
  contains(child) { return child === this || this.children.some(item => item.contains(child)); }
  setAttribute(key, value) { this.attrs[key] = value; }
  getAttribute(key) { return this.attrs[key]; }
  removeAttribute(key) { delete this.attrs[key]; }
  addEventListener(name, callback) { this.handlers[name] = callback; }
  getBoundingClientRect() { return this.rect || { top: 0, bottom: 40, left: 0, right: 200, width: 200, height: 40 }; }
  setPointerCapture(pointerId) { this.capturedPointer = pointerId; }
  hasPointerCapture(pointerId) { return this.capturedPointer === pointerId; }
  releasePointerCapture(pointerId) {
    if (this.capturedPointer !== pointerId) return;
    delete this.capturedPointer;
    this.handlers.lostpointercapture?.(makeEvent({ pointerId }));
  }
  focus(options) { this.focused = true; this.focusOptions = options; }
}
function makeEvent(values = {}) {
  return Object.assign({ defaultPrevented: false, propagationStopped: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this.propagationStopped = true; } }, values);
}
function outlineScenario({ saved = new Map(), pathname = '/nested.html', hash = '', blocked = false, reduced = false } = {}) {
  const handlers = {}, documentHandlers = {}, frames = [], timers = [], links = [], items = [], headings = new Map(), historyCalls = [];
  const nav = new Element('nav'); nav.rect = { top: 10, bottom: 190, left: 0, right: 260, width: 260, height: 180 };
  const list = nav.append(new Element('ul', 'toc-list'));
  function chapter(parent, level, id) {
    const item = parent.append(new Element('li', 'level-' + level));
    item.dataset.outlineLevel = String(level); items.push(item);
    const link = item.append(new Element('a')); link.attrs.href = '#' + id; link.textContent = id;
    const top = 24 + links.length * 45;
    link.rect = { top, bottom: top + 40, left: 14, right: 224, width: 210, height: 40 }; links.push(link);
    const heading = { id, top: links.length === 1 ? 0 : 1000 + links.length * 400,
      scrollCalls: [], getBoundingClientRect() { return { top: this.top }; },
      scrollIntoView(options) { this.scrollCalls.push(options); } };
    headings.set(id, heading);
    return { item, link, children: item.append(new Element('ul', 'toc-children')) };
  }
  const chain = [chapter(list, 1, 'one')];
  for (let level = 2; level <= 6; level++) chain.push(chapter(chain.at(-1).children, level, level === 6 ? '深层字段' : 'level-' + level));
  chain.at(-1).item.removeChild(chain.at(-1).children); // A leaf has no expansion button.
  const other = chapter(list, 1, 'other');
  const otherChild = chapter(other.children, 2, 'other-child');
  const otherTable = chapter(otherChild.children, 3, 'other-table');
  otherTable.item.removeChild(otherTable.children);
  nav.querySelectorAll = selector => selector === 'a[href^="#"]' ? links : items;
  const toggle = new Element('input'); toggle.checked = true; toggle.focus = () => { toggle.focused = true; };
  const label = {};
  const document = {
    documentElement: { scrollHeight: 10000 }, addEventListener: (name, fn) => { documentHandlers[name] = fn; },
    getElementById: id => id === 'toc-toggle' ? toggle : headings.get(id),
    querySelector: selector => selector === '.toc-toggle-label' ? label : selector === '.toc-chapters' ? nav : null,
    createElement: tag => new Element(tag),
  };
  const window = {
    innerHeight: 800, scrollY: 0, location: { pathname, hash },
    matchMedia: query => ({ matches: query.includes('prefers-reduced-motion') ? reduced : false }),
    history: { pushState: (_state, _title, target) => { historyCalls.push(target); window.location.hash = target; } },
    addEventListener: (name, fn) => { handlers[name] = fn; }, requestAnimationFrame: fn => frames.push(fn),
    setTimeout: fn => { timers.push(fn); return timers.length; },
    localStorage: {
      getItem: key => { if (blocked) throw Error('disabled'); return saved.get(key); },
      setItem: (key, value) => { if (blocked) throw Error('disabled'); saved.set(key, value); },
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../assets/document-navigation.js'), 'utf8'), { document, window });
  const flush = () => { while (frames.length) frames.shift()(); };
  const flushTimers = () => { while (timers.length) timers.shift()(); };
  const button = branch => branch.item.children.find(child => child.classList.contains('toc-branch-toggle'));
  const click = branch => { button(branch).handlers.click(); flush(); };
  const scrollTo = id => {
    let reached = false;
    for (const heading of headings.values()) { heading.top = reached ? 1500 : -500; if (heading.id === id) reached = true; }
    window.scrollY = 1500; handlers.scroll(); flush();
  };
  flush();
  const indicator = nav.children.find(child => child.classList.contains('toc-active-glass'));
  const handle = () => items.flatMap(item => item.children).find(child => child.classList?.contains('toc-drag-handle'));
  return { chain, other, otherChild, otherTable, nav, links, headings, window, document, handlers, documentHandlers,
    historyCalls, button, click, scrollTo, flush, flushTimers, saved, indicator, handle };
}
const folded = outlineScenario();
assert.equal(folded.chain[0].children.hidden, false);
for (const branch of folded.chain.slice(1, -1)) assert.equal(branch.children.hidden, true);
assert.equal(folded.button(folded.chain.at(-1)), undefined);
assert.equal(folded.button(folded.chain[1]).attrs['aria-controls'], folded.chain[1].children.id);
assert.equal(folded.chain[1].link.attrs.href, '#level-2');
const untouchedClick = makeEvent(); folded.chain[1].link.handlers.click(untouchedClick);
assert.equal(untouchedClick.defaultPrevented, false); // Non-dragged anchor navigation stays native.
folded.click(folded.chain[1]);
assert.equal(folded.chain[1].children.hidden, false);
assert.equal(folded.chain[2].children.hidden, true); // Expand only this immediate branch.
assert.equal(folded.window.location.hash, '');
folded.scrollTo('深层字段');
assert.equal(folded.chain[2].link.attrs['aria-current'], 'location');
folded.click(folded.chain[1]);
assert.equal(folded.chain[1].link.attrs['aria-current'], 'location');
folded.scrollTo('深层字段');
assert.equal(folded.chain[1].children.hidden, true); // Scroll never reverses a manual collapse.
assert.equal(folded.links.filter(link => link.attrs['aria-current']).length, 1);
const reloaded = outlineScenario({ saved: folded.saved });
assert.equal(reloaded.chain[1].children.hidden, true);
folded.click(folded.chain[0]);
assert.equal(outlineScenario({ saved: folded.saved }).chain[0].children.hidden, true);
assert.equal(outlineScenario({ saved: folded.saved, pathname: '/separate.html' }).chain[0].children.hidden, false);
const linked = outlineScenario({ saved: folded.saved, hash: '#' + encodeURIComponent('深层字段') });
for (const branch of linked.chain.slice(0, -1)) assert.equal(branch.children.hidden, false);
assert.equal(linked.otherChild.children.hidden, true); // Unrelated branches stay folded.
linked.scrollTo('深层字段');
assert.equal(linked.chain.at(-1).link.attrs['aria-current'], 'location');
linked.click(linked.chain[2]);
assert.equal(linked.chain[2].link.attrs['aria-current'], 'location');
linked.window.location.hash = '#other-table'; linked.handlers.hashchange(); linked.flush();
assert.equal(linked.otherChild.children.hidden, false);
assert.equal(linked.chain[2].children.hidden, true);
linked.window.location.hash = '#%invalid'; linked.handlers.hashchange(); linked.flush();
assert.equal(linked.chain[2].children.hidden, true);
const unavailable = outlineScenario({ blocked: true });
unavailable.click(unavailable.chain[1]); assert.equal(unavailable.chain[1].children.hidden, false);
for (const value of ['[]', '{broken', 'null', '42']) {
  const invalid = outlineScenario({ saved: new Map([['waterline-outline-v2-two-levels:/nested.html', value]]) });
  assert.equal(invalid.chain[1].children.hidden, true);
}

// One background-only indicator follows the active row and repositions after directory scrolling.
const positioned = outlineScenario();
assert(positioned.nav.classList.contains('has-glass-indicator'));
assert.equal(positioned.nav.children.filter(child => child.classList.contains('toc-active-glass')).length, 1);
assert.equal(positioned.indicator.attrs['aria-hidden'], 'true');
assert.equal(positioned.handle().attrs['aria-label'], '拖动切换章节');
assert.equal(positioned.links.every(link => link.attrs.draggable === 'false'), true);
positioned.chain[0].link.rect.top = 50; positioned.chain[0].link.rect.bottom = 90; positioned.nav.scrollTop = 20;
positioned.nav.handlers.scroll(); positioned.flush();
assert.equal(positioned.indicator.style.transform, 'translate3d(14px,60px,0)');
positioned.chain[0].link.rect.top = -100; positioned.chain[0].link.rect.bottom = -60; positioned.nav.scrollTop = 70;
positioned.nav.handlers.scroll(); positioned.flush();
assert.equal(positioned.nav.scrollTop, 70); // Manual directory scrolling is never pulled back to the active row.
positioned.document.activeElement = positioned.handle();
positioned.scrollTo('level-2');
assert.equal(positioned.handle().parentElement, positioned.chain[1].item);
assert.equal(positioned.handle().focusOptions.preventScroll, true);

// Mouse/pen can drag the active row; a gesture below six pixels preserves its normal click.
const direct = outlineScenario();
const source = direct.chain[0].link;
source.handlers.pointerdown(makeEvent({ pointerId: 1, pointerType: 'mouse', button: 0, clientY: 30 }));
source.handlers.pointermove(makeEvent({ pointerId: 1, pointerType: 'mouse', clientY: 35 }));
source.handlers.pointerup(makeEvent({ pointerId: 1, pointerType: 'mouse', clientY: 35 }));
const ordinaryClick = makeEvent(); source.handlers.click(ordinaryClick);
assert.equal(ordinaryClick.defaultPrevented, false);
assert.equal(direct.historyCalls.length, 0);
source.handlers.pointerdown(makeEvent({ pointerId: 2, pointerType: 'pen', button: 0, clientY: 30 }));
source.handlers.pointermove(makeEvent({ pointerId: 2, pointerType: 'pen', clientY: direct.chain[1].link.rect.top + 20 }));
assert.equal(direct.chain[1].link.attrs['data-drag-preview'], 'true');
assert.equal(source.attrs['aria-current'], 'location'); // Preview does not jump the document.
assert.equal(direct.historyCalls.length, 0);
source.handlers.pointerup(makeEvent({ pointerId: 2, pointerType: 'pen', clientY: direct.chain[1].link.rect.top + 20 }));
assert.deepEqual(direct.historyCalls, ['#level-2']);
assert.equal(direct.headings.get('level-2').scrollCalls[0].behavior, 'smooth');
assert.equal(direct.links.some(link => link.attrs['data-drag-preview']), false);
direct.scrollTo('other');
assert.equal(direct.links.some(link => link.attrs['data-drag-preview']), false);
const keyboardClick = makeEvent({ detail: 0 }); source.handlers.click(keyboardClick);
assert.equal(keyboardClick.defaultPrevented, false);
const syntheticClick = makeEvent({ detail: 1 }); source.handlers.click(syntheticClick);
assert.equal(syntheticClick.defaultPrevented, true);
const laterClick = makeEvent({ detail: 1 }); source.handlers.click(laterClick);
assert.equal(laterClick.defaultPrevented, false); // Drag click suppression is one-shot.
assert.equal(direct.historyCalls.length, 1); // lostpointercapture cannot navigate twice.

const stale = outlineScenario();
const staleSource = stale.chain[0].link;
staleSource.handlers.pointerdown(makeEvent({ pointerId: 7, pointerType: 'mouse', button: 0, clientY: 30 }));
staleSource.handlers.pointermove(makeEvent({ pointerId: 7, pointerType: 'mouse', clientY: stale.chain[1].link.rect.top + 20 }));
staleSource.handlers.pointerup(makeEvent({ pointerId: 7, pointerType: 'mouse', clientY: stale.chain[1].link.rect.top + 20 }));
stale.flushTimers();
const laterRealClick = makeEvent({ detail: 1 }); staleSource.handlers.click(laterRealClick);
assert.equal(laterRealClick.defaultPrevented, false); // Missing synthetic clicks cannot poison the next input.

// Touch starts only on the handle. Its preview clamps to the panel and excludes folded rows.
const touch = outlineScenario();
touch.chain[0].link.handlers.pointerdown(makeEvent({ pointerId: 3, pointerType: 'touch', button: 0, clientY: 30 }));
touch.chain[0].link.handlers.pointermove(makeEvent({ pointerId: 3, pointerType: 'touch', clientY: 100 }));
assert.equal(touch.nav.dataset.dragging, undefined);
const grip = touch.handle();
grip.handlers.pointerdown(makeEvent({ pointerId: 4, pointerType: 'touch', button: 0, clientY: 30 }));
grip.handlers.pointermove(makeEvent({ pointerId: 4, pointerType: 'touch', clientY: -1000 }));
assert.equal(touch.indicator.style.transform, 'translate3d(14px,0px,0)');
grip.handlers.pointermove(makeEvent({ pointerId: 4, pointerType: 'touch', clientY: 10000 }));
assert.equal(touch.indicator.style.transform, 'translate3d(14px,140px,0)');
assert.equal(touch.chain[1].link.attrs['data-drag-preview'], 'true'); // Offscreen rows are not picked beyond the clamp.
for (const link of touch.links.filter(link => link.attrs['data-drag-preview'])) {
  for (let node = link; node && node !== touch.nav; node = node.parentElement) assert.equal(node.hidden, false);
}
grip.handlers.pointercancel(makeEvent({ pointerId: 4 }));
assert.equal(touch.historyCalls.length, 0);
assert.equal(touch.nav.dataset.dragging, undefined);
assert.equal(touch.links.some(link => link.attrs['data-drag-preview']), false);

const lost = outlineScenario();
lost.handle().handlers.pointerdown(makeEvent({ pointerId: 5, pointerType: 'mouse', button: 0, clientY: 30 }));
lost.handle().handlers.pointermove(makeEvent({ pointerId: 5, pointerType: 'mouse', clientY: lost.other.link.rect.top + 20 }));
lost.handle().handlers.lostpointercapture(makeEvent({ pointerId: 5 }));
assert.equal(lost.historyCalls.length, 0);
assert.equal(lost.nav.dataset.dragging, undefined);

const escaped = outlineScenario();
escaped.handle().handlers.pointerdown(makeEvent({ pointerId: 6, pointerType: 'mouse', button: 0, clientY: 30 }));
escaped.handle().handlers.pointermove(makeEvent({ pointerId: 6, pointerType: 'mouse', clientY: escaped.other.link.rect.top + 20 }));
const escapeDrag = makeEvent({ key: 'Escape' }); escaped.documentHandlers.keydown(escapeDrag);
assert.equal(escapeDrag.defaultPrevented, true);
assert.equal(escaped.handle().focused, true);
assert.equal(escaped.historyCalls.length, 0);
assert.equal(escaped.nav.dataset.dragging, undefined);

// Keyboard preview skips folded descendants; Escape cancels and Enter commits once.
const keyboard = outlineScenario();
keyboard.click(keyboard.chain[0]);
const keyboardHandle = keyboard.handle();
keyboardHandle.handlers.keydown(makeEvent({ key: 'ArrowDown' }));
assert.equal(keyboard.other.link.attrs['data-drag-preview'], 'true');
assert.equal(keyboard.historyCalls.length, 0);
assert(keyboard.nav.scrollTop > 0); // Keyboard preview is revealed without scrolling the document.
const previewEscape = makeEvent({ key: 'Escape' }); keyboardHandle.handlers.keydown(previewEscape);
assert.equal(previewEscape.propagationStopped, true);
assert.equal(keyboard.other.link.attrs['data-drag-preview'], undefined);
keyboardHandle.handlers.keydown(makeEvent({ key: 'ArrowDown' }));
keyboardHandle.handlers.keydown(makeEvent({ key: 'Enter' }));
assert.deepEqual(keyboard.historyCalls, ['#other']);
assert.equal(keyboard.headings.get('other').scrollCalls.length, 1);
const hiddenPreview = outlineScenario();
hiddenPreview.handle().handlers.keydown(makeEvent({ key: 'ArrowDown' }));
assert.equal(hiddenPreview.chain[1].link.attrs['data-drag-preview'], 'true');
hiddenPreview.click(hiddenPreview.chain[0]);
assert.equal(hiddenPreview.chain[1].link.attrs['data-drag-preview'], undefined);
hiddenPreview.handle().handlers.keydown(makeEvent({ key: 'ArrowDown' }));
hiddenPreview.handle().handlers.blur();
assert.equal(hiddenPreview.links.some(link => link.attrs['data-drag-preview']), false);

const stableCapture = outlineScenario();
const capturedHandle = stableCapture.handle();
capturedHandle.handlers.pointerdown(makeEvent({ pointerId: 8, pointerType: 'mouse', button: 0, clientY: 30 }));
capturedHandle.handlers.pointermove(makeEvent({ pointerId: 8, pointerType: 'mouse', clientY: stableCapture.chain[1].link.rect.top + 20 }));
stableCapture.headings.get('one').top = -500; stableCapture.headings.get('level-2').top = -400;
stableCapture.window.scrollY = 500; stableCapture.handlers.scroll(); stableCapture.flush();
assert.equal(capturedHandle.parentElement, stableCapture.chain[0].item);
assert.equal(stableCapture.chain[0].link.attrs['aria-current'], 'location');
capturedHandle.handlers.pointercancel(makeEvent({ pointerId: 8 }));
const reduced = outlineScenario({ reduced: true });
reduced.handle().handlers.keydown(makeEvent({ key: 'ArrowDown' }));
reduced.handle().handlers.keydown(makeEvent({ key: 'Enter' }));
assert.equal(reduced.headings.get('level-2').scrollCalls[0].behavior, 'auto');

console.log('Navigation: scroll tracking, moving glass indicator, desktop/touch drag threshold, clamp, cancellation, click suppression and keyboard commit passed');
console.log('Outline: six levels, separate arrows/links, folding, persistence/isolation, ancestor hashes and visible-only selection passed');
console.log('Theme: system default, saved preference, toggling, accessible labels, invalid preference and unavailable storage passed');

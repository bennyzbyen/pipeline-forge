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
    getAttribute(key) { return this.attrs[key]; },
    setAttribute(key, value) { this.attrs[key] = value; },
    removeAttribute(key) { delete this.attrs[key]; },
    closest() { return null; },
    getBoundingClientRect() { return { top: index * 100, bottom: index * 100 + 50 }; },
  }));
  let tops = [0, 800, 2400];
  const headings = links.map((_, index) => ({ getBoundingClientRect: () => ({ top: tops[index] }) }));
  const toggle = { checked: true, attrs: {}, addEventListener: listen,
    setAttribute(key, value) { this.attrs[key] = value; }, focus() { this.focused = true; } };
  const label = {};
  const nav = { scrollTop: 0, querySelectorAll: selector => selector === 'a[href^="#"]' ? links : [],
    getBoundingClientRect: () => ({ top: 0, bottom: 180 }) };
  const document = { documentElement: { scrollHeight: 4000 }, addEventListener: listen,
    getElementById: id => id === 'toc-toggle' ? toggle : headings[Number(id.split('-')[1])],
    querySelector: selector => selector === '.toc-toggle-label' ? label : selector === '.toc-chapters' ? nav : null };
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
    this.handlers = {}; this.dataset = {}; this.hidden = false; this.textContent = '';
    this.classList = { add: name => { this.className += ' ' + name; } };
  }
  append(child) { this.children.push(child); child.parentElement = this; return child; }
  insertBefore(child, before) { this.children.splice(this.children.indexOf(before), 0, child); child.parentElement = this; }
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
  getBoundingClientRect() { return this.rect || { top: 0, bottom: 40 }; }
}
function outlineScenario({ saved = new Map(), pathname = '/nested.html', hash = '', blocked = false } = {}) {
  const handlers = {}, frames = [], links = [], items = [], headings = new Map();
  const nav = new Element('nav'); nav.scrollTop = 0; nav.rect = { top: 0, bottom: 180 };
  const list = nav.append(new Element('ul', 'toc-list'));
  function chapter(parent, level, id) {
    const item = parent.append(new Element('li', 'level-' + level));
    item.dataset.outlineLevel = String(level); items.push(item);
    const link = item.append(new Element('a')); link.attrs.href = '#' + id; link.textContent = id;
    link.rect = { top: links.length * 45, bottom: links.length * 45 + 40 }; links.push(link);
    const heading = { id, top: links.length === 1 ? 0 : 1000 + links.length * 400,
      getBoundingClientRect() { return { top: this.top }; } };
    headings.set(id, heading);
    return { item, link, children: item.append(new Element('ul', 'toc-children')) };
  }
  const chain = [chapter(list, 1, 'one')];
  for (let level = 2; level <= 6; level++) chain.push(chapter(chain.at(-1).children, level, level === 6 ? '深层字段' : 'level-' + level));
  chain.at(-1).item.children.pop(); // A leaf has no expansion button.
  const other = chapter(list, 1, 'other');
  const otherChild = chapter(other.children, 2, 'other-child');
  chapter(otherChild.children, 3, 'other-table').item.children.pop();
  nav.querySelectorAll = selector => selector === 'a[href^="#"]' ? links : items;
  const toggle = new Element('input'); toggle.checked = true; toggle.focus = () => { toggle.focused = true; };
  const label = {};
  const document = {
    documentElement: { scrollHeight: 10000 }, addEventListener: (name, fn) => { handlers[name] = fn; },
    getElementById: id => id === 'toc-toggle' ? toggle : headings.get(id),
    querySelector: selector => selector === '.toc-toggle-label' ? label : selector === '.toc-chapters' ? nav : null,
    createElement: tag => new Element(tag),
  };
  const window = {
    innerHeight: 800, scrollY: 0, location: { pathname, hash }, matchMedia: () => ({ matches: false }),
    addEventListener: (name, fn) => { handlers[name] = fn; }, requestAnimationFrame: fn => frames.push(fn),
    localStorage: {
      getItem: key => { if (blocked) throw Error('disabled'); return saved.get(key); },
      setItem: (key, value) => { if (blocked) throw Error('disabled'); saved.set(key, value); },
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../assets/document-navigation.js'), 'utf8'), { document, window });
  const flush = () => { while (frames.length) frames.shift()(); };
  const button = branch => branch.item.children.find(child => child.tag === 'button');
  const click = branch => { button(branch).handlers.click(); flush(); };
  const scrollTo = id => {
    let reached = false;
    for (const heading of headings.values()) { heading.top = reached ? 1500 : -500; if (heading.id === id) reached = true; }
    window.scrollY = 1500; handlers.scroll(); flush();
  };
  flush();
  return { chain, other, otherChild, nav, links, headings, window, handlers, button, click, scrollTo, flush, saved };
}
const folded = outlineScenario();
assert.equal(folded.chain[0].children.hidden, false);
for (const branch of folded.chain.slice(1, -1)) assert.equal(branch.children.hidden, true);
assert.equal(folded.button(folded.chain.at(-1)), undefined);
assert.equal(folded.button(folded.chain[1]).attrs['aria-controls'], folded.chain[1].children.id);
assert.equal(folded.chain[1].link.attrs.href, '#level-2');
assert.equal(folded.chain[1].link.handlers.click, undefined); // Native anchor navigation stays intact.
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
console.log('Navigation: scroll tracking, long tables, reverse scrolling, bottom selection, reveal, mobile and keyboard checks passed');
console.log('Outline: six levels, separate arrows/links, immediate folding, persistence/isolation, ancestor-only hashes, manual collapse and visible highlight passed');
console.log('Theme: system default, saved preference, toggling, accessible labels, invalid preference and unavailable storage passed');

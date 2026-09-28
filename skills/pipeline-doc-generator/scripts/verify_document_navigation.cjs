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
    getBoundingClientRect() { return { top: index * 100, bottom: index * 100 + 50 }; },
  }));
  let tops = [0, 800, 2400];
  const headings = links.map((_, index) => ({ getBoundingClientRect: () => ({ top: tops[index] }) }));
  const toggle = { checked: true, attrs: {}, addEventListener: listen,
    setAttribute(key, value) { this.attrs[key] = value; }, focus() { this.focused = true; } };
  const label = {};
  const nav = { scrollTop: 0, querySelectorAll: () => links,
    getBoundingClientRect: () => ({ top: 0, bottom: 180 }) };
  const document = { documentElement: { scrollHeight: 4000 }, addEventListener: listen,
    getElementById: id => id === 'toc-toggle' ? toggle : headings[Number(id.split('-')[1])],
    querySelector: selector => selector === '.toc-toggle-label' ? label : selector === '.toc-chapters' ? nav : null };
  const window = { innerHeight: 800, scrollY: 0, matchMedia: () => ({ matches: mobile }),
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
console.log('Navigation: scroll tracking, long tables, reverse scrolling, bottom selection, reveal, mobile and keyboard checks passed');
console.log('Theme: system default, saved preference, toggling, accessible labels, invalid preference and unavailable storage passed');

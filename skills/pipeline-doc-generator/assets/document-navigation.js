/* Trusted offline navigation. All labels come from the rendered document DOM. */
(() => {
  'use strict';
  const themeButton = document.getElementById('theme-toggle');
  if (themeButton) {
    const preferenceKey = 'waterline-theme';
    let theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    try {
      const saved = window.localStorage.getItem(preferenceKey);
      if (saved === 'light' || saved === 'dark') theme = saved;
    } catch (_) { /* File previews may disable storage; switching still works. */ }
    function paintTheme() {
      document.documentElement.setAttribute('data-theme', theme);
      themeButton.setAttribute('aria-pressed', String(theme === 'dark'));
      const text = theme === 'dark' ? '当前深色模式，切换为浅色模式' : '当前浅色模式，切换为深色模式';
      themeButton.setAttribute('aria-label', text);
      themeButton.title = text;
    }
    themeButton.addEventListener('click', () => {
      theme = theme === 'dark' ? 'light' : 'dark';
      paintTheme();
      try { window.localStorage.setItem(preferenceKey, theme); } catch (_) { /* Optional persistence. */ }
    });
    paintTheme();
  }
  const toggle = document.getElementById('toc-toggle');
  const label = document.querySelector('.toc-toggle-label');
  const navigation = document.querySelector('.toc-chapters');
  if (!toggle || !label || !navigation) return;
  const entries = Array.from(navigation.querySelectorAll('a[href^="#"]'))
    .map(link => ({ link, heading: document.getElementById(link.getAttribute('href').slice(1)) }))
    .filter(entry => entry.heading);
  if (!entries.length) return;
  const entriesByLink = new Map(entries.map(entry => [entry.link, entry]));

  const storageKey = 'waterline-outline-v2-two-levels:' + window.location.pathname;
  let savedBranches = {};
  try {
    const saved = JSON.parse(window.localStorage.getItem(storageKey) || '{}');
    if (saved && typeof saved === 'object' && !Array.isArray(saved)) savedBranches = saved;
  } catch (_) { /* Storage is optional for local file previews. */ }
  const branches = [];
  function persistBranches() {
    try { window.localStorage.setItem(storageKey, JSON.stringify(savedBranches)); }
    catch (_) { /* Folding remains available without storage. */ }
  }
  for (const item of navigation.querySelectorAll('.toc-list li')) {
    const children = Array.from(item.children).find(child => child.matches('ul.toc-children'));
    const link = Array.from(item.children).find(child => child.matches('a[href^="#"]'));
    if (!children || !link) continue;
    const id = link.getAttribute('href').slice(1);
    children.id = 'outline-children-' + id;
    item.classList.add('toc-branch');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'toc-branch-toggle';
    button.setAttribute('aria-controls', children.id);
    item.insertBefore(button, link);
    const branch = { item, children, link, button, id };
    function paint(expanded) {
      children.hidden = !expanded;
      button.setAttribute('aria-expanded', String(expanded));
      const label = (expanded ? '收起：' : '展开：') + link.textContent.trim();
      button.setAttribute('aria-label', label);
      button.title = label;
    }
    branch.paint = paint;
    paint(Object.prototype.hasOwnProperty.call(savedBranches, id)
      ? savedBranches[id] === true : Number(item.dataset.outlineLevel) < 2);
    button.addEventListener('click', () => {
      const expanded = children.hidden;
      paint(expanded);
      savedBranches[id] = expanded;
      persistBranches();
      schedule();
    });
    branches.push(branch);
  }
  function visibleLink(link) {
    let visible = link;
    for (let item = link.closest('li'); item; item = item.parentElement?.closest('li')) {
      const children = Array.from(item.children).find(child => child.matches('ul.toc-children'));
      if (children?.hidden && !children.contains(visible)) continue;
      if (children?.hidden) visible = Array.from(item.children).find(child => child.matches('a[href^="#"]')) || visible;
    }
    return visible;
  }
  function openHashAncestors() {
    let id = window.location.hash.slice(1);
    try { id = decodeURIComponent(id); } catch (_) { /* Malformed fragments are harmless. */ }
    const target = entries.find(entry => entry.heading.id === id);
    if (!target) return;
    for (const branch of branches) {
      if (branch.children.contains(target.link)) {
        branch.paint(true);
        savedBranches[branch.id] = true;
      }
    }
    persistBranches();
    schedule();
  }

  let active = null;
  let pending = false;
  function reveal() {
    if (!active || !toggle.checked) return;
    const item = active.link.getBoundingClientRect();
    const panel = navigation.getBoundingClientRect();
    if (item.top < panel.top + 12) navigation.scrollTop += item.top - panel.top - 12;
    else if (item.bottom > panel.bottom - 12) navigation.scrollTop += item.bottom - panel.bottom + 12;
  }
  function update() {
    pending = false;
    const threshold = Math.min(120, window.innerHeight * 0.2);
    let selected = entries[0];
    for (const entry of entries) {
      if (entry.heading.getBoundingClientRect().top <= threshold) selected = entry;
      else break;
    }
    if (window.scrollY > 0 && window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) {
      selected = entries[entries.length - 1];
    }
    selected = entriesByLink.get(visibleLink(selected.link)) || selected;
    if (active === selected) return;
    if (active) active.link.removeAttribute('aria-current');
    active = selected;
    active.link.setAttribute('aria-current', 'location');
    reveal();
  }
  function schedule() {
    if (!pending) { pending = true; window.requestAnimationFrame(update); }
  }
  function toggleState() {
    label.title = toggle.checked ? '收起目录' : '展开目录';
    toggle.setAttribute('aria-label', label.title);
    toggle.setAttribute('aria-expanded', String(toggle.checked));
    reveal();
  }
  if (window.matchMedia('(max-width: 980px)').matches) toggle.checked = false;
  toggle.addEventListener('change', toggleState);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && toggle.checked && !document.querySelector('dialog[open]')) {
      toggle.checked = false;
      toggleState();
      toggle.focus();
    }
  });
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule);
  window.addEventListener('hashchange', openHashAncestors);
  window.addEventListener('load', schedule);
  openHashAncestors();
  toggleState();
  update();
})();

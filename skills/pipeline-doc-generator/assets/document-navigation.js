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
    // A small, bounded elastic capsule; never animate the document's color change.
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let pressed = false;
    let rebound = null;
    function resetMotion() {
      pressed = false;
      rebound?.cancel();
      rebound = null;
      themeButton.style.transform = '';
    }
    function releaseMotion() {
      pressed = false;
      rebound?.cancel();
      rebound = null;
      themeButton.style.transform = '';
      if (reducedMotion.matches || !themeButton.animate) return;
      rebound = themeButton.animate([
        { transform: 'scale(.9,.86)', offset: 0 },
        { transform: 'scale(1.12,.96)', offset: .36 },
        { transform: 'scale(.98,1.04)', offset: .65 },
        { transform: 'scale(1.02,.99)', offset: .84 },
        { transform: 'scale(1)', offset: 1 },
      ], { duration: 520, easing: 'cubic-bezier(.2,.7,.3,1)' });
    }
    themeButton.addEventListener('pointermove', event => {
      if (pressed || reducedMotion.matches || event.pointerType === 'touch') return;
      const rect = themeButton.getBoundingClientRect();
      const x = Math.max(-1, Math.min(1, (event.clientX - rect.left - rect.width / 2) / (rect.width / 2)));
      const y = Math.max(-1, Math.min(1, (event.clientY - rect.top - rect.height / 2) / (rect.height / 2)));
      rebound?.cancel();
      rebound = null;
      themeButton.style.transform = 'translate(' + (x * 2.5).toFixed(2) + 'px,' + (y * 2.5).toFixed(2) +
        'px) scale(' + (1.035 + Math.abs(x) * .025).toFixed(3) + ',' + (1.035 + Math.abs(y) * .025).toFixed(3) + ')';
    });
    themeButton.addEventListener('pointerdown', event => {
      if (event.button !== undefined && event.button !== 0) return;
      resetMotion();
      pressed = true;
      if (!reducedMotion.matches) themeButton.style.transform = 'scale(.9,.86)';
    });
    themeButton.addEventListener('pointerup', resetMotion);
    themeButton.addEventListener('pointerleave', resetMotion);
    themeButton.addEventListener('pointercancel', resetMotion);
    themeButton.addEventListener('blur', resetMotion);
    reducedMotion.addEventListener?.('change', resetMotion);
    themeButton.addEventListener('click', () => {
      theme = theme === 'dark' ? 'light' : 'dark';
      paintTheme();
      releaseMotion();
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
  const indicator = document.createElement('div');
  indicator.className = 'toc-active-glass';
  indicator.setAttribute('aria-hidden', 'true');
  const lensFilter = document.getElementById('pf-glass-standard');
  const lensMap = lensFilter?.querySelector?.('feImage');
  const lensBend = lensFilter?.querySelector?.('feDisplacementMap');
  const lensMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  navigation.appendChild(indicator);
  navigation.classList.add('has-glass-indicator');
  const dragHandle = document.createElement('button');
  dragHandle.type = 'button';
  dragHandle.className = 'toc-drag-handle';
  dragHandle.setAttribute('aria-label', '拖动切换章节');
  dragHandle.title = '拖动切换章节；方向键预览，Enter 打开';
  let active = null;
  let preview = null;
  let dragState = null;
  let suppressClick = null;
  let pending = false;

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
      if (preview && !linkIsVisible(preview.link)) clearPreview();
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
  function linkIsVisible(link) {
    for (let node = link; node && node !== navigation; node = node.parentElement) {
      if (node.hidden) return false;
    }
    return true;
  }
  function visibleEntries() {
    return entries.filter(entry => linkIsVisible(entry.link));
  }
  function setIndicator(entry, pointerY) {
    if (!entry) return;
    const item = entry.link.getBoundingClientRect();
    const panel = navigation.getBoundingClientRect();
    const height = Math.max(1, item.height || item.bottom - item.top);
    const panelHeight = Math.max(height, panel.height || panel.bottom - panel.top);
    const width = Math.max(1, item.width || (item.right || 0) - (item.left || 0));
    const left = Math.max(0, (item.left || panel.left || 0) - (panel.left || 0) + (navigation.scrollLeft || 0));
    let top = item.top - panel.top + navigation.scrollTop;
    if (typeof pointerY === 'number') {
      const minimum = navigation.scrollTop;
      const maximum = minimum + panelHeight - height;
      top = Math.max(minimum, Math.min(maximum, pointerY - panel.top + navigation.scrollTop - height / 2));
    }
    indicator.style.width = Math.round(width) + 'px';
    indicator.style.height = Math.round(height) + 'px';
    indicator.style.transform = 'translate3d(' + Math.round(left) + 'px,' + Math.round(top) + 'px,0)';
    // SVG backdrop coordinates must match the lens, not the hidden 1px SVG viewport.
    if (lensFilter && lensMap && lensBend) {
      const moving = typeof pointerY === 'number';
      const delta = moving && !lensMotion.matches ? dragState?.velocity || 0 : 0;
      const strength = moving && !lensMotion.matches ? 28 + Math.abs(delta) * .5 : 18;
      for (const node of [lensFilter, lensMap]) {
        node.setAttribute('width', String(Math.max(1, Math.round(width - 2))));
        node.setAttribute('height', String(Math.max(1, Math.round(height - 2))));
      }
      lensBend.setAttribute('scale', strength.toFixed(2));
      indicator.style.setProperty('--lens-shift', (delta * .11).toFixed(2) + 'px');
      indicator.style.setProperty('--lens-stretch', String(moving && !lensMotion.matches ? 1.045 + Math.abs(delta) * .002 : 1));
    }
  }
  function moveHandle(entry) {
    const item = entry?.link.closest('li');
    if (item && dragHandle.parentElement !== item) {
      const restoreFocus = document.activeElement === dragHandle;
      item.appendChild(dragHandle);
      if (restoreFocus) dragHandle.focus({ preventScroll: true });
    }
  }
  function setPreview(entry, pointerY) {
    if (preview) preview.link.removeAttribute('data-drag-preview');
    preview = entry;
    if (preview && preview !== active) preview.link.setAttribute('data-drag-preview', 'true');
    setIndicator(preview || active, pointerY);
  }
  function clearPreview() {
    if (preview) preview.link.removeAttribute('data-drag-preview');
    preview = null;
    setIndicator(active);
  }
  function select(entry) {
    if (!entry) return false;
    const changed = active !== entry;
    if (active && active !== entry) active.link.removeAttribute('aria-current');
    active = entry;
    active.link.setAttribute('aria-current', 'location');
    if (!dragState) moveHandle(active);
    if (!preview) setIndicator(active);
    return changed;
  }
  function nearestVisibleEntry(pointerY) {
    const available = visibleEntries();
    let nearest = available[0] || active;
    let distance = Infinity;
    for (const entry of available) {
      const rect = entry.link.getBoundingClientRect();
      const center = rect.top + (rect.height || rect.bottom - rect.top) / 2;
      const candidate = Math.abs(pointerY - center);
      if (candidate < distance) { nearest = entry; distance = candidate; }
    }
    return nearest;
  }
  function clampPointerY(pointerY) {
    const panel = navigation.getBoundingClientRect();
    return Math.max(panel.top, Math.min(panel.bottom - 1, pointerY));
  }
  function revealEntry(entry) {
    if (!entry || !toggle.checked) return;
    const item = entry.link.getBoundingClientRect();
    const panel = navigation.getBoundingClientRect();
    if (item.top < panel.top + 12) navigation.scrollTop += item.top - panel.top - 12;
    else if (item.bottom > panel.bottom - 12) navigation.scrollTop += item.bottom - panel.bottom + 12;
    setIndicator(entry);
  }
  function navigate(entry) {
    if (!entry) return;
    select(entry);
    clearPreview();
    const hash = '#' + encodeURIComponent(entry.heading.id);
    if (window.history?.pushState) window.history.pushState(null, '', hash);
    else window.location.hash = hash;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    entry.heading.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
  }
  function finishDrag(commit, pointerId) {
    if (!dragState || (pointerId !== undefined && dragState.pointerId !== pointerId)) return;
    const state = dragState;
    const target = preview;
    dragState = null;
    delete navigation.dataset.dragging;
    if (state.dragging && state.sourceLink) {
      const token = {};
      suppressClick = { link: state.sourceLink, token };
      window.setTimeout?.(() => {
        if (suppressClick?.token === token) suppressClick = null;
      }, 0);
    }
    if (state.captureElement.hasPointerCapture?.(state.pointerId)) state.captureElement.releasePointerCapture(state.pointerId);
    if (commit && state.dragging && target) navigate(target);
    else clearPreview();
  }
  function beginDrag(captureElement, sourceLink, event) {
    if (event.button !== undefined && event.button !== 0) return;
    suppressClick = null;
    clearPreview();
    dragState = { pointerId: event.pointerId, startY: event.clientY, lastY: event.clientY,
      lastTime: event.timeStamp || 0, velocity: 0, dragging: false, captureElement, sourceLink };
    try { captureElement.setPointerCapture?.(event.pointerId); } catch (_) { /* Capture can fail after a synthetic event. */ }
  }
  function moveDrag(event) {
    if (!dragState || dragState.pointerId !== event.pointerId) return;
    if (!dragState.dragging && Math.abs(event.clientY - dragState.startY) < 6) return;
    dragState.dragging = true;
    navigation.dataset.dragging = 'true';
    event.preventDefault();
    const now = event.timeStamp || dragState.lastTime + 16;
    const elapsed = Math.max(8, now - dragState.lastTime);
    dragState.velocity = Math.max(-24, Math.min(24, (event.clientY - dragState.lastY) * 16 / elapsed));
    dragState.lastY = event.clientY;
    dragState.lastTime = now;
    const pointerY = clampPointerY(event.clientY);
    setPreview(nearestVisibleEntry(pointerY), pointerY);
  }
  dragHandle.addEventListener('pointerdown', event => beginDrag(dragHandle, null, event));
  dragHandle.addEventListener('pointermove', moveDrag);
  dragHandle.addEventListener('pointerup', event => finishDrag(true, event.pointerId));
  dragHandle.addEventListener('pointercancel', event => finishDrag(false, event.pointerId));
  dragHandle.addEventListener('lostpointercapture', event => finishDrag(false, event.pointerId));
  for (const entry of entries) {
    entry.link.setAttribute('draggable', 'false');
    entry.link.addEventListener('pointerdown', event => {
      if (entry !== active || event.pointerType === 'touch') return;
      beginDrag(entry.link, entry.link, event);
    });
    entry.link.addEventListener('pointermove', moveDrag);
    entry.link.addEventListener('pointerup', event => finishDrag(true, event.pointerId));
    entry.link.addEventListener('pointercancel', event => finishDrag(false, event.pointerId));
    entry.link.addEventListener('lostpointercapture', event => finishDrag(false, event.pointerId));
    entry.link.addEventListener('click', event => {
      if (suppressClick?.link !== entry.link || event.detail === 0) return;
      suppressClick = null;
      event.preventDefault();
      event.stopPropagation();
    });
  }
  dragHandle.addEventListener('keydown', event => {
    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      const available = visibleEntries();
      if (!available.length) return;
      const current = preview || active;
      const currentIndex = Math.max(0, available.indexOf(current));
      const offset = event.key === 'ArrowUp' ? -1 : 1;
      setPreview(available[Math.max(0, Math.min(available.length - 1, currentIndex + offset))]);
      revealEntry(preview);
      event.preventDefault();
    } else if (event.key === 'Enter' && preview) {
      event.preventDefault();
      navigate(preview);
    } else if (event.key === 'Escape' && preview) {
      event.preventDefault();
      event.stopPropagation();
      clearPreview();
    }
  });
  dragHandle.addEventListener('blur', clearPreview);
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

  function reveal() {
    revealEntry(active);
  }
  function update() {
    pending = false;
    if (dragState) {
      if (!preview) setIndicator(active);
      return;
    }
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
    if (select(selected)) reveal();
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
    if (event.key === 'Escape' && dragState) {
      event.preventDefault();
      finishDrag(false);
      dragHandle.focus();
      return;
    }
    if (event.key === 'Escape' && toggle.checked && !document.querySelector('dialog[open]')) {
      toggle.checked = false;
      toggleState();
      toggle.focus();
    }
  });
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule);
  lensMotion.addEventListener?.('change', () => {
    if (dragState) dragState.velocity = 0;
    setIndicator(preview || active, dragState?.dragging ? clampPointerY(dragState.lastY) : undefined);
  });
  navigation.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('hashchange', openHashAncestors);
  window.addEventListener('load', schedule);
  openHashAncestors();
  toggleState();
  update();
})();

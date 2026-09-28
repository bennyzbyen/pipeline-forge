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
  window.addEventListener('hashchange', schedule);
  window.addEventListener('load', schedule);
  toggleState();
  update();
})();

/* Trusted, offline-only viewer. Requirement text is never interpolated here. */
(() => {
  'use strict';
  const root = document.getElementById('waterline-diagram-viewer');
  if (!root || root.dataset.ready) return;
  root.dataset.ready = 'true';
  const dialog = root.querySelector('.wl-dialog');
  const stage = root.querySelector('.wl-stage');
  const art = root.querySelector('.wl-art');
  const zoomOutput = root.querySelector('.wl-zoom');
  const zoomIn = root.querySelector('[data-action="zoom-in"]');
  const zoomOut = root.querySelector('[data-action="zoom-out"]');
  const minimum = 0.05, maximum = 5;
  const view = { x: 0, y: 0, scale: 1, width: 1, height: 1 };
  const pointers = new Map();
  let drag = null, pinch = null, opener = null;
  const clamp = value => Math.max(minimum, Math.min(maximum, value));
  function paint() {
    art.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
    stage.dataset.scale = String(view.scale);
    stage.dataset.panX = String(view.x);
    stage.dataset.panY = String(view.y);
    zoomOutput.value = `${Math.round(view.scale * 100)}%`;
    zoomIn.disabled = view.scale >= maximum - 0.0001;
    zoomOut.disabled = view.scale <= minimum + 0.0001;
  }
  function fit() {
    const bounds = stage.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    view.scale = clamp(Math.min((bounds.width - 32) / view.width, (bounds.height - 32) / view.height, 1.4));
    view.x = (bounds.width - view.width * view.scale) / 2;
    view.y = (bounds.height - view.height * view.scale) / 2;
    paint();
  }
  function zoom(factor, anchorX, anchorY) {
    const bounds = stage.getBoundingClientRect();
    const x = anchorX ?? bounds.width / 2, y = anchorY ?? bounds.height / 2;
    const next = clamp(view.scale * factor), ratio = next / view.scale;
    view.x = x - (x - view.x) * ratio;
    view.y = y - (y - view.y) * ratio;
    view.scale = next;
    paint();
  }
  function open(button) {
    if (dialog.open) return;
    const original = button.querySelector('svg');
    if (!original) return;
    const svg = original.cloneNode(true);
    // Avoid duplicate marker, clip, and accessibility IDs while the original is visible.
    const ids = new Map();
    svg.querySelectorAll('[id]').forEach(node => {
      const previous = node.id, next = 'focus-' + previous;
      ids.set(previous, next); node.id = next;
    });
    [svg, ...svg.querySelectorAll('*')].forEach(node => {
      [...node.attributes].forEach(attribute => {
        if (attribute.name === 'id') return;
        let value = attribute.value;
        ids.forEach((next, previous) => {
          value = value.replaceAll(`url(#${previous})`, `url(#${next})`);
          if (value === `#${previous}`) value = `#${next}`;
        });
        if (attribute.name.startsWith('aria-')) value = value.split(' ').map(id => ids.get(id) || id).join(' ');
        node.setAttribute(attribute.name, value);
      });
    });
    opener = button;
    art.replaceChildren(svg);
    const box = svg.viewBox.baseVal;
    view.width = box.width; view.height = box.height;
    svg.style.width = `${box.width}px`;
    art.style.width = `${box.width}px`; art.style.height = `${box.height}px`;
    root.querySelector('#wl-dialog-title').textContent = button.dataset.caption || '流程图';
    dialog.showModal(); fit(); requestAnimationFrame(fit);
  }
  document.querySelectorAll('.waterline-diagram-open').forEach(button => button.addEventListener('click', () => open(button)));
  zoomIn.addEventListener('click', () => zoom(1.25));
  zoomOut.addEventListener('click', () => zoom(0.8));
  root.querySelector('[data-action="fit"]').addEventListener('click', fit);
  root.querySelector('[data-action="close"]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    pointers.clear(); drag = null; pinch = null; stage.dataset.dragging = 'false';
    art.replaceChildren();
    if (opener && opener.isConnected) opener.focus({ preventScroll: true });
  });
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const b = dialog.getBoundingClientRect();
    if (event.clientX < b.left || event.clientX > b.right || event.clientY < b.top || event.clientY > b.bottom) dialog.close();
  });
  dialog.addEventListener('keydown', event => {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === '+' || event.key === '=') { event.preventDefault(); zoom(1.25); }
    if (event.key === '-') { event.preventDefault(); zoom(0.8); }
    if (event.key === '0') { event.preventDefault(); fit(); }
  });
  stage.addEventListener('wheel', event => {
    event.preventDefault();
    const bounds = stage.getBoundingClientRect();
    const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? bounds.height : 1);
    zoom(Math.exp(-delta * 0.0018), event.clientX - bounds.left, event.clientY - bounds.top);
  }, { passive: false });
  function startGesture() {
    const points = Array.from(pointers.values());
    if (points.length === 1) {
      drag = { point: points[0], x: view.x, y: view.y }; pinch = null;
    } else if (points.length >= 2) {
      const b = stage.getBoundingClientRect();
      const middle = { x: (points[0].x + points[1].x) / 2 - b.left, y: (points[0].y + points[1].y) / 2 - b.top };
      pinch = { distance: Math.max(1, Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y)), scale: view.scale, worldX: (middle.x - view.x) / view.scale, worldY: (middle.y - view.y) / view.scale };
      drag = null;
    }
  }
  stage.addEventListener('pointerdown', event => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    event.preventDefault(); stage.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    stage.dataset.dragging = 'true'; startGesture();
  });
  stage.addEventListener('pointermove', event => {
    if (!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    const points = Array.from(pointers.values());
    if (pinch && points.length >= 2) {
      const b = stage.getBoundingClientRect();
      view.scale = clamp(pinch.scale * Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y) / pinch.distance);
      view.x = (points[0].x + points[1].x) / 2 - b.left - pinch.worldX * view.scale;
      view.y = (points[0].y + points[1].y) / 2 - b.top - pinch.worldY * view.scale;
    } else if (drag) {
      view.x = drag.x + event.clientX - drag.point.x; view.y = drag.y + event.clientY - drag.point.y;
    }
    paint();
  });
  function finishPointer(event) {
    pointers.delete(event.pointerId);
    if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
    drag = null; pinch = null;
    stage.dataset.dragging = pointers.size ? 'true' : 'false';
    if (pointers.size) startGesture();
  }
  stage.addEventListener('pointerup', finishPointer);
  stage.addEventListener('pointercancel', finishPointer);
  new ResizeObserver(() => { if (dialog.open) fit(); }).observe(stage);
})();

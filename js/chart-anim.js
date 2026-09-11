(function () {
  // Entrance animations run once per page load (not on option/filter switches).
  window.__chartAnim = window.__chartAnim || {};

  function once(key) {
    if (window.__chartAnim[key]) return false;
    window.__chartAnim[key] = true;
    return true;
  }

  function nextFrame(fn) {
    if (window.requestAnimationFrame) requestAnimationFrame(function () { requestAnimationFrame(fn); });
    else setTimeout(fn, 30);
  }

  var ChartAnim = {
    once: once,

    // Run `fn` once, only after `container` scrolls into view (or immediately
    // if already visible). Animations never restart on re-render or scroll-back.
    whenVisible: function (container, key, fn) {
      if (!fn) return;
      var run = function () { if (once(key)) fn(); };
      if (!container || !window.IntersectionObserver) { run(); return; }
      try {
        var rect = container.getBoundingClientRect();
        var vh = window.innerHeight || document.documentElement.clientHeight;
        if (rect.top < vh && rect.bottom > 0) { run(); return; }
        var obs = new IntersectionObserver(function (entries) {
          for (var i = 0; i < entries.length; i++) {
            if (entries[i].isIntersecting) { run(); obs.disconnect(); return; }
          }
        }, { threshold: 0.12 });
        obs.observe(container);
      } catch (e) { run(); }
    },

    // Vertical bars: grow from 0 height (scaleY) with optional stagger.
    growBars: function (elements, opts) {
      opts = opts || {};
      var els = Array.prototype.slice.call(elements || []);
      if (!els.length) return;
      els.forEach(function (b, i) {
        b.style.transformOrigin = 'bottom';
        b.style.transform = 'scaleY(0)';
        b.style.transition = 'transform ' + (opts.duration || 800) + 'ms cubic-bezier(0.22, 1, 0.36, 1)';
        b.style.transitionDelay = (i * (opts.stagger == null ? 60 : opts.stagger)) + 'ms';
      });
      nextFrame(function () {
        els.forEach(function (b) { b.style.transform = 'scaleY(1)'; });
      });
    },

    // Line/path draw-in using stroke dash offset.
    drawLine: function (path, opts) {
      opts = opts || {};
      if (!path || typeof path.getTotalLength !== 'function') return;
      var len;
      try { len = path.getTotalLength(); } catch (e) { return; }
      if (!len) return;
      path.style.strokeDasharray = len + ' ' + len;
      path.style.strokeDashoffset = len;
      path.style.transition = 'none';
      path.style.transitionDelay = (opts.delay || 0) + 'ms';
      nextFrame(function () {
        path.style.transition = 'stroke-dashoffset ' + (opts.duration || 1200) + 'ms ease';
        path.style.strokeDashoffset = '0';
      });
    },

    // Scatter / dot pop-in with optional fade + scale.
    popIn: function (elements, opts) {
      opts = opts || {};
      var els = Array.prototype.slice.call(elements || []);
      if (!els.length) return;
      var fade = opts.fade !== false;
      els.forEach(function (el, i) {
        el.style.transformOrigin = 'center';
        el.style.transform = 'scale(0.3)';
        if (fade) el.style.opacity = '0';
        el.style.transition = (fade ? 'opacity ' + (opts.duration || 450) + 'ms ease, ' : '') + 'transform ' + (opts.duration || 450) + 'ms cubic-bezier(0.22, 1, 0.36, 1)';
        el.style.transitionDelay = (i * (opts.stagger == null ? 22 : opts.stagger)) + 'ms';
      });
      nextFrame(function () {
        els.forEach(function (el) { el.style.transform = 'scale(1)'; if (fade) el.style.opacity = '1'; });
      });
    },

    // Animated donut/ring draw-in for stroke-dasharray based circles.
    drawDonut: function (segments, circ, opts) {
      opts = opts || {};
      var els = segments || [];
      els.forEach(function (s) { if (s.el) s.el.setAttribute('stroke-dasharray', '0 ' + circ); });
      var dur = opts.duration || 900;
      var start = (window.performance && performance.now) ? performance.now() : Date.now();
      function frame() {
        var now = (window.performance && performance.now) ? performance.now() : Date.now();
        var t = Math.min((now - start) / dur, 1);
        var e = 1 - Math.pow(1 - t, 3);
        els.forEach(function (s) {
          if (s.el) s.el.setAttribute('stroke-dasharray', (s.len * e) + ' ' + circ);
        });
        if (t < 1) requestAnimationFrame(frame);
      }
      if (window.requestAnimationFrame) requestAnimationFrame(frame);
      else els.forEach(function (s) { if (s.el) s.el.setAttribute('stroke-dasharray', s.len + ' ' + circ); });
    }
  };

  // Lightweight hover CSS (no layout thrash).
  var css = '.chart-anim-hover:hover{filter:brightness(1.08)}' +
    '.scatter-dot,.scatter-point,.quadrant-node{transition:r .15s ease,opacity .15s ease,filter .15s ease}' +
    '.scatter-dot:hover,.scatter-point:hover,.quadrant-node:hover{r:8;filter:drop-shadow(0 0 6px rgba(37,99,235,.5))}';
  var style = document.createElement('style');
  style.textContent = css;
  if (document.head) document.head.appendChild(style);
  else document.addEventListener('DOMContentLoaded', function () { document.head.appendChild(style); });

  window.ChartAnim = ChartAnim;
})();

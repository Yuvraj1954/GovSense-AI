(function () {
  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  var MEMBER_CACHE_KEY = 'classificationCache';
  var STATE_CACHE_KEY = 'stateClassificationCache';
  var CACHE_TTL_MS = 24 * 60 * 60 * 1000;
  var CACHE_VERSION = '2.0';

  function getCached(key) {
    try {
      var raw = localStorage.getItem(key);
      if (!raw) return null;
      var cached = JSON.parse(raw);
      if (cached.v !== CACHE_VERSION) return null;
      if (Date.now() - cached.timestamp > CACHE_TTL_MS) return null;
      return cached;
    } catch (e) { return null; }
  }

  function setCache(key, data) {
    localStorage.setItem(key, JSON.stringify({ data: data, timestamp: Date.now(), v: CACHE_VERSION }));
  }

  function clearStaleCaches() {
    try {
      var keys = Object.keys(localStorage);
      for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        if (k.indexOf('classificationCache') === 0 || k.indexOf('stateClassificationCache') === 0) {
          var raw = localStorage.getItem(k);
          if (raw) {
            var cached = JSON.parse(raw);
            if (cached.v !== CACHE_VERSION) localStorage.removeItem(k);
          }
        }
      }
    } catch (e) {}
  }

  // ── Member Classification (dashboard + mps.html) ──
  function updateMemberDOM(items, total) {
    var map = {};
    items.forEach(function (item) { map[item.classification] = item.count; });

    // Dashboard IDs (cls-*) and mps.html IDs (mp-cls-*)
    var idMap = {
      EXCEPTIONAL:       ['cls-performer',   'mp-cls-performer'],
      PERFORMER:         ['cls-performer',   'mp-cls-performer'],
      STABLE:            ['cls-average',     'mp-cls-average'],
      AVERAGE:           ['cls-average',     'mp-cls-average'],
      NEEDS_ATTENTION:   ['cls-needs',       'mp-cls-needs'],
      UNDERPERFORMER:    ['cls-under',       'mp-cls-under'],
      NO_DATA:           ['cls-nodata',      'mp-cls-nodata'],
      INSUFFICIENT_DATA: ['cls-insufficient','mp-cls-insufficient']
    };

    var countClasses = ['cls-count', 'mp-cls-count'];
    var pctClasses   = ['cls-pct',   'mp-cls-pct'];
    var barClasses   = ['cls-bar',   'mp-cls-bar'];

    Object.keys(idMap).forEach(function (label) {
      var count = map[label] || 0;
      var pct = total > 0 ? ((count / total) * 100).toFixed(1) : '0.0';

      idMap[label].forEach(function (rowId) {
        var row = document.getElementById(rowId);
        if (!row) return;

        countClasses.forEach(function (cls) {
          var el = row.querySelector('.' + cls);
          if (el) el.textContent = count.toLocaleString();
        });
        pctClasses.forEach(function (cls) {
          var el = row.querySelector('.' + cls);
          if (el) el.textContent = pct + '%';
        });
        barClasses.forEach(function (cls) {
          var el = row.querySelector('.' + cls);
          if (el) el.style.width = pct + '%';
        });
      });
    });

    // Summary insights for mps.html
    var sorted = items.slice().sort(function (a, b) { return b.count - a.count; });
    var top = sorted[0];
    var topEl = document.getElementById('mp-cls-top-label');
    if (topEl && top) topEl.textContent = top.classification.replace('_', ' ');

    var healthy = (map['EXCEPTIONAL'] || 0) + (map['PERFORMER'] || 0) + (map['STABLE'] || 0) + (map['AVERAGE'] || 0);
    var healthyPctEl = document.getElementById('mp-cls-healthy-pct');
    if (healthyPctEl) healthyPctEl.textContent = total > 0 ? ((healthy / total) * 100).toFixed(1) + '%' : '—';

    var risk = (map['UNDERPERFORMER'] || 0) + (map['NEEDS_ATTENTION'] || 0);
    var riskPctEl = document.getElementById('mp-cls-risk-pct');
    if (riskPctEl) riskPctEl.textContent = total > 0 ? ((risk / total) * 100).toFixed(1) + '%' : '—';
  }

  // ── State Classification ──
  function updateStateDOM(states) {
    var dist = {};
    states.forEach(function (s) {
      var cls = s.performance_classification;
      dist[cls] = (dist[cls] || 0) + 1;
    });

    var stateIds = {
      EXCEPTIONAL: 'st-performer',
      PERFORMER: 'st-performer',
      STABLE: 'st-average',
      AVERAGE: 'st-average',
      NEEDS_ATTENTION: 'st-needs',
      UNDERPERFORMER: 'st-under',
      NO_DATA: 'st-nodata',
      INSUFFICIENT_DATA: 'st-insufficient'
    };

    Object.keys(stateIds).forEach(function (label) {
      var el = document.getElementById(stateIds[label]);
      if (el) el.textContent = dist[label] || 0;
    });
  }

  function fetchMember() {
    return fetch(API_BASE + '/api/classification/distribution')
      .then(function (res) { if (!res.ok) throw new Error(); return res.json(); })
      .then(function (data) { setCache(MEMBER_CACHE_KEY, data); updateMemberDOM(data.items, data.total); })
      .catch(function () { });
  }

  function fetchStates() {
    return fetch(API_BASE + '/api/classification/states')
      .then(function (res) { if (!res.ok) throw new Error(); return res.json(); })
      .then(function (data) { setCache(STATE_CACHE_KEY, data); updateStateDOM(data); })
      .catch(function () { });
  }

  document.addEventListener('DOMContentLoaded', function () {
    clearStaleCaches();

    var memberCached = getCached(MEMBER_CACHE_KEY);
    if (memberCached) { updateMemberDOM(memberCached.data.items, memberCached.data.total); }
    else { fetchMember(); }

    var stateCached = getCached(STATE_CACHE_KEY);
    if (stateCached) { updateStateDOM(stateCached.data); }
    else { fetchStates(); }
  });
})();

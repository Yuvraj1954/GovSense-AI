(function () {
  // ---------------------------------------------------------------------------
  // Header "Data updated …" reliability fix.
  //
  // ROOT CAUSE (previous version):
  //   1. `formatIST()` never validated its input. Any missing/invalid value
  //      produced "NaN undefined NaN · NaN:NaN IST".
  //   2. `dataUpdatedCache` had TWO incompatible schemas:
  //        - index.html preloader wrote { data: {...}, ts }
  //        - this file wrote        { completed_at, timestamp }
  //      Reading the other schema yielded `undefined` for the timestamp AND for
  //      the freshness field (so the entry never expired), which then fed
  //      undefined straight into the formatter.
  //
  // FIX: one tolerant reader, one schema written, strict validation, and an
  // explicit "Data update unavailable" instead of fabricated output.
  // ---------------------------------------------------------------------------

  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  var CACHE_KEY = 'dataUpdatedCache';
  var CACHE_TTL_MS = 24 * 60 * 60 * 1000;
  var UNAVAILABLE_TEXT = 'Data update unavailable';
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  // IST is a fixed UTC+05:30 offset (no daylight saving), so converting via a
  // fixed offset avoids the fragile toLocaleString -> new Date round-trip.
  var IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

  // App-scoped cache keys that belong to GovSense. Used only for a one-time
  // reset when the frontend version changes so an old cache schema cannot be
  // mixed with new code. Unrelated browser storage is never touched.
  var APP_CACHE_KEYS = [
    'dataUpdatedCache', 'overviewCache', 'trendCache', 'statePerfCache',
    'classificationCache', 'stateClassificationCache', 'projectSummaryCache',
    'riskOverviewCache', 'riskAlertsCache', 'statesListCache',
    'riskEntitiesCache', 'scatterCache',
  ];

  function resetCachesOnVersionChange() {
    try {
      var version = (typeof window.APP_VERSION === 'string' && window.APP_VERSION)
        ? window.APP_VERSION : 'unknown';
      var last = localStorage.getItem('govsenseAppVersion');
      if (last === version) return;
      for (var i = 0; i < APP_CACHE_KEYS.length; i++) {
        try { localStorage.removeItem(APP_CACHE_KEYS[i]); } catch (e) {}
      }
      localStorage.setItem('govsenseAppVersion', version);
    } catch (e) {}
  }

  // Returns a valid Date, or null. Never returns an Invalid Date.
  function toValidDate(value) {
    if (value === null || value === undefined || value === '') return null;
    var date = (value instanceof Date) ? value : new Date(value);
    if (isNaN(date.getTime())) return null;
    return date;
  }

  // Formats a backend timestamp as "14 Sep 2026 · 7:02 PM IST".
  // Returns null when the value cannot be parsed (never NaN/undefined text).
  function formatIST(value) {
    var date = toValidDate(value);
    if (!date) return null;
    var ist = new Date(date.getTime() + IST_OFFSET_MS);
    var day = ist.getUTCDate();
    var month = MONTHS[ist.getUTCMonth()];
    var year = ist.getUTCFullYear();
    var hour24 = ist.getUTCHours();
    var minute = ist.getUTCMinutes();
    if (!day || !month || !year || isNaN(hour24) || isNaN(minute)) return null;
    var period = hour24 >= 12 ? 'PM' : 'AM';
    var hour12 = hour24 % 12;
    if (hour12 === 0) hour12 = 12;
    var mm = (minute < 10 ? '0' : '') + minute;
    return day + ' ' + month + ' ' + year + ' \u00B7 ' + hour12 + ':' + mm + ' ' + period + ' IST';
  }

  // Reads the cache, tolerating BOTH historical schemas, and returns the raw
  // timestamp value (or null when there is no usable, fresh entry).
  function getCached() {
    try {
      var raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      var cached = JSON.parse(raw);
      if (!cached || typeof cached !== 'object') return null;

      var ts = (typeof cached.timestamp === 'number') ? cached.timestamp
        : (typeof cached.ts === 'number') ? cached.ts : null;
      // Unknown age -> treat as unusable rather than "fresh forever".
      if (ts === null || (Date.now() - ts) > CACHE_TTL_MS) return null;

      if (cached.data && cached.data.completed_at !== undefined) return cached.data.completed_at;
      if (cached.completed_at !== undefined) return cached.completed_at;
      return null;
    } catch (e) {
      return null;
    }
  }

  // Writes BOTH shapes so either reader (this file or index.html) works.
  function setCache(completedAt) {
    try {
      var now = Date.now();
      localStorage.setItem(CACHE_KEY, JSON.stringify({
        data: { completed_at: completedAt },
        completed_at: completedAt,
        ts: now,
        timestamp: now,
      }));
    } catch (e) {}
  }

  function statusDotClass(isValid) {
    return 'w-1.5 h-1.5 rounded-full ' + (isValid ? 'bg-emerald-500' : 'bg-slate-400');
  }

  function updateDOM(completedAt) {
    var display = formatIST(completedAt);
    var isValid = display !== null;
    var headerText = isValid ? ('Data updated ' + display) : UNAVAILABLE_TEXT;
    var sidebarText = isValid ? display : 'unavailable';

    // Top header badge. The text is wrapped in an element so the existing
    // mobile rule (hide everything except the .w-1.5 dot) keeps working.
    var headerBadge = null;
    var candidates = document.querySelectorAll('header span');
    for (var i = 0; i < candidates.length; i++) {
      var el = candidates[i];
      if (el.classList.contains('w-1.5') &&
          el.classList.contains('rounded-full') &&
          el.classList.contains('bg-emerald-500')) {
        headerBadge = el;
        break;
      }
    }
    if (!headerBadge) {
      var alt = document.querySelector('header span.inline-flex span.w-1\\.5');
      if (alt) headerBadge = alt;
    }
    if (headerBadge && headerBadge.parentElement) {
      var badge = headerBadge.parentElement;
      badge.innerHTML = '<span class="' + statusDotClass(isValid) + '"></span>' +
        '<span>' + headerText + '</span>';
      badge.setAttribute('title', headerText);
    }

    // Sidebar collapsed status (title attribute only)
    var collapsedDot = document.getElementById('sidebarCollapsedStatus');
    if (collapsedDot) {
      var dotSpan = collapsedDot.querySelector('span');
      if (dotSpan) {
        dotSpan.setAttribute('title', isValid ? ('Database Synced: ' + display) : UNAVAILABLE_TEXT);
      }
    }

    // Sidebar expanded status paragraph
    var expandedCard = document.getElementById('sidebarExpandedStatus');
    if (expandedCard) {
      var paragraphs = expandedCard.querySelectorAll('p');
      for (var j = 0; j < paragraphs.length; j++) {
        var content = paragraphs[j].textContent;
        if (content.indexOf('Last updated:') !== -1 || content.indexOf('Updated ') !== -1 ||
            content.indexOf('unavailable') !== -1) {
          var backendReady = paragraphs[j].querySelector('.text-emerald-600');
          var suffix = backendReady ? ' ' + backendReady.outerHTML : '';
          paragraphs[j].innerHTML = 'Last updated: ' + sidebarText + suffix;
          break;
        }
      }
    }
  }

  function fetchData() {
    return fetch(API_BASE + '/api/data-updated')
      .then(function (res) {
        if (!res.ok) throw new Error('API error ' + res.status);
        return res.json();
      })
      .then(function (data) {
        var completedAt = null;
        if (data && typeof data === 'object') {
          if (data.completed_at !== undefined) completedAt = data.completed_at;
          else if (data.data && data.data.completed_at !== undefined) completedAt = data.data.completed_at;
        }
        if (completedAt !== null && formatIST(completedAt) !== null) {
          setCache(completedAt);
        }
        updateDOM(completedAt);
      })
      .catch(function () {
        // Do NOT leave a stale/fabricated date in place. Prefer a cached valid
        // value; otherwise show the explicit unavailable state.
        var cached = getCached();
        updateDOM((cached !== null && formatIST(cached) !== null) ? cached : null);
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    resetCachesOnVersionChange();
    var cached = getCached();
    if (cached !== null && formatIST(cached) !== null) {
      updateDOM(cached);
    } else {
      fetchData();
    }
  });
})();

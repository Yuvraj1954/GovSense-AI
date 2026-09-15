(function () {
  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  var KPI_CACHE_KEY = 'mpsKpiCache';
  var LIST_CACHE_KEY = 'mpsListCache';
  var CACHE_TTL_MS = 24 * 60 * 60 * 1000;
  var CACHE_VERSION = '2.1';

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
    try { localStorage.setItem(key, JSON.stringify({ data: data, timestamp: Date.now(), v: CACHE_VERSION })); } catch (e) {}
  }

  function clearStaleCaches() {
    try {
      var keys = Object.keys(localStorage);
      for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        if (k.indexOf('mpsKpiCache') === 0 || k.indexOf('mpsListCache') === 0) {
          var raw = localStorage.getItem(k);
          if (raw) {
            var cached = JSON.parse(raw);
            if (cached.v !== CACHE_VERSION) localStorage.removeItem(k);
          }
        }
      }
    } catch (e) {}
  }

  function fmtNum(n) {
    if (n == null) return '—';
    return Number(n).toLocaleString('en-IN');
  }

  function fmtCr(n) {
    if (n == null) return '—';
    var cr = Number(n) / 1e7;
    return '₹' + cr.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' Cr';
  }

  function fmtPct(n) {
    if (n == null) return '—';
    return Number(n).toFixed(1) + '%';
  }

  function updateKPIs(d) {
    var el;
    el = document.getElementById('kpi-total-members');
    if (el) el.textContent = fmtNum(d.total_members);
    el = document.getElementById('kpi-total-allocated');
    if (el) el.textContent = fmtCr(d.recommended_amount);
    el = document.getElementById('kpi-total-expenditure');
    if (el) el.textContent = fmtCr(d.expenditure_amount);
    el = document.getElementById('kpi-fund-utilization');
    if (el) el.textContent = fmtPct(d.fund_utilization_pct);
    el = document.getElementById('kpi-total-works');
    if (el) el.textContent = fmtNum(d.total_works);
    el = document.getElementById('kpi-completed-works');
    if (el) el.innerHTML = fmtNum(d.completed_works) + ' <span class="text-xs font-semibold text-emerald-600">(' + fmtPct(d.completion_rate_pct) + ')</span>';
    var ongoing = d.ongoing_works || 0;
    var ongoingPct = d.total_works > 0 ? ((ongoing / d.total_works) * 100).toFixed(1) : '0.0';
    el = document.getElementById('kpi-ongoing-works');
    if (el) el.innerHTML = fmtNum(ongoing) + ' <span class="text-xs font-semibold text-blue-600">(' + ongoingPct + '%)</span>';
    var pending = d.pending_works || 0;
    var pendingPct = d.total_works > 0 ? ((pending / d.total_works) * 100).toFixed(1) : '0.0';
    el = document.getElementById('kpi-pending-works');
    if (el) el.innerHTML = fmtNum(pending) + ' <span class="text-xs font-semibold text-amber-600">(' + pendingPct + '%)</span>';
  }

  function fetchKPIs() {
    return fetch(API_BASE + '/api/overview?scope=BOTH')
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (data) { setCache(KPI_CACHE_KEY, data); updateKPIs(data); })
      .catch(function () {});
  }

  function renderHistogram(members) {
    var total = members.length;
    if (total === 0) return;
    var buckets = { high: 0, moderate: 0, low: 0, critical: 0 };
    members.forEach(function (m) {
      var u = Number(m.fund_utilization_pct) || 0;
      if (u >= 70) buckets.high++;
      else if (u >= 50) buckets.moderate++;
      else if (u >= 30) buckets.low++;
      else buckets.critical++;
    });
    function set(id, count) {
      var pct = total > 0 ? ((count / total) * 100).toFixed(1) : '0.0';
      var countEl = document.getElementById('hist-' + id + '-count');
      var pctEl = document.getElementById('hist-' + id + '-pct');
      var barEl = document.getElementById('hist-' + id + '-bar');
      if (countEl) countEl.textContent = count + ' MPs';
      if (pctEl) pctEl.textContent = pct + '%';
      if (barEl) barEl.style.width = pct + '%';
    }
    set('high', buckets.high);
    set('moderate', buckets.moderate);
    set('low', buckets.low);
    set('critical', buckets.critical);
    var benchmark = document.getElementById('hist-benchmark');
    var evaluated = document.getElementById('hist-total-evaluated');
    if (benchmark) benchmark.textContent = 'Total MPs evaluated: ' + fmtNum(total);
    if (evaluated) evaluated.textContent = '';
  }

  function renderScatter(members) {
    var container = document.getElementById('scatter-points');
    if (!container) return;
    container.innerHTML = '';
    var svgNS = 'http://www.w3.org/2000/svg';
    var chartX0 = 60, chartX1 = 960, chartY0 = 30, chartY1 = 330;
    var w = chartX1 - chartX0, h = chartY1 - chartY0;
    var colorMap = { EXCEPTIONAL: '#10b981', PERFORMER: '#10b981', STABLE: '#3b82f6', AVERAGE: '#3b82f6', NEEDS_ATTENTION: '#f59e0b', UNDERPERFORMER: '#ef4444', NO_DATA: '#cbd5e1', INSUFFICIENT_DATA: '#a78bfa' };
    members.forEach(function (m) {
      var util = Number(m.fund_utilization_pct) || 0;
      var comp = Number(m.completion_rate_pct) || 0;
      var cx = chartX0 + (util / 100) * w;
      var cy = chartY1 - (comp / 100) * h;
      var fill = colorMap[m.performance_classification] || '#94a3b8';
      var circle = document.createElementNS(svgNS, 'circle');
      circle.setAttribute('class', 'scatter-point');
      circle.setAttribute('cx', cx.toFixed(1));
      circle.setAttribute('cy', cy.toFixed(1));
      circle.setAttribute('r', '4');
      circle.setAttribute('fill', fill);
      circle.setAttribute('stroke', '#ffffff');
      circle.setAttribute('stroke-width', '1');
      circle.setAttribute('opacity', '0.75');
      circle.setAttribute('data-mp', m.member_name || '');
      circle.setAttribute('data-place', m.state_name || '');
      circle.setAttribute('data-util', fmtPct(util));
      circle.setAttribute('data-comp', fmtPct(comp));
      circle.addEventListener('mouseenter', function (e) {
        circle.setAttribute('r', '7');
        circle.setAttribute('opacity', '1');
        showScatterTooltip(e, m);
      });
      circle.addEventListener('mouseleave', function () {
        circle.setAttribute('r', '4');
        circle.setAttribute('opacity', '0.75');
        hideScatterTooltip();
      });
      container.appendChild(circle);
    });

    if (window.ChartAnim) {
      window.ChartAnim.whenVisible(container, 'mpsScatter', function () {
        window.ChartAnim.popIn(container.querySelectorAll('circle'), { fade: false, stagger: 5, duration: 500 });
      });
    }
  }

  function showScatterTooltip(e, m) {
    var tip = document.getElementById('scatterTooltip');
    if (!tip) return;
    var cls = m.performance_classification || 'N/A';
    var score = Number(m.performance_score) || 0;
    tip.innerHTML =
      '<div class="font-bold text-white text-xs">' + (m.member_name || 'Unknown') + '</div>' +
      '<div class="text-[11px] text-slate-300 mt-0.5">' + (m.state_name || '') + ' · ' + cls + ' · ' + score.toFixed(0) + '/200</div>' +
      '<div class="mt-1 pt-1 border-t border-slate-700/80 flex items-center gap-3 text-[10px]">' +
      '<span>Utilization: <strong class="text-emerald-400 font-bold">' + fmtPct(m.fund_utilization_pct) + '</strong></span>' +
      '<span>Completion: <strong class="text-blue-400 font-bold">' + fmtPct(m.completion_rate_pct) + '</strong></span>' +
      '</div>';
    var wrap = tip.closest('.relative') || tip.parentElement;
    var wrapRect = wrap.getBoundingClientRect();
    tip.style.left = (e.clientX - wrapRect.left) + 'px';
    tip.style.top = (e.clientY - wrapRect.top - 60) + 'px';
    tip.classList.remove('opacity-0');
  }

  function hideScatterTooltip() {
    var tip = document.getElementById('scatterTooltip');
    if (tip) tip.classList.add('opacity-0');
  }

  function fetchScatterAndHistogram() {
    var SCATTER_CACHE_KEY = 'mpsScatterCache_' + _currentHouse;
    var cached = getCached(SCATTER_CACHE_KEY);
    if (cached && Array.isArray(cached.data)) {
      renderHistogram(cached.data);
      renderScatter(cached.data);
    }
    return fetch(API_BASE + '/api/members/scatter?member_type=' + _currentHouse)
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (data) {
        setCache(SCATTER_CACHE_KEY, data);
        renderHistogram(data);
        renderScatter(data);
      })
      .catch(function () {});
  }

  var currentPage = 1;
  var PAGE_SIZE = 6;
  var _currentSort = 'mixed';
  var _currentHouse = 'BOTH';
  var _searchQuery = '';
  var _searchTimeout = null;

  function getInitials(name) {
    if (!name) return '??';
    var parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function colorForCls(cls) {
    var map = {
      EXCEPTIONAL: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', bar: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-600' },
      PERFORMER: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', bar: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-600' },
      STABLE: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', bar: 'bg-blue-500', badge: 'bg-blue-50 text-blue-600' },
      AVERAGE: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', bar: 'bg-blue-500', badge: 'bg-blue-50 text-blue-600' },
      NEEDS_ATTENTION: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', bar: 'bg-amber-500', badge: 'bg-amber-50 text-amber-600' },
      UNDERPERFORMER: { bg: 'bg-rose-50', border: 'border-rose-200', text: 'text-rose-700', bar: 'bg-rose-500', badge: 'bg-rose-50 text-rose-600' }
    };
    return map[cls] || { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-700', bar: 'bg-slate-500', badge: 'bg-slate-50 text-slate-600' };
  }

  function buildCard(m) {
    var cls = m.performance_classification || 'NO_DATA';
    var c = colorForCls(cls);
    var util = Number(m.fund_utilization_pct) || 0;
    var comp = Number(m.completion_rate_pct) || 0;
    var alloc = Number(m.sanctioned_amount) || 0;
    var exp = Number(m.expenditure_amount) || 0;
    var completed = m.completed_works || 0;
    var recommended = m.sanctioned_works || m.total_works || 0;
    var initials = getInitials(m.member_name);
    var utilColor = util >= 50 ? 'text-emerald-600' : util >= 30 ? 'text-amber-600' : 'text-rose-600';
    var compColor = comp >= 50 ? 'text-emerald-600' : comp >= 30 ? 'text-blue-600' : 'text-rose-600';
    var houseLabel = (m.member_type_field || m.member_type) === 'MLA' ? 'Rajya Sabha' : 'Lok Sabha';
    var detailUrl = 'mpdetail.html?member_id=' + (m.member_id || '') + '&member_type=' + encodeURIComponent(m.member_type_field || m.member_type || 'MP');

    return '<article class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs hover:shadow-md hover:border-blue-400 transition-all duration-200 flex flex-col justify-between">' +
      '<div>' +
      '<div class="flex items-start justify-between gap-2">' +
      '<div class="flex items-center gap-3">' +
      '<div class="w-10 h-10 rounded-full ' + c.bg + ' border ' + c.border + ' flex items-center justify-center ' + c.text + ' font-bold text-sm flex-shrink-0">' + initials + '</div>' +
      '<div>' +
      '<h3 class="text-sm font-bold text-slate-900 leading-snug">' + (m.member_name || 'Unknown') + '</h3>' +
      '<div class="flex items-center gap-1 text-[11px] text-slate-500 mt-0.5">' +
      '<svg class="w-3 h-3 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path><path d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>' +
      '<span>' + (m.state_name || 'India') + '</span>' +
      '</div></div></div>' +
      '<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ' + c.bg + ' ' + c.text + ' border ' + c.border + '">' + cls.replace(/_/g, ' ') + '</span>' +
      '</div>' +
      '<div class="flex items-center gap-2 mt-3">' +
      '<span class="text-[10px] font-medium bg-slate-100 text-slate-600 px-2 py-0.5 rounded">' + houseLabel + '</span>' +
      '<span class="text-[10px] font-medium bg-slate-100 text-slate-600 px-2 py-0.5 rounded flex items-center gap-1">' +
      '<span class="w-1 h-1 rounded-full ' + (util >= 50 ? 'bg-emerald-500' : 'bg-amber-500') + '"></span> ' + (util >= 50 ? 'On Track' : 'Review Needed') + '</span>' +
      '</div>' +
      '<div class="grid grid-cols-2 gap-2 mt-4 p-2.5 rounded-lg bg-slate-50/80 border border-slate-100">' +
      '<div><span class="text-[10px] font-semibold uppercase text-slate-400 tracking-wider">ALLOCATED</span>' +
      '<div class="text-sm font-bold text-slate-900 mt-0.5">₹' + (alloc / 1e7).toFixed(1) + ' <span class="text-xs text-slate-500">CR</span></div></div>' +
      '<div><span class="text-[10px] font-semibold uppercase text-slate-400 tracking-wider">RECORDED EXP.</span>' +
      '<div class="text-sm font-bold text-slate-900 mt-0.5">₹' + (exp / 1e7).toFixed(1) + ' <span class="text-xs text-slate-500">CR</span></div></div>' +
      '</div>' +
      '<div class="mt-3.5">' +
      '<div class="flex justify-between items-center text-xs mb-1">' +
      '<span class="text-[11px] font-semibold text-slate-600">Fund Utilization</span>' +
      '<span class="font-bold ' + utilColor + ' text-xs">' + fmtPct(util) + '</span>' +
      '</div>' +
      '<div class="w-full h-2 bg-slate-100 rounded-full overflow-hidden">' +
      '<div class="h-full ' + c.bar + ' rounded-full" style="width: ' + Math.min(util, 100) + '%;"></div>' +
      '</div>' +
      '<div class="text-[10px] text-slate-400 mt-1">₹' + (exp / 1e7).toFixed(1) + ' Cr recorded of ₹' + (alloc / 1e7).toFixed(1) + ' Cr allocated</div>' +
      '</div>' +
      '<div class="mt-3 grid grid-cols-2 gap-2 text-xs">' +
      '<div class="p-2 border border-slate-100 rounded-lg"><span class="text-[10px] text-slate-400">Completed Works</span><div class="font-bold text-slate-800 text-sm mt-0.5">' + fmtNum(completed) + '</div></div>' +
      '<div class="p-2 border border-slate-100 rounded-lg"><span class="text-[10px] text-slate-400">Recommended</span><div class="font-bold text-slate-800 text-sm mt-0.5">' + fmtNum(recommended) + '</div></div>' +
      '</div>' +
      '<div class="flex justify-between items-center text-[11px] text-slate-500 mt-1.5 px-0.5">' +
      '<span>Completion Rate</span>' +
      '<span class="font-semibold ' + compColor + '">' + fmtPct(comp) + '</span>' +
      '</div>' +
      '</div>' +
      '<div class="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">' +
      '<span class="text-[11px] text-slate-400 font-mono">ID: ' + (m.member_id || '—') + '</span>' +
      '<a href="' + detailUrl + '" class="text-xs font-semibold text-slate-900 hover:text-blue-600 flex items-center gap-1 transition-colors group">' +
      '<span>View MP Details</span><span class="group-hover:translate-x-0.5 transition-transform">\u2192</span></a>' +
      '</div></article>';
  }

  function renderCards(data, keepVisible) {
    var container = document.getElementById('mp-cards-container');
    if (!container) return;
    if (!data.items || data.items.length === 0) {
      container.innerHTML = '<div class="col-span-3 text-center py-8 text-slate-400 text-sm">No members found</div>';
      return;
    }
    var html = data.items.map(buildCard).join('');
    if (keepVisible) {
      var temp = document.createElement('div');
      temp.innerHTML = html;
      while (temp.firstChild) container.appendChild(temp.firstChild);
    } else {
      container.innerHTML = html;
    }
  }

  function renderPagination(data) {
    var showing = document.getElementById('mp-showing-text');
    var btns = document.getElementById('mp-page-buttons');
    if (!showing || !btns) return;
    var start = (data.page - 1) * data.page_size + 1;
    var end = Math.min(data.page * data.page_size, data.total);
    var label = _currentHouse === 'BOTH' ? 'Members' : (_currentHouse === 'MLA' ? 'MLAs' : 'MPs');
    showing.innerHTML = 'Showing <strong class="text-slate-900 font-semibold">' + start + '</strong> to <strong class="text-slate-900 font-semibold">' + end + '</strong> of <strong class="text-slate-900 font-semibold">' + data.total + '</strong> ' + label;
    var html = '';
    html += '<button class="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 font-medium text-xs' + (data.page <= 1 ? ' text-slate-400 cursor-not-allowed' : '') + '" data-page="' + (data.page - 1) + '"' + (data.page <= 1 ? ' disabled' : '') + '>Previous</button>';
    var pages = [];
    if (data.total_pages <= 5) { for (var i = 1; i <= data.total_pages; i++) pages.push(i); }
    else {
      pages.push(1);
      if (data.page > 3) pages.push('...');
      for (var j = Math.max(2, data.page - 1); j <= Math.min(data.total_pages - 1, data.page + 1); j++) pages.push(j);
      if (data.page < data.total_pages - 2) pages.push('...');
      pages.push(data.total_pages);
    }
    pages.forEach(function (p) {
      if (p === '...') { html += '<span class="px-1 text-slate-400">...</span>'; }
      else {
        var active = p === data.page;
        html += '<button class="w-8 h-8 rounded-lg ' + (active ? 'bg-blue-600 text-white font-semibold shadow-xs' : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 font-medium') + ' text-xs" data-page="' + p + '">' + p + '</button>';
      }
    });
    html += '<button class="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 font-medium text-xs' + (data.page >= data.total_pages ? ' text-slate-400 cursor-not-allowed' : '') + '" data-page="' + (data.page + 1) + '"' + (data.page >= data.total_pages ? ' disabled' : '') + '>Next</button>';
    btns.innerHTML = html;
    btns.querySelectorAll('button[data-page]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var pg = parseInt(btn.getAttribute('data-page'));
        if (pg && pg !== currentPage && pg >= 1 && pg <= data.total_pages) { currentPage = pg; loadCards(pg, false); }
      });
    });
  }

  function buildListUrl(page) {
    var url = API_BASE + '/api/members/list?member_type=' + _currentHouse + '&page=' + page + '&page_size=' + PAGE_SIZE + '&sort_by=' + _currentSort + '&sort_dir=desc';
    var stateFilter = document.getElementById('stateFilter');
    var clsFilter = document.getElementById('classificationFilter');
    if (stateFilter && stateFilter.value) url += '&state=' + encodeURIComponent(stateFilter.value);
    if (clsFilter && clsFilter.value) url += '&classification=' + encodeURIComponent(clsFilter.value);
    return url;
  }

  function loadCards(page, useCache) {
    var cacheKey = LIST_CACHE_KEY + '_' + _currentHouse + '_' + _currentSort + '_' + page;
    if (useCache) {
      var cached = getCached(cacheKey);
      if (cached) { renderCards(cached.data); renderPagination(cached.data); return; }
    }
    var container = document.getElementById('mp-cards-container');
    var spinner = document.getElementById('mp-loading-spinner');
    if (spinner) spinner.classList.remove('hidden');
    fetch(buildListUrl(page))
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (data) {
        setCache(cacheKey, data);
        if (spinner) spinner.classList.add('hidden');
        renderCards(data);
        renderPagination(data);
      })
      .catch(function () { if (spinner) spinner.classList.add('hidden'); });
  }

  function setupSortButtons() {
    var container = document.getElementById('mpSortButtons');
    if (!container) return;
    var btns = container.querySelectorAll('.mp-sort-btn');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        btns.forEach(function (b) {
          b.classList.remove('bg-blue-600', 'text-white', 'shadow-xs', 'font-semibold');
          b.classList.add('border', 'border-slate-200', 'bg-white', 'text-slate-600', 'font-medium');
        });
        btn.classList.add('bg-blue-600', 'text-white', 'shadow-xs', 'font-semibold');
        btn.classList.remove('border', 'border-slate-200', 'bg-white', 'text-slate-600', 'font-medium');
        _currentSort = btn.getAttribute('data-sort');
        currentPage = 1;
        loadCards(1, false);
      });
    });
  }

  function setupHouseFilter() {
    var sel = document.getElementById('houseFilter');
    if (!sel) return;
    sel.addEventListener('change', function () {
      _currentHouse = sel.value;
      currentPage = 1;
      loadCards(1, false);
      fetchScatterAndHistogram();
    });
  }

  function setupSearch() {
    var input = document.getElementById('mpSearchInput');
    var clearBtn = document.getElementById('clearSearchBtn');
    var dropdown = document.getElementById('autocompleteDropdown');
    if (!input || !dropdown) return;

    input.addEventListener('focus', function () {
      if (input.value.trim().length >= 3) performSearch(input.value.trim());
    });

    input.addEventListener('input', function () {
      var val = input.value.trim();
      if (clearBtn) clearBtn.classList.toggle('hidden', val.length === 0);
      if (_searchTimeout) clearTimeout(_searchTimeout);
      if (val.length < 3) { dropdown.classList.add('hidden'); return; }
      _searchTimeout = setTimeout(function () { performSearch(val); }, 150);
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        input.value = '';
        clearBtn.classList.add('hidden');
        dropdown.classList.add('hidden');
        _searchQuery = '';
        currentPage = 1;
        loadCards(1, false);
        input.focus();
      });
    }

    document.addEventListener('click', function (e) {
      var wrapper = document.getElementById('searchWrapper');
      if (wrapper && !wrapper.contains(e.target)) dropdown.classList.add('hidden');
    });
  }

  function performSearch(query) {
    var dropdown = document.getElementById('autocompleteDropdown');
    if (!dropdown) return;
    var stateFilter = document.getElementById('stateFilter');
    var clsFilter = document.getElementById('classificationFilter');
    dropdown.innerHTML = '<div class="px-3 py-3 text-center text-slate-400 text-xs">Searching...</div>';
    dropdown.classList.remove('hidden');
    var url = API_BASE + '/api/members/search?q=' + encodeURIComponent(query) + '&member_type=' + _currentHouse + '&limit=15';
    if (stateFilter && stateFilter.value) url += '&state=' + encodeURIComponent(stateFilter.value);
    if (clsFilter && clsFilter.value) url += '&classification=' + encodeURIComponent(clsFilter.value);

    fetch(url)
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (data) {
        if (!data.items || data.items.length === 0) {
          dropdown.innerHTML = '<div class="px-3 py-4 text-center text-slate-400 text-xs">No results for "' + query + '"</div>';
        } else {
          var qLower = query.toLowerCase();
          var html = '<div class="p-1">';
          data.items.forEach(function (m) {
            var cls = m.performance_classification || '';
            var name = m.member_name || 'Unknown';
            var nameHtml = name;
            var li = name.toLowerCase().indexOf(qLower);
            if (li >= 0) {
              nameHtml = name.substring(0, li) + '<strong class="text-blue-600">' + name.substring(li, li + query.length) + '</strong>' + name.substring(li + query.length);
            }
    var detailUrl = 'mpdetail.html?member_id=' + (m.member_id || '') + '&member_type=' + encodeURIComponent(m.member_type_field || m.member_type || 'MP');
            html += '<a href="' + detailUrl + '" class="flex items-center justify-between px-2.5 py-2 hover:bg-slate-50 rounded cursor-pointer transition no-underline">';
            html += '<div><span class="font-medium text-slate-800 text-xs">' + nameHtml + '</span>';
            html += '<span class="text-[10px] text-slate-400 ml-2">' + (m.state_name || '') + '</span></div>';
            html += '<span class="text-[10px] font-semibold text-slate-500">' + cls.replace(/_/g, ' ') + '</span>';
            html += '</a>';
          });
          html += '</div>';
          dropdown.innerHTML = html;
        }
        dropdown.classList.remove('hidden');
      })
      .catch(function () { dropdown.classList.add('hidden'); });
  }

  function setupFilters() {
    var stateSel = document.getElementById('stateFilter');
    var clsSel = document.getElementById('classificationFilter');
    if (stateSel) {
      stateSel.addEventListener('change', function () { currentPage = 1; loadCards(1, false); });
    }
    if (clsSel) {
      clsSel.addEventListener('change', function () { currentPage = 1; loadCards(1, false); });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    clearStaleCaches();
    setupSortButtons();
    setupHouseFilter();
    setupSearch();
    setupFilters();

    var cached = getCached(KPI_CACHE_KEY);
    if (cached) { updateKPIs(cached.data); } else { fetchKPIs(); }

    fetchScatterAndHistogram();
    loadCards(1, true);
  });
})();

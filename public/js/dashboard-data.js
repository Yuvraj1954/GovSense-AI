(function () {
  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  var TREND_CACHE = 'trendCache';
  var STATE_CACHE = 'statePerfCache';
  var CLASS_CACHE = 'classificationCache';
  var STATE_CLS_CACHE = 'stateClassificationCache';
  var OVERVIEW_CACHE = 'overviewCache';
  var TTL = 24 * 60 * 60 * 1000;
  var CACHE_VERSION = '2.0';
  var _trendData = null;
  var _activeMetric = 'expenditure';
  var _currentHouse = 'both';

  function cached(key) {
    try {
      var d = JSON.parse(localStorage.getItem(key));
      if (d && d.v === CACHE_VERSION && Date.now() - d.ts < TTL) return d.data;
    } catch (e) {}
    return null;
  }
  function save(key, data) { localStorage.setItem(key, JSON.stringify({ data: data, ts: Date.now(), v: CACHE_VERSION })); }
  function clearCache(key) { try { localStorage.removeItem(key); } catch (e) {} }

  function clearStaleCaches() {
    try {
      var keys = Object.keys(localStorage);
      var prefixes = ['trendCache', 'statePerfCache', 'classificationCache', 'stateClassificationCache', 'overviewCache'];
      for (var i = 0; i < keys.length; i++) {
        var k = keys[i];
        for (var j = 0; j < prefixes.length; j++) {
          if (k.indexOf(prefixes[j]) === 0) {
            var raw = localStorage.getItem(k);
            if (raw) {
              var cached = JSON.parse(raw);
              if (cached.v !== CACHE_VERSION) localStorage.removeItem(k);
            }
            break;
          }
        }
      }
    } catch (e) {}
  }

  function fmtCr(val) {
    var cr = val / 1e7;
    if (cr >= 10000) return '₹' + (cr / 1000).toFixed(1) + 'K Cr';
    if (cr >= 100) return '₹' + cr.toFixed(0) + ' Cr';
    return '₹' + cr.toFixed(1) + ' Cr';
  }
  function barColor(pct) {
    if (pct >= 70) return 'bg-emerald-500 hover:bg-emerald-400';
    if (pct >= 50) return 'bg-blue-500 hover:bg-blue-400';
    if (pct >= 30) return 'bg-amber-500 hover:bg-amber-400';
    return 'bg-rose-500 hover:bg-rose-400';
  }
  function stateBarColor(pct) {
    if (pct >= 70) return 'bg-emerald-500';
    if (pct >= 50) return 'bg-blue-500';
    if (pct >= 30) return 'bg-amber-500';
    return 'bg-rose-500';
  }

  // ── Trends Chart ──
  function aggregateTrends(rows) {
    var byYear = {};
    rows.forEach(function (r) {
      if (!byYear[r.year]) byYear[r.year] = { mp: null, mla: null };
      if (r.member_type === 'MP') byYear[r.year].mp = r;
      else byYear[r.year].mla = r;
    });
    var years = Object.keys(byYear).sort();
    return years.map(function (y) {
      var mp = byYear[y].mp || {};
      var mla = byYear[y].mla || {};
      var mpExp = parseFloat(mp.expenditure_amount) || 0;
      var mlaExp = parseFloat(mla.expenditure_amount) || 0;
      return {
        year: parseInt(y),
        total_works: (mp.total_works || 0) + (mla.total_works || 0),
        sanctioned_works: (mp.sanctioned_works || 0) + (mla.sanctioned_works || 0),
        completed_works: (mp.completed_works || 0) + (mla.completed_works || 0),
        expenditure: mpExp + mlaExp,
        utilization_pct: ((mpExp + mlaExp) / (((parseFloat(mp.sanctioned_amount) || 0) + (parseFloat(mla.sanctioned_amount) || 0)) || 1)) * 100,
        completion_rate_pct: mp.completion_rate_pct && mla.completion_rate_pct
          ? (((mp.completed_works || 0) + (mla.completed_works || 0)) / (((mp.total_works || 0) + (mla.total_works || 0)) || 1)) * 100
          : (mp.completion_rate_pct || mla.completion_rate_pct || 0),
        flagged_rate_pct: mp.flagged_rate_pct || mla.flagged_rate_pct || 0
      };
    });
  }

  function getMetricValue(item, metric) {
    switch (metric) {
      case 'expenditure': return item.expenditure;
      case 'total_works': return item.total_works;
      case 'completed_works': return item.completed_works;
      case 'completion_rate': return item.completion_rate_pct;
      case 'fund_utilization': return item.utilization_pct;
      default: return item.expenditure;
    }
  }

  function getMetricLabel(metric) {
    switch (metric) {
      case 'expenditure': return 'Expenditure';
      case 'total_works': return 'Total Works';
      case 'completed_works': return 'Completed Works';
      case 'completion_rate': return 'Completion Rate %';
      case 'fund_utilization': return 'Utilization %';
      default: return 'Expenditure';
    }
  }

  function isPercentMetric(metric) {
    return metric === 'completion_rate' || metric === 'fund_utilization';
  }

  function fmtMetric(val, metric) {
    if (isPercentMetric(metric)) return val.toFixed(1) + '%';
    if (metric === 'expenditure') return fmtCr(val);
    return val.toLocaleString();
  }

  function getBarColor(val, maxVal, isPct) {
    if (isPct) {
      if (val >= 70) return 'bg-emerald-500 hover:bg-emerald-400';
      if (val >= 50) return 'bg-blue-500 hover:bg-blue-400';
      if (val >= 30) return 'bg-amber-500 hover:bg-amber-400';
      return 'bg-rose-500 hover:bg-rose-400';
    }
    // For absolute metrics: color by bar height relative to max
    var ratio = maxVal > 0 ? (val / maxVal) : 0;
    if (ratio >= 0.7) return 'bg-emerald-500 hover:bg-emerald-400';
    if (ratio >= 0.5) return 'bg-blue-500 hover:bg-blue-400';
    if (ratio >= 0.3) return 'bg-amber-500 hover:bg-amber-400';
    return 'bg-rose-500 hover:bg-rose-400';
  }

  function renderTrends(rows, metric) {
    metric = metric || _activeMetric;
    var agg = aggregateTrends(rows);
    var n = agg.length;
    if (n === 0) return;

    var values = agg.map(function (a) { return getMetricValue(a, metric); });
    var maxVal = Math.max.apply(null, values);
    if (maxVal === 0) maxVal = 1;
    var isPct = isPercentMetric(metric);

    // Y-axis: 5 gridlines
    var yAxis = document.getElementById('trend-y-axis');
    if (yAxis) {
      var html = '';
      for (var i = 4; i >= 0; i--) {
        var v = (maxVal * i) / 4;
        var label = isPct ? v.toFixed(0) + '%' : fmtCr(v);
        html += '<div class="flex items-center w-full"><span class="w-14 text-right mr-2">' + label + '</span><div class="flex-1 border-b border-slate-' + (i === 0 ? '200' : '100') + '"></div></div>';
      }
      yAxis.innerHTML = html;
    }

    // Measure the chart area — single coordinate space for bars + SVG
    var chartArea = document.getElementById('trend-chart-area');
    if (!chartArea) return;

    var W = chartArea.offsetWidth;
    var H = chartArea.offsetHeight;
    if (W === 0 || H === 0) return;

    var LABEL_H = 28;
    var CHART_TOP = 8;
    var CHART_H = H - LABEL_H - CHART_TOP;
    var colW = W / n;
    var barW = Math.min(colW * 0.5, 56);

    // Render bars as absolutely positioned divs inside chart area
    var barsTrack = document.getElementById('trend-bars-track');
    var barTopPoints = [];

    if (barsTrack) {
      var barsHtml = '';
      agg.forEach(function (a, idx) {
        var val = getMetricValue(a, metric);
        var pct = (val / maxVal) * 100;
        var cls = getBarColor(val, maxVal, isPct);
        var barH = Math.max((pct / 100) * CHART_H, 2);

        var fy = 'FY ' + String(a.year).slice(2) + '-' + String(((a.year + 1) % 100)).padStart(2, '0');
        if (a.year === 2026) fy += '*';
        var tip = fy + ': ' + fmtMetric(val, metric);

        var left = idx * colW + (colW - barW) / 2;
        var bottom = LABEL_H;
        var top = CHART_TOP + CHART_H - barH;

        barsHtml += '<div class="absolute group cursor-pointer" style="left:' + left.toFixed(1) + 'px; bottom:' + bottom + 'px; width:' + barW + 'px; height:' + barH.toFixed(1) + 'px;">';
        barsHtml += '<div class="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[10px] rounded px-2 py-1 whitespace-nowrap z-20 pointer-events-none shadow-lg">' + tip + '</div>';
        barsHtml += '<div class="' + cls + ' w-full h-full rounded-t-sm transition-all duration-300"></div>';
        barsHtml += '</div>';

        // Year label
        var labelLeft = idx * colW + colW / 2;
        barsHtml += '<div class="absolute text-[10px] font-medium text-slate-600 whitespace-nowrap -translate-x-1/2" style="left:' + labelLeft.toFixed(1) + 'px; bottom:4px;">' + fy + '</div>';

        // SVG dot coordinate (same pixel space as bars)
        var cx = idx * colW + colW / 2;
        var cy = top;
        barTopPoints.push({ x: cx, y: cy });
      });
      barsTrack.innerHTML = barsHtml;
    }

    // SVG trend line — viewBox matches chart area pixel dimensions
    var svg = document.getElementById('trend-svg-line');
    if (svg) {
      svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);

      if (barTopPoints.length > 1) {
        var pathD = 'M' + barTopPoints[0].x.toFixed(1) + ',' + barTopPoints[0].y.toFixed(1);
        for (var i = 1; i < barTopPoints.length; i++) {
          var prev = barTopPoints[i - 1];
          var curr = barTopPoints[i];
          var midX = (prev.x + curr.x) / 2;
          pathD += ' C' + midX.toFixed(1) + ',' + prev.y.toFixed(1) + ' ' + midX.toFixed(1) + ',' + curr.y.toFixed(1) + ' ' + curr.x.toFixed(1) + ',' + curr.y.toFixed(1);
        }
        var circles = barTopPoints.map(function (p) {
          return '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" fill="#4338ca" r="4" stroke="white" stroke-width="2"></circle>';
        }).join('');
        svg.innerHTML = '<path d="' + pathD + '" fill="none" stroke="#6366f1" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"></path>' + circles;
      }
    }

    // Entrance animation — only when scrolled into view, once per page load
    if (window.ChartAnim) {
      var trendWrap = document.getElementById('trend-chart-container') || chartArea;
      window.ChartAnim.whenVisible(trendWrap, 'dashTrend', function () {
        var innerBars = barsTrack ? barsTrack.querySelectorAll('.rounded-t-sm') : [];
        if (innerBars.length) window.ChartAnim.growBars(innerBars, { stagger: 70, duration: 800 });
        var tpath = svg ? svg.querySelector('path') : null;
        if (tpath) window.ChartAnim.drawLine(tpath, { duration: 1400, delay: 450 });
        var tdots = svg ? svg.querySelectorAll('circle') : [];
        if (tdots.length) window.ChartAnim.popIn(tdots, { stagger: 80, duration: 400 });
      });
    }
  }

  // ── State Performance Bars ──
  function renderStateBars(states, sortKey) {
    var sortMap = {
      utilization: 'expenditure_sanction_utilization_pct',
      expenditure: 'expenditure_amount',
      total_works: 'total_works',
      completed_works: 'completed_works',
      completion_rate: 'completion_rate_pct'
    };
    var field = sortMap[sortKey] || 'expenditure_sanction_utilization_pct';
    var sorted = states.slice().sort(function (a, b) { return (b[field] || 0) - (a[field] || 0); });
    var top = sorted.slice(0, 8);
    var maxVal = Math.max.apply(null, top.map(function (s) { return s[field] || 0; }));
    if (maxVal === 0) maxVal = 1;
    var container = document.getElementById('state-bars-container');
    if (!container) return;

    var html = '';
    top.forEach(function (s) {
      var val = s[field] || 0;
      var displayPct = s.expenditure_sanction_utilization_pct || 0;
      var barWidth = (val / maxVal) * 100;
      var color = stateBarColor(displayPct);
      var spent = fmtCr(s.expenditure_amount || 0);
      var works = (s.total_works || 0).toLocaleString();

      html += '<div class="flex flex-col sm:flex-row sm:items-center gap-3 text-xs">';
      html += '<div class="w-32 font-medium text-slate-800 flex-shrink-0 flex items-center justify-between sm:justify-start gap-1">';
      html += '<span>' + s.state_name + '</span>';
      html += '<span class="text-[10px] text-slate-400 font-mono sm:hidden">' + displayPct.toFixed(1) + '%</span>';
      html += '</div>';
      html += '<div class="flex-1 bg-slate-100 rounded-md h-6 relative overflow-hidden flex items-center">';
      html += '<div class="h-full ' + color + ' rounded-md flex items-center justify-end pr-2.5 text-white text-[11px] font-bold transition-all" style="width: ' + barWidth.toFixed(1) + '%;">';
      html += displayPct.toFixed(1) + '%';
      html += '</div></div>';
      html += '<div class="w-48 flex items-center justify-between text-[11px] text-slate-500 font-mono flex-shrink-0">';
      html += '<span>' + spent + ' spent</span>';
      html += '<span class="text-slate-400">' + works + ' works</span>';
      html += '</div></div>';
    });
    container.innerHTML = html;
  }

  // ── Metric button handlers ──
  function setupMetricButtons() {
    var container = document.getElementById('trendMetricButtons');
    if (!container) return;
    var btns = container.querySelectorAll('.trend-btn');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        btns.forEach(function (b) {
          b.classList.remove('bg-white', 'text-slate-900', 'shadow-2xs', 'font-semibold');
          b.classList.add('text-slate-600', 'font-medium');
        });
        btn.classList.add('bg-white', 'text-slate-900', 'shadow-2xs', 'font-semibold');
        btn.classList.remove('text-slate-600', 'font-medium');
        _activeMetric = btn.getAttribute('data-metric');
        if (_trendData) renderTrends(_trendData, _activeMetric);
      });
    });
  }

  // ── Sort handler ──
  var stateData = null;
  function setupSort() {
    var container = document.getElementById('stateSortButtons');
    if (!container) return;
    var btns = container.querySelectorAll('.state-sort-btn');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        btns.forEach(function (b) {
          b.classList.remove('bg-white', 'text-slate-900', 'shadow-2xs', 'font-semibold');
          b.classList.add('text-slate-600', 'font-medium');
        });
        btn.classList.add('bg-white', 'text-slate-900', 'shadow-2xs', 'font-semibold');
        btn.classList.remove('text-slate-600', 'font-medium');
        if (stateData) renderStateBars(stateData, btn.getAttribute('data-sort'));
      });
    });
  }

  // ── Overview KPIs ──
  function fmtINR(val) {
    var cr = val / 1e7;
    if (cr >= 1000) return '₹' + (cr / 1000).toFixed(1).replace(/\.0$/, '') + ',';
    return '₹' + cr.toFixed(1);
  }
  function fmtINRCr(val) {
    var cr = val / 1e7;
    return '₹' + cr.toLocaleString('en-IN', { maximumFractionDigits: 1 }) + ' Cr';
  }
  function fmtNum(n) { return n.toLocaleString('en-IN'); }

  function renderOverview(d) {
    if (!d || !d.total_works) return;

    var set = function(id, txt) { var el = document.getElementById(id); if (el) el.textContent = txt; };

    // Row 1 KPIs
    set('kpi-allocated', fmtINRCr(d.sanctioned_amount || 0).replace(' Cr', ''));
    set('kpi-expenditure', fmtINRCr(d.expenditure_amount || 0).replace(' Cr', ''));
    set('kpi-utilization', d.fund_utilization_pct + '%');
    set('kpi-total-works', fmtNum(d.total_works));

    // Row 2 KPIs
    set('kpi-sanctioned', fmtNum(d.sanctioned_works));
    set('kpi-sanction-rate', d.sanction_rate_pct + '% sanction rate');
    set('kpi-completed', fmtNum(d.completed_works));
    set('kpi-completion-rate', d.completion_rate_pct + '% completion');
    set('kpi-ongoing', fmtNum(d.ongoing_works));
    set('kpi-ongoing-rate', ((d.ongoing_works / d.total_works) * 100).toFixed(1) + '% under execution');
    set('kpi-unspent', fmtINRCr(d.unspent_amount || 0).replace(' Cr', ''));

    // Donut chart
    var compPct = d.completion_rate_pct || 0;
    var ongoPct = ((d.ongoing_works / d.total_works) * 100).toFixed(1);
    var pendPct = ((d.pending_works / d.total_works) * 100).toFixed(1);
    set('donut-pct', compPct + '%');
    set('donut-count', fmtNum(d.completed_works) + ' works');
    set('donut-completed-count', fmtNum(d.completed_works));
    set('donut-completed-pct', compPct + '%');
    set('donut-ongoing-count', fmtNum(d.ongoing_works));
    set('donut-ongoing-pct', ongoPct + '%');
    set('donut-pending-count', fmtNum(d.pending_works));
    set('donut-pending-pct', pendPct + '%');
    set('donut-sanctioned-label', 'Sanctioned: ' + fmtNum(d.sanctioned_works) + ' works');

    // Donut chart segments (animated draw-in on first load)
    var circ = 408.4;
    var cp = (d.total_works ? d.completed_works / d.total_works : 0);
    var op = (d.total_works ? d.ongoing_works / d.total_works : 0);
    var pp = (d.total_works ? d.pending_works / d.total_works : 0);
    var segPending = pp * circ, segOngoing = op * circ, segCompleted = cp * circ;
    var dP = document.getElementById('dashDonutPending');
    var dO = document.getElementById('dashDonutOngoing');
    var dC = document.getElementById('dashDonutCompleted');
    if (dP) dP.setAttribute('stroke-dashoffset', '0');
    if (dO) dO.setAttribute('stroke-dashoffset', '-' + segPending.toFixed(2));
    if (dC) dC.setAttribute('stroke-dashoffset', '-' + (segPending + segOngoing).toFixed(2));
    var donutSegs = [{ el: dP, len: segPending }, { el: dO, len: segOngoing }, { el: dC, len: segCompleted }];
    if (window.ChartAnim) {
      window.ChartAnim.whenVisible(dC || dP || dO, 'dashDonut', function () {
        window.ChartAnim.drawDonut(donutSegs, circ, { duration: 1100 });
      });
    } else {
      donutSegs.forEach(function (s) { if (s.el) s.el.setAttribute('stroke-dasharray', s.len + ' ' + circ); });
    }

    // Fund flow
    set('flow-allocated', fmtINRCr(d.sanctioned_amount || 0));
    set('flow-recommended', fmtINRCr(d.recommended_amount || 0));
    set('flow-sanctioned', fmtINRCr(d.sanctioned_amount || 0));
    set('flow-expenditure', fmtINRCr(d.expenditure_amount || 0));
    set('fund-remaining', fmtINRCr(d.unspent_amount || 0));
    var remPct = d.sanctioned_amount > 0 ? ((d.unspent_amount / d.sanctioned_amount) * 100).toFixed(1) : 0;
    set('fund-remaining-pct', '(' + remPct + '%)');

    // Execution analytics
    set('exec-sanction-delay', Math.round(d.avg_sanction_delay_days || 0));
    set('exec-execution-duration', ((d.avg_execution_days || 0) / 30).toFixed(1));
    set('exec-overdue', fmtNum(d.overdue_over_1_year || 0));
    set('exec-overdue-2yr', fmtNum(d.overdue_over_2_years || 0));
  }

  // ── House filter: maps dropdown values to API params ──
  function houseToParams(house) {
    if (house === 'ls') return { scope: 'MP', memberType: 'MP', label: 'Lok Sabha' };
    if (house === 'rs') return { scope: 'MLA', memberType: 'MLA', label: 'Rajya Sabha' };
    return { scope: 'BOTH', memberType: null, label: 'Both Houses' };
  }

  // Scope-specific cache keys: "overviewCache_MP", "trendCache_MLA", etc.
  function scopeKey(base, scope) { return base + '_' + scope; }

  function setupHouseFilter() {
    var sel = document.getElementById('houseFilter');           // desktop (header)
    var selM = document.getElementById('houseFilterMobile');    // mobile (below header)
    if (!sel && !selM) return;
    function apply(value) {
      _currentHouse = value;
      if (sel) sel.value = value;
      if (selM) selM.value = value;
      loadFilteredData(value);
    }
    if (sel) sel.addEventListener('change', function () { apply(sel.value); });
    if (selM) selM.addEventListener('change', function () { apply(selM.value); });
  }

  function loadFilteredData(house) {
    var p = houseToParams(house);
    var scope = p.scope;

    // Overview — check scope-specific cache first
    var ovKey = scopeKey(OVERVIEW_CACHE, scope);
    var ovCached = cached(ovKey);
    if (ovCached) {
      renderOverview(ovCached);
    } else {
      fetch(API_BASE + '/api/overview?scope=' + scope)
        .then(function (r) { return r.json(); })
        .then(function (d) { save(ovKey, d); renderOverview(d); })
        .catch(function () {});
    }

    // Trends — fetch all, filter client-side
    var trKey = scopeKey(TREND_CACHE, scope);
    var trCached = cached(trKey);
    if (trCached) {
      var filtered = p.memberType ? trCached.filter(function(r){ return r.member_type === p.memberType; }) : trCached;
      _trendData = filtered;
      renderTrends(filtered, _activeMetric);
    } else {
      fetch(API_BASE + '/api/trends')
        .then(function (r) { return r.json(); })
        .then(function (d) {
          save(trKey, d);
          var filtered = p.memberType ? d.filter(function(r){ return r.member_type === p.memberType; }) : d;
          _trendData = filtered;
          renderTrends(filtered, _activeMetric);
        })
        .catch(function () {});
    }

    // State performance — check scope-specific cache first
    var spKey = scopeKey(STATE_CACHE, scope);
    var spCached = cached(spKey);
    if (spCached) {
      stateData = spCached;
      renderStateBars(spCached, 'utilization');
    } else {
      var stateUrl = API_BASE + '/api/state-performance';
      if (p.memberType) stateUrl += '?member_type=' + p.memberType;
      fetch(stateUrl)
        .then(function (r) { return r.json(); })
        .then(function (d) { save(spKey, d); stateData = d; renderStateBars(d, 'utilization'); })
        .catch(function () {});
    }
  }

  // ── Signal dashboard loaded (for index.html transition) ──
  function signalReady() {
    try { sessionStorage.setItem('dashboardLoaded', 'true'); } catch (e) {}
  }

  // ── Init ──
  document.addEventListener('DOMContentLoaded', function () {
    clearStaleCaches();
    setupMetricButtons();
    setupSort();
    setupHouseFilter();

    // Overview KPIs — prefer scope-specific cache, fall back to generic
    var ovScopeKey = scopeKey(OVERVIEW_CACHE, 'BOTH');
    var ovCached = cached(ovScopeKey) || cached(OVERVIEW_CACHE);
    if (ovCached) renderOverview(ovCached);
    else {
      fetch(API_BASE + '/api/overview').then(function (r) { return r.json(); }).then(function (d) {
        save(ovScopeKey, d); renderOverview(d);
      }).catch(function () {});
    }

    // Trends — prefer scope-specific cache, fall back to generic
    var trScopeKey = scopeKey(TREND_CACHE, 'BOTH');
    var trendCached = cached(trScopeKey) || cached(TREND_CACHE);
    if (trendCached) { _trendData = trendCached; renderTrends(trendCached, _activeMetric); signalReady(); }
    else {
      fetch(API_BASE + '/api/trends').then(function (r) { return r.json(); }).then(function (d) {
        save(trScopeKey, d); _trendData = d; renderTrends(d, _activeMetric); signalReady();
      }).catch(function () { signalReady(); });
    }

    // State performance — prefer scope-specific cache, fall back to generic
    var spScopeKey = scopeKey(STATE_CACHE, 'BOTH');
    var stateCached = cached(spScopeKey) || cached(STATE_CACHE);
    if (stateCached) { stateData = stateCached; renderStateBars(stateCached, 'utilization'); }
    else {
      fetch(API_BASE + '/api/state-performance').then(function (r) { return r.json(); }).then(function (d) {
        save(spScopeKey, d); stateData = d; renderStateBars(d, 'utilization');
      }).catch(function () {});
    }

    // classification (dashboard + states) — always cache these (no scope filter)
    var clsCached = cached(CLASS_CACHE);
    if (!clsCached) {
      fetch(API_BASE + '/api/classification/distribution').then(function (r) { return r.json(); }).then(function (d) {
        save(CLASS_CACHE, d);
      }).catch(function () {});
    }
    var stClsCached = cached(STATE_CLS_CACHE);
    if (!stClsCached) {
      fetch(API_BASE + '/api/classification/states').then(function (r) { return r.json(); }).then(function (d) {
        save(STATE_CLS_CACHE, d);
      }).catch(function () {});
    }
  });
})();

(function () {
  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  var CACHE_KEY = 'riskOverviewCache';
  var CACHE_TTL = 30 * 60 * 1000;

  var explore = { entity: 'mp', levels: ['high', 'medium', 'low'], state_id: '', sort: 'flagged', page: 1, pageSize: 9 };

  function fmtNum(n) { if (n == null || isNaN(n)) return '—'; return Number(n).toLocaleString('en-IN'); }
  function fmtPct(n) { if (n == null || isNaN(n)) return '—'; return Number(n).toFixed(1) + '%'; }
  function setText(id, t) { var e = document.getElementById(id); if (e) e.textContent = t; }
  function setHTML(id, h) { var e = document.getElementById(id); if (e) e.innerHTML = h; }
  function getColor(p) { return p >= 70 ? 'emerald' : p >= 50 ? 'blue' : p >= 30 ? 'amber' : 'rose'; }

  // ================= OVERVIEW =================
  function loadOverview() {
    var cached = null;
    try { var raw = localStorage.getItem(CACHE_KEY); if (raw) { var cc = JSON.parse(raw); if (Date.now() - cc.ts < CACHE_TTL) cached = cc.data; } } catch (e) {}
    if (cached) {
      renderOverview(cached);
    } else {
      showRiskOverviewSkeleton(true);
    }
    fetch(API_BASE + '/api/risk/overview')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d) {
          try { localStorage.setItem(CACHE_KEY, JSON.stringify({ data: d, ts: Date.now() })); } catch (e) {}
          renderOverview(d);
          showRiskOverviewSkeleton(false);
        }
      })
      .catch(function () { showRiskOverviewSkeleton(false, true); });
  }

  function showRiskOverviewSkeleton(on, error) {
    // Banner
    var banner = document.getElementById('riskOverviewBanner');
    if (banner) {
      banner.hidden = false;
      if (on) {
        banner.className = 'flex items-center gap-2 text-xs text-slate-500';
        banner.innerHTML =
          '<svg class="animate-spin h-3.5 w-3.5 text-cyan-600" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>' +
          '<span class="font-semibold text-slate-700">Loading risk intelligence…</span>';
      } else if (error) {
        banner.className = 'section-error';
        banner.innerHTML =
          '<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>' +
          '<span>Could not load risk intelligence. Other sections remain available.</span>' +
          '<button type="button" id="retryRiskOverviewBtn">Retry</button>';
        var btn = document.getElementById('retryRiskOverviewBtn');
        if (btn) btn.addEventListener('click', function () { loadOverview(); });
      } else {
        // Setting the `hidden` ATTRIBUTE (not just the class) removes the
        // banner from Tailwind's space-y sibling chain, so no extra top gap.
        banner.className = 'hidden';
        banner.hidden = true;
        banner.innerHTML = '';
      }
    }
  }

  function renderOverview(d) {
    setText('kpiHighRiskReps', fmtNum(d.high_reps));
    setText('kpiMediumRiskReps', fmtNum(d.medium_reps));
    setText('kpiLowRiskReps', fmtNum(d.normal_reps));
    setText('kpiHighRiskStates', fmtNum(d.high_states));
    setText('kpiFlaggedWorks', fmtNum(d.flagged_works));
    setText('kpiCostAnomaly', fmtNum(d.cost_anomaly_works));
    setText('kpiDurationAnomaly', fmtNum(d.duration_anomaly_works));
    setText('kpiOverdueWorks', fmtNum(d.overdue_works));
    var sub = document.getElementById('riskSubtitle');
    if (sub) sub.textContent = fmtNum(d.total_members) + ' Total Synthesized Entities · ' + fmtNum(d.total_works) + ' Monitored Works';
    setText('headerMeta', fmtNum(d.total_members) + ' Entities');

    // AI Intelligence numbers
    setText('aiHighRiskPct', fmtPct(d.total_members ? (d.high_reps / d.total_members * 100) : 0));
    var costDur = (d.cost_total || 0) + (d.duration_total || 0);
    setText('aiCostShare', fmtPct(costDur ? ((d.cost_total || 0) / costDur * 100) : 0));
    setText('aiCostTriggers', fmtNum(d.cost_anomaly_works));
    setText('aiNeCompletion', fmtPct(d.completion_rate_pct));
    setText('aiOverdueProjects', fmtNum(d.overdue_works));
    setText('aiHighRiskSeats', fmtNum(d.high_reps));

    renderChartA(d);
    renderChartC(d);
    renderChartD(d);
    loadChartB();
  }

  // Chart A: representative risk donut
  function renderChartA(d) {
    var dist = d.rep_distribution || [];
    var normal = 0, medium = 0, high = 0;
    dist.forEach(function (x) { if (x.level === 'Normal') normal = x.count; else if (x.level === 'Medium') medium = x.count; else if (x.level === 'High') high = x.count; });
    var total = normal + medium + high || 1;
    var circ = 238.7;
    var np = normal / total, mp = medium / total, hp = high / total;

    var el = document.getElementById('raLow');
    var em = document.getElementById('raMedium');
    var eh = document.getElementById('raHigh');
    if (el) el.setAttribute('stroke-dashoffset', '0');
    if (em) em.setAttribute('stroke-dashoffset', '-' + (np * circ).toFixed(2));
    if (eh) eh.setAttribute('stroke-dashoffset', '-' + ((np + mp) * circ).toFixed(2));
    var segs = [{ el: el, len: np * circ }, { el: em, len: mp * circ }, { el: eh, len: hp * circ }];
    if (window.ChartAnim) {
      window.ChartAnim.whenVisible(el || em || eh, 'riskChartA', function () {
        window.ChartAnim.drawDonut(segs, circ, { duration: 900 });
      });
    } else {
      segs.forEach(function (s) { if (s.el) s.el.setAttribute('stroke-dasharray', s.len + ' ' + circ); });
    }

    setText('riskRepTotal', fmtNum(total));
    setText('raLowCount', fmtNum(normal)); setText('raLowPct', fmtPct(np * 100));
    setText('raMediumCount', fmtNum(medium)); setText('raMediumPct', fmtPct(mp * 100));
    setText('raHighCount', fmtNum(high)); setText('raHighPct', fmtPct(hp * 100));
    var sub = document.getElementById('riskRepSub');
    if (sub) sub.textContent = fmtNum(total) + ' Representatives by Severity';
  }

  // Chart B: performance vs anomaly scatter
  function loadChartB() {
    Promise.all([
      fetch(API_BASE + '/api/risk/entities?entity=mp&sort=score&page_size=4').then(function (r) { return r.ok ? r.json() : { items: [] }; }),
      fetch(API_BASE + '/api/risk/entities?entity=mp&sort=utilization&page_size=2').then(function (r) { return r.ok ? r.json() : { items: [] }; })
    ]).then(function (res) {
      var risky = (res[0].items || []);
      var best = (res[1].items || []);
      var g = document.getElementById('riskScatterNodes');
      if (!g) return;
      var NS = 'http://www.w3.org/2000/svg';
      function node(name, util, score, color, textColor) {
        var x = 35 + (Math.min(Math.max(util, 0), 100) / 100) * 270;
        var y = 170 - (Math.min(Math.max(score, 0), 2) / 2) * 155;
        var c = document.createElementNS(NS, 'circle');
        c.setAttribute('cx', x); c.setAttribute('cy', y); c.setAttribute('r', 6);
        c.setAttribute('fill', color); c.setAttribute('stroke', '#fff'); c.setAttribute('stroke-width', '1.5');
        g.appendChild(c);
        var t = document.createElementNS(NS, 'text');
        t.setAttribute('x', x + 8); t.setAttribute('y', y + 3); t.setAttribute('font-size', '7.5');
        t.setAttribute('fill', textColor); t.setAttribute('font-weight', 'bold');
        var short = (name || '').split(' ').slice(0, 2).join(' ');
        t.textContent = short + ' (' + (score != null ? Number(score).toFixed(1) : '—') + ')';
        g.appendChild(t);
      }
      risky.forEach(function (m) { node(m.name, m.fund_utilization_pct, m.anomaly_score, '#ef4444', '#991b1b'); });
      best.forEach(function (m) { node(m.name, m.fund_utilization_pct, m.anomaly_score, '#10b981', '#065f46'); });
      if (window.ChartAnim) {
        window.ChartAnim.whenVisible(g, 'riskScatter', function () {
          window.ChartAnim.popIn(g.querySelectorAll('circle'), { fade: false, stagger: 90, duration: 550 });
        });
      }
      setText('riskCriticalCount', fmtNum(risky.length) + '+ in critical concern quadrant');
    }).catch(function () {});
  }

  // Chart C: signal composition
  function renderChartC(d) {
    var costTotal = d.cost_total || 0, durTotal = d.duration_total || 0;
    var grand = (costTotal + durTotal - (d.dual_anomaly || 0)) || 1;
    setText('rcCostOnly', fmtNum(d.cost_only));
    setText('rcCostOnlyPct', '(' + fmtPct((d.cost_only / grand) * 100) + ')');
    setText('rcDual', fmtNum(d.dual_anomaly));
    setText('rcDualPct', '(' + fmtPct((d.dual_anomaly / grand) * 100) + ')');
    setText('rcDurOnly', fmtNum(d.duration_only));
    setText('rcDurOnlyPct', '(' + fmtPct((d.duration_only / grand) * 100) + ')');
    setText('rcDualBadge', fmtNum(d.dual_anomaly) + ' Dual-Flagged');
    setText('rcCostTotal', fmtNum(costTotal) + ' (' + fmtPct(costTotal / grand * 100) + ')');
    setText('rcDurTotal', fmtNum(durTotal) + ' (' + fmtPct(durTotal / grand * 100) + ')');
    setText('rcOverdue', fmtNum(d.overdue_works));
    if (window.ChartAnim) {
      var venn = document.querySelectorAll('.venn-circle');
      if (venn.length) window.ChartAnim.whenVisible(venn[0], 'riskChartC', function () {
        window.ChartAnim.popIn(venn, { stagger: 160, duration: 650 });
      });
    }
  }

  // Chart D: historical trend
  function renderChartD(d) {
    var el = document.getElementById('riskTrendChart');
    if (!el) return;
    var trend = (d.trend || []);
    if (!trend.length) { el.innerHTML = '<div class="text-xs text-slate-400 text-center py-10">No trend data</div>'; return; }
    var W = 340, H = 160, x0 = 30, x1 = 320, yTop = 30, yBot = 130;
    var n = trend.length;
    var maxV = Math.max.apply(null, trend.map(function (t) { return Math.max(t.flagged, t.resolved); }).concat([1]));
    function px(i) { return n === 1 ? (x0 + x1) / 2 : x0 + (i / (n - 1)) * (x1 - x0); }
    function py(v) { return yBot - (v / maxV) * (yBot - yTop); }
    var flaggedPts = trend.map(function (t, i) { return px(i) + ' ' + py(t.flagged); });
    var resolvedPts = trend.map(function (t, i) { return px(i) + ' ' + py(t.resolved); });
    var svg = '<svg class="w-full" viewBox="0 0 340 160">';
    [30, 65, 100, 130].forEach(function (y) { svg += '<line stroke="#f1f5f9" stroke-width="1" x1="30" x2="320" y1="' + y + '" y2="' + y + '"></line>'; });
    svg += '<path d="M ' + flaggedPts.join(' L ') + '" fill="none" stroke="#f43f5e" stroke-linecap="round" stroke-width="2.5"></path>';
    svg += '<path d="M ' + resolvedPts.join(' L ') + '" fill="none" stroke="#10b981" stroke-linecap="round" stroke-width="2.5"></path>';
    trend.forEach(function (t, i) {
      svg += '<circle cx="' + px(i) + '" cy="' + py(t.flagged) + '" fill="#f43f5e" r="3.5" stroke="#fff" stroke-width="1.5"></circle>';
      svg += '<circle cx="' + px(i) + '" cy="' + py(t.resolved) + '" fill="#10b981" r="3.5" stroke="#fff" stroke-width="1.5"></circle>';
      svg += '<text fill="#64748b" font-size="8" text-anchor="middle" x="' + px(i) + '" y="145">' + t.year + '</text>';
    });
    svg += '</svg>';
    el.innerHTML = svg;
    if (window.ChartAnim) {
      window.ChartAnim.whenVisible(el, 'riskTrend', function () {
        var paths = el.querySelectorAll('path');
        if (paths[0]) window.ChartAnim.drawLine(paths[0], { duration: 1200 });
        if (paths[1]) window.ChartAnim.drawLine(paths[1], { duration: 1200, delay: 150 });
        var dots = el.querySelectorAll('circle');
        if (dots.length) window.ChartAnim.popIn(dots, { fade: false, stagger: 60, duration: 400 });
      });
    }
    var last = trend[trend.length - 1];
    if (last) {
      var pct = last.total ? (last.resolved / last.total * 100) : 0;
      setText('riskTrendBadge', fmtPct(pct) + ' Resolved');
    }
  }

  // ================= ALERTS =================
  var baseAlerts = [];
  var alertsExpanded = false;

  function loadAlerts() {
    fetch(API_BASE + '/api/risk/alerts?limit=12')
      .then(function (r) { return r.ok ? r.json() : { items: [] }; })
      .then(function (d) {
        var items = d.items || [];
        baseAlerts = items.slice();
        renderAlerts(items, 'all');
        wireAlertTabs(items);
      })
      .catch(function () {});
  }

  function initials(name) {
    return (name || '?').split(' ').filter(Boolean).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase();
  }

  function alertCard(e) {
    // Prefer composite risk_level over ML-only anomaly_level for actionable triage.
    var lvl = (e.risk_level || e.anomaly_level || '').toUpperCase();
    var lc = lvl === 'HIGH' || lvl === 'CRITICAL' ? 'rose' : lvl === 'MODERATE' || lvl === 'MEDIUM' ? 'amber' : 'emerald';
    var type = e.entity_type || (e.member_type || '').toLowerCase();
    var isState = type === 'state';
    var typeLabel = isState ? 'State / UT' : (e.member_type || '').toUpperCase();
    var href = isState
      ? 'statedetail.html?state_id=' + encodeURIComponent(e.id || '') + '&state=' + encodeURIComponent(e.name || '') + '&from=airiskcentre'
      : 'mpdetail.html?member_id=' + e.id + '&member_type=' + encodeURIComponent((e.member_type || 'MP').toUpperCase()) + '&from=airiskcentre';
    var score = e.risk_score != null ? Number(e.risk_score) : (e.anomaly_score != null ? Number(e.anomaly_score) : 0);
    var scorePct = Math.min(score, 100);
    var conf = e.confidence_level || 'MEDIUM';
    return '<article class="alert-item bg-white border border-slate-200 rounded-xl p-4 shadow-2xs hover:shadow-md hover:border-' + lc + '-400 transition-all duration-200 flex flex-col justify-between" data-type="' + type + '">' +
      '<div>' +
      '<div class="flex items-start justify-between gap-2">' +
      '<div class="flex items-center gap-3">' +
      '<div class="w-10 h-10 rounded-full bg-' + lc + '-50 border border-' + lc + '-200 flex items-center justify-center text-' + lc + '-700 font-bold text-sm flex-shrink-0">' + initials(e.name) + '</div>' +
      '<div><h3 class="text-sm font-bold text-slate-900 leading-snug">' + (e.name || 'Unknown') + '</h3>' +
      '<div class="flex items-center gap-1 text-[11px] text-slate-500 mt-0.5">' +
      '<svg class="w-3 h-3 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path><path d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>' +
      '<span>' + (e.state_name || 'India') + '</span></div></div></div>' +
      '<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-' + lc + '-100 text-' + lc + '-800 border border-' + lc + '-200">' + lvl + ' RISK</span></div>' +
      '<div class="flex items-center gap-2 mt-3">' +
      '<span class="text-[10px] font-medium bg-slate-100 text-slate-600 px-2 py-0.5 rounded">' + typeLabel + '</span>' +
      '<span class="text-[10px] font-medium bg-slate-100 text-slate-600 px-2 py-0.5 rounded flex items-center gap-1"><span class="w-1 h-1 rounded-full bg-' + lc + '-500"></span> ' + conf + ' Confidence</span></div>' +
      '<div class="mt-3.5"><div class="flex justify-between items-center text-xs mb-1">' +
      '<span class="text-[11px] font-semibold text-slate-600">Risk Score</span>' +
      '<span class="font-bold text-' + lc + '-700 text-xs">' + score.toFixed(1) + ' / 100</span></div>' +
      '<div class="w-full h-2 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + lc + '-500 rounded-full transition-all duration-700" style="width:' + scorePct + '%"></div></div></div>' +
      '<div class="grid grid-cols-2 gap-2 mt-3">' +
      '<div class="p-2 border border-slate-100 rounded-lg"><span class="text-[10px] text-slate-400">Flagged Works</span><div class="font-bold text-slate-800 text-sm mt-0.5">' + fmtNum(e.flagged_works || 0) + '</div></div>' +
      '<div class="p-2 border border-slate-100 rounded-lg"><span class="text-[10px] text-slate-400">High-Risk</span><div class="font-bold text-' + lc + '-600 text-sm mt-0.5">' + fmtNum(e.high_risk_works || 0) + '</div></div></div>' +
      '</div>' +
      '<div class="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">' +
      '<span class="text-[11px] text-slate-400 font-mono">ID: ' + e.id + '</span>' +
      '<a href="' + href + '" class="text-xs font-semibold text-slate-900 hover:text-' + lc + '-600 flex items-center gap-1 transition-colors group"><span>View Details</span><span class="group-hover:translate-x-0.5 transition-transform">\u2192</span></a></div>' +
      '</article>';
  }

  function renderAlerts(items, filter) {
    var grid = document.getElementById('priorityAlertsGrid');
    if (!grid) return;
    var list = filter === 'all' ? items : items.filter(function (x) { return (x.entity_type || '').toLowerCase() === filter; });
    if (!list.length) { grid.innerHTML = '<div class="col-span-full text-center py-10 text-slate-400 text-sm">No alerts in this category.</div>'; return; }
    grid.innerHTML = list.map(alertCard).join('');
  }

  var currentAlertItems = [];

  function wireAlertTabs(items) {
    currentAlertItems = items;
    var tabs = document.querySelectorAll('.alert-tab-btn');
    if (!tabs.length) return;
    var counts = { all: items.length, mp: 0, mla: 0, state: 0 };
    items.forEach(function (x) { var t = (x.entity_type || '').toLowerCase(); if (counts[t] != null) counts[t]++; });
    tabs.forEach(function (tab) {
      var target = tab.getAttribute('data-target');
      var badge = tab.querySelector('span');
      if (badge && counts[target] != null) badge.textContent = counts[target];
      if (!tab.dataset.wired) {
        tab.dataset.wired = '1';
        tab.addEventListener('click', function () {
          tabs.forEach(function (t) { t.classList.remove('bg-white', 'text-slate-900', 'text-blue-700', 'shadow-xs', 'font-semibold'); t.classList.add('text-slate-600'); });
          tab.classList.add('bg-white', 'text-slate-900', 'shadow-xs', 'font-semibold');
          tab.classList.remove('text-slate-600');
          renderAlerts(currentAlertItems, target);
        });
      }
    });
  }

  // ================= EXPLORE =================
  function loadStatesForFilter() {
    fetch(API_BASE + '/api/states')
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (states) {
        var sel = document.getElementById('filterStateSelect');
        if (!sel) return;
        sel.innerHTML = '<option value="">All States</option>';
        states.forEach(function (s) {
          var o = document.createElement('option');
          o.value = s.state_id; o.textContent = s.state_name;
          sel.appendChild(o);
        });
      })
      .catch(function () {});
  }

  function currentLevels() {
    var cbs = document.querySelectorAll('.risk-level-cb');
    var out = [];
    cbs.forEach(function (cb) { if (cb.checked) out.push(cb.value); });
    return out.length ? out : ['high', 'medium', 'low'];
  }

  function levelParam(levels) {
    // backend supports a single level filter; if all 3, pass none
    if (levels.length === 3) return '';
    return levels.join(',');
  }

  function loadExplore() {
    var grid = document.getElementById('exploreCardsGrid');
    if (grid) grid.innerHTML = '<div class="col-span-full text-center py-10 text-slate-400 text-sm">Loading...</div>';
    var levels = currentLevels();
    var url = API_BASE + '/api/risk/entities?entity=' + explore.entity + '&sort=' + explore.sort + '&page=' + explore.page + '&page_size=' + explore.pageSize;
    if (explore.state_id) url += '&state_id=' + explore.state_id;
    var lp = levelParam(levels);
    if (lp) url += '&level=' + encodeURIComponent(lp);
    fetch(url)
      .then(function (r) { return r.ok ? r.json() : { items: [], total: 0 }; })
      .then(function (d) { renderExplore(d); })
      .catch(function () { if (grid) grid.innerHTML = '<div class="col-span-full text-center py-10 text-rose-400 text-sm">Failed to load.</div>'; });
  }

  function renderExplore(d) {
    var items = d.items || [];
    var grid = document.getElementById('exploreCardsGrid');
    setText('resultsSummaryCount', fmtNum(d.total || 0) + ' entities');
    if (grid) {
      if (!items.length) grid.innerHTML = '<div class="col-span-full text-center py-10 text-slate-400 text-sm">No entities match the filters.</div>';
      else grid.innerHTML = items.map(entityCard).join('');
    }
    renderPagination(d);
  }

  function entityCard(e) {
    // Prefer composite risk_level over ML-only anomaly_level for actionable triage.
    var lvl = (e.risk_level || e.anomaly_level || '').toUpperCase();
    var lc = lvl === 'HIGH' || lvl === 'CRITICAL' ? 'rose' : lvl === 'MODERATE' || lvl === 'MEDIUM' ? 'amber' : 'emerald';
    var isState = (e.member_type || '') === 'State';
    var href = isState
      ? 'statedetail.html?state_id=' + encodeURIComponent(e.id || '') + '&state=' + encodeURIComponent(e.name || '') + '&from=airiskcentre'
      : 'mpdetail.html?member_id=' + e.id + '&member_type=' + encodeURIComponent((e.member_type || 'MP').toUpperCase()) + '&from=airiskcentre';
    var score = e.risk_score != null ? Number(e.risk_score) : (e.anomaly_score != null ? Number(e.anomaly_score) : 0);
    var scorePct = Math.min(score, 100);
    var conf = e.confidence_level || 'MEDIUM';
    return '<article class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs hover:shadow-md hover:border-' + lc + '-400 transition-all duration-200 flex flex-col justify-between">' +
      '<div>' +
      '<div class="flex items-start justify-between gap-2">' +
      '<div class="flex items-center gap-3">' +
      '<div class="w-10 h-10 rounded-full bg-' + lc + '-50 border border-' + lc + '-200 flex items-center justify-center text-' + lc + '-700 font-bold text-sm flex-shrink-0">' + initials(e.name) + '</div>' +
      '<div><h3 class="text-sm font-bold text-slate-900 leading-snug">' + (e.name || 'Unknown') + '</h3>' +
      '<div class="flex items-center gap-1 text-[11px] text-slate-500 mt-0.5">' +
      '<svg class="w-3 h-3 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path><path d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>' +
      '<span>' + (isState ? 'State / UT' : (e.state_name || 'India')) + '</span></div></div></div>' +
      '<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-' + lc + '-100 text-' + lc + '-800 border border-' + lc + '-200">' + lvl + '</span></div>' +
      '<div class="flex items-center gap-2 mt-3">' +
      '<span class="text-[10px] font-medium bg-slate-100 text-slate-600 px-2 py-0.5 rounded">' + (isState ? 'State / UT' : (e.member_type || 'MP')) + '</span>' +
      '<span class="text-[10px] font-medium bg-slate-100 text-slate-600 px-2 py-0.5 rounded flex items-center gap-1"><span class="w-1 h-1 rounded-full bg-' + lc + '-500"></span> ' + conf + ' Confidence</span></div>' +
      '<div class="mt-3.5"><div class="flex justify-between items-center text-xs mb-1">' +
      '<span class="text-[11px] font-semibold text-slate-600">Risk Score</span>' +
      '<span class="font-bold text-' + lc + '-700 text-xs">' + score.toFixed(1) + ' / 100</span></div>' +
      '<div class="w-full h-2 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + lc + '-500 rounded-full transition-all duration-700" style="width:' + scorePct + '%"></div></div></div>' +
      '<div class="grid grid-cols-3 gap-2 mt-3">' +
      '<div class="p-2 border border-slate-100 rounded-lg"><span class="text-[10px] text-slate-400">Flagged</span><div class="font-bold text-slate-800 text-sm mt-0.5">' + fmtNum(e.flagged_works || 0) + '</div></div>' +
      '<div class="p-2 border border-slate-100 rounded-lg"><span class="text-[10px] text-slate-400">High-Risk</span><div class="font-bold text-' + lc + '-600 text-sm mt-0.5">' + fmtNum(e.high_risk_works || 0) + '</div></div>' +
      '<div class="p-2 border border-slate-100 rounded-lg"><span class="text-[10px] text-slate-400">Utilization</span><div class="font-bold text-slate-800 text-sm mt-0.5">' + fmtPct(e.fund_utilization_pct) + '</div></div></div>' +
      '</div>' +
      '<div class="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">' +
      '<span class="text-[11px] text-slate-400 font-mono">ID: ' + e.id + '</span>' +
      '<a href="' + href + '" class="text-xs font-semibold text-slate-900 hover:text-' + lc + '-600 flex items-center gap-1 transition-colors group"><span>View Details</span><span class="group-hover:translate-x-0.5 transition-transform">\u2192</span></a></div>' +
      '</article>';
  }

  function renderPagination(d) {
    var total = d.total || 0, totalPages = d.total_pages || 1, page = d.page || 1;
    setText('paginationInfo', 'Page ' + page + ' of ' + totalPages);
    var nums = document.getElementById('paginationPageNumbers');
    if (nums) {
      var h = '';
      var from = Math.max(1, page - 2), to = Math.min(totalPages, from + 4);
      if (to - from < 4) from = Math.max(1, to - 4);
      for (var i = from; i <= to; i++) {
        h += '<button class="risk-page w-7 h-7 rounded-md text-xs font-medium ' + (i === page ? 'bg-blue-600 text-white' : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50') + '" data-page="' + i + '">' + i + '</button>';
      }
      nums.innerHTML = h;
      nums.querySelectorAll('.risk-page').forEach(function (b) {
        b.addEventListener('click', function () { explore.page = parseInt(b.getAttribute('data-page')); loadExplore(); });
      });
    }
    var prev = document.getElementById('btnPrevPage');
    var next = document.getElementById('btnNextPage');
    if (prev) prev.disabled = page <= 1;
    if (next) next.disabled = page >= totalPages;
  }

  function wireExplore() {
    document.querySelectorAll('.filter-entity-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.filter-entity-btn').forEach(function (b) { b.classList.remove('bg-blue-600', 'text-white'); b.classList.add('bg-white', 'text-slate-600'); });
        btn.classList.add('bg-blue-600', 'text-white'); btn.classList.remove('bg-white', 'text-slate-600');
        explore.entity = btn.getAttribute('data-mode'); explore.page = 1; loadExplore();
      });
    });
    document.querySelectorAll('.risk-level-cb').forEach(function (cb) {
      cb.addEventListener('change', function () { explore.page = 1; loadExplore(); });
    });
    var ss = document.getElementById('filterStateSelect');
    if (ss) ss.addEventListener('change', function () { explore.state_id = ss.value; explore.page = 1; loadExplore(); });
    var sort = document.getElementById('filterSortBy');
    if (sort) sort.addEventListener('change', function () { explore.sort = sort.value; explore.page = 1; loadExplore(); });
    var analyze = document.getElementById('filterAnalyzeBtn');
    if (analyze) analyze.addEventListener('click', function () { explore.page = 1; loadExplore(); });
    var reset = document.getElementById('filterResetBtn');
    if (reset) reset.addEventListener('click', function () {
      explore = { entity: 'mp', levels: ['high', 'medium', 'low'], state_id: '', sort: 'flagged', page: 1, pageSize: 9 };
      document.querySelectorAll('.risk-level-cb').forEach(function (cb) { cb.checked = true; });
      if (ss) ss.value = '';
      if (sort) sort.value = 'flagged';
      document.querySelectorAll('.filter-entity-btn').forEach(function (b) { b.classList.remove('bg-blue-600', 'text-white'); b.classList.add('bg-white', 'text-slate-600'); });
      var mp = document.getElementById('entityBtnMP'); if (mp) { mp.classList.add('bg-blue-600', 'text-white'); mp.classList.remove('bg-white', 'text-slate-600'); }
      loadExplore();
    });
    var prev = document.getElementById('btnPrevPage');
    if (prev) prev.addEventListener('click', function () { if (explore.page > 1) { explore.page--; loadExplore(); } });
    var next = document.getElementById('btnNextPage');
    if (next) next.addEventListener('click', function () { explore.page++; loadExplore(); });
  }

  function setupSidebar() {
    var toggleBtn = document.getElementById('sidebarToggleBtn');
    var sidebar = document.getElementById('appSidebar');
    var textElements = document.querySelectorAll('.sidebar-text-content');
    var collapsedStatus = document.getElementById('sidebarCollapsedStatus');
    var expandedStatus = document.getElementById('sidebarExpandedStatus');
    if (!toggleBtn || !sidebar) return;
    var isCollapsed = true;  // Always start collapsed (no localStorage persistence)
    function apply() {
      if (isCollapsed) {
        textElements.forEach(function (el) { el.classList.add('hidden'); });
        if (collapsedStatus) collapsedStatus.classList.remove('hidden');
        if (expandedStatus) expandedStatus.classList.add('hidden');
        sidebar.classList.remove('w-64'); sidebar.classList.add('w-16');
      } else {
        sidebar.classList.remove('w-16'); sidebar.classList.add('w-64');
        textElements.forEach(function (el) { el.classList.remove('hidden'); });
        if (collapsedStatus) collapsedStatus.classList.add('hidden');
        if (expandedStatus) expandedStatus.classList.remove('hidden');
      }
    }
    apply();
    toggleBtn.addEventListener('click', function () {
      isCollapsed = !isCollapsed;
      localStorage.removeItem('sidebarCollapsed');
      apply();
    });
  }

  function setupViewAll() {
    var btn = document.getElementById('viewAllAlertsBtn');
    if (!btn) return;
    var label = document.getElementById('viewAllAlertsLabel');
    btn.addEventListener('click', function () {
      if (alertsExpanded) {
        // collapse back to the default set
        renderAlerts(baseAlerts, 'all');
        wireAlertTabs(baseAlerts);
        alertsExpanded = false;
        if (label) label.textContent = 'View All High-Priority Alerts';
        var badge = document.querySelector('.alert-tab-btn[data-target="all"] span');
        if (badge) badge.textContent = baseAlerts.length;
        var allTab = document.querySelector('.alert-tab-btn[data-target="all"]');
        if (allTab) {
          document.querySelectorAll('.alert-tab-btn').forEach(function (t) { t.classList.remove('bg-white', 'text-slate-900', 'text-blue-700', 'shadow-xs', 'font-semibold'); t.classList.add('text-slate-600'); });
          allTab.classList.add('bg-white', 'text-slate-900', 'shadow-xs', 'font-semibold');
          allTab.classList.remove('text-slate-600');
        }
        return;
      }
      btn.disabled = true;
      fetch(API_BASE + '/api/risk/alerts?limit=50')
        .then(function (r) { return r.ok ? r.json() : { items: [] }; })
        .then(function (d) {
          var items = d.items || [];
          renderAlerts(items, 'all');
          wireAlertTabs(items);
          alertsExpanded = true;
          if (label) label.textContent = 'Show Fewer Alerts';
          var badge = document.querySelector('.alert-tab-btn[data-target="all"] span');
          if (badge) badge.textContent = items.length;
        })
        .catch(function () {})
        .then(function () { btn.disabled = false; });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    setupSidebar();
    setupViewAll();
    loadOverview();
    loadAlerts();
    loadStatesForFilter();
    wireExplore();
    loadExplore();
  });
})();

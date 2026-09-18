(function () {
  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  var CACHE_PREFIX = 'stateDetailCache_';
  var CACHE_TTL_MS = 30 * 60 * 1000;
  var stateData = null;
  var stateId = null;
  var currentCategory = 'all';
  var currentPage = 1;
  var pageSize = 6;
  var worksCache = {};
  var stateAiRingTarget = null;

  function animateStateAiRing() {
    var ring = document.getElementById('stateAiScoreRing');
    if (!ring || stateAiRingTarget == null || ring.dataset.anim) return;
    ring.dataset.anim = '1';
    ring.style.strokeDashoffset = stateAiRingTarget;
  }

  function getStateParam() {
    var params = new URLSearchParams(window.location.search);
    return params.get('state_id') || params.get('state') || params.get('id');
  }

  function getCache(id) {
    try {
      var raw = localStorage.getItem(CACHE_PREFIX + id);
      if (!raw) return null;
      var c = JSON.parse(raw);
      if (Date.now() - c.ts > CACHE_TTL_MS) { localStorage.removeItem(CACHE_PREFIX + id); return null; }
      return c.data;
    } catch (e) { return null; }
  }

  function setCache(id, data) {
    try { localStorage.setItem(CACHE_PREFIX + id, JSON.stringify({ data: data, ts: Date.now() })); } catch (e) {}
  }

  function fmtNum(n) {
    if (n == null || isNaN(n)) return '—';
    return Number(n).toLocaleString('en-IN');
  }

  function fmtCr(n) {
    if (n == null || isNaN(n)) return '—';
    var val = Number(n);
    if (val >= 1e7) return '₹' + (val / 1e7).toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' Cr';
    if (val >= 1e5) return '₹' + (val / 1e5).toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' L';
    return '₹' + val.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  function fmtPct(n) {
    if (n == null || isNaN(n)) return '—';
    return Number(n).toFixed(1) + '%';
  }

  function fmtDays(n) {
    if (n == null || isNaN(n)) return '—';
    return Math.round(Number(n)) + ' days';
  }

  function getColor(pct) {
    if (pct >= 70) return 'emerald';
    if (pct >= 50) return 'blue';
    if (pct >= 30) return 'amber';
    return 'rose';
  }

  function getClsColor(cls) {
    if (cls === 'EXCEPTIONAL') return 'emerald';
    if (cls === 'PERFORMER') return 'emerald';
    if (cls === 'STABLE') return 'blue';
    if (cls === 'AVERAGE') return 'blue';
    if (cls === 'NEEDS_ATTENTION') return 'amber';
    if (cls === 'UNDERPERFORMER') return 'rose';
    if (cls === 'NO_DATA' || cls === 'INSUFFICIENT_DATA') return 'slate';
    return 'slate';
  }

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function setHTML(id, html) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  function showShell(state, title, msg) {
    var loading = document.getElementById('stateLoadingState');
    var errorEl = document.getElementById('stateErrorState');
    var main = document.getElementById('stateMainContent');
    if (loading) loading.classList.toggle('hidden', state !== 'loading');
    if (errorEl) errorEl.classList.toggle('hidden', state !== 'error');
    if (main) main.classList.toggle('hidden', state !== 'main');
    if (state === 'error') {
      var t = document.getElementById('stateErrorTitle');
      var m = document.getElementById('stateErrorMsg');
      if (t && title) t.textContent = title;
      if (m && msg) m.textContent = msg;
    }
  }

  function regionFor(name) {
    var north = ['Jammu And Kashmir', 'Ladakh', 'Himachal Pradesh', 'Punjab', 'Uttarakhand', 'Haryana', 'Delhi', 'Chandigarh'];
    var northeast = ['Arunachal Pradesh', 'Assam', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland', 'Sikkim', 'Tripura'];
    var east = ['Bihar', 'Jharkhand', 'Odisha', 'West Bengal'];
    var west = ['Gujarat', 'Maharashtra', 'Rajasthan', 'Goa', 'The Dadra And Nagar Haveli And Daman And Diu'];
    var south = ['Andhra Pradesh', 'Karnataka', 'Kerala', 'Tamil Nadu', 'Telangana', 'Puducherry', 'Andaman And Nicobar Islands', 'Lakshadweep'];
    var central = ['Madhya Pradesh', 'Chhattisgarh', 'Uttar Pradesh'];
    if (north.indexOf(name) > -1) return 'Northern Region';
    if (northeast.indexOf(name) > -1) return 'Northeast Region';
    if (east.indexOf(name) > -1) return 'Eastern Region';
    if (west.indexOf(name) > -1) return 'Western Region';
    if (south.indexOf(name) > -1) return 'Southern Region';
    if (central.indexOf(name) > -1) return 'Central Region';
    return 'India';
  }

  // ===== HEADER =====
  function populateHeader(s) {
    document.title = (s.state_name || 'State') + ' — Govsense AI';
    setText('stateName', (s.state_name || '—').toUpperCase());
    var cls = s.performance_label || s.performance_classification || 'N/A';
    var c = getClsColor(cls);
    var el = document.getElementById('stateClassification');
    if (el) {
      el.className = 'px-3 py-1 rounded-full text-xs font-extrabold border flex items-center gap-1.5 bg-' + c + '-100 text-' + c + '-800 border-' + c + '-300';
      el.innerHTML = '<span class="w-2 h-2 rounded-full bg-' + c + '-500"></span>' + cls.replace(/_/g, ' ');
    }
    setText('stateRegion', regionFor(s.state_name));
    setText('stateMpCount', fmtNum(s.mp_count || 0) + ' MPs');
    setText('stateMlaCount', fmtNum(s.mla_count || 0) + ' MLAs');
    setText('stateRank', s.rank ? ('National Rank #' + s.rank) : 'Rank: N/A');
    setText('headerMeta', s.rank ? '#' + s.rank : 'Overview');
    setText('tabProjectsCount', fmtNum(s.total_works || 0));
    setText('repDescMp', fmtNum(s.mp_count || 0));
    setText('repDescMla', fmtNum(s.mla_count || 0));
    setText('repDescState', s.state_name || '');
    var sl = document.getElementById('scatterLegendState');
    if (sl) sl.textContent = (s.state_name || 'State') + (s.rank ? (' (Rank #' + s.rank + ')') : '');
  }

  // ===== KPI CARDS =====
  function populateKPIs(s) {
    var allocated = Number(s.allocated_amount) || Number(s.sanctioned_amount) || 0;
    var exp = Number(s.expenditure_amount) || 0;
    var util = Number(s.fund_utilization_pct) || 0;
    var comp = Number(s.completion_rate_pct) || 0;

    setText('kpiAllocated', fmtCr(allocated));
    setText('kpiAllocatedSub', 'Total envelope across ' + fmtNum(s.total_members || 0) + ' representatives');
    setText('kpiTotalWorks', fmtNum(s.total_works || 0));
    setText('kpiTotalWorksSub', fmtNum(s.completed_works || 0) + ' Completed · ' + fmtNum(s.ongoing_works || 0) + ' Ongoing · ' + fmtNum(s.pending_works || 0) + ' Pending');
    setText('kpiCompletionRate', fmtPct(comp));
    setText('kpiCompletionRateSub', fmtNum(s.completed_works || 0) + ' of ' + fmtNum(s.total_works || 0) + ' works completed');

    var uc = getColor(util);
    var uv = document.getElementById('kpiUtilization');
    if (uv) { uv.textContent = fmtPct(util); uv.className = 'text-2xl font-bold tracking-tight text-' + uc + '-600'; }
    var ub = document.getElementById('kpiUtilBadge');
    if (ub) {
      var ul = util >= 70 ? 'High' : util >= 50 ? 'Moderate' : util >= 30 ? 'Low' : 'Critical';
      ub.textContent = ul;
      ub.className = 'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border bg-' + uc + '-100 text-' + uc + '-800 border-' + uc + '-200';
    }
    setText('kpiUtilizationSub', fmtCr(exp) + ' spent of ' + fmtCr(allocated));

    var cc = getColor(comp);
    var cv = document.getElementById('kpiCompletionRate');
    if (cv) cv.className = 'text-2xl font-bold tracking-tight text-' + cc + '-600';
    var cb = document.getElementById('kpiCompBadge');
    if (cb) {
      var cl = comp >= 70 ? 'High' : comp >= 50 ? 'Moderate' : comp >= 30 ? 'Low' : 'Critical';
      cb.textContent = cl;
      cb.className = 'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border bg-' + cc + '-100 text-' + cc + '-800 border-' + cc + '-200';
    }
  }

  // ===== RISK DISTRIBUTION =====
  function populateRiskDistribution(s) {
    var container = document.getElementById('stateRiskDistribution');
    if (!container) return;
    var total = Number(s.total_works) || 1;
    var high = Number(s.high_risk_works) || 0;
    var flagged = Number(s.flagged_works) || 0;
    var medium = Math.max(flagged - high, 0);
    var low = Math.max(total - high - medium, 0);
    var items = [
      { label: 'High Risk', count: high, color: 'rose' },
      { label: 'Flagged', count: medium, color: 'amber' },
      { label: 'Low Risk', count: low, color: 'emerald' },
    ];
    var html = '';
    items.forEach(function (it) {
      var pct = total > 0 ? (it.count / total * 100) : 0;
      html += '<div class="p-3 bg-slate-50/70 border border-slate-200 rounded-lg text-center">' +
        '<div class="text-xl font-black text-' + it.color + '-600">' + fmtNum(it.count) + '</div>' +
        '<div class="text-[10px] font-bold text-' + it.color + '-700 uppercase tracking-wider mt-0.5">' + it.label + '</div>' +
        '<div class="text-[11px] text-slate-500">' + fmtPct(pct) + '</div>' +
        '<div class="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden mt-1.5"><div class="h-full bg-' + it.color + '-500 rounded-full" style="width:' + Math.min(pct, 100) + '%"></div></div></div>';
    });
    html += '<div class="col-span-full pt-2 border-t border-slate-100 flex justify-between text-xs text-slate-500">' +
      '<span>Anomaly level: <span class="font-bold text-slate-700">' + (s.anomaly_level || 'N/A') + '</span></span>' +
      '<span>Risk rate: <span class="font-bold">' + fmtPct(s.risk_rate_pct) + '</span></span></div>';
    container.innerHTML = html;
  }

  // ===== WORK STATUS =====
  function populateWorkStatus(s) {
    var container = document.getElementById('stateWorkStatusCounts');
    if (!container) return;
    var total = Number(s.total_works) || 1;
    var items = [
      { label: 'Completed', count: Number(s.completed_works) || 0, color: 'emerald' },
      { label: 'In Progress', count: Number(s.ongoing_works) || 0, color: 'blue' },
      { label: 'Recommended', count: Number(s.pending_works) || 0, color: 'violet' },
    ];
    var html = '';
    items.forEach(function (it) {
      var pct = total > 0 ? (it.count / total * 100) : 0;
      html += '<div class="p-3 bg-slate-50/70 border border-slate-200 rounded-lg text-center">' +
        '<div class="text-xl font-black text-' + it.color + '-600">' + fmtNum(it.count) + '</div>' +
        '<div class="text-[10px] font-bold text-' + it.color + '-700 uppercase tracking-wider mt-0.5">' + it.label + '</div>' +
        '<div class="text-[11px] text-slate-500">' + fmtPct(pct) + '</div>' +
        '<div class="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden mt-1.5"><div class="h-full bg-' + it.color + '-500 rounded-full" style="width:' + Math.min(pct, 100) + '%"></div></div></div>';
    });
    container.innerHTML = html;
  }

  // ===== WORKS =====
  function loadWorks(category, page) {
    currentCategory = category;
    currentPage = page;
    var grid = document.getElementById('stateWorksGrid');
    var key = category + '_' + page;
    if (worksCache[key]) { renderWorksData(worksCache[key]); return; }
    if (grid) grid.innerHTML = '<div class="col-span-full text-center py-8 text-slate-400 text-sm">Loading works...</div>';
    setText('stateWorksShowingText', 'Loading...');
    setHTML('stateWorksPageButtons', '');
    fetch(API_BASE + '/api/states/detail/' + stateId + '/works?category=' + category + '&page=' + page + '&page_size=' + pageSize)
      .then(function (r) { if (!r.ok) throw new Error('works'); return r.json(); })
      .then(function (data) { worksCache[key] = data; renderWorksData(data); })
      .catch(function () {
        if (!grid) return;
        grid.innerHTML =
          '<div class="col-span-full section-error">' +
            '<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>' +
            '<span>Could not load works for this state.</span>' +
            '<button type="button" data-retry-works="' + category + '|' + page + '">Retry</button>' +
          '</div>';
        var btn = grid.querySelector('[data-retry-works]');
        if (btn) btn.addEventListener('click', function () { loadWorks(category, page); });
      });
  }

  function renderWorksData(data) {
    var items = data.items || [];
    var total = data.total || 0;
    var totalPages = data.total_pages || 1;
    var page = data.page || 1;
    var grid = document.getElementById('stateWorksGrid');
    if (!grid) return;

    if (items.length === 0) {
      grid.innerHTML = '<div class="col-span-full text-center py-8 text-slate-400 text-sm">No works found in this category.</div>';
      setText('stateWorksShowingText', 'No works');
      setHTML('stateWorksPageButtons', '');
      return;
    }

    var html = '';
    items.forEach(function (w) {
      var st = (w.status || 'Unknown').toLowerCase();
      var sc = 'slate', displayStatus = w.status || 'Unknown';
      if (st === 'completed') { sc = 'emerald'; displayStatus = 'Completed'; }
      else if (st === 'ongoing' || st === 'in progress' || st === 'inprogress' || st === 'active') { sc = 'blue'; displayStatus = 'In Progress'; }
      else if (st === 'pending' || st === 'recommended' || st === 'sanctioned' || st === 'proposed') { sc = 'amber'; displayStatus = 'Recommended'; }
      var rc = 'slate';
      var rk = (w.risk_level || '').toLowerCase();
      if (rk === 'high') rc = 'rose';
      else if (rk === 'medium') rc = 'amber';
      else if (rk === 'low') rc = 'emerald';
      var desc = w.work_description || w.activity_name || 'No description';
      if (desc.length > 120) desc = desc.substring(0, 120) + '...';
      html += '<a class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md hover:border-blue-300 transition-all cursor-pointer block" href="workdetail.html?id=' + w.work_id + '">' +
        '<div class="flex items-start justify-between gap-2 mb-2">' +
        '<span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">' + (w.work_category || 'General') + '</span>' +
        '<div class="flex items-center gap-1.5">' +
        '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-' + sc + '-50 text-' + sc + '-700 border border-' + sc + '-200">' + displayStatus + '</span>' +
        (rk && rk !== 'normal' ? '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-' + rc + '-50 text-' + rc + '-700 border border-' + rc + '-200">' + rk + '</span>' : '') +
        '</div></div>' +
        '<p class="text-sm text-slate-800 font-medium mb-3 leading-snug">' + desc + '</p>' +
        '<div class="grid grid-cols-2 gap-2 text-xs">' +
        '<div><span class="text-slate-400">Sanction</span><div class="font-bold text-slate-900">' + fmtCr(w.sanction_amount) + '</div></div>' +
        '<div><span class="text-slate-400">Expenditure</span><div class="font-bold text-slate-900">' + fmtCr(w.expenditure_amount) + '</div></div></div>' +
        (w.recommendation_date ? '<div class="mt-2 text-[10px] text-slate-400">Recommended: ' + String(w.recommendation_date).substring(0, 10) + '</div>' : '') +
        '</a>';
    });
    grid.innerHTML = html;

    var start = (page - 1) * pageSize;
    var end = start + items.length;
    setText('stateWorksShowingText', 'Showing ' + (start + 1) + '-' + end + ' of ' + fmtNum(total) + ' works');

    var btns = '';
    if (totalPages > 1) {
      btns += '<button class="state-page-btn px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 bg-white text-slate-600 hover:bg-slate-50' + (page <= 1 ? ' opacity-50 cursor-not-allowed' : '') + '" data-page="' + (page - 1) + '">Prev</button>';
      var from = Math.max(1, page - 2);
      var to = Math.min(totalPages, from + 4);
      if (to - from < 4) from = Math.max(1, to - 4);
      for (var i = from; i <= to; i++) {
        btns += i === page
          ? '<button class="state-page-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white shadow-xs" data-page="' + i + '">' + i + '</button>'
          : '<button class="state-page-btn px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 bg-white text-slate-600 hover:bg-slate-50" data-page="' + i + '">' + i + '</button>';
      }
      btns += '<button class="state-page-btn px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 bg-white text-slate-600 hover:bg-slate-50' + (page >= totalPages ? ' opacity-50 cursor-not-allowed' : '') + '" data-page="' + (page + 1) + '">Next</button>';
    }
    setHTML('stateWorksPageButtons', btns);
    document.querySelectorAll('.state-page-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var p = parseInt(btn.getAttribute('data-page'));
        if (p >= 1 && p <= totalPages && p !== page) loadWorks(currentCategory, p);
      });
    });
  }

  function setupCategoryTabs() {
    document.querySelectorAll('.state-category-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.state-category-btn').forEach(function (b) {
          b.classList.remove('bg-blue-600', 'text-white', 'shadow-xs');
          b.classList.add('border', 'border-slate-200', 'bg-white', 'text-slate-600', 'font-medium');
        });
        btn.classList.add('bg-blue-600', 'text-white', 'shadow-xs');
        btn.classList.remove('border', 'border-slate-200', 'bg-white', 'text-slate-600', 'font-medium');
        loadWorks(btn.getAttribute('data-category'), 1);
      });
    });
  }

  // ===== AI TAB =====
  function populateAI(s, analysis) {
    var score = Number(s.performance_score_weighted != null ? s.performance_score_weighted
      : s.performance_score_100 != null ? s.performance_score_100 : s.performance_score) || 0;
    var cls = s.performance_label || s.performance_classification || 'N/A';
    var displayMax = 100;
    var cc = getClsColor(cls);

    var ring = document.getElementById('stateAiScoreRing');
    if (ring) {
      var circ = 364.42;
      ring.setAttribute('stroke-dasharray', circ + ' ' + circ);
      ring.setAttribute('stroke-dashoffset', circ);
      ring.setAttribute('stroke', cc === 'emerald' ? '#10b981' : cc === 'blue' ? '#3b82f6' : cc === 'amber' ? '#f59e0b' : '#ef4444');
      stateAiRingTarget = circ - (circ * Math.min(score / displayMax, 1));
    }
    setText('stateAiScoreValue', Math.round(score));
    var badge = document.getElementById('stateAiScoreBadge');
    if (badge) {
      badge.textContent = cls.replace(/_/g, ' ');
      badge.className = 'mt-3 px-3 py-1 rounded-full text-xs font-bold border bg-' + cc + '-100 text-' + cc + '-800 border-' + cc + '-300';
    }

    // Intelligence meta: rank, percentile, cluster, risk
    setText('stateAiNationalRank', s.rank != null ? ('#' + fmtNum(s.rank)) : '—');
    setText('stateAiNationalPercentile', s.national_percentile != null ? fmtPct(s.national_percentile) : '—');
    setText('stateAiClusterLabel', s.cluster_label && s.cluster_label !== 'insufficient' ? s.cluster_label : '—');
    var riskEl = document.getElementById('stateAiRiskLevel');
    if (riskEl) {
      var rl = (s.risk_level || 'N/A').toUpperCase();
      var rc = rl === 'CRITICAL' || rl === 'HIGH' ? 'rose' : rl === 'MODERATE' || rl === 'MEDIUM' ? 'amber' : 'emerald';
      riskEl.textContent = rl.replace(/_/g, ' ');
      riskEl.className = 'text-xs font-semibold text-' + rc + '-700';
    }
    var confEl = document.getElementById('stateAiRiskConfidence');
    if (confEl) {
      confEl.textContent = s.risk_confidence ? s.risk_confidence.toUpperCase() : '—';
    }

    var breakdown = document.getElementById('stateAiScoreBreakdown');
    if (breakdown) {
      var comp = Number(s.completion_rate_pct) || 0;
      var util = Number(s.fund_utilization_pct) || 0;
      var sanction = Number(s.sanction_rate_pct) || 0;
      var riskRate = Number(s.risk_rate_pct) || 0;
      var metrics = [
        { label: 'Completion Rate', value: comp, color: getColor(comp) },
        { label: 'Fund Utilization', value: util, color: getColor(util) },
        { label: 'Sanction Rate', value: sanction, color: getColor(sanction) },
        { label: 'Risk / Anomaly Rate', value: riskRate, color: riskRate > 20 ? 'rose' : 'emerald' },
      ];
      var html = '<div class="flex items-center justify-between mb-3"><h4 class="text-xs font-bold text-slate-900 uppercase tracking-wider">Score Components</h4>' +
        '<span class="text-xs font-bold text-slate-500">' + Math.round(score) + ' / ' + displayMax + ' points</span></div>';
      metrics.forEach(function (m) {
        html += '<div class="space-y-1.5"><div class="flex justify-between items-center text-xs">' +
          '<span class="font-medium text-slate-600">' + m.label + '</span>' +
          '<span class="font-bold text-' + m.color + '-700">' + fmtPct(m.value) + '</span></div>' +
          '<div class="w-full h-4 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + m.color + '-500 rounded-full transition-all duration-1000" style="width:' + Math.min(m.value, 100) + '%"></div></div></div>';
      });
      breakdown.innerHTML = html;
    }

    // Summary
    var summaryEl = document.getElementById('stateAiSummaryContent');
    if (summaryEl) {
      var summaryText = '';
      if (analysis) {
        if (typeof analysis === 'string') summaryText = analysis;
        else if (analysis.summary) summaryText = analysis.summary;
      }
      summaryEl.innerHTML = summaryText
        ? '<p class="text-[14px] text-slate-700 leading-relaxed">' + summaryText + '</p>'
        : '<p class="text-sm text-slate-500 italic">No AI summary available for this state.</p>';
    }

    // Highlights
    var highlightsEl = document.getElementById('stateAiHighlightsContent');
    if (highlightsEl) {
      var highlights = (analysis && typeof analysis === 'object' && analysis.highlights) ? analysis.highlights : [];
      if (highlights.length > 0) {
        var h = '<ul class="space-y-2">';
        highlights.forEach(function (x) {
          h += '<li class="text-[13px] text-slate-700 flex items-start gap-2.5 p-2 bg-emerald-50/50 rounded-lg border border-emerald-100">' +
            '<svg class="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>' +
            '<span>' + x + '</span></li>';
        });
        highlightsEl.innerHTML = h + '</ul>';
      } else {
        highlightsEl.innerHTML = '<p class="text-sm text-slate-500 italic">No highlights available.</p>';
      }
    }

    // Peer Benchmark — fetch cluster/national averages from API
    var benchEl = document.getElementById('stateAiPeerBenchmarkChart');
    if (benchEl) {
      var stateId = s.state_id || stateData.state_id;
      var apiUrl = API_BASE + '/api/peer-benchmark?member_type=MLA&entity_id=' + stateId;
      benchEl.innerHTML = '<div class="text-sm text-slate-400 text-center py-8">Loading...</div>';
      fetch(apiUrl).then(function(r) { return r.json(); }).then(function(bench) {
        var stateMetrics = [
          { label: 'Completion Rate', value: Number(s.completion_rate_pct) || 0, cluster: bench.cluster_avg ? bench.cluster_avg.completion_rate_pct : null, national: bench.national_avg ? bench.national_avg.completion_rate_pct : null },
          { label: 'Fund Utilization', value: Number(s.fund_utilization_pct) || 0, cluster: bench.cluster_avg ? bench.cluster_avg.fund_utilization_pct : null, national: bench.national_avg ? bench.national_avg.fund_utilization_pct : null },
          { label: 'Sanction Rate', value: Number(s.sanction_rate_pct) || 0, cluster: bench.cluster_avg ? bench.cluster_avg.sanction_rate_pct : null, national: bench.national_avg ? bench.national_avg.sanction_rate_pct : null },
        ];
        var hasAvgs = stateMetrics.some(function(p) { return p.cluster !== null || p.national !== null; });
        var bhtml = '<div class="space-y-5">';
        stateMetrics.forEach(function(p) {
          bhtml += '<div class="space-y-2">';
          bhtml += '<div class="flex justify-between items-center"><span class="text-xs font-bold text-slate-700">' + p.label + '</span><span class="text-sm font-black text-' + getColor(p.value) + '-700">' + fmtPct(p.value) + '</span></div>';
          bhtml += '<div class="space-y-1">';
          bhtml += '<div class="flex items-center gap-2"><span class="text-[10px] font-semibold text-slate-500 w-14 flex-shrink-0">State</span>';
          bhtml += '<div class="flex-1 h-5 bg-slate-100 rounded-full overflow-hidden relative">';
          bhtml += '<div class="h-full bg-' + getColor(p.value) + '-500 rounded-full transition-all duration-1000" style="width:' + Math.min(p.value, 100) + '%"></div>';
          bhtml += '</div><span class="text-[10px] font-bold text-slate-700 w-12 text-right">' + fmtPct(p.value) + '</span></div>';
          if (p.cluster !== null) {
            bhtml += '<div class="flex items-center gap-2"><span class="text-[10px] font-semibold text-violet-500 w-14 flex-shrink-0">Cluster</span>';
            bhtml += '<div class="flex-1 h-3 bg-slate-50 rounded-full overflow-hidden relative">';
            bhtml += '<div class="h-full bg-violet-400 rounded-full transition-all duration-1000 opacity-70" style="width:' + Math.min(p.cluster, 100) + '%"></div>';
            bhtml += '</div><span class="text-[10px] font-semibold text-violet-600 w-12 text-right">' + fmtPct(p.cluster) + '</span></div>';
          }
          if (p.national !== null) {
            bhtml += '<div class="flex items-center gap-2"><span class="text-[10px] font-semibold text-slate-400 w-14 flex-shrink-0">National</span>';
            bhtml += '<div class="flex-1 h-3 bg-slate-50 rounded-full overflow-hidden relative">';
            bhtml += '<div class="h-full bg-slate-400 rounded-full transition-all duration-1000 opacity-60" style="width:' + Math.min(p.national, 100) + '%"></div>';
            bhtml += '</div><span class="text-[10px] font-semibold text-slate-500 w-12 text-right">' + fmtPct(p.national) + '</span></div>';
          }
          bhtml += '</div></div>';
        });
        if (hasAvgs) {
          bhtml += '<div class="flex items-center gap-5 text-[10px] text-slate-500 pt-2 border-t border-slate-100">' +
            '<span class="flex items-center gap-1.5"><span class="w-3 h-2 bg-emerald-500 rounded inline-block"></span> State</span>' +
            '<span class="flex items-center gap-1.5"><span class="w-3 h-1.5 bg-violet-400 rounded inline-block opacity-70"></span> Cluster Avg</span>' +
            '<span class="flex items-center gap-1.5"><span class="w-3 h-1.5 bg-slate-400 rounded inline-block opacity-60"></span> National Avg</span></div>';
        }
        bhtml += '</div>';
        benchEl.innerHTML = bhtml;
      }).catch(function() {
        benchEl.innerHTML = '<p class="text-[11px] text-slate-400 italic text-center py-4">Peer averages unavailable.</p>';
      });
    }

    // Performance Metrics
    var chartEl = document.getElementById('stateAiPerformanceChart');
    if (chartEl) {
      var anomalyLevel = s.anomaly_level || 'N/A';
      var ac = anomalyLevel === 'high' ? 'rose' : anomalyLevel === 'medium' ? 'amber' : 'emerald';
      var cm = [
        { label: 'Fund Utilization', value: Number(s.fund_utilization_pct) || 0 },
        { label: 'Completion Rate', value: Number(s.completion_rate_pct) || 0 },
        { label: 'Sanction Rate', value: Number(s.sanction_rate_pct) || 0 },
        { label: 'Anomaly Score', value: Number(s.anomaly_score) || 0, color: ac },
        { label: 'Flagged Rate', value: Number(s.risk_rate_pct) || 0, color: (Number(s.risk_rate_pct) || 0) > 10 ? 'rose' : 'emerald' },
      ];
      var ch = '';
      cm.forEach(function (m) {
        var c = m.color || getColor(m.value);
        ch += '<div class="space-y-1.5"><div class="flex justify-between items-center text-xs">' +
          '<span class="font-semibold text-slate-700">' + m.label + '</span>' +
          '<span class="font-bold text-' + c + '-700">' + fmtPct(m.value) + '</span></div>' +
          '<div class="w-full h-4 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + c + '-500 rounded-full transition-all duration-1000" style="width:' + Math.min(m.value, 100) + '%"></div></div></div>';
      });
      chartEl.innerHTML = ch;
    }
  }

  // ===== OVERVIEW =====
  function populateOverview(s, benchmarks) {
    var util = Number(s.fund_utilization_pct) || 0;
    var comp = Number(s.completion_rate_pct) || 0;
    var sanction = Number(s.sanction_rate_pct) || 0;
    var total = Number(s.total_works) || 0;
    var completed = Number(s.completed_works) || 0;
    var ongoing = Number(s.ongoing_works) || 0;
    var pending = Number(s.pending_works) || 0;
    var allocated = Number(s.allocated_amount) || Number(s.sanctioned_amount) || 0;
    var exp = Number(s.expenditure_amount) || 0;

    // Gauge
    var totalLen = 282.74;
    var offset = totalLen - (totalLen * Math.min(util, 100) / 100);
    var arc = document.getElementById('gaugeActiveArc');
    var needle = document.getElementById('gaugeNeedle');
    var uc = getColor(util);
    if (arc) arc.style.strokeDashoffset = offset;
    if (needle) needle.style.transform = 'rotate(' + (-90 + (180 * Math.min(util, 100) / 100)) + 'deg)';

    var gv = document.getElementById('gaugeValue');
    if (gv) gv.innerHTML = fmtPct(util).replace('%', '<span class="text-xl font-bold text-' + uc + '-600">%</span>');
    var gb = document.getElementById('gaugeBadge');
    if (gb) { gb.textContent = fmtPct(util) + ' Disbursed'; gb.className = 'text-xs font-semibold px-2 py-0.5 rounded border bg-' + uc + '-50 text-' + uc + '-700 border-' + uc + '-200'; }
    var gt = document.getElementById('gaugeTier');
    if (gt) { var tier = util >= 70 ? '>=70% Performer' : util >= 50 ? '50-69% Average' : util >= 30 ? '30-49% Needs Attention' : '<30% Underperformer'; gt.textContent = tier; gt.className = 'text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider border bg-' + uc + '-100 text-' + uc + '-800 border-' + uc + '-200'; }
    var gl = document.getElementById('gaugeLabel');
    if (gl) gl.textContent = util >= 70 ? 'High Fund Utilization Velocity' : util >= 50 ? 'Moderate Utilization' : util >= 30 ? 'Below Average Utilization' : 'Critical Underutilization';
    setText('gaugeSanctionExp', fmtCr(exp) + ' / ' + fmtCr(s.sanctioned_amount) + ' (' + fmtPct(util) + ')');
    setText('gaugeAllocPool', fmtCr(allocated) + ' · ' + fmtPct(allocated > 0 ? exp / allocated * 100 : 0) + ' of allocated');

    // Donut (animated draw-in, viewport-aware, runs once)
    var circ = 326.72;
    var t2 = total || 1;
    var cp = completed / t2, op = ongoing / t2, pp = pending / t2;
    var dc = document.getElementById('donutCompleted');
    var do2 = document.getElementById('donutOngoing');
    var dp = document.getElementById('donutPending');
    if (dc) dc.setAttribute('stroke-dashoffset', '0');
    if (do2) do2.setAttribute('stroke-dashoffset', '-' + (cp * circ).toFixed(2));
    if (dp) dp.setAttribute('stroke-dashoffset', '-' + ((cp + op) * circ).toFixed(2));
    var _dsegs = [{ el: dc, len: cp * circ }, { el: do2, len: op * circ }, { el: dp, len: pp * circ }];
    if (window.ChartAnim) {
      window.ChartAnim.whenVisible(dc || dp, 'stateDonut', function () {
        window.ChartAnim.drawDonut(_dsegs, circ, { duration: 900 });
      });
    } else {
      _dsegs.forEach(function (s) { if (s.el) s.el.setAttribute('stroke-dasharray', s.len + ' ' + circ); });
    }
    setText('donutTotalTag', fmtNum(total) + ' Works');
    setText('donutCenter', fmtNum(total));
    setText('donutCompCount', fmtNum(completed));
    setText('donutCompPct', fmtPct(cp * 100));
    setText('donutOngCount', fmtNum(ongoing));
    setText('donutOngPct', fmtPct(op * 100));
    setText('donutPendCount', fmtNum(pending));
    setText('donutPendPct', fmtPct(pp * 100));

    // Benchmark
    setText('benchmarkTitle', (s.state_name || 'State') + ' vs National Benchmark');
    setText('benchmarkRank', s.rank ? ('Rank #' + s.rank) : 'Rank: N/A');
    var benchEl = document.getElementById('benchmarkMetrics');
    // Phase 5: national benchmarks are shown ONLY when the authoritative DB
    // value exists. No hardcoded fallbacks.
    var bval = function (k) {
      return (benchmarks && benchmarks[k] != null && !isNaN(Number(benchmarks[k])))
        ? Number(benchmarks[k]) : null;
    };
    if (benchEl) {
      var metrics = [
        { label: 'Fund Utilization', value: util, bench: bval('fund_utilization_pct'), fmt: fmtPct },
        { label: 'Completion Rate', value: comp, bench: bval('completion_rate_pct'), fmt: fmtPct },
        { label: 'Sanctioned / Recommended', value: sanction, bench: bval('sanction_rate_pct'), fmt: fmtPct },
        { label: 'Risk / Anomaly Rate', value: Number(s.risk_rate_pct) || 0, bench: null, fmt: fmtPct },
      ];
      var bh = '';
      metrics.forEach(function (m) {
        var hasBench = m.bench != null;
        var delta = hasBench ? (m.value - m.bench) : null;
        var dc2 = (delta != null && delta >= 0) ? 'emerald' : 'rose';
        bh += '<div class="p-3 bg-white rounded-lg border border-slate-200 flex items-center justify-between">' +
          '<div><span class="font-semibold text-slate-800 block">' + m.label + '</span>' +
          '<span class="text-[11px] text-slate-500">Nat. Benchmark: ' + (hasBench ? fmtPct(m.bench) : 'unavailable') + '</span></div>' +
          '<div class="text-right"><div class="text-sm font-bold text-' + getColor(m.value) + '-600">' + m.fmt(m.value) + '</div>' +
          (hasBench ? '<span class="inline-flex items-center text-[10px] font-bold text-' + dc2 + '-700 bg-' + dc2 + '-50 px-1.5 py-0.5 rounded">' +
          (delta >= 0 ? '+' : '') + fmtPct(delta) + '</span>' : '') + '</div></div>';
      });
      benchEl.innerHTML = bh;
    }

    // State vs National
    var svn = document.getElementById('stateVsNational');
    if (svn) {
      var cards = [
        { label: 'Fund Utilization', value: util, bench: bval('fund_utilization_pct') },
        { label: 'Completion Rate', value: comp, bench: bval('completion_rate_pct') },
        { label: 'Sanctioned / Recommended', value: sanction, bench: bval('sanction_rate_pct') },
      ];
      var sh = '';
      cards.forEach(function (m) {
        var c = getColor(m.value);
        var hasBench = m.bench != null;
        var delta = hasBench ? (m.value - m.bench) : null;
        var label = m.value >= 70 ? 'Leader' : m.value >= 50 ? 'Upper Cohort' : m.value >= 30 ? 'Developing' : 'At Risk';
        sh += '<div class="space-y-3 text-xs p-4 bg-slate-50/70 rounded-xl border border-slate-200">' +
          '<div class="flex justify-between items-baseline"><span class="font-bold text-slate-800 text-sm">' + m.label + '</span>' +
          '<span class="text-' + c + '-600 font-extrabold text-base">' + fmtPct(m.value) + '</span></div>' +
          '<div class="space-y-1"><div class="flex justify-between text-[11px] text-slate-600">' +
          '<span class="font-bold text-slate-800">' + (s.state_name || '') + '</span>' +
          '<span class="font-bold text-' + c + '-600">' + fmtPct(m.value) + '</span></div>' +
          '<div class="w-full h-3 bg-slate-200 rounded-full overflow-hidden"><div class="bg-' + c + '-500 h-full rounded-full transition-all duration-1000 ease-out" style="width:' + Math.min(m.value, 100) + '%"></div></div></div>' +
          (hasBench ? '<div class="space-y-1 pt-1"><div class="flex justify-between text-[11px] text-slate-500"><span>National Benchmark</span>' +
          '<span class="font-medium text-slate-600">' + fmtPct(m.bench) + '</span></div>' +
          '<div class="w-full h-2.5 bg-slate-200 rounded-full overflow-hidden"><div class="bg-slate-400 h-full rounded-full" style="width:' + Math.min(m.bench, 100) + '%"></div></div></div>' +
          '<div class="pt-2 border-t border-slate-200 flex items-center justify-between text-[11px]">' +
          '<span class="font-bold text-' + (delta >= 0 ? 'emerald' : 'rose') + '-700">' + (delta >= 0 ? '▲ +' : '▼ ') + fmtPct(delta) + ' vs national</span>' +
          '<span class="font-bold bg-' + c + '-100 text-' + c + '-800 px-2 py-0.5 rounded text-[10px]">' + label + '</span></div></div>'
          : '<div class="pt-2 border-t border-slate-200 text-[11px] text-slate-500">National benchmark unavailable</div></div>');
      });
      svn.innerHTML = sh;
    }
  }

  // ===== REPRESENTATIVES =====
  function populateRepresentatives(members) {
    var mps = members.filter(function (m) { return (m.member_type || '').toUpperCase() === 'MP'; });
    var mlas = members.filter(function (m) { return (m.member_type || '').toUpperCase() === 'MLA'; });
    function agg(list) {
      var works = 0, done = 0, alloc = 0, exp = 0;
      list.forEach(function (m) { works += Number(m.total_works) || 0; done += Number(m.completed_works) || 0; alloc += Number(m.sanctioned_amount) || 0; exp += Number(m.expenditure_amount) || 0; });
      return { count: list.length, works: works, done: done, alloc: alloc, exp: exp, util: alloc > 0 ? exp / alloc * 100 : 0, comp: works > 0 ? done / works * 100 : 0 };
    }
    var mp = agg(mps), mla = agg(mlas);

    var el1 = document.getElementById('repMpSpent');
    var el2 = document.getElementById('repMlaSpent');
    var el3 = document.getElementById('repMpWorks');
    var el4 = document.getElementById('repMlaWorks');
    if (el1) el1.textContent = fmtCr(mp.exp) + ' spent';
    if (el2) el2.textContent = fmtCr(mla.exp) + ' spent';
    if (el3) el3.textContent = fmtNum(mp.works) + ' Works · ' + fmtNum(mp.done) + ' Completed';
    if (el4) el4.textContent = fmtNum(mla.works) + ' Works · ' + fmtNum(mla.done) + ' Completed';

    var repBars = document.getElementById('repBars');
    if (repBars) {
      var bars = [
        { label: 'Fund Utilization', mp: mp.util, mla: mla.util },
        { label: 'Project Completion Rate', mp: mp.comp, mla: mla.comp },
      ];
      var h = '';
      bars.forEach(function (b) {
        h += '<div class="space-y-1.5"><div class="flex justify-between text-xs font-medium">' +
          '<span class="text-slate-700">' + b.label + '</span>' +
          '<div class="flex gap-4 font-bold text-[11px]"><span class="text-blue-700">MPs: ' + fmtPct(b.mp) + '</span>' +
          '<span class="text-indigo-700">MLAs: ' + fmtPct(b.mla) + '</span></div></div>' +
          '<div class="w-full h-3 bg-slate-100 rounded-full flex overflow-hidden">' +
          '<div class="bg-blue-600 h-full" style="width:' + Math.min(b.mp, 50) + '%"></div>' +
          '<div class="bg-indigo-600 h-full opacity-75" style="width:' + Math.min(b.mla, 50) + '%"></div></div></div>';
      });
      h += '<div class="grid grid-cols-2 gap-3 pt-2 text-xs">' +
        '<div class="p-3 bg-blue-50/70 border border-blue-200 rounded-lg"><div class="text-[10px] uppercase font-bold text-blue-600">Members of Parliament (' + fmtNum(mp.count) + ')</div>' +
        '<div class="text-base font-bold text-blue-950 mt-0.5">' + fmtCr(mp.exp) + ' spent</div>' +
        '<div class="text-[11px] text-blue-700 mt-0.5">' + fmtNum(mp.works) + ' Works · ' + fmtNum(mp.done) + ' Completed</div></div>' +
        '<div class="p-3 bg-indigo-50 border border-indigo-200 rounded-lg"><div class="text-[10px] uppercase font-bold text-indigo-600">MLAs Assembly Cohort (' + fmtNum(mla.count) + ')</div>' +
        '<div class="text-base font-bold text-slate-900 mt-0.5">' + fmtCr(mla.exp) + ' spent</div>' +
        '<div class="text-[11px] text-indigo-700 mt-0.5">' + fmtNum(mla.works) + ' Works · ' + fmtNum(mla.done) + ' Completed</div></div></div>';
      repBars.innerHTML = h;
    }

    // Build mobile card view for representatives table
    var cardsContainer = document.getElementById('repsMobileCards');
    if (!cardsContainer) {
      var tableEl = document.querySelector('#tab-representatives table');
      if (tableEl) {
        cardsContainer = document.createElement('div');
        cardsContainer.id = 'repsMobileCards';
        cardsContainer.className = 'reps-mobile-cards hidden space-y-3';
        tableEl.parentElement.insertBefore(cardsContainer, tableEl.nextSibling);
      }
    }
    if (cardsContainer) {
      var rows = [];
      var tbody = document.getElementById('topRepresentativesBody');
      if (tbody) {
        var trs = tbody.querySelectorAll('tr');
        trs.forEach(function(tr) {
          var tds = tr.querySelectorAll('td');
          if (tds.length >= 7) {
            rows.push({
              rank: tds[0].textContent.trim(),
              name: tds[1].textContent.trim(),
              constituency: tds[2].textContent.trim(),
              util: tds[3].textContent.trim(),
              comp: tds[4].textContent.trim(),
              works: tds[5].textContent.trim(),
              classification: tds[6].textContent.trim()
            });
          }
        });
      }
      if (rows.length > 0) {
        var chtml = '<div class="text-xs font-bold text-slate-800 uppercase tracking-wider mb-2">Top Performing Representatives</div>';
        rows.forEach(function(r) {
          var uc = 'slate';
          if (r.classification.indexOf('PERFORMER') > -1 || r.classification.indexOf('EXCEPTIONAL') > -1) uc = 'emerald';
          else if (r.classification.indexOf('STABLE') > -1 || r.classification.indexOf('AVERAGE') > -1) uc = 'blue';
          else if (r.classification.indexOf('NEEDS') > -1) uc = 'amber';
          else if (r.classification.indexOf('UNDER') > -1) uc = 'rose';
          chtml += '<div class="p-3 bg-white border border-slate-200 rounded-xl">' +
            '<div class="flex items-center justify-between mb-1.5">' +
            '<div class="flex items-center gap-2">' +
            '<span class="text-sm font-black text-blue-600">' + r.rank + '</span>' +
            '<span class="text-sm font-bold text-slate-900">' + r.name + '</span></div>' +
            '<span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-' + uc + '-100 text-' + uc + '-800 border border-' + uc + '-200">' + r.classification + '</span></div>' +
            '<div class="text-[11px] text-slate-500 mb-1.5">' + r.constituency + '</div>' +
            '<div class="grid grid-cols-3 gap-2 text-[11px]">' +
            '<div><span class="text-slate-500">Util</span> <span class="font-bold text-slate-800">' + r.util + '</span></div>' +
            '<div><span class="text-slate-500">Comp</span> <span class="font-bold text-slate-800">' + r.comp + '</span></div>' +
            '<div><span class="text-slate-500">Works</span> <span class="font-bold text-slate-800">' + r.works + '</span></div></div></div>';
        });
        cardsContainer.innerHTML = chtml;
      }
    }
  }

  // ===== FINANCIAL =====
  function populateFinancial(s) {
    var allocated = Number(s.allocated_amount) || Number(s.sanctioned_amount) || 0;
    var recommended = Number(s.recommended_amount) || 0;
    var sanctioned = Number(s.sanctioned_amount) || 0;
    var exp = Number(s.expenditure_amount) || 0;
    var util = Number(s.fund_utilization_pct) || 0;
    var comp = Number(s.completion_rate_pct) || 0;
    var sanctionRate = Number(s.sanction_rate_pct) || 0;
    var unspent = Math.max(allocated - exp, 0);
    var completionAmt = Number(s.completion_amount) || 0;

    setText('finAllocated', fmtCr(allocated));
    setText('finRecommended', fmtCr(recommended));
    setText('finSanctioned', fmtCr(sanctioned));
    setText('finExpenditure', fmtCr(exp));
    setText('finUtil', fmtPct(util));
    setText('finComp', fmtPct(comp));
    setText('finSanctionRate', fmtPct(sanctionRate));
    setText('finRecPct', allocated > 0 ? fmtPct(recommended / allocated * 100) : '—');
    setText('finSancPct', allocated > 0 ? fmtPct(sanctioned / allocated * 100) : '—');
    setText('finExpPct', allocated > 0 ? fmtPct(exp / allocated * 100) : '—');

    var distEl = document.getElementById('finDistributionBar');
    if (distEl) {
      var pct = allocated > 0 ? exp / allocated * 100 : 0;
      var rem = 100 - pct;
      distEl.innerHTML = '<div class="flex flex-col sm:flex-row sm:items-center justify-between text-xs gap-1">' +
        '<div class="font-bold text-slate-800">Allocation Distribution (Total: ' + fmtCr(allocated) + ')</div>' +
        '<div class="text-slate-500 text-[11px]">' + fmtCr(exp) + ' Disbursed (' + fmtPct(pct) + ') vs ' + fmtCr(unspent) + ' Remaining (' + fmtPct(rem) + ')</div></div>' +
        '<div class="w-full h-4 bg-slate-200 rounded-full overflow-hidden flex shadow-inner mt-2">' +
        '<div class="bg-[#10b981] h-full flex items-center justify-end pr-2 text-[10px] font-bold text-white tracking-wider" style="width:' + pct + '%;">' + fmtPct(pct) + '</div>' +
        '<div class="bg-[#f59e0b] h-full flex items-center justify-center text-[10px] font-bold text-amber-950" style="width:' + rem + '%;">' + fmtPct(rem) + '</div></div>';
    }

    // Fund Flow Progression bars
    var flowEl = document.getElementById('finFundFlowBars');
    if (flowEl) {
      var stages = [
        { label: 'Allocated', amount: allocated, pct: 100, color: 'teal' },
        { label: 'Recommended', amount: recommended, pct: allocated > 0 ? (recommended / allocated * 100) : 0, color: 'emerald' },
        { label: 'Sanctioned', amount: sanctioned, pct: allocated > 0 ? (sanctioned / allocated * 100) : 0, color: 'blue' },
        { label: 'Expenditure', amount: exp, pct: allocated > 0 ? (exp / allocated * 100) : 0, color: 'violet' },
      ];
      var fhtml = '';
      stages.forEach(function(st) {
        fhtml += '<div class="space-y-1">' +
          '<div class="flex justify-between text-xs"><span class="font-semibold text-slate-700">' + st.label + '</span>' +
          '<span class="font-bold text-slate-900">' + fmtCr(st.amount) + ' <span class="text-slate-400 font-normal">(' + fmtPct(st.pct) + ')</span></span></div>' +
          '<div class="w-full h-3 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + st.color + '-500 rounded-full transition-all duration-700" style="width:' + Math.min(st.pct, 100) + '%"></div></div></div>';
      });
      fhtml += '<div class="pt-2 border-t border-slate-100 flex justify-between text-xs text-slate-500">' +
        '<span>Unspent: <span class="font-bold text-slate-700">' + fmtCr(unspent) + '</span></span>' +
        '<span>' + fmtPct(allocated > 0 ? (unspent / allocated * 100) : 0) + ' remaining</span></div>';
      flowEl.innerHTML = fhtml;
    }

    // Expenditure stacked bar
    var expEl = document.getElementById('finExpStackedBar');
    if (expEl) {
      var expPct = allocated > 0 ? (exp / allocated * 100) : 0;
      var unspentPct = 100 - expPct;
      var ehtml = '<div class="space-y-2">' +
        '<div class="flex justify-between text-xs"><span class="font-semibold text-slate-700">Expenditure</span><span class="font-bold text-slate-900">' + fmtCr(exp) + ' (' + fmtPct(expPct) + ')</span></div>' +
        '<div class="w-full h-6 bg-slate-100 rounded-full overflow-hidden flex">' +
        '<div class="h-full bg-blue-500 rounded-l-full transition-all duration-1000" style="width:' + expPct + '%"></div>' +
        '<div class="h-full bg-slate-300 rounded-r-full transition-all duration-1000" style="width:' + unspentPct + '%"></div></div>' +
        '<div class="flex justify-between text-[10px] text-slate-400"><span>Utilized</span><span>Unspent</span></div></div>';
      ehtml += '<div class="pt-3 border-t border-slate-100 space-y-2 text-xs">' +
        '<div class="flex justify-between"><span class="text-slate-500">Completion Amount</span><span class="font-semibold text-slate-900">' + fmtCr(completionAmt) + '</span></div>' +
        '<div class="flex justify-between"><span class="text-slate-500">Unspent Balance</span><span class="font-semibold text-slate-900">' + fmtCr(unspent) + '</span></div></div>';
      expEl.innerHTML = ehtml;
    }

    // Financial ratio bars
    var ratioEl = document.getElementById('finRatioBars');
    if (ratioEl) {
      var ratios = [
        { label: 'Fund Utilization', value: util, color: getColor(util) },
        { label: 'Completion Rate', value: comp, color: getColor(comp) },
        { label: 'Sanction Rate', value: sanctionRate, color: getColor(sanctionRate) },
      ];
      var rhtml = '';
      ratios.forEach(function(r) {
        rhtml += '<div class="space-y-1">' +
          '<div class="flex justify-between text-xs"><span class="font-medium text-slate-600">' + r.label + '</span><span class="font-bold text-slate-900">' + fmtPct(r.value) + '</span></div>' +
          '<div class="w-full h-3 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + r.color + '-500 rounded-full transition-all duration-1000" style="width:' + Math.min(r.value, 100) + '%"></div></div></div>';
      });
      rhtml += '<div class="pt-3 border-t border-slate-100 space-y-2 text-xs">' +
        '<div class="flex justify-between"><span class="text-slate-500">Avg Work Cost</span><span class="font-semibold text-slate-900">' + fmtCr(s.avg_work_cost) + '</span></div>' +
        '<div class="flex justify-between"><span class="text-slate-500">Median Work Cost</span><span class="font-semibold text-slate-900">' + fmtCr(s.median_work_cost) + '</span></div></div>';
      ratioEl.innerHTML = rhtml;
    }

    // Timeline metrics
    var timeEl = document.getElementById('finTimelineMetrics');
    if (timeEl) {
      var avgExec = Number(s.avg_execution_days) || 0;
      var medExec = Number(s.median_execution_days) || 0;
      var avgDelay = Number(s.avg_sanction_delay_days) || 0;
      var medDelay = Number(s.median_sanction_delay_days) || 0;
      var avgAge = Number(s.avg_project_age_days) || 0;
      var maxAge = Number(s.max_project_age_days) || 0;
      var overdue1 = s.overdue_over_1_year || 0;
      var overdue2 = s.overdue_over_2_years || 0;
      var titems = [
        { label: 'Avg Execution Time', value: fmtDays(avgExec), sub: 'Median: ' + fmtDays(medExec), color: 'blue' },
        { label: 'Avg Sanction Delay', value: fmtDays(avgDelay), sub: 'Median: ' + fmtDays(medDelay), color: 'amber' },
        { label: 'Avg Project Age', value: fmtDays(avgAge), sub: 'Max: ' + fmtDays(maxAge), color: 'violet' },
        { label: 'Overdue Works', value: fmtNum(overdue1) + ' / ' + fmtNum(overdue2), sub: '> 1yr / > 2yr', color: overdue1 > 0 ? 'rose' : 'emerald' },
      ];
      var thtml = '';
      titems.forEach(function(item) {
        thtml += '<div class="p-4 bg-slate-50/70 border border-slate-200 rounded-xl">' +
          '<div class="flex items-center gap-2 mb-2"><span class="w-2 h-2 rounded-full bg-' + item.color + '-500"></span>' +
          '<span class="text-[10px] font-bold uppercase tracking-wider text-slate-500">' + item.label + '</span></div>' +
          '<div class="text-xl font-bold text-slate-900">' + item.value + '</div>' +
          '<div class="text-[11px] text-slate-500 mt-0.5">' + item.sub + '</div></div>';
      });
      timeEl.innerHTML = thtml;
    }

    // Detailed financial table
    var tableBody = document.getElementById('finTableBody');
    if (tableBody) {
      var benchmarks = stateData.__benchmarks || {};
      var rows = [
        { label: 'Allocated Amount', value: fmtCr(allocated), median: fmtCr(benchmarks.allocated_amount || null), delta: benchmarks.allocated_amount != null ? allocated - benchmarks.allocated_amount : null, isMoney: true },
        { label: 'Sanctioned Amount', value: fmtCr(sanctioned), median: fmtCr(benchmarks.sanctioned_amount || null), delta: benchmarks.sanctioned_amount != null ? sanctioned - benchmarks.sanctioned_amount : null, isMoney: true },
        { label: 'Expenditure Amount', value: fmtCr(exp), median: fmtCr(benchmarks.expenditure_amount || null), delta: benchmarks.expenditure_amount != null ? exp - benchmarks.expenditure_amount : null, isMoney: true },
        { label: 'Fund Utilization', value: fmtPct(util), median: fmtPct(benchmarks.fund_utilization_pct || null), delta: benchmarks.fund_utilization_pct != null ? util - benchmarks.fund_utilization_pct : null, isMoney: false },
        { label: 'Completion Rate', value: fmtPct(comp), median: fmtPct(benchmarks.completion_rate_pct || null), delta: benchmarks.completion_rate_pct != null ? comp - benchmarks.completion_rate_pct : null, isMoney: false },
        { label: 'Sanction Rate', value: fmtPct(sanctionRate), median: fmtPct(benchmarks.sanction_rate_pct || null), delta: benchmarks.sanction_rate_pct != null ? sanctionRate - benchmarks.sanction_rate_pct : null, isMoney: false },
      ];
      var dhtml = '';
      rows.forEach(function(row) {
        var dc = row.delta != null ? (row.delta >= 0 ? 'emerald' : 'rose') : 'slate';
        var sign = row.delta != null ? (row.delta >= 0 ? '+' : '') : '';
        var deltaFmt = row.delta != null ? (row.isMoney ? fmtCr(Math.abs(row.delta)) : fmtPct(Math.abs(row.delta))) : '—';
        dhtml += '<tr class="border-b border-slate-100 hover:bg-slate-50">' +
          '<td class="py-2.5 px-3 font-medium text-slate-700">' + row.label + '</td>' +
          '<td class="py-2.5 px-3 text-right font-bold text-slate-900">' + row.value + '</td>' +
          '<td class="py-2.5 px-3 text-right text-slate-500">' + row.median + '</td>' +
          '<td class="py-2.5 px-3 text-right font-semibold text-' + dc + '-700">' + (row.delta != null ? sign + deltaFmt : '—') + '</td></tr>';
      });
      tableBody.innerHTML = dhtml;
    }
  }

  // ===== RISK =====
  function populateRisk(s) {
    var total = Number(s.total_works) || 0;
    var high = Number(s.high_risk_works) || 0;
    var flagged = Number(s.flagged_works) || 0;
    var medium = Math.max(flagged - high, 0);
    var low = Math.max(total - high - medium, 0);
    setText('riskLow', fmtNum(low) + ' Works');
    setText('riskMedium', fmtNum(medium) + ' Works');
    setText('riskHigh', fmtNum(high) + ' Works');
    setText('riskScoreBadge', 'Risk Score: ' + (s.anomaly_level || 'N/A') + ' (' + fmtPct(s.risk_rate_pct) + ' Anomaly Rate)');

    // Risk tab timeline metrics
    var tEl = document.getElementById('stateTimelineMetrics');
    if (tEl) {
      var avgExec = Number(s.avg_execution_days) || 0;
      var medExec = Number(s.median_execution_days) || 0;
      var avgDelay = Number(s.avg_sanction_delay_days) || 0;
      var medDelay = Number(s.median_sanction_delay_days) || 0;
      var avgAge = Number(s.avg_project_age_days) || 0;
      var maxAge = Number(s.max_project_age_days) || 0;
      var overdue1 = s.overdue_over_1_year || 0;
      var overdue2 = s.overdue_over_2_years || 0;
      var items = [
        { label: 'Avg Execution Time', value: fmtDays(avgExec), sub: 'Median: ' + fmtDays(medExec), color: 'blue' },
        { label: 'Avg Sanction Delay', value: fmtDays(avgDelay), sub: 'Median: ' + fmtDays(medDelay), color: 'amber' },
        { label: 'Avg Project Age', value: fmtDays(avgAge), sub: 'Max: ' + fmtDays(maxAge), color: 'violet' },
        { label: 'Overdue Works', value: fmtNum(overdue1) + ' / ' + fmtNum(overdue2), sub: '> 1yr / > 2yr', color: overdue1 > 0 ? 'rose' : 'emerald' },
      ];
      var thtml = '';
      items.forEach(function(item) {
        thtml += '<div class="p-4 bg-slate-50/70 border border-slate-200 rounded-xl">' +
          '<div class="flex items-center gap-2 mb-2"><span class="w-2 h-2 rounded-full bg-' + item.color + '-500"></span>' +
          '<span class="text-[10px] font-bold uppercase tracking-wider text-slate-500">' + item.label + '</span></div>' +
          '<div class="text-xl font-bold text-slate-900">' + item.value + '</div>' +
          '<div class="text-[11px] text-slate-500 mt-0.5">' + item.sub + '</div></div>';
      });
      tEl.innerHTML = thtml;
    }

    // Risk Distribution (Performance & Risk tab)
    var riskDistEl = document.getElementById('perfRiskDistribution');
    if (riskDistEl) {
      var risks = [
        { label: 'High Risk', count: high, color: 'rose' },
        { label: 'Medium Risk', count: medium, color: 'amber' },
        { label: 'Low Risk', count: low, color: 'emerald' },
      ];
      var rhtml = '';
      risks.forEach(function(r) {
        var pct = total > 0 ? (r.count / total * 100) : 0;
        rhtml += '<div class="p-3 bg-slate-50/70 border border-slate-200 rounded-lg text-center">' +
          '<div class="text-xl font-black text-' + r.color + '-600">' + fmtNum(r.count) + '</div>' +
          '<div class="text-[10px] font-bold text-' + r.color + '-700 uppercase tracking-wider mt-0.5">' + r.label + '</div>' +
          '<div class="text-[11px] text-slate-500">' + fmtPct(pct) + '</div>' +
          '<div class="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden mt-1.5"><div class="h-full bg-' + r.color + '-500 rounded-full" style="width:' + Math.min(pct, 100) + '%"></div></div></div>';
      });
      rhtml += '<div class="col-span-full pt-2 border-t border-slate-100 flex justify-between text-xs text-slate-500">' +
        '<span>Anomaly level: <span class="font-bold text-slate-700">' + (s.anomaly_level || 'N/A') + '</span></span>' +
        '<span>Risk rate: <span class="font-bold">' + fmtPct(s.risk_rate_pct) + '</span></span></div>';
      riskDistEl.innerHTML = rhtml;
    }

    // Work Status (Performance & Risk tab)
    var workStEl = document.getElementById('perfWorkStatusCounts');
    if (workStEl) {
      var statuses = [
        { label: 'Completed', count: Number(s.completed_works) || 0, color: 'emerald' },
        { label: 'In Progress', count: Number(s.ongoing_works) || 0, color: 'blue' },
        { label: 'Recommended', count: Number(s.pending_works) || 0, color: 'violet' },
      ];
      var whtml = '';
      statuses.forEach(function(st) {
        var pct = total > 0 ? (st.count / total * 100) : 0;
        whtml += '<div class="p-3 bg-slate-50/70 border border-slate-200 rounded-lg text-center">' +
          '<div class="text-xl font-black text-' + st.color + '-600">' + fmtNum(st.count) + '</div>' +
          '<div class="text-[10px] font-bold text-' + st.color + '-700 uppercase tracking-wider mt-0.5">' + st.label + '</div>' +
          '<div class="text-[11px] text-slate-500">' + fmtPct(pct) + '</div>' +
          '<div class="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden mt-1.5"><div class="h-full bg-' + st.color + '-500 rounded-full" style="width:' + Math.min(pct, 100) + '%"></div></div></div>';
      });
      workStEl.innerHTML = whtml;
    }
  }

  // ===== SCATTER FOCAL NODE =====
  function populateScatterFocal(s) {
    var g = document.getElementById('scatterFocalNode');
    if (!g) return;
    var util = Number(s.fund_utilization_pct) || 0;
    var comp = Number(s.completion_rate_pct) || 0;
    var x = 60 + util * 7;
    var y = 330 - comp * 3;
    if (x < 70) x = 70; if (x > 750) x = 750;
    if (y < 40) y = 40; if (y > 325) y = 325;
    var label = (s.state_name || 'STATE').toUpperCase();
    var w = Math.max(88, label.length * 7 + 22);
    g.setAttribute('data-state', s.state_name || '');
    g.setAttribute('data-rank', '#' + (s.rank || ''));
    g.setAttribute('data-util', fmtPct(util));
    g.setAttribute('data-comp', fmtPct(comp));
    g.setAttribute('data-works', fmtNum(s.total_works || 0) + ' Works');
    g.setAttribute('data-class', s.performance_classification || '');
    g.innerHTML =
      '<circle cx="' + x + '" cy="' + y + '" fill="url(#meghalayaGlow)" opacity="0.6" r="16">' +
      '<animate attributeName="r" dur="2.5s" repeatCount="indefinite" values="8;20;8"></animate>' +
      '<animate attributeName="opacity" dur="2.5s" repeatCount="indefinite" values="0.7;0.1;0.7"></animate>' +
      '</circle>' +
      '<circle class="shadow-lg" cx="' + x + '" cy="' + y + '" fill="#10b981" r="9" stroke="#ffffff" stroke-width="2.5"></circle>' +
      '<circle cx="' + x + '" cy="' + y + '" fill="#ffffff" r="4"></circle>' +
      '<rect fill="#0f172a" height="20" opacity="0.9" rx="4" width="' + w + '" x="' + (x - w / 2) + '" y="' + (y + 15) + '"></rect>' +
      '<text fill="#34d399" font-size="10" font-weight="800" letter-spacing="0.5" text-anchor="middle" x="' + x + '" y="' + (y + 29) + '">\u2605 ' + label + '</text>';

    // Build mobile scatter summary from SVG data points
    var el = document.getElementById('scatterQuadrantCards');
    if (el) {
      var quadrants = { leaders: [], efficient: [], lagging: [], highSpend: [] };
      var nodes = document.querySelectorAll('.scatter-node[data-state]');
      nodes.forEach(function(node) {
        var state = node.getAttribute('data-state');
        if (!state || state === 'National Average') return;
        var utilStr = node.getAttribute('data-util') || '0';
        var compStr = node.getAttribute('data-comp') || '0';
        var util = parseFloat(utilStr) || 0;
        var comp = parseFloat(compStr) || 0;
        if (comp >= 50 && util >= 50) quadrants.leaders.push(state);
        else if (comp >= 50 && util < 50) quadrants.efficient.push(state);
        else if (comp < 50 && util < 50) quadrants.lagging.push(state);
        else quadrants.highSpend.push(state);
      });
      var cards = [
        { label: 'High Delivery / High Spend', count: quadrants.leaders.length, color: 'emerald', items: quadrants.leaders },
        { label: 'High Delivery / Low Spend', count: quadrants.efficient.length, color: 'blue', items: quadrants.efficient },
        { label: 'Low Delivery / Low Spend', count: quadrants.lagging.length, color: 'amber', items: quadrants.lagging },
        { label: 'Low Delivery / High Spend', count: quadrants.highSpend.length, color: 'rose', items: quadrants.highSpend },
      ];
      var h = '';
      cards.forEach(function(c) {
        h += '<div class="p-3 bg-white border border-slate-200 rounded-lg">' +
          '<div class="flex items-center justify-between mb-1">' +
          '<span class="text-[10px] font-bold uppercase tracking-wider text-' + c.color + '-700">' + c.label + '</span>' +
          '<span class="text-lg font-black text-' + c.color + '-600">' + c.count + '</span></div>' +
          '<div class="text-[10px] text-slate-500">' + (c.items.length > 0 ? c.items.join(', ') : 'None') + '</div></div>';
      });
      el.innerHTML = h;
    }
  }

  // ===== RESOLVE STATE ID =====
  function applyBackLink() {
    var link = document.getElementById('backLink');
    var text = document.getElementById('backLinkText');
    if (!link) return;
    var params = new URLSearchParams(window.location.search);
    var from = params.get('from');
    var ref = document.referrer || '';
    var cameFromDashboard = ref.indexOf('dashboard.html') !== -1 || from === 'dashboard';
    var cameFromRisk = ref.indexOf('airiskcentre.html') !== -1 || from === 'airiskcentre';
    if (cameFromDashboard) {
      link.setAttribute('href', 'dashboard.html');
      if (text) text.textContent = 'Back to Home';
    } else if (cameFromRisk) {
      link.setAttribute('href', 'airiskcentre.html');
      if (text) text.textContent = 'Back to AI Risk Centre';
    } else {
      link.setAttribute('href', 'state.html');
      if (text) text.textContent = 'Back to all States & UTs';
    }
  }
  function resolveStateId(param) {
    var asNum = parseInt(param, 10);
    if (!isNaN(asNum) && String(asNum) === String(param)) {
      return Promise.resolve(asNum);
    }
    return fetch(API_BASE + '/api/state-performance')
      .then(function (r) { return r.json(); })
      .then(function (list) {
        var target = param.toLowerCase();
        var match = list.find(function (x) { return (x.state_name || '').toLowerCase() === target; });
        if (match) return match.state_id;
        var partial = list.find(function (x) { return (x.state_name || '').toLowerCase().indexOf(target) !== -1; });
        return partial ? partial.state_id : null;
      });
  }

  function processData(data) {
    stateData = data.state || {};
    stateData.__members = data.members || [];
    stateData.__benchmarks = data.benchmarks || {};
    populateHeader(stateData);
    populateKPIs(stateData);
    populateOverview(stateData, data.benchmarks || {});
    populateScatterFocal(stateData);
    populateRepresentatives(data.members || []);
    populateFinancial(stateData);
    populateRisk(stateData);
    populateRiskDistribution(stateData);
    populateWorkStatus(stateData);
    populateAI(stateData, data.analysis || {});
    loadWorks(currentCategory, 1);
  }


  document.addEventListener('DOMContentLoaded', function () {
    var param = getStateParam();
    if (!param) {
      showShell('error', 'No state selected', 'Please navigate from the States page.');
      return;
    }

    applyBackLink();
    setupCategoryTabs();
    showShell('loading');

    var aiTabBtn = document.getElementById('tab-btn-ai');
    if (aiTabBtn) aiTabBtn.addEventListener('click', function () { setTimeout(animateStateAiRing, 60); });

    var resolvePromise;
    if (/^\d+$/.test(String(param))) {
      stateId = parseInt(param, 10);
      resolvePromise = Promise.resolve(stateId);
    } else {
      resolvePromise = resolveStateId(param).then(function (id) {
        if (id) stateId = id;
        return id;
      });
    }

    resolvePromise.then(function (id) {
      if (!id) {
        showShell('error', 'State not found', 'We could not resolve that state. Please try again.');
        return;
      }

      // Kick off works request in parallel with the detail request
      loadWorks(currentCategory, 1);

      var cached = getCache(id);
      if (cached) {
        processData(cached);
        showShell('main');
        // Refresh in background
        fetch(API_BASE + '/api/states/detail/' + id)
          .then(function (r) { if (!r.ok) return null; return r.json(); })
          .then(function (data) { if (data) { setCache(id, data); processData(data); } })
          .catch(function () {});
        return;
      }

      fetch(API_BASE + '/api/states/detail/' + id)
        .then(function (r) { if (!r.ok) throw new Error('state'); return r.json(); })
        .then(function (data) { setCache(id, data); processData(data); showShell('main'); })
        .catch(function () {
          showShell('error', 'Failed to load state data', 'Please try again in a moment.');
        });
    });
  });
})();

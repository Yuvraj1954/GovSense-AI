(function () {
  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  var CACHE_KEY = 'stateDataCache';
  var CACHE_TTL_MS = 24 * 60 * 60 * 1000;
  var allStates = [];
  var filteredStates = [];
  var currentPage = 1;
  var pageSize = 6;
  var searchQuery = '';
  var filterClassification = '';
  var filterUtilization = '';
  var sortBy = 'util';

  function getCached() {
    try {
      var raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      var cached = JSON.parse(raw);
      if (Date.now() - cached.ts > CACHE_TTL_MS) { localStorage.removeItem(CACHE_KEY); return null; }
      return cached.data;
    } catch (e) { return null; }
  }

  function setCache(data) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify({ data: data, ts: Date.now() })); } catch (e) {}
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

  // ========== KPI CARDS ==========
  function populateKPIs(data) {
    var totalStates = data.length;
    setText('headerMeta', fmtNum(totalStates) + ' States');
    var totalAllocated = 0, totalExpenditure = 0, totalWorks = 0, completedWorks = 0, ongoingWorks = 0, pendingWorks = 0;
    data.forEach(function(s) {
      totalAllocated += Number(s.sanctioned_amount) || Number(s.recommended_amount) || 0;
      totalExpenditure += Number(s.expenditure_amount) || 0;
      totalWorks += Number(s.total_works) || 0;
      completedWorks += Number(s.completed_works) || 0;
      ongoingWorks += (Number(s.total_works) || 0) - (Number(s.completed_works) || 0);
    });
    var util = totalAllocated > 0 ? (totalExpenditure / totalAllocated * 100) : 0;
    var compRate = totalWorks > 0 ? (completedWorks / totalWorks * 100) : 0;
    pendingWorks = totalWorks - completedWorks;

    var kpis = [
      { id: 'kpiTotalStates', value: fmtNum(totalStates), sub: 'States and union territories' },
      { id: 'kpiTotalAllocated', value: fmtCr(totalAllocated), sub: 'Cumulative fund outlay' },
      { id: 'kpiTotalExpenditure', value: fmtCr(totalExpenditure), sub: 'Disbursed expenditure' },
      { id: 'kpiFundUtilization', value: fmtPct(util), sub: 'Share of allocated funds disbursed' },
      { id: 'kpiTotalWorks', value: fmtNum(totalWorks), sub: 'All registered works' },
      { id: 'kpiCompletedWorks', value: fmtNum(completedWorks), sub: fmtPct(compRate) + ' completion rate' },
      { id: 'kpiOngoingWorks', value: fmtNum(ongoingWorks), sub: 'Currently active' },
      { id: 'kpiPendingWorks', value: fmtNum(pendingWorks), sub: 'Awaiting completion' },
    ];
    kpis.forEach(function(k) { setText(k.id, k.value); });
  }

  // ========== DISTRIBUTION CHARTS ==========
  function populateDistributions(data) {
    var clsCounts = { EXCEPTIONAL: 0, PERFORMER: 0, STABLE: 0, AVERAGE: 0, NEEDS_ATTENTION: 0, UNDERPERFORMER: 0, NO_DATA: 0, INSUFFICIENT_DATA: 0 };
    var utilBuckets = { high: 0, moderate: 0, low: 0, critical: 0 };

    data.forEach(function(s) {
      var cls = s.performance_classification || 'NO_DATA';
      clsCounts[cls] = (clsCounts[cls] || 0) + 1;
      var util = Number(s.fund_utilization_pct) || Number(s.expenditure_sanction_utilization_pct) || 0;
      if (util >= 70) utilBuckets.high++;
      else if (util >= 50) utilBuckets.moderate++;
      else if (util >= 30) utilBuckets.low++;
      else utilBuckets.critical++;
    });

    // Classification bars
    var clsItems = [
      { key: 'EXCEPTIONAL', label: 'Exceptional', color: 'emerald' },
      { key: 'PERFORMER', label: 'Performer', color: 'emerald' },
      { key: 'STABLE', label: 'Stable', color: 'blue' },
      { key: 'AVERAGE', label: 'Average', color: 'blue' },
      { key: 'NEEDS_ATTENTION', label: 'Needs Attention', color: 'amber' },
      { key: 'UNDERPERFORMER', label: 'Underperformer', color: 'rose' },
    ];
    var total = data.length || 1;
    var clsHtml = '';
    clsItems.forEach(function(item) {
      var count = clsCounts[item.key] || 0;
      var pct = (count / total * 100);
      clsHtml += '<div class="space-y-1">' +
        '<div class="flex justify-between text-xs"><div class="flex items-center gap-2">' +
        '<span class="w-2.5 h-2.5 rounded-xs bg-' + item.color + '-500"></span>' +
        '<span class="font-medium text-slate-700">' + item.label + '</span></div>' +
        '<div class="flex items-center gap-2"><span class="font-semibold text-slate-900">' + count + '</span>' +
        '<span class="text-slate-400">' + fmtPct(pct) + '</span></div></div>' +
        '<div class="w-full h-2 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + item.color + '-500 rounded-full" style="width:' + pct + '%"></div></div></div>';
    });
    setHTML('clsDistBars', clsHtml);

    // Utilization buckets
    var utilItems = [
      { key: 'high', label: '≥70% High', color: 'emerald' },
      { key: 'moderate', label: '50–69% Moderate', color: 'sky' },
      { key: 'low', label: '30–49% Needs Attention', color: 'amber' },
      { key: 'critical', label: '<30% Critical', color: 'rose' },
    ];
    var utilHtml = '';
    utilItems.forEach(function(item) {
      var count = utilBuckets[item.key] || 0;
      var pct = (count / total * 100);
      utilHtml += '<div class="space-y-1">' +
        '<div class="flex justify-between text-xs"><div class="flex items-center gap-2">' +
        '<span class="w-2.5 h-2.5 rounded-xs bg-' + item.color + '-500"></span>' +
        '<span class="font-medium text-slate-700">' + item.label + '</span></div>' +
        '<div class="flex items-center gap-2"><span class="font-semibold text-slate-900">' + count + '</span>' +
        '<span class="text-slate-400">' + fmtPct(pct) + '</span></div></div>' +
        '<div class="w-full h-2 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + item.color + '-500 rounded-full" style="width:' + pct + '%"></div></div></div>';
    });
    setHTML('utilDistBars', utilHtml);
  }

  // ========== SCATTER PLOT ==========
  function populateScatter(data) {
    var container = document.getElementById('scatterPoints');
    if (!container) return;
    var svg = '';
    data.forEach(function(s, i) {
      var util = Number(s.fund_utilization_pct) || Number(s.expenditure_sanction_utilization_pct) || 0;
      var comp = Number(s.completion_rate_pct) || 0;
      var cls = s.performance_classification || '';
      var color = cls === 'EXCEPTIONAL' ? '#10b981' : cls === 'PERFORMER' ? '#10b981' : cls === 'STABLE' ? '#3b82f6' : cls === 'AVERAGE' ? '#3b82f6' : cls === 'NEEDS_ATTENTION' ? '#f59e0b' : cls === 'UNDERPERFORMER' ? '#ef4444' : '#94a3b8';
      var cx = 60 + (util / 100) * 900;
      var cy = 330 - (comp / 100) * 300;
      svg += '<circle cx="' + cx + '" cy="' + cy + '" r="6" fill="' + color + '" opacity="0.8" class="scatter-dot scatter-point" ' +
        'data-state="' + (s.state_name || '') + '" data-util="' + fmtPct(util) + '" data-comp="' + fmtPct(comp) + '" data-works="' + fmtNum(s.total_works || 0) + '" data-cls="' + cls.replace(/_/g, ' ') + '"></circle>';
    });
    container.innerHTML = svg;
    if (window.ChartAnim) {
      window.ChartAnim.whenVisible(container, 'stateScatter', function () {
        window.ChartAnim.popIn(container.querySelectorAll('circle'), { fade: false, stagger: 25, duration: 500 });
      });
    }
    buildScatterMobileSummary(data);
  }

  function buildScatterMobileSummary(data) {
    var el = document.getElementById('scatterQuadrantCards');
    if (!el) return;
    var quadrants = { leaders: [], efficient: [], lagging: [], highSpend: [] };
    data.forEach(function(s) {
      var util = Number(s.fund_utilization_pct) || 0;
      var comp = Number(s.completion_rate_pct) || 0;
      var name = s.state_name || 'Unknown';
      if (comp >= 50 && util >= 50) quadrants.leaders.push(name);
      else if (comp >= 50 && util < 50) quadrants.efficient.push(name);
      else if (comp < 50 && util < 50) quadrants.lagging.push(name);
      else quadrants.highSpend.push(name);
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
        '<div class="text-[10px] text-slate-500">' + (c.items.length > 0 ? c.items.slice(0, 3).join(', ') + (c.items.length > 3 ? ' +' + (c.items.length - 3) : '') : 'None') + '</div></div>';
    });
    el.innerHTML = h;
  }

  // ========== RANKING ==========
  function renderRanking(metric) {
    var container = document.getElementById('rankingBarsList');
    if (!container) return;
    var sorted = allStates.slice().sort(function(a, b) {
      if (metric === 'utilization') return (Number(b.fund_utilization_pct) || Number(b.expenditure_sanction_utilization_pct) || 0) - (Number(a.fund_utilization_pct) || Number(a.expenditure_sanction_utilization_pct) || 0);
      if (metric === 'completion') return (Number(b.completion_rate_pct) || 0) - (Number(a.completion_rate_pct) || 0);
      if (metric === 'expenditure') return (Number(b.expenditure_amount) || 0) - (Number(a.expenditure_amount) || 0);
      if (metric === 'works') return (Number(b.total_works) || 0) - (Number(a.total_works) || 0);
      return 0;
    }).slice(0, 10);

    var maxVal = 0;
    sorted.forEach(function(s) {
      var v = 0;
      if (metric === 'utilization') v = Number(s.fund_utilization_pct) || Number(s.expenditure_sanction_utilization_pct) || 0;
      else if (metric === 'completion') v = Number(s.completion_rate_pct) || 0;
      else if (metric === 'expenditure') v = Number(s.expenditure_amount) || 0;
      else if (metric === 'works') v = Number(s.total_works) || 0;
      if (v > maxVal) maxVal = v;
    });
    if (maxVal === 0) maxVal = 1;

    var html = '';
    sorted.forEach(function(s, i) {
      var val = 0, displayVal = '', sub = '';
      if (metric === 'utilization') {
        val = Number(s.fund_utilization_pct) || Number(s.expenditure_sanction_utilization_pct) || 0;
        displayVal = fmtPct(val);
        sub = fmtCr(s.expenditure_amount);
      } else if (metric === 'completion') {
        val = Number(s.completion_rate_pct) || 0;
        displayVal = fmtPct(val);
        sub = fmtNum(s.completed_works) + ' Done';
      } else if (metric === 'expenditure') {
        val = Number(s.expenditure_amount) || 0;
        displayVal = fmtCr(val);
        sub = fmtPct(s.fund_utilization_pct) + ' Util';
      } else if (metric === 'works') {
        val = Number(s.total_works) || 0;
        displayVal = fmtNum(val);
        sub = fmtNum(s.completed_works) + ' Done';
      }
      var widthPct = (val / maxVal * 100);
      var color = (metric === 'expenditure' || metric === 'works') ? 'blue' : getColor(val);
      html += '<div class="flex items-center gap-3 text-xs">' +
        '<span class="w-6 font-mono font-bold text-slate-400 text-right">#' + (i + 1) + '</span>' +
        '<span class="w-32 font-semibold text-slate-800 truncate">' + (s.state_name || '') + '</span>' +
        '<div class="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden"><div class="rank-bar h-full bg-' + color + '-500 rounded-full transition-all duration-700" style="width:' + widthPct + '%"></div></div>' +
        '<span class="w-24 text-right font-bold text-slate-900 rank-val">' + displayVal + '</span>' +
        '<span class="w-24 text-right text-[11px] text-slate-400 rank-sub">' + sub + '</span></div>';
    });
    container.innerHTML = html;
  }

  function setupRankingTabs() {
    document.querySelectorAll('.rank-tab-btn').forEach(function(tab) {
      tab.addEventListener('click', function() {
        document.querySelectorAll('.rank-tab-btn').forEach(function(t) {
          t.classList.remove('active', 'bg-white', 'text-slate-900', 'shadow-2xs', 'font-semibold');
          t.classList.add('text-slate-600');
        });
        tab.classList.add('active', 'bg-white', 'text-slate-900', 'shadow-2xs', 'font-semibold');
        tab.classList.remove('text-slate-600');
        renderRanking(tab.getAttribute('data-metric'));
      });
    });
  }

  // ========== FILTERING & SORTING ==========
  function applyFilters() {
    filteredStates = allStates.filter(function(s) {
      // Search
      if (searchQuery) {
        var name = (s.state_name || '').toLowerCase();
        if (name.indexOf(searchQuery) === -1) return false;
      }
      // Classification filter
      if (filterClassification) {
        var cls = (s.performance_classification || '').toLowerCase();
        if (cls !== filterClassification) return false;
      }
      // Utilization filter
      if (filterUtilization) {
        var util = Number(s.fund_utilization_pct) || Number(s.expenditure_sanction_utilization_pct) || 0;
        if (filterUtilization === 'high' && util < 70) return false;
        if (filterUtilization === 'moderate' && (util < 50 || util >= 70)) return false;
        if (filterUtilization === 'low' && (util < 30 || util >= 50)) return false;
        if (filterUtilization === 'critical' && util >= 30) return false;
      }
      return true;
    });

    // Sort
    filteredStates.sort(function(a, b) {
      if (sortBy === 'util') return (Number(b.fund_utilization_pct) || 0) - (Number(a.fund_utilization_pct) || 0);
      if (sortBy === 'comp') return (Number(b.completion_rate_pct) || 0) - (Number(a.completion_rate_pct) || 0);
      if (sortBy === 'exp') return (Number(b.expenditure_amount) || 0) - (Number(a.expenditure_amount) || 0);
      if (sortBy === 'works') return (Number(b.total_works) || 0) - (Number(a.total_works) || 0);
      return (Number(a.state_id) || 0) - (Number(b.state_id) || 0);
    });

    currentPage = 1;
    // Update KPI tiles based on filtered selection
    populateKPIs(filteredStates);
    renderStateCards();
    updateResultCount();
  }

  function updateResultCount() {
    var el = document.getElementById('resultCount');
    if (el) el.textContent = filteredStates.length + ' States & UTs found';
  }

  // ========== SCATTER TOOLTIP ==========
  function setupScatterTooltip() {
    var svg = document.getElementById('scatterPoints');
    var tooltip = document.getElementById('scatterTooltip');
    if (!svg || !tooltip) return;

    svg.addEventListener('mousemove', function(e) {
      var point = e.target.closest('.scatter-point');
      if (!point) { tooltip.classList.add('opacity-0'); return; }
      var state = point.getAttribute('data-state');
      var util = point.getAttribute('data-util');
      var comp = point.getAttribute('data-comp');
      var works = point.getAttribute('data-works');
      var cls = point.getAttribute('data-cls');
      tooltip.innerHTML =
        '<div class="font-bold text-white text-xs">' + state + '</div>' +
        '<div class="text-[11px] text-slate-300 mt-0.5">Total Works: <strong>' + works + '</strong></div>' +
        '<div class="mt-1 pt-1 border-t border-slate-700/80 flex items-center gap-3 text-[10px]">' +
        '<span>Util: <strong class="text-emerald-400 font-bold">' + util + '</strong></span>' +
        '<span>Comp: <strong class="text-blue-400 font-bold">' + comp + '</strong></span></div>' +
        '<div class="text-[10px] font-semibold text-blue-300 mt-0.5">' + (cls || '') + '</div>';
      var rect = point.getBoundingClientRect();
      var parentRect = point.closest('.relative').getBoundingClientRect();
      tooltip.style.left = (rect.left - parentRect.left + rect.width / 2) + 'px';
      tooltip.style.top = (rect.top - parentRect.top - 6) + 'px';
      tooltip.classList.remove('opacity-0');
    });

    svg.addEventListener('mouseleave', function() {
      tooltip.classList.add('opacity-0');
    });
  }

  // ========== STATE CARDS ==========
  function renderStateCards() {
    var grid = document.getElementById('stateCardsGrid');
    if (!grid) return;
    var total = filteredStates.length;
    var totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage > totalPages) currentPage = totalPages;
    var start = (currentPage - 1) * pageSize;
    var end = Math.min(start + pageSize, total);
    var pageStates = filteredStates.slice(start, end);

    if (total === 0) {
      grid.innerHTML = '<div class="col-span-full text-center py-8 text-slate-400 text-sm">No states match your filters.</div>';
      setText('showingText', 'No states');
      setHTML('paginationBtns', '');
      return;
    }

    var html = '';
    pageStates.forEach(function(s, i) {
      var util = Number(s.fund_utilization_pct) || Number(s.expenditure_sanction_utilization_pct) || 0;
      var comp = Number(s.completion_rate_pct) || 0;
      var cls = s.performance_label || s.performance_classification || 'N/A';
      var cc = getClsColor(cls);
      var uc = getColor(util);
      var totalWorks = s.total_works || 0;
      var completed = s.completed_works || 0;
      var allocated = Number(s.sanctioned_amount) || Number(s.recommended_amount) || 0;
      var exp = Number(s.expenditure_amount) || 0;
      var rank = start + i + 1;
      var stateCode = (s.state_name || '').substring(0, 2).toUpperCase();

      html += '<a class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs hover:shadow-md hover:border-blue-400 transition-all duration-200 flex flex-col justify-between block cursor-pointer group" href="statedetail.html?state_id=' + encodeURIComponent(s.state_id) + '&state=' + encodeURIComponent(s.state_name) + '">' +
        '<div><div class="flex items-start justify-between gap-2">' +
        '<div class="flex items-center gap-3">' +
        '<div class="w-10 h-10 rounded-full bg-blue-50 border border-blue-200 flex items-center justify-center text-blue-700 font-bold text-sm flex-shrink-0">' + stateCode + '</div>' +
        '<div><h3 class="text-sm font-bold text-slate-900 leading-snug group-hover:text-blue-600 transition-colors">' + (s.state_name || 'Unknown') + '</h3>' +
        '<div class="flex items-center gap-1.5 text-[11px] text-slate-500 mt-0.5"><span class="font-mono font-semibold text-slate-700">Rank #' + rank + '</span></div></div></div>' +
        '<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-' + cc + '-50 text-' + cc + '-700 border border-' + cc + '-200">' + cls.replace(/_/g, ' ') + '</span></div>' +
        '<div class="grid grid-cols-2 gap-2 mt-4 p-2.5 rounded-lg bg-slate-50/80 border border-slate-100">' +
        '<div><span class="text-[10px] font-semibold uppercase text-slate-400 tracking-wider">ALLOCATED</span>' +
        '<div class="text-sm font-bold text-slate-900 mt-0.5">' + fmtCr(allocated) + '</div></div>' +
        '<div><span class="text-[10px] font-semibold uppercase text-slate-400 tracking-wider">EXPENDITURE</span>' +
        '<div class="text-sm font-bold text-slate-900 mt-0.5">' + fmtCr(exp) + '</div></div></div>' +
        '<div class="mt-3.5"><div class="flex justify-between items-center text-xs mb-1">' +
        '<span class="text-[11px] font-semibold text-slate-600">Fund Utilization</span>' +
        '<span class="font-bold text-' + uc + '-600 text-xs">' + fmtPct(util) + '</span></div>' +
        '<div class="w-full h-2 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + uc + '-500 rounded-full" style="width:' + Math.min(util, 100) + '%"></div></div></div>' +
        '<div class="mt-3 grid grid-cols-2 gap-2 text-xs">' +
        '<div class="p-2 border border-slate-100 rounded-lg"><span class="text-[10px] text-slate-400">Total Works</span><div class="font-bold text-slate-800 text-sm mt-0.5">' + fmtNum(totalWorks) + '</div></div>' +
        '<div class="p-2 border border-slate-100 rounded-lg"><span class="text-[10px] text-slate-400">Completed</span><div class="font-bold text-slate-800 text-sm mt-0.5">' + fmtNum(completed) + '</div></div></div>' +
        '<div class="flex justify-between items-center text-[11px] text-slate-500 mt-1.5 px-0.5">' +
        '<span>Completion Rate</span><span class="font-semibold text-' + getColor(comp) + '-600">' + fmtPct(comp) + '</span></div></div>' +
        '<div class="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">' +
        '<span class="text-[11px] text-slate-400 font-mono">' + (s.state_name || '') + '</span>' +
        '<span class="text-xs font-semibold text-slate-900 group-hover:text-blue-600 flex items-center gap-1 transition-colors">' +
        '<span>View Details</span><span class="group-hover:translate-x-0.5 transition-transform">→</span></span></div></a>';
    });
    grid.innerHTML = html;

    setText('showingText', 'Showing ' + (start + 1) + ' to ' + end + ' of ' + total + ' States & UTs');
    setText('paginationInfo', 'Showing ' + (start + 1) + ' to ' + end + ' of ' + total + ' States & UTs');

    // Pagination
    var btnsHtml = '';
    btnsHtml += '<button class="page-btn px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium' + (currentPage <= 1 ? ' text-slate-400 cursor-not-allowed' : ' text-slate-700 hover:bg-slate-50') + '" data-page="' + (currentPage - 1) + '">Previous</button>';
    for (var p = 1; p <= totalPages; p++) {
      btnsHtml += p === currentPage
        ? '<button class="page-btn w-8 h-8 rounded-lg bg-blue-600 text-white font-semibold text-xs shadow-xs" data-page="' + p + '">' + p + '</button>'
        : '<button class="page-btn w-8 h-8 rounded-lg border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 font-medium text-xs" data-page="' + p + '">' + p + '</button>';
    }
    btnsHtml += '<button class="page-btn px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium' + (currentPage >= totalPages ? ' text-slate-400 cursor-not-allowed' : ' text-slate-700 hover:bg-slate-50') + '" data-page="' + (currentPage + 1) + '">Next</button>';
    setHTML('paginationBtns', btnsHtml);

    document.querySelectorAll('.page-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var page = parseInt(btn.getAttribute('data-page'));
        if (page >= 1 && page <= totalPages) { currentPage = page; renderStateCards(); }
      });
    });
  }

  // ========== SEARCH AUTOCOMPLETE ==========
  function setupSearch() {
    var input = document.getElementById('stateSearchInput');
    var dropdown = document.getElementById('autocompleteDropdown');
    var clearBtn = document.getElementById('clearSearchBtn');
    if (!input) return;

    function showMatches(query) {
      var val = (query || '').trim().toLowerCase();
      var matches = allStates.filter(function(s) { return (s.state_name || '').toLowerCase().indexOf(val) !== -1; }).slice(0, 8);
      if (matches.length === 0) { dropdown.classList.add('hidden'); return; }
      var html = '<div class="p-1"><div class="px-2 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">States & UTs</div>';
      matches.forEach(function(s) {
        var util = Number(s.fund_utilization_pct) || Number(s.expenditure_sanction_utilization_pct) || 0;
        html += '<div class="search-suggest-item flex items-center justify-between px-2.5 py-1.5 hover:bg-slate-50 rounded cursor-pointer transition" data-name="' + (s.state_name || '') + '" data-id="' + (s.state_id || '') + '">' +
          '<span class="font-medium text-slate-800">' + s.state_name + '</span>' +
          '<span class="text-[10px] text-slate-400">' + fmtPct(util) + ' utilization</span></div>';
      });
      html += '</div>';
      dropdown.innerHTML = html;
      dropdown.classList.remove('hidden');
      dropdown.querySelectorAll('.search-suggest-item').forEach(function(item) {
        item.addEventListener('click', function() {
          var name = item.getAttribute('data-name');
          dropdown.classList.add('hidden');
          window.location.href = 'statedetail.html?state_id=' + encodeURIComponent(item.getAttribute('data-id')) + '&state=' + encodeURIComponent(name);
        });
      });
    }

    input.addEventListener('focus', function() {
      if (allStates.length) showMatches(input.value);
    });

    input.addEventListener('input', function() {
      var val = input.value.trim().toLowerCase();
      searchQuery = val;
      if (val.length > 0) {
        clearBtn.classList.remove('hidden');
        showMatches(val);
      } else {
        clearBtn.classList.add('hidden');
        dropdown.classList.add('hidden');
        searchQuery = '';
        applyFilters();
      }
    });

    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        var val = input.value.trim().toLowerCase();
        var match = allStates.find(function(s) { return (s.state_name || '').toLowerCase() === val; })
          || allStates.find(function(s) { return (s.state_name || '').toLowerCase().indexOf(val) !== -1; });
        dropdown.classList.add('hidden');
        if (val.length > 0 && match) {
          window.location.href = 'statedetail.html?state_id=' + encodeURIComponent(match.state_id) + '&state=' + encodeURIComponent(match.state_name);
        }
      }
      if (e.key === 'Escape') { dropdown.classList.add('hidden'); input.blur(); }
    });

    clearBtn.addEventListener('click', function() {
      input.value = '';
      searchQuery = '';
      clearBtn.classList.add('hidden');
      dropdown.classList.add('hidden');
      applyFilters();
    });

    document.addEventListener('click', function(e) {
      var wrapper = document.getElementById('searchWrapper');
      if (wrapper && !wrapper.contains(e.target)) dropdown.classList.add('hidden');
    });
  }

  // ========== FILTERS ==========
  function setupFilters() {
    var clsFilter = document.getElementById('clsFilter');
    var utilFilter = document.getElementById('utilFilter');
    var sortFilter = document.getElementById('sortFilter');
    var resetBtn = document.getElementById('resetFiltersBtn');

    if (clsFilter) clsFilter.addEventListener('change', function() { filterClassification = clsFilter.value; applyFilters(); });
    if (utilFilter) utilFilter.addEventListener('change', function() { filterUtilization = utilFilter.value; applyFilters(); });
    if (sortFilter) sortFilter.addEventListener('change', function() { sortBy = sortFilter.value; applyFilters(); });
    if (resetBtn) resetBtn.addEventListener('click', function() {
      searchQuery = ''; filterClassification = ''; filterUtilization = ''; sortBy = 'util';
      if (clsFilter) clsFilter.value = '';
      if (utilFilter) utilFilter.value = '';
      if (sortFilter) sortFilter.value = 'util';
      var input = document.getElementById('stateSearchInput');
      if (input) input.value = '';
      document.getElementById('clearSearchBtn').classList.add('hidden');
      applyFilters();
    });
  }

  // ========== INIT ==========
  function mergeClassification(states, classes) {
    var map = {};
    (classes || []).forEach(function(c) { map[c.state_id] = c; });
    states.forEach(function(s) {
      var c = map[s.state_id];
      if (c) {
        s.performance_classification = c.performance_classification;
        s.performance_label = c.performance_label;
        s.performance_score = c.performance_score;
        if (!s.fund_utilization_pct) s.fund_utilization_pct = c.fund_utilization_pct;
      }
    });
    return states;
  }

  function fetchAll() {
    return Promise.all([
      fetch(API_BASE + '/api/state-performance').then(function(r) { if (!r.ok) throw new Error('API error'); return r.json(); }),
      fetch(API_BASE + '/api/classification/states').then(function(r) { return r.ok ? r.json() : []; }).catch(function() { return []; })
    ]).then(function(results) {
      return mergeClassification(results[0], results[1]);
    });
  }

  function processData(data) {
    allStates = data;
    filteredStates = data.slice();
    populateKPIs(data);
    populateDistributions(data);
    populateScatter(data);
    renderRanking('utilization');
    applyFilters();
  }

  document.addEventListener('DOMContentLoaded', function() {
    setupSearch();
    setupFilters();
    setupScatterTooltip();
    setupRankingTabs();

    var cached = getCached();
    if (cached) {
      processData(cached);
      fetchAll()
        .then(function(data) { if (data && data.length) { setCache(data); processData(data); } })
        .catch(function() {});
      return;
    }

    fetchAll()
      .then(function(data) {
        setCache(data);
        processData(data);
      })
      .catch(function(err) {
        var grid = document.getElementById('stateCardsGrid');
        if (grid) grid.innerHTML = '<div class="col-span-full text-center py-8 text-rose-400 text-sm">Failed to load state data. Please try again.</div>';
      });
  });
})();

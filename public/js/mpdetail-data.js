(function () {
  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  var CACHE_PREFIX = 'mpDetailCache_';
  var CACHE_TTL_MS = 30 * 60 * 1000; // 30 minutes
  var memberData = null;
  var worksData = [];
  var worksCache = {};
  var currentMemberId = null;
  var benchmarksData = {};
  var analysisData = {};
  var evidenceData = null;
  var currentCategory = 'all';
  var currentPage = 1;
  var pageSize = 6;
  var aiRingTarget = null;

  function animateAiRing() {
    var ring = document.getElementById('aiScoreRing');
    if (!ring || aiRingTarget == null || ring.dataset.anim) return;
    ring.dataset.anim = '1';
    ring.style.strokeDashoffset = aiRingTarget;
  }

  function getCache(memberId) {
    try {
      var raw = localStorage.getItem(CACHE_PREFIX + memberId);
      if (!raw) return null;
      var cached = JSON.parse(raw);
      if (Date.now() - cached.ts > CACHE_TTL_MS) { localStorage.removeItem(CACHE_PREFIX + memberId); return null; }
      return cached.data;
    } catch (e) { return null; }
  }

  function setCache(memberId, data) {
    try { localStorage.setItem(CACHE_PREFIX + memberId, JSON.stringify({ data: data, ts: Date.now() })); } catch (e) {}
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

  function getMemberId() {
    var params = new URLSearchParams(window.location.search);
    return params.get('member_id') || params.get('id');
  }

  function getMemberType() {
    var params = new URLSearchParams(window.location.search);
    return params.get('member_type') || params.get('type');
  }

  function memberQuerySuffix() {
    var mt = getMemberType();
    return mt ? '&member_type=' + encodeURIComponent(mt) : '';
  }

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function setHTML(id, html) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  function showState(state) {
    document.getElementById('loadingState').classList.toggle('hidden', state !== 'loading');
    document.getElementById('errorState').classList.toggle('hidden', state !== 'error');
    document.getElementById('mainContent').classList.toggle('hidden', state !== 'main');
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

  // ========== HEADER ==========
  function populateHeader(m) {
    document.title = (m.member_name || 'MP') + ' — Govsense AI';
    setText('mpName', m.member_name || 'Unknown');
    setText('mpState', m.state_name || 'India');
    setText('mpHouse', m.house_name || (m.member_type === 'MLA' ? 'Rajya Sabha' : 'Lok Sabha'));
    setText('mpTenure', m.tenure || 'Current Term');
    setText('headerMpName', (m.member_name || '') + ' — ' + (m.state_name || ''));
    var rank = m.rank;
    var rankLabel = rank ? ('National Rank #' + rank) : 'Rank: N/A';
    var pct = m.national_percentile;
    if (pct !== null && pct !== undefined) {
      rankLabel += '  ·  ' + Number(pct).toFixed(1) + ' %ile';
    }
    var cluster = m.cluster_label;
    if (cluster && cluster !== 'insufficient') {
      rankLabel += '  ·  ' + cluster;
    }
    setText('mpRank', rankLabel);
    var cls = m.performance_classification || 'N/A';
    var c = getClsColor(cls);
    var clsEl = document.getElementById('mpClassification');
    if (clsEl) {
      clsEl.textContent = cls.replace(/_/g, ' ');
      clsEl.className = 'px-3 py-1 rounded-full text-xs font-extrabold border flex items-center gap-1.5 bg-' + c + '-100 text-' + c + '-800 border-' + c + '-300';
    }
  }

  // ========== KPIs ==========
  function populateKPIs(m) {
    var allocated = Number(m.allocated_amount) || Number(m.sanctioned_amount) || 0;
    var util = Number(m.fund_utilization_pct) || 0;
    var completed = m.completed_works || 0;
    var total = m.total_works || 0;
    var compRate = Number(m.completion_rate_pct) || 0;
    var exp = Number(m.expenditure_amount) || 0;

    setText('kpiAllocated', fmtCr(allocated));
    setText('kpiUtilization', fmtPct(util));
    setText('kpiCompleted', fmtNum(completed));
    setText('kpiCompletionRate', fmtPct(compRate));
    setText('kpiCompletedSub', fmtNum(total) + ' total works');
    setText('kpiCompSub', fmtNum(completed) + ' of ' + fmtNum(total) + ' works');
    setText('kpiUtilSub', fmtCr(exp) + ' spent of ' + fmtCr(allocated));
    setText('tabProjectsCount', fmtNum(total));

    var uc = getColor(util);
    var ub = document.getElementById('kpiUtilBadge');
    if (ub) {
      var ul = util >= 70 ? 'Green' : util >= 50 ? 'Moderate' : util >= 30 ? 'Low' : 'Critical';
      ub.textContent = ul;
      ub.className = 'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border bg-' + uc + '-100 text-' + uc + '-800 border-' + uc + '-200';
    }
    var cc = getColor(compRate);
    var cb = document.getElementById('kpiCompBadge');
    if (cb) {
      var cl = compRate >= 70 ? 'Green' : compRate >= 50 ? 'Moderate' : compRate >= 30 ? 'Low' : 'Critical';
      cb.textContent = cl;
      cb.className = 'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border bg-' + cc + '-100 text-' + cc + '-800 border-' + cc + '-200';
    }
  }

  // ========== GAUGE ==========
  function populateGauge(m) {
    var util = Number(m.fund_utilization_pct) || 0;
    var allocated = Number(m.allocated_amount) || Number(m.sanctioned_amount) || 0;
    var exp = Number(m.expenditure_amount) || 0;
    var totalLen = 282.74;
    var offset = totalLen - (totalLen * Math.min(util, 100) / 100);
    var arc = document.getElementById('gaugeActiveArc');
    var needle = document.getElementById('gaugeNeedle');
    if (arc) setTimeout(function() { arc.style.strokeDashoffset = offset; }, 200);
    if (needle) {
      var angle = -90 + (180 * Math.min(util, 100) / 100);
      setTimeout(function() { needle.style.transform = 'rotate(' + angle + 'deg)'; }, 200);
    }
    var uc = getColor(util);
    var gv = document.getElementById('gaugeValue');
    if (gv) gv.innerHTML = fmtPct(util).replace('%', '<span class="text-xl font-bold text-' + uc + '-600">%</span>');
    var gl = document.getElementById('gaugeLabel');
    if (gl) gl.textContent = util >= 70 ? 'High Fund Utilization Velocity' : util >= 50 ? 'Moderate Utilization' : util >= 30 ? 'Below Average' : 'Critical Underutilization';
    var gb = document.getElementById('gaugeBadge');
    if (gb) { gb.textContent = fmtPct(util) + ' Disbursed'; gb.className = 'text-xs font-semibold px-2 py-0.5 rounded border bg-' + uc + '-50 text-' + uc + '-700 border-' + uc + '-200'; }
    setText('gaugeExpenditure', fmtCr(exp) + ' / ' + fmtCr(allocated) + ' (' + fmtPct(util) + ')');
    setText('gaugeAllocated', fmtCr(allocated));
  }

  // ========== DONUT ==========
  function populateDonut(m) {
    var total = m.total_works || 0;
    var completed = m.completed_works || 0;
    var ongoing = m.ongoing_works || 0;
    var pending = m.pending_works || 0;
    if (total === 0) return;
    var circ = 326.72;
    var cp = completed / total, op = ongoing / total, pp = pending / total;
    var dc = document.getElementById('donutCompleted');
    var do2 = document.getElementById('donutOngoing');
    var dp = document.getElementById('donutPending');

    if (dc) dc.setAttribute('stroke-dashoffset', '0');
    if (do2) do2.setAttribute('stroke-dashoffset', '-' + (cp * circ).toFixed(2));
    if (dp) dp.setAttribute('stroke-dashoffset', '-' + ((cp + op) * circ).toFixed(2));
    var _dsegs = [{ el: dc, len: cp * circ }, { el: do2, len: op * circ }, { el: dp, len: pp * circ }];
    if (window.ChartAnim) {
      window.ChartAnim.whenVisible(dc || dp, 'mpDonut', function () {
        window.ChartAnim.drawDonut(_dsegs, circ, { duration: 900 });
      });
    } else {
      _dsegs.forEach(function (s) { if (s.el) s.el.setAttribute('stroke-dasharray', s.len + ' ' + circ); });
    }

    setText('donutTotal', fmtNum(total) + ' Works');
    setText('donutCenter', fmtNum(total));
    setText('donutCompCount', fmtNum(completed));
    setText('donutCompPct', fmtPct(cp * 100));
    setText('donutOngoingCount', fmtNum(ongoing));
    setText('donutOngoingPct', fmtPct(op * 100));
    setText('donutPendingCount', fmtNum(pending));
    setText('donutPendingPct', fmtPct(pp * 100));
  }

  // ========== BENCHMARKS ==========
  function populateBenchmarks(m, benchmarks) {
    var br = document.getElementById('benchRank');
    if (br) { br.textContent = m.rank ? ('Rank #' + m.rank) : 'N/A'; br.className = 'text-xs font-bold px-2 py-0.5 rounded border bg-blue-50 text-blue-700 border-blue-200'; }
    var html = '';
    var metrics = [
      { key: 'fund_utilization_pct', label: 'Fund Utilization', mpVal: m.fund_utilization_pct, format: fmtPct },
      { key: 'completion_rate_pct', label: 'Completion Rate', mpVal: m.completion_rate_pct, format: fmtPct },
      { key: 'sanction_rate_pct', label: 'Sanction Rate', mpVal: m.sanction_rate_pct, format: fmtPct },
      { key: 'total_works', label: 'Total Works', mpVal: m.total_works, format: fmtNum },
    ];
    metrics.forEach(function(metric) {
      var nat = benchmarks[metric.key] || 0;
      var mp = Number(metric.mpVal) || 0;
      var delta = mp - nat;
      var sign = delta >= 0 ? '+' : '';
      var dc = delta >= 0 ? 'emerald' : 'rose';
      html += '<div class="p-3 bg-white rounded-lg border border-slate-200 flex items-center justify-between">' +
        '<div><span class="font-semibold text-slate-800 block">' + metric.label + '</span>' +
        '<span class="text-[11px] text-slate-500">Nat. Median: ' + metric.format(nat) + '</span></div>' +
        '<div class="text-right"><div class="text-sm font-bold text-slate-900">' + metric.format(mp) + '</div>' +
        '<span class="inline-flex items-center text-[10px] font-bold text-' + dc + '-700 bg-' + dc + '-50 px-1.5 py-0.5 rounded">' + sign + metric.format(Math.abs(delta)).replace('—', '0') + '</span></div></div>';
    });
    setHTML('benchmarkCards', html);
  }

  // ========== OVERVIEW METRICS ==========
  function populateOverviewMetrics(m) {
    setText('ovSanctionRate', fmtPct(m.sanction_rate_pct));
    setText('ovSanctionSub', fmtNum(m.sanctioned_works || 0) + ' of ' + fmtNum(m.total_works || 0) + ' recommended');
    setText('ovOngoing', fmtNum(m.ongoing_works || 0));
    setText('ovOngoingSub', fmtNum(m.pending_works || 0) + ' pending');
    setText('ovAvgExec', fmtDays(m.avg_execution_days));
    setText('ovAvgExecSub', 'Sanction delay: ' + fmtDays(m.avg_sanction_delay_days));
    setText('ovOverdue', fmtNum(m.overdue_over_1_year || 0));
    setText('ovOverdue2', fmtNum(m.overdue_over_2_years || 0));
  }

  // ========== RISK DISTRIBUTION ==========
  function populateRiskDistribution(m, worksSummary) {
    var container = document.getElementById('riskDistribution');
    if (!container) return;
    var byRisk = (worksSummary && worksSummary.by_risk) ? worksSummary.by_risk : {};

    // Fallback: use member_metrics data if works_summary is empty
    var highCount = byRisk['high'] || m.high_risk_works || 0;
    var mediumCount = byRisk['medium'] || m.medium_risk_works || 0;
    var flaggedCount = m.flagged_works || 0;
    var total = m.total_works || 1;
    var lowCount = Math.max(total - highCount - mediumCount, 0);

    var risks = [
      { label: 'High Risk', count: highCount, color: 'rose' },
      { label: 'Medium Risk', count: mediumCount, color: 'amber' },
      { label: 'Low Risk', count: lowCount, color: 'emerald' },
    ];
    var html = '';
    risks.forEach(function(r) {
      var pct = total > 0 ? (r.count / total * 100) : 0;
      html += '<div class="p-3 bg-slate-50/70 border border-slate-200 rounded-lg text-center">' +
        '<div class="text-xl font-black text-' + r.color + '-600">' + fmtNum(r.count) + '</div>' +
        '<div class="text-[10px] font-bold text-' + r.color + '-700 uppercase tracking-wider mt-0.5">' + r.label + '</div>' +
        '<div class="text-[11px] text-slate-500">' + fmtPct(pct) + '</div>' +
        '<div class="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden mt-1.5"><div class="h-full bg-' + r.color + '-500 rounded-full" style="width:' + Math.min(pct, 100) + '%"></div></div></div>';
    });
    html += '<div class="col-span-full pt-2 border-t border-slate-100 flex justify-between text-xs text-slate-500">' +
      '<span>Flagged: <span class="font-bold text-rose-600">' + fmtNum(flaggedCount) + '</span></span>' +
      '<span>Flagged rate: <span class="font-bold">' + fmtPct(m.flagged_rate_pct) + '</span></span></div>';
    container.innerHTML = html;
  }

  // ========== WORK STATUS COUNTS ==========
  function populateWorkStatusCounts(m, worksSummary) {
    var container = document.getElementById('workStatusCounts');
    if (!container) return;
    var byStatus = (worksSummary && worksSummary.by_status) ? worksSummary.by_status : {};

    var completed = (byStatus['Completed'] || byStatus['completed'] || {}).count || m.completed_works || 0;
    var ongoing = (byStatus['Ongoing'] || byStatus['ongoing'] || {}).count || m.ongoing_works || 0;
    var recommended = (byStatus['Recommended'] || byStatus['recommended'] || byStatus['Sanctioned'] || byStatus['sanctioned'] || {}).count || m.recommended_works || m.sanctioned_works || 0;
    var total = m.total_works || 1;

    var statuses = [
      { label: 'Completed', count: completed, color: 'emerald' },
      { label: 'In Progress', count: ongoing, color: 'blue' },
      { label: 'Recommended', count: recommended, color: 'violet' },
    ];
    var html = '';
    statuses.forEach(function(s) {
      var pct = total > 0 ? (s.count / total * 100) : 0;
      html += '<div class="p-3 bg-slate-50/70 border border-slate-200 rounded-lg text-center">' +
        '<div class="text-xl font-black text-' + s.color + '-600">' + fmtNum(s.count) + '</div>' +
        '<div class="text-[10px] font-bold text-' + s.color + '-700 uppercase tracking-wider mt-0.5">' + s.label + '</div>' +
        '<div class="text-[11px] text-slate-500">' + fmtPct(pct) + '</div>' +
        '<div class="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden mt-1.5"><div class="h-full bg-' + s.color + '-500 rounded-full" style="width:' + Math.min(pct, 100) + '%"></div></div></div>';
    });
    container.innerHTML = html;
  }

  // ========== WORK CATEGORIES ==========
  function populateWorkCategories(worksSummary) {
    var container = document.getElementById('workCategories');
    if (!container) return;
    var byCat = (worksSummary && worksSummary.by_category) ? worksSummary.by_category : {};
    var entries = Object.entries(byCat).sort(function(a, b) { return b[1] - a[1]; });
    if (entries.length === 0) {
      container.innerHTML = '<div class="text-sm text-slate-400 text-center py-4">No category data available</div>';
      return;
    }
    var maxCount = entries[0][1] || 1;
    var colors = ['blue', 'emerald', 'violet', 'amber', 'rose', 'cyan', 'indigo', 'slate'];
    var html = '';
    entries.forEach(function(entry, i) {
      var cat = entry[0], count = entry[1];
      var pct = (count / maxCount) * 100;
      var color = colors[i % colors.length];
      html += '<div class="flex items-center gap-3">' +
        '<div class="w-20 text-xs font-medium text-slate-600 truncate flex-shrink-0">' + cat + '</div>' +
        '<div class="flex-1 h-5 bg-slate-100 rounded overflow-hidden"><div class="h-full bg-' + color + '-500 rounded transition-all duration-700 flex items-center" style="width:' + Math.max(pct, 2) + '%">' +
        (pct > 15 ? '<span class="text-[10px] font-bold text-white px-1.5">' + fmtNum(count) + '</span>' : '') +
        '</div></div>' +
        '<div class="text-xs font-bold text-slate-700 w-10 text-right">' + fmtNum(count) + '</div></div>';
    });
    container.innerHTML = html;
  }

  // ========== TIMELINE METRICS ==========
  function populateTimelineMetrics(m) {
    var container = document.getElementById('timelineMetrics');
    if (!container) return;
    var avgExec = Number(m.avg_execution_days) || 0;
    var medExec = Number(m.median_execution_days) || 0;
    var avgDelay = Number(m.avg_sanction_delay_days) || 0;
    var medDelay = Number(m.median_sanction_delay_days) || 0;
    var avgAge = Number(m.avg_project_age_days) || 0;
    var maxAge = Number(m.max_project_age_days) || 0;
    var overdue1 = m.overdue_over_1_year || 0;
    var overdue2 = m.overdue_over_2_years || 0;

    var items = [
      { label: 'Avg Execution Time', value: fmtDays(avgExec), sub: 'Median: ' + fmtDays(medExec), color: 'blue' },
      { label: 'Avg Sanction Delay', value: fmtDays(avgDelay), sub: 'Median: ' + fmtDays(medDelay), color: 'amber' },
      { label: 'Avg Project Age', value: fmtDays(avgAge), sub: 'Max: ' + fmtDays(maxAge), color: 'violet' },
      { label: 'Overdue Works', value: fmtNum(overdue1) + ' / ' + fmtNum(overdue2), sub: '> 1yr / > 2yr', color: overdue1 > 0 ? 'rose' : 'emerald' },
    ];
    var html = '';
    items.forEach(function(item) {
      html += '<div class="p-4 bg-slate-50/70 border border-slate-200 rounded-xl">' +
        '<div class="flex items-center gap-2 mb-2"><span class="w-2 h-2 rounded-full bg-' + item.color + '-500"></span>' +
        '<span class="text-[10px] font-bold uppercase tracking-wider text-slate-500">' + item.label + '</span></div>' +
        '<div class="text-xl font-bold text-slate-900">' + item.value + '</div>' +
        '<div class="text-[11px] text-slate-500 mt-0.5">' + item.sub + '</div></div>';
    });
    container.innerHTML = html;
  }

  // ========== FUND FLOW BARS ==========
  function populateFundFlowSvg(m) {
    var allocated = Number(m.allocated_amount) || Number(m.sanctioned_amount) || 0;
    // Phase 5: never fabricate a recommended amount. Use the authoritative
    // value (0 when the DB has none) — the bar simply shows 0.
    var recommended = Number(m.recommended_amount) || 0;
    var sanctioned = Number(m.sanctioned_amount) || 0;
    var exp = Number(m.expenditure_amount) || 0;
    if (allocated === 0) return;

    var stages = [
      { label: 'Allocated', amount: allocated, pct: 100, color: 'teal' },
      { label: 'Recommended', amount: recommended, pct: (recommended / allocated * 100), color: 'emerald' },
      { label: 'Sanctioned', amount: sanctioned, pct: (sanctioned / allocated * 100), color: 'blue' },
      { label: 'Expenditure', amount: exp, pct: (exp / allocated * 100), color: 'violet' },
    ];

    var container = document.getElementById('fundFlowBars');
    if (!container) return;
    var html = '';
    stages.forEach(function(s) {
      html += '<div class="space-y-1">' +
        '<div class="flex justify-between text-xs"><span class="font-semibold text-slate-700">' + s.label + '</span>' +
        '<span class="font-bold text-slate-900">' + fmtCr(s.amount) + ' <span class="text-slate-400 font-normal">(' + fmtPct(s.pct) + ')</span></span></div>' +
        '<div class="w-full h-3 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + s.color + '-500 rounded-full transition-all duration-700" style="width:' + Math.min(s.pct, 100) + '%"></div></div></div>';
    });
    var unspent = allocated - exp;
    html += '<div class="pt-2 border-t border-slate-100 flex justify-between text-xs text-slate-500">' +
      '<span>Unspent: <span class="font-bold text-slate-700">' + fmtCr(unspent) + '</span></span>' +
      '<span>' + fmtPct(allocated > 0 ? (unspent / allocated * 100) : 0) + ' remaining</span></div>';
    container.innerHTML = html;

    setText('finAllocated', fmtCr(allocated));
    setText('finExpenditure', fmtCr(exp));
    setText('finUnspent', fmtCr(unspent));
    var ue = document.getElementById('finUtilRate');
    if (ue) {
      var util = Number(m.fund_utilization_pct) || 0;
      ue.textContent = fmtPct(util);
      ue.className = 'text-xl font-bold text-' + getColor(util) + '-600';
    }
  }

  // ========== FINANCIAL STACKED BAR ==========
  function populateFinancialBars(m) {
    var allocated = Number(m.allocated_amount) || Number(m.sanctioned_amount) || 0;
    var exp = Number(m.expenditure_amount) || 0;
    var completionAmt = Number(m.completion_amount) || 0;
    var unspent = allocated - exp;
    var util = Number(m.fund_utilization_pct) || 0;

    var barContainer = document.getElementById('expStackedBar');
    if (barContainer) {
      var expPct = allocated > 0 ? (exp / allocated * 100) : 0;
      var unspentPct = 100 - expPct;
      var html = '<div class="space-y-2">' +
        '<div class="flex justify-between text-xs"><span class="font-semibold text-slate-700">Expenditure</span><span class="font-bold text-slate-900">' + fmtCr(exp) + ' (' + fmtPct(expPct) + ')</span></div>' +
        '<div class="w-full h-6 bg-slate-100 rounded-full overflow-hidden flex">' +
        '<div class="h-full bg-blue-500 rounded-l-full transition-all duration-1000" style="width:' + expPct + '%"></div>' +
        '<div class="h-full bg-slate-300 rounded-r-full transition-all duration-1000" style="width:' + unspentPct + '%"></div></div>' +
        '<div class="flex justify-between text-[10px] text-slate-400"><span>Utilized</span><span>Unspent</span></div></div>';
      html += '<div class="pt-3 border-t border-slate-100 space-y-2 text-xs">' +
        '<div class="flex justify-between"><span class="text-slate-500">Completion Amount</span><span class="font-semibold text-slate-900">' + fmtCr(completionAmt) + '</span></div>' +
        '<div class="flex justify-between"><span class="text-slate-500">Unspent Balance</span><span class="font-semibold text-slate-900">' + fmtCr(unspent) + '</span></div></div>';
      barContainer.innerHTML = html;
    }

    var ratioContainer = document.getElementById('finRatioBars');
    if (ratioContainer) {
      var compRate = Number(m.completion_rate_pct) || 0;
      var sanctionRate = Number(m.sanction_rate_pct) || 0;
      var ratios = [
        { label: 'Fund Utilization', value: util, color: getColor(util) },
        { label: 'Completion Rate', value: compRate, color: getColor(compRate) },
        { label: 'Sanction Rate', value: sanctionRate, color: getColor(sanctionRate) },
      ];
      var html2 = '';
      ratios.forEach(function(r) {
        html2 += '<div class="space-y-1">' +
          '<div class="flex justify-between text-xs"><span class="font-medium text-slate-600">' + r.label + '</span><span class="font-bold text-slate-900">' + fmtPct(r.value) + '</span></div>' +
          '<div class="w-full h-3 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + r.color + '-500 rounded-full transition-all duration-1000" style="width:' + Math.min(r.value, 100) + '%"></div></div></div>';
      });
      html2 += '<div class="pt-3 border-t border-slate-100 space-y-2 text-xs">' +
        '<div class="flex justify-between"><span class="text-slate-500">Avg Work Cost</span><span class="font-semibold text-slate-900">' + fmtCr(m.avg_work_cost) + '</span></div>' +
        '<div class="flex justify-between"><span class="text-slate-500">Median Work Cost</span><span class="font-semibold text-slate-900">' + fmtCr(m.median_work_cost) + '</span></div></div>';
      ratioContainer.innerHTML = html2;
    }

    // Financial Detail Table
    var tableBody = document.getElementById('finTableBody');
    if (tableBody) {
      var rows = [
        { label: 'Allocated Amount', value: fmtCr(m.allocated_amount), median: fmtCr(benchmarksData.allocated_amount), delta: (Number(m.allocated_amount) || 0) - (benchmarksData.allocated_amount || 0) },
        { label: 'Sanctioned Amount', value: fmtCr(m.sanctioned_amount), median: fmtCr(benchmarksData.sanctioned_amount), delta: (Number(m.sanctioned_amount) || 0) - (benchmarksData.sanctioned_amount || 0) },
        { label: 'Expenditure Amount', value: fmtCr(m.expenditure_amount), median: fmtCr(benchmarksData.expenditure_amount), delta: (Number(m.expenditure_amount) || 0) - (benchmarksData.expenditure_amount || 0) },
        { label: 'Fund Utilization', value: fmtPct(m.fund_utilization_pct), median: fmtPct(benchmarksData.fund_utilization_pct), delta: (Number(m.fund_utilization_pct) || 0) - (benchmarksData.fund_utilization_pct || 0) },
        { label: 'Completion Rate', value: fmtPct(m.completion_rate_pct), median: fmtPct(benchmarksData.completion_rate_pct), delta: (Number(m.completion_rate_pct) || 0) - (benchmarksData.completion_rate_pct || 0) },
        { label: 'Sanction Rate', value: fmtPct(m.sanction_rate_pct), median: fmtPct(benchmarksData.sanction_rate_pct), delta: (Number(m.sanction_rate_pct) || 0) - (benchmarksData.sanction_rate_pct || 0) },
      ];
      var thtml = '';
      rows.forEach(function(row) {
        var dc = row.delta >= 0 ? 'emerald' : 'rose';
        var sign = row.delta >= 0 ? '+' : '';
        var isMoney = row.label.indexOf('Amount') > -1;
        var deltaFmt = isMoney ? fmtCr(Math.abs(row.delta)) : fmtPct(Math.abs(row.delta));
        thtml += '<tr class="border-b border-slate-100 hover:bg-slate-50">' +
          '<td class="py-2.5 px-3 font-medium text-slate-700">' + row.label + '</td>' +
          '<td class="py-2.5 px-3 text-right font-bold text-slate-900">' + row.value + '</td>' +
          '<td class="py-2.5 px-3 text-right text-slate-500">' + row.median + '</td>' +
          '<td class="py-2.5 px-3 text-right font-semibold text-' + dc + '-700">' + sign + deltaFmt + '</td></tr>';
      });
      tableBody.innerHTML = thtml;
    }
  }

  // ========== AI ANALYSIS ==========
  function populateAIAnalysis(m, analysis) {
    // Phase: Intelligence Foundation. Prefer the authoritative 0-100 score +
    // label + national rank/percentile + cluster label + risk from DB. Fall back
    // to the legacy 0-200 score + classification only if the new fields are
    // missing (e.g. before the intelligence backfill has run for this row).
    var newScore = m.performance_score_100;
    var newLabel = m.performance_label;
    var legacyScore = Number(m.performance_score) || 0;
    var legacyLabel = m.performance_classification || 'N/A';
    var hasNew = (newScore !== null && newScore !== undefined && newLabel);
    var displayScore = hasNew ? Number(newScore) : legacyScore;
    var displayLabel = hasNew ? newLabel : legacyLabel;
    var displayMax = hasNew ? 100 : 200;
    var cc = getClsColor(hasNew ? newLabel : legacyLabel);

    // Score ring — animated when the AI Analysis tab is opened
    var ring = document.getElementById('aiScoreRing');
    if (ring) {
      var circ = 364.42;
      ring.setAttribute('stroke-dasharray', circ + ' ' + circ);
      ring.setAttribute('stroke-dashoffset', circ);
      ring.setAttribute('stroke', cc === 'emerald' ? '#10b981' : cc === 'blue' ? '#3b82f6' : cc === 'amber' ? '#f59e0b' : '#ef4444');
      aiRingTarget = circ - (circ * Math.min(displayScore / displayMax, 1));
    }
    setText('aiScoreValue', Math.round(displayScore));
    var badge = document.getElementById('aiScoreBadge');
    if (badge) {
      badge.textContent = String(displayLabel).replace(/_/g, ' ');
      badge.className = 'px-3 py-1 rounded-full text-xs font-bold border bg-' + cc + '-100 text-' + cc + '-800 border-' + cc + '-300';
    }

    // Intelligence meta: rank, percentile, cluster, risk
    setText('aiNationalRank', m.national_rank != null ? ('#' + fmtNum(m.national_rank)) : '—');
    setText('aiNationalPercentile', m.national_percentile != null ? fmtPct(m.national_percentile) : '—');
    setText('aiPeerRank', m.peer_rank != null ? ('#' + fmtNum(m.peer_rank)) : '—');
    setText('aiPeerPercentile', m.peer_percentile != null ? fmtPct(m.peer_percentile) : '—');
    setText('aiClusterLabel', m.cluster_label && m.cluster_label !== 'insufficient' ? m.cluster_label : '—');
    var riskEl = document.getElementById('aiRiskLevel');
    if (riskEl) {
      var rl = (m.risk_level || 'N/A').toUpperCase();
      var rc = rl === 'CRITICAL' || rl === 'HIGH' ? 'rose' : rl === 'MODERATE' || rl === 'MEDIUM' ? 'amber' : 'emerald';
      riskEl.textContent = rl.replace(/_/g, ' ') + (m.risk_confidence ? ' (' + m.risk_confidence + ' confidence)' : '');
      riskEl.className = 'text-xs font-semibold text-' + rc + '-700';
    }

    // Append "/100" suffix next to the score when using the new scale
    var ringContainer = ring ? ring.parentElement && ring.parentElement.parentElement : null;
    var suffix = document.getElementById('aiScoreMaxSuffix');
    if (!suffix) {
      // Create a one-time suffix node next to the aiScoreValue (does not
      // redesign the layout; just appends a label).
      var valEl = document.getElementById('aiScoreValue');
      if (valEl) {
        suffix = document.createElement('span');
        suffix.id = 'aiScoreMaxSuffix';
        suffix.className = 'text-[10px] font-bold text-slate-500 ml-1';
        suffix.textContent = '/ ' + displayMax;
        valEl.parentNode && valEl.parentNode.appendChild(suffix);
      }
    } else {
      suffix.textContent = '/ ' + displayMax;
    }

    // Score breakdown
    var breakdown = document.getElementById('aiScoreBreakdown');
    if (breakdown) {
      var comp = Number(m.completion_rate_pct) || 0;
      var util = Number(m.fund_utilization_pct) || 0;
      var sanction = Number(m.sanction_rate_pct) || 0;
      var flagged = Number(m.flagged_rate_pct) || 0;
      var metrics = [
        { label: 'Completion Rate', value: comp, color: getColor(comp) },
        { label: 'Fund Utilization', value: util, color: getColor(util) },
        { label: 'Sanction Rate', value: sanction, color: getColor(sanction) },
        // Phase 5: show the authoritative flagged rate; do not invent an
        // inverted "risk score".
        { label: 'Flagged Rate', value: flagged, color: flagged > 20 ? 'rose' : 'emerald' },
      ];
      var html = '<div class="flex items-center justify-between mb-3"><h4 class="text-xs font-bold text-slate-900 uppercase tracking-wider">Score Components</h4>' +
        '<span class="text-xs font-bold text-slate-500">' + Math.round(displayScore) + ' / ' + displayMax + ' points</span></div>';
      metrics.forEach(function(metric) {
        html += '<div class="space-y-1.5">' +
          '<div class="flex justify-between items-center text-xs">' +
          '<span class="font-medium text-slate-600">' + metric.label + '</span>' +
          '<span class="font-bold text-' + metric.color + '-700">' + fmtPct(metric.value) + '</span></div>' +
          '<div class="w-full h-4 bg-slate-100 rounded-full overflow-hidden">' +
          '<div class="h-full bg-' + metric.color + '-500 rounded-full transition-all duration-1000" style="width:' + Math.min(metric.value, 100) + '%"></div></div></div>';
      });
      breakdown.innerHTML = html;
    }

    // Summary - handle if analysis is a string (not parsed JSON)
    var summaryContent = document.getElementById('aiSummaryContent');
    if (summaryContent) {
      var summaryText = '';
      if (analysis) {
        if (typeof analysis === 'string') {
          summaryText = analysis;
        } else if (analysis.summary) {
          summaryText = analysis.summary;
        }
      }
      if (summaryText) {
        summaryContent.innerHTML = '<p class="text-[14px] text-slate-700 leading-relaxed">' + summaryText + '</p>';
      } else {
        summaryContent.innerHTML = '<p class="text-sm text-slate-500 italic">No AI summary available.</p>';
      }
    }

    // Highlights
    var highlightsContent = document.getElementById('aiHighlightsContent');
    if (highlightsContent) {
      var highlights = [];
      if (analysis && typeof analysis === 'object' && analysis.highlights) {
        highlights = analysis.highlights;
      }
      if (highlights.length > 0) {
        var hhtml = '<ul class="space-y-2">';
        highlights.forEach(function(h) {
          hhtml += '<li class="text-[13px] text-slate-700 flex items-start gap-2.5 p-2 bg-emerald-50/50 rounded-lg border border-emerald-100">' +
            '<svg class="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>' +
            '<span>' + h + '</span></li>';
        });
        hhtml += '</ul>';
        highlightsContent.innerHTML = hhtml;
      } else {
        highlightsContent.innerHTML = '<p class="text-sm text-slate-500 italic">No highlights available.</p>';
      }
    }

    // Performance Chart - all metrics in one
    var chartContainer = document.getElementById('aiPerformanceChart');
    if (chartContainer) {
      var anomalyScore = Number(m.anomaly_score) || 0;
      var anomalyLevel = m.anomaly_level || 'N/A';
      var ac = anomalyLevel === 'high' ? 'rose' : anomalyLevel === 'medium' ? 'amber' : 'emerald';
      var chartMetrics = [
        { label: 'Fund Utilization', value: Number(m.fund_utilization_pct) || 0 },
        { label: 'Completion Rate', value: Number(m.completion_rate_pct) || 0 },
        { label: 'Sanction Rate', value: Number(m.sanction_rate_pct) || 0 },
        { label: 'Performance Score', value: (Number(m.performance_score) || 0) / 2 },
        { label: 'Anomaly Score', value: anomalyScore, color: ac },
        { label: 'Flagged Rate', value: Number(m.flagged_rate_pct) || 0, color: (Number(m.flagged_rate_pct) || 0) > 10 ? 'rose' : 'emerald' },
      ];
      var chtml = '';
      chartMetrics.forEach(function(metric) {
        var vc = metric.color || getColor(metric.value);
        chtml += '<div class="space-y-1.5">' +
          '<div class="flex justify-between items-center text-xs">' +
          '<span class="font-semibold text-slate-700">' + metric.label + '</span>' +
          '<span class="font-bold text-' + vc + '-700">' + fmtPct(metric.value) + '</span></div>' +
          '<div class="w-full h-4 bg-slate-100 rounded-full overflow-hidden">' +
          '<div class="h-full bg-' + vc + '-500 rounded-full transition-all duration-1000" style="width:' + Math.min(metric.value, 100) + '%"></div></div></div>';
      });
      chartContainer.innerHTML = chtml;
    }
  }

  // ========== WORKS (Projects Tab) - server-side category + pagination ==========
  function loadWorks(category, page) {
    currentCategory = category;
    currentPage = page;
    var grid = document.getElementById('worksGrid');
    var key = category + '_' + page;
    if (worksCache[key]) {
      renderWorksData(worksCache[key]);
      return;
    }
    if (grid) grid.innerHTML =
      '<div class="col-span-full grid grid-cols-1 sm:grid-cols-2 gap-3">' +
      Array.from({length: 4}).map(function () {
        return '<div class="bg-white border border-slate-200 rounded-xl p-4"><div class="flex justify-between mb-3"><div class="skeleton h-4 w-20"></div><div class="skeleton h-4 w-16"></div></div><div class="skeleton h-3 w-3/4 mb-2"></div><div class="skeleton h-3 w-1/2 mb-4"></div><div class="grid grid-cols-3 gap-2"><div class="skeleton h-10"></div><div class="skeleton h-10"></div><div class="skeleton h-10"></div></div></div>';
      }).join('') +
      '</div>';
    setText('worksShowingText', 'Loading…');
    setHTML('worksPageButtons', '');
    fetch(API_BASE + '/api/members/detail/' + currentMemberId + '/works?category=' + category + '&page=' + page + '&page_size=' + pageSize + memberQuerySuffix())
      .then(function(r) { if (!r.ok) throw new Error('works error'); return r.json(); })
      .then(function(data) {
        worksCache[key] = data;
        renderWorksData(data);
      })
      .catch(function() {
        if (!grid) return;
        grid.innerHTML =
          '<div class="col-span-full section-error">' +
            '<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>' +
            '<span>Could not load works for this MP.</span>' +
            '<button type="button" data-retry-mpworks="' + category + '|' + page + '">Retry</button>' +
          '</div>';
        var btn = grid.querySelector('[data-retry-mpworks]');
        if (btn) btn.addEventListener('click', function () { loadWorks(category, page); });
      });
  }

  function renderWorksData(data) {
    var items = data.items || [];
    var total = data.total || 0;
    var totalPages = data.total_pages || 1;
    var page = data.page || 1;
    var grid = document.getElementById('worksGrid');
    if (!grid) return;

    if (items.length === 0) {
      grid.innerHTML = '<div class="col-span-full text-center py-8 text-slate-400 text-sm">No works found in this category.</div>';
      setText('worksShowingText', 'No works');
      setHTML('worksPageButtons', '');
      return;
    }

    var html = '';
    items.forEach(function(w) {
      var sc = 'slate';
      var st = (w.status || 'Unknown').toLowerCase();
      var displayStatus = w.status || 'Unknown';
      if (st === 'completed' || st === 'complete') { sc = 'emerald'; displayStatus = 'Completed'; }
      else if (st === 'ongoing' || st === 'in progress' || st === 'inprogress' || st === 'active') { sc = 'blue'; displayStatus = 'In Progress'; }
      else if (st === 'pending' || st === 'recommended' || st === 'sanctioned' || st === 'proposed') { sc = 'amber'; displayStatus = 'Recommended'; }
      var rc = 'slate';
      var rk = (w.risk_level || '').toLowerCase();
      if (rk === 'high') rc = 'rose';
      else if (rk === 'medium') rc = 'amber';
      else if (rk === 'low') rc = 'emerald';
      var desc = w.work_description || w.activity_name || 'No description';
      if (desc.length > 120) desc = desc.substring(0, 120) + '...';
      html += '<div class="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow">' +
        '<div class="flex items-start justify-between gap-2 mb-2">' +
        '<span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">' + (w.work_category || 'General') + '</span>' +
        '<div class="flex items-center gap-1.5">' +
        '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-' + sc + '-50 text-' + sc + '-700 border border-' + sc + '-200">' + displayStatus + '</span>' +
        (rk ? '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-' + rc + '-50 text-' + rc + '-700 border border-' + rc + '-200">' + rk + '</span>' : '') +
        '</div></div>' +
        '<p class="text-sm text-slate-800 font-medium mb-3 leading-snug">' + desc + '</p>' +
        '<div class="grid grid-cols-2 gap-2 text-xs">' +
        '<div><span class="text-slate-400">Sanction</span><div class="font-bold text-slate-900">' + fmtCr(w.sanction_amount) + '</div></div>' +
        '<div><span class="text-slate-400">Expenditure</span><div class="font-bold text-slate-900">' + fmtCr(w.expenditure_amount) + '</div></div></div>' +
        (w.recommendation_date ? '<div class="mt-2 text-[10px] text-slate-400">Recommended: ' + w.recommendation_date + '</div>' : '') +
        '</div>';
    });
    grid.innerHTML = html;

    var start = (page - 1) * pageSize;
    var end = start + items.length;
    setText('worksShowingText', 'Showing ' + (start + 1) + '-' + end + ' of ' + total + ' works');

    var btnsHtml = '';
    if (totalPages > 1) {
      btnsHtml += '<button class="page-btn px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 bg-white text-slate-600 hover:bg-slate-50' + (page <= 1 ? ' opacity-50 cursor-not-allowed' : '') + '" data-page="' + (page - 1) + '">Prev</button>';
      var from = Math.max(1, page - 2);
      var to = Math.min(totalPages, from + 4);
      if (to - from < 4) from = Math.max(1, to - 4);
      for (var i = from; i <= to; i++) {
        btnsHtml += i === page
          ? '<button class="page-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white shadow-xs" data-page="' + i + '">' + i + '</button>'
          : '<button class="page-btn px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 bg-white text-slate-600 hover:bg-slate-50" data-page="' + i + '">' + i + '</button>';
      }
      btnsHtml += '<button class="page-btn px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 bg-white text-slate-600 hover:bg-slate-50' + (page >= totalPages ? ' opacity-50 cursor-not-allowed' : '') + '" data-page="' + (page + 1) + '">Next</button>';
    }
    setHTML('worksPageButtons', btnsHtml);

    document.querySelectorAll('.page-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var p = parseInt(btn.getAttribute('data-page'));
        if (p >= 1 && p <= totalPages && p !== page) { loadWorks(currentCategory, p); }
      });
    });
  }

  function renderWorks() {
    loadWorks(currentCategory, currentPage);
  }

  // ========== TABS & EVENTS ==========
  function setupTabs() {
    var tabs = document.querySelectorAll('.tab-link');
    var panels = document.querySelectorAll('.tab-panel');
    tabs.forEach(function(tab) {
      tab.addEventListener('click', function() {
        tabs.forEach(function(t) { t.classList.remove('text-blue-600', 'border-blue-600', 'font-semibold'); t.classList.add('text-slate-500', 'border-transparent'); t.setAttribute('aria-selected', 'false'); });
        tab.classList.add('text-blue-600', 'border-blue-600', 'font-semibold'); tab.classList.remove('text-slate-500', 'border-transparent'); tab.setAttribute('aria-selected', 'true');
        panels.forEach(function(p) { p.classList.add('hidden'); });
        var panel = document.getElementById(tab.getAttribute('data-tab-target'));
        if (panel) panel.classList.remove('hidden');
        if (tab.getAttribute('data-tab-target') === 'tab-ai') setTimeout(animateAiRing, 60);
      });
    });
  }

  function setupCategoryTabs() {
    document.querySelectorAll('.category-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        document.querySelectorAll('.category-btn').forEach(function(b) { b.classList.remove('bg-blue-600', 'text-white', 'shadow-xs'); b.classList.add('border', 'border-slate-200', 'bg-white', 'text-slate-600', 'font-medium'); });
        btn.classList.add('bg-blue-600', 'text-white', 'shadow-xs'); btn.classList.remove('border', 'border-slate-200', 'bg-white', 'text-slate-600', 'font-medium');
        loadWorks(btn.getAttribute('data-category'), 1);
      });
    });
  }

  function setupCopyLink() {
    var copyBtn = document.getElementById('copyLinkBtn');
    if (copyBtn) {
      copyBtn.addEventListener('click', function() {
        var url = window.location.href;
        if (navigator.clipboard) {
          navigator.clipboard.writeText(url).then(function() { setText('copyBtnText', 'Copied!'); setTimeout(function() { setText('copyBtnText', 'Copy Link'); }, 2000); });
        } else {
          var input = document.createElement('input'); input.value = url; document.body.appendChild(input); input.select(); document.execCommand('copy'); document.body.removeChild(input);
          setText('copyBtnText', 'Copied!'); setTimeout(function() { setText('copyBtnText', 'Copy Link'); }, 2000);
        }
      });
    }
  }

  // ========== INIT ==========
  function applyBackLink(defaultHref, defaultText) {
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
      link.setAttribute('href', defaultHref);
      if (text) text.textContent = defaultText;
    }
  }

  function processData(data) {
    memberData = data.member || {};
    worksData = data.works || [];
    benchmarksData = data.benchmarks || {};
    analysisData = data.analysis || {};
    evidenceData = data.evidence || null;
    var worksSummary = data.works_summary || {};

    populateHeader(memberData);
    populateKPIs(memberData);
    populateGauge(memberData);
    populateDonut(memberData);
    populateBenchmarks(memberData, benchmarksData);
    populateOverviewMetrics(memberData);
    populateRiskDistribution(memberData, worksSummary);
    populateWorkStatusCounts(memberData, worksSummary);
    populateTimelineMetrics(memberData);
    populateFundFlowSvg(memberData);
    populateFinancialBars(memberData);
    populateAIAnalysis(memberData, analysisData);
  }

  document.addEventListener('DOMContentLoaded', function() {
    var memberId = getMemberId();
    if (!memberId) { showState('error'); setText('errorTitle', 'No member selected'); setText('errorMsg', 'Please navigate from the MPs page to view a member profile.'); return; }

    currentMemberId = memberId;
    worksCache = {};

    applyBackLink('mps.html', 'Back to all MPs');

    setupTabs();
    setupCategoryTabs();
    setupCopyLink();

    // Kick off the works request in parallel with the detail request
    loadWorks('all', 1);

    // Check cache first
    var cached = getCache(memberId);
    if (cached) {
      processData(cached);
      showState('main');
      // Refresh in background
      fetch(API_BASE + '/api/members/detail/' + memberId + '?' + memberQuerySuffix().replace(/^&/, ''))
        .then(function(r) { if (!r.ok) return null; return r.json(); })
        .then(function(data) { if (data) { setCache(memberId, data); processData(data); } })
        .catch(function() {});
      return;
    }

    fetch(API_BASE + '/api/members/detail/' + memberId + '?' + memberQuerySuffix().replace(/^&/, ''))
      .then(function(r) {
        if (!r.ok) throw new Error(r.status === 404 ? 'Member not found' : 'API error');
        return r.json();
      })
      .then(function(data) {
        setCache(memberId, data);
        processData(data);
        showState('main');
      })
      .catch(function(err) {
        showState('error');
        setText('errorTitle', 'Failed to load MP data');
        setText('errorMsg', err.message || 'Please try again later.');
      });
  });
})();

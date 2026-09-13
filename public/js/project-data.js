(function () {
  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  var CACHE_KEY = 'projectSummaryCache';
  var CACHE_TTL = 30 * 60 * 1000;

  var stateId = '';
  var memberId = '';
  var searchQ = '';
  var sortBy = 'highest_comp';
  var statusFilter = 'all';
  var categoryFilter = '';
  var page = 1;
  var pageSize = 9;
  var totalPages = 1;

  function cleanName(w) {
    var s = (w.activity_name && w.activity_name.trim())
      ? w.activity_name
      : (w.work_description && w.work_description.trim() ? w.work_description : '');
    if (!s) return '';
    s = s.replace(/^\s*NA\s*[-–—:]\s*/i, '').trim();
    // Strip leading reference codes like "WS/MP18309/2024-2025/143138-"
    s = s.replace(/^[A-Z]{2,}\/[^\s]+-\s*/, '').trim();
    s = s.replace(/^\s*NA\s*[-–—:]\s*/i, '').trim();
    if (/^NA$/i.test(s) || s.length < 3) return '';
    return s;
  }

  function fmtNum(n) { if (n == null || isNaN(n)) return '—'; return Number(n).toLocaleString('en-IN'); }
  function fmtCr(n) {
    if (n == null || isNaN(n)) return '—';
    var v = Number(n);
    if (v >= 1e7) return '₹' + (v / 1e7).toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' Cr';
    if (v >= 1e5) return '₹' + (v / 1e5).toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' L';
    return '₹' + v.toLocaleString('en-IN', { maximumFractionDigits: 0 });
  }
  function fmtPct(n) { if (n == null || isNaN(n)) return '—'; return Number(n).toFixed(1) + '%'; }
  function getColor(p) { return p >= 70 ? 'emerald' : p >= 50 ? 'blue' : p >= 30 ? 'amber' : 'rose'; }
  function setText(id, t) { var e = document.getElementById(id); if (e) e.textContent = t; }
  function setHTML(id, h) { var e = document.getElementById(id); if (e) e.innerHTML = h; }

  // ================= SEARCHABLE SELECT =================
  function enhanceSelect(select, placeholder) {
    if (!select || select.dataset.enh) return;
    select.dataset.enh = '1';
    select.style.display = 'none';

    var wrap = document.createElement('div');
    wrap.className = 'relative shrink-0';
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);

    var input = document.createElement('input');
    input.type = 'text';
    input.autocomplete = 'off';
    input.placeholder = placeholder || 'Search...';
    input.className = 'bg-white border border-slate-300 hover:border-slate-400 text-slate-800 text-xs py-1.5 pl-2.5 pr-7 rounded-lg shadow-2xs focus:ring-1 focus:ring-blue-500 focus:outline-none font-medium w-44 overflow-hidden text-ellipsis whitespace-nowrap';
    var list = document.createElement('div');
    list.className = 'hidden absolute top-full left-0 mt-1 w-max min-w-full max-w-[320px] max-h-64 overflow-y-auto bg-white border border-slate-200 rounded-lg shadow-lg z-50 text-xs';
    wrap.appendChild(input);
    wrap.appendChild(list);

    function renderList(filter) {
      var f = (filter || '').toLowerCase().trim();
      var html = '';
      var opts = Array.prototype.slice.call(select.options);
      opts.forEach(function (opt) {
        if (!opt.value) return;
        if (f && opt.text.toLowerCase().indexOf(f) === -1) return;
        html += '<div class="opt px-2.5 py-1.5 hover:bg-slate-50 cursor-pointer text-slate-700" data-val="' + opt.value + '">' + opt.text + '</div>';
      });
      list.innerHTML = html || '<div class="px-2.5 py-2 text-slate-400">No matches</div>';
      list.querySelectorAll('.opt').forEach(function (el) {
        el.addEventListener('click', function () {
          select.value = el.getAttribute('data-val');
          input.value = el.textContent;
          input.dataset.sel = el.textContent;
          list.classList.add('hidden');
          select.dispatchEvent(new Event('change'));
        });
      });
    }

    input.addEventListener('focus', function () {
      input.select();
      renderList(input.value === input.dataset.sel ? '' : input.value);
      list.classList.remove('hidden');
    });
    input.addEventListener('input', function () { renderList(input.value); list.classList.remove('hidden'); });
    document.addEventListener('click', function (e) { if (!wrap.contains(e.target)) list.classList.add('hidden'); });

    // Display setter used when options are (re)loaded or reset
    select._setDisplay = function (text) {
      input.value = text || '';
      input.dataset.sel = text || '';
    };
    select._clear = function () { input.value = ''; input.dataset.sel = ''; };
  }

  // ================= STATES =================
  function loadStates() {
    return fetch(API_BASE + '/api/states')
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (states) {
        var sel = document.getElementById('stateSelect');
        if (!sel) return;
        sel.innerHTML = '<option value="">Choose State / UT...</option>';
        states.forEach(function (s) {
          var o = document.createElement('option');
          o.value = s.state_id;
          o.textContent = s.state_name;
          sel.appendChild(o);
        });
        enhanceSelect(sel, 'Search state...');
      })
      .catch(function () {});
  }

  // ================= CONSTITUENCIES =================
  function loadConstituencies(sid) {
    var sel = document.getElementById('constituencySelect');
    if (!sel) return;
    if (!sel.dataset.enh) enhanceSelect(sel, 'Search member...');
    sel.innerHTML = '<option value="">All Members</option>';
    if (sel._setDisplay) sel._setDisplay('All Members');
    if (!sid) { sel.disabled = true; return; }
    sel.disabled = false;
    fetch(API_BASE + '/api/constituencies?state_id=' + sid)
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (items) {
        items.sort(function (a, b) {
          var am = (a.member_type === 'MP') ? 0 : 1;
          var bm = (b.member_type === 'MP') ? 0 : 1;
          if (am !== bm) return am - bm;
          return (b.work_count || 0) - (a.work_count || 0);
        });
        items.forEach(function (c) {
          var o = document.createElement('option');
          o.value = c.member_id || c.constituency_id;
          o.textContent = c.constituency_name + (c.member_type ? ' · ' + c.member_type : '');
          sel.appendChild(o);
        });
        if (sel._setDisplay) sel._setDisplay('All Members');
      })
      .catch(function () {});
  }

  // ================= WORKS =================
  function loadWorks() {
    if (!stateId) { showEmpty(); return; }
    var grid = document.getElementById('worksGrid');
    if (grid) grid.innerHTML = '<div class="col-span-full text-center py-10 text-slate-400 text-sm">Loading works...</div>';
    // Show loading placeholders instead of stale "0" values
    setText('resultCountLabel', 'Loading...');
    setText('constituencyContextLabel', '');
    setText('showingCountSummary', 'Loading...');
    setHTML('worksPagination', '');
    showResults(true);

    var url = API_BASE + '/api/works?page=' + page + '&page_size=' + pageSize + '&sort=' + sortBy + '&state_id=' + stateId + '&category=' + statusFilter;
    if (memberId) url += '&member_id=' + memberId;
    if (categoryFilter) url += '&work_category=' + encodeURIComponent(categoryFilter);
    if (searchQ) url += '&q=' + encodeURIComponent(searchQ);

    fetch(url)
      .then(function (r) { if (!r.ok) throw new Error('works'); return r.json(); })
      .then(function (data) { renderWorks(data); })
      .catch(function () {
        if (grid) grid.innerHTML = '<div class="col-span-full text-center py-10 text-rose-400 text-sm">Failed to load works. Please try again.</div>';
      });
  }

  function renderWorks(data) {
    var items = data.items || [];
    var total = data.total || 0;
    totalPages = data.total_pages || 1;
    var pg = data.page || 1;
    var grid = document.getElementById('worksGrid');
    if (!grid) return;

    setText('resultCountLabel', fmtNum(total) + ' Works Registered');
    var ctx = 'All Members';
    var csel = document.getElementById('constituencySelect');
    if (csel && csel.value) { var o = csel.options[csel.selectedIndex]; if (o) ctx = o.textContent; }
    setText('constituencyContextLabel', 'Member of Parliament: ' + ctx);

    if (items.length === 0) {
      grid.innerHTML = '<div class="col-span-full text-center py-10 text-slate-400 text-sm">No works match the current filters.</div>';
      setText('showingCountSummary', 'No works');
      setHTML('worksPagination', '');
      return;
    }

    var html = '';
    items.forEach(function (w) {
      var st = (w.status || '').toLowerCase();
      var sc = 'slate', label = w.status || 'Unknown';
      if (st === 'completed') { sc = 'emerald'; label = 'COMPLETED'; }
      else if (st === 'ongoing' || st === 'in progress' || st === 'inprogress' || st === 'active') { sc = 'blue'; label = 'ONGOING'; }
      else if (st === 'pending' || st === 'recommended' || st === 'sanctioned' || st === 'proposed') { sc = 'amber'; label = 'PENDING'; }
      var name = cleanName(w);
      var desc = name || 'MPLADS Works (Unnamed)';
      if (desc.length > 130) desc = desc.substring(0, 130) + '...';
      var comp = Number(w.completion_percentage) || 0;
      var nameCls = name ? 'text-slate-900' : 'text-slate-400 italic';
      html += '<a class="bg-white border border-slate-200 rounded-xl p-4 shadow-2xs hover:shadow-md hover:border-blue-300 transition-all cursor-pointer flex flex-col justify-between" href="workdetail.html?id=' + w.work_id + '">' +
        '<div><div class="flex items-start justify-between gap-2 mb-2">' +
        '<span class="text-[10px] font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">' + (w.work_category || 'General') + '</span>' +
        '<span class="text-[10px] font-extrabold px-2 py-0.5 rounded border bg-' + sc + '-100 text-' + sc + '-800 border-' + sc + '-200">' + label + '</span></div>' +
        '<div class="font-bold ' + nameCls + ' text-xs leading-snug">' + desc + '</div>' +
        '<div class="text-[11px] text-slate-500 mt-1">' + (w.constituency_name || '') + '</div>' +
        '<div class="grid grid-cols-3 gap-1.5 mt-3 text-center">' +
        '<div class="bg-slate-50 border border-slate-100 rounded-lg px-1.5 py-1.5"><div class="text-[9px] font-semibold uppercase text-slate-400">Rec</div><div class="text-xs font-bold text-slate-900 mt-0.5">' + fmtCr(w.recommended_amount) + '</div></div>' +
        '<div class="bg-slate-50 border border-slate-100 rounded-lg px-1.5 py-1.5"><div class="text-[9px] font-semibold uppercase text-slate-400">San</div><div class="text-xs font-bold text-slate-900 mt-0.5">' + fmtCr(w.sanction_amount) + '</div></div>' +
        '<div class="bg-slate-50 border border-slate-100 rounded-lg px-1.5 py-1.5"><div class="text-[9px] font-semibold uppercase text-slate-400">Exp</div><div class="text-xs font-bold text-slate-900 mt-0.5">' + fmtCr(w.expenditure_amount) + '</div></div>' +
        '</div></div>' +
        '<div class="flex items-center gap-2 mt-3 pt-2 border-t border-slate-100">' +
        '<span class="text-[10px] font-semibold text-slate-500 whitespace-nowrap">Progress</span>' +
        '<div class="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + getColor(comp) + '-500 rounded-full" style="width:' + Math.min(comp, 100) + '%"></div></div>' +
        '<span class="text-[10px] font-bold text-slate-700">' + fmtPct(comp) + '</span></div></a>';
    });
    grid.innerHTML = html;

    var start = (pg - 1) * pageSize;
    var end = start + items.length;
    setText('showingCountSummary', 'Showing ' + (start + 1) + '-' + end + ' of ' + fmtNum(total) + ' works');

    var btns = '';
    btns += '<button class="wk-page px-2.5 py-1 rounded-md border border-slate-200 bg-white text-xs font-medium' + (pg <= 1 ? ' text-slate-300 cursor-not-allowed' : ' text-slate-700 hover:bg-slate-50') + '" data-page="' + (pg - 1) + '">Prev</button>';
    var from = Math.max(1, pg - 2), to = Math.min(totalPages, from + 4);
    if (to - from < 4) from = Math.max(1, to - 4);
    for (var i = from; i <= to; i++) {
      btns += i === pg
        ? '<button class="wk-page w-7 h-7 rounded-md bg-blue-600 text-white font-semibold text-xs" data-page="' + i + '">' + i + '</button>'
        : '<button class="wk-page w-7 h-7 rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 font-medium text-xs" data-page="' + i + '">' + i + '</button>';
    }
    btns += '<button class="wk-page px-2.5 py-1 rounded-md border border-slate-200 bg-white text-xs font-medium' + (pg >= totalPages ? ' text-slate-300 cursor-not-allowed' : ' text-slate-700 hover:bg-slate-50') + '" data-page="' + (pg + 1) + '">Next</button>';
    setHTML('worksPagination', btns);
    document.querySelectorAll('.wk-page').forEach(function (b) {
      b.addEventListener('click', function () {
        var p = parseInt(b.getAttribute('data-page'));
        if (p >= 1 && p <= totalPages && p !== pg) { page = p; loadWorks(); }
      });
    });
  }

  function showEmpty() {
    var e = document.getElementById('exploreEmptyState'); if (e) e.classList.remove('hidden');
    var r = document.getElementById('exploreResultsContainer'); if (r) r.classList.add('hidden');
    var btn = document.getElementById('resetExploreBtn'); if (btn) btn.classList.add('hidden');
  }
  function showResults(on) {
    var e = document.getElementById('exploreEmptyState'); if (e) e.classList.add('hidden');
    var r = document.getElementById('exploreResultsContainer'); if (r) r.classList.toggle('hidden', !on);
    var btn = document.getElementById('resetExploreBtn'); if (btn) btn.classList.remove('hidden');
  }

  // ================= SUMMARY =================
  function loadSummary() {
    var cached = null;
    try { var raw = localStorage.getItem(CACHE_KEY); if (raw) { var cc = JSON.parse(raw); if (Date.now() - cc.ts < CACHE_TTL) cached = cc.data; } } catch (e) {}
    if (cached) { renderSummary(cached); }
    else { showSummarySkeleton(true); }
    fetch(API_BASE + '/api/projects/summary')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d) {
          try { localStorage.setItem(CACHE_KEY, JSON.stringify({ data: d, ts: Date.now() })); } catch (e) {}
          renderSummary(d);
          showSummarySkeleton(false);
        }
      })
      .catch(function () { showSummarySkeleton(false, true); });
  }

  function showSummarySkeleton(on, error) {
    var ids = ['kpiTotalWorks','kpiRecommended','kpiSanctioned','kpiCompleted','kpiOngoing','kpiPending','kpiCompletionRate','kpiSanctionConversion'];
    ids.forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      if (on) {
        el.innerHTML = '<span class="skeleton inline-block align-middle" style="width:64px;height:22px"></span>';
      }
    });
    // Banner
    var banner = document.getElementById('projectSummaryBanner');
    if (banner) {
      banner.hidden = false;
      if (on) {
        banner.className = 'flex items-center gap-2 text-xs text-slate-500';
        banner.innerHTML =
          '<svg class="animate-spin h-3.5 w-3.5 text-blue-600" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>' +
          '<span class="font-semibold text-slate-700">Loading project analytics…</span>';
      } else if (error) {
        banner.className = 'section-error';
        banner.innerHTML =
          '<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>' +
          '<span>Could not load project analytics. Charts below may be incomplete.</span>' +
          '<button type="button" id="retrySummaryBtn">Retry</button>';
        var btn = document.getElementById('retrySummaryBtn');
        if (btn) btn.addEventListener('click', function () { loadSummary(); });
      } else {
        // `hidden` attribute removes it from the space-y sibling chain so
        // there is no extra top gap once analytics load.
        banner.className = 'hidden';
        banner.hidden = true;
        banner.innerHTML = '';
      }
    }
  }

  function renderSummary(s) {
    setText('kpiTotalWorks', fmtNum(s.total_works));
    setText('kpiRecommended', fmtNum(s.recommended_works));
    setText('kpiSanctioned', fmtNum(s.sanctioned_works));
    setText('kpiCompleted', fmtNum(s.completed_works));
    setText('kpiOngoing', fmtNum(s.ongoing_works));
    setText('kpiPending', fmtNum(s.pending_works));
    setText('kpiCompletionRate', fmtPct(s.completion_rate_pct));
    var conv = s.recommended_works ? (s.sanctioned_works / s.recommended_works * 100) : 0;
    setText('kpiSanctionConversion', fmtPct(conv));

    renderTreemap(s.categories || []);
    renderDonut(s);
    renderFunnel(s);
    renderMilestones(s.milestones || [], s.total_works);
    renderDuration(s.duration || [], s.total_works);
    renderAge(s.age || [], s.total_works);
    renderCost(s.cost || [], s.total_works);
    populateCategoryFilter(s.categories || []);
  }

  function populateCategoryFilter(cats) {
    var sel = document.getElementById('workCategoryFilter');
    if (!sel || sel.dataset.populated) return;
    sel.dataset.populated = '1';
    cats.forEach(function (c) {
      if (!c.category) return;
      var o = document.createElement('option');
      o.value = c.category;
      o.textContent = c.category + ' (' + fmtNum(c.count) + ')';
      sel.appendChild(o);
    });
  }

  function renderTreemap(cats) {
    var el = document.getElementById('sectorTreemap');
    if (!el) return;
    if (!cats.length) { el.innerHTML = '<div class="text-sm text-slate-400 text-center py-6">No category data.</div>'; return; }
    var top = cats.slice(0, 10);
    var total = top.reduce(function (a, b) { return a + b.count; }, 0) || 1;
    var colors = ['blue', 'indigo', 'emerald', 'cyan', 'amber', 'orange', 'teal', 'violet', 'rose', 'sky'];
    var html = '<div class="space-y-3 pt-1">';
    top.forEach(function (c, i) {
      var share = c.count / total * 100;
      var col = colors[i % colors.length];
      html += '<div class="flex items-center gap-3 text-xs">' +
        '<span class="w-2.5 h-2.5 rounded-full bg-' + col + '-500 flex-shrink-0"></span>' +
        '<div class="w-40 sm:w-52 font-medium text-slate-700 truncate" title="' + c.category + '">' + c.category + '</div>' +
        '<div class="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + col + '-500 rounded-full transition-all duration-700" style="width:' + Math.min(share, 100) + '%"></div></div>' +
        '<div class="w-20 text-right font-semibold text-slate-900">' + fmtNum(c.count) + '</div>' +
        '<div class="w-24 text-right text-slate-500">' + fmtCr(c.amount) + '</div>' +
        '<div class="w-12 text-right text-slate-400">' + fmtPct(share) + '</div></div>';
    });
    html += '</div>';
    el.innerHTML = html;
  }

  function renderDonut(s) {
    var total = s.total_works || 1;
    var completed = s.completed_works || 0, ongoing = s.ongoing_works || 0, pending = s.pending_works || 0;
    var circ = 408.4;
    var cp = completed / total, op = ongoing / total, pp = pending / total;
    var dc = document.getElementById('pdCompleted'), do2 = document.getElementById('pdOngoing'), dp = document.getElementById('pdPending');
    if (dc) dc.setAttribute('stroke-dashoffset', '0');
    if (do2) do2.setAttribute('stroke-dashoffset', '-' + (cp * circ).toFixed(2));
    if (dp) dp.setAttribute('stroke-dashoffset', '-' + ((cp + op) * circ).toFixed(2));
    var segs = [{ el: dc, len: cp * circ }, { el: do2, len: op * circ }, { el: dp, len: pp * circ }];
    if (window.ChartAnim) {
      window.ChartAnim.whenVisible(dc || dp, 'projectDonut', function () {
        window.ChartAnim.drawDonut(segs, circ, { duration: 900 });
      });
    } else {
      segs.forEach(function (x) { if (x.el) x.el.setAttribute('stroke-dasharray', x.len + ' ' + circ); });
    }
    setText('pdCenter', fmtNum(s.total_works));
    setText('donutTotalTag', fmtNum(s.total_works) + ' Works');
    var legend = [
      { label: 'Completed', count: completed, pct: cp * 100, color: 'emerald' },
      { label: 'Ongoing', count: ongoing, pct: op * 100, color: 'blue' },
      { label: 'Pending', count: pending, pct: pp * 100, color: 'amber' },
    ];
    var lh = '';
    legend.forEach(function (x) {
      lh += '<div class="flex items-center justify-between gap-4 p-2.5 rounded-lg bg-' + x.color + '-50/60 border border-' + x.color + '-100">' +
        '<div class="flex items-center gap-2"><span class="w-3 h-3 rounded-full bg-' + x.color + '-500"></span>' +
        '<span class="font-semibold text-slate-800 text-xs">' + x.label + '</span></div>' +
        '<div class="text-right"><div class="font-bold text-slate-900 text-xs">' + fmtNum(x.count) + '</div>' +
        '<div class="text-[10px] text-' + x.color + '-700 font-semibold">' + fmtPct(x.pct) + '</div></div></div>';
    });
    setHTML('pdLegend', lh);
  }

  function renderFunnel(s) {
    var el = document.getElementById('pipelineFunnel');
    if (!el) return;
    var total = s.total_works || 1;
    var steps = [
      { label: 'Recommended', count: s.recommended_works || total, color: 'indigo' },
      { label: 'Sanctioned', count: s.sanctioned_works || 0, color: 'sky' },
      { label: 'Ongoing', count: s.ongoing_works || 0, color: 'blue' },
      { label: 'Completed', count: s.completed_works || 0, color: 'emerald' },
    ];
    var html = '';
    steps.forEach(function (st, i) {
      var pct = st.count / total * 100;
      html += '<div class="p-2.5 rounded-lg border border-' + st.color + '-200 bg-' + st.color + '-50/40">' +
        '<div class="flex items-center justify-between text-xs">' +
        '<div class="flex items-center gap-2"><span class="w-5 h-5 rounded-full bg-white/80 text-' + st.color + '-700 text-[10px] font-bold flex items-center justify-center">' + (i + 1) + '</span>' +
        '<span class="font-bold text-' + st.color + '-950">' + st.label + '</span></div>' +
        '<div class="text-right"><span class="text-xs font-bold text-' + st.color + '-950">' + fmtNum(st.count) + '</span>' +
        '<span class="text-[10px] text-' + st.color + '-700 block">' + fmtPct(pct) + '</span></div></div>' +
        '<div class="w-full h-2 bg-white/70 rounded-full overflow-hidden mt-1.5"><div class="h-full bg-' + st.color + '-500 rounded-full transition-all duration-700" style="width:' + Math.min(pct, 100) + '%"></div></div></div>';
    });
    el.innerHTML = html;
  }

  function renderMilestones(m, total) {
    var el = document.getElementById('milestoneChart');
    if (!el) return;
    var colors = ['emerald', 'teal', 'blue', 'amber', 'rose'];
    var t = total || 1;
    var html = '';
    m.forEach(function (x, i) {
      var pct = x.count / t * 100;
      var c = colors[i] || 'slate';
      html += '<div class="space-y-1"><div class="flex justify-between text-xs"><span class="font-semibold text-' + c + '-950">' + x.label + '</span>' +
        '<span class="font-bold text-' + c + '-700">' + fmtNum(x.count) + ' (' + fmtPct(pct) + ')</span></div>' +
        '<div class="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + c + '-500 rounded-full transition-all duration-700" style="width:' + Math.min(pct, 100) + '%"></div></div></div>';
    });
    el.innerHTML = html;
  }

  function renderDuration(d, total) {
    var el = document.getElementById('durationChart');
    if (!el) return;
    var t = total || 1;
    var max = Math.max.apply(null, d.map(function (x) { return x.count; }).concat([1]));
    var colors = ['emerald', 'sky', 'amber', 'rose'];
    var html = '';
    d.forEach(function (x, i) {
      var pct = x.count / t * 100;
      var height = (x.count / max) * 100;
      var c = colors[i] || 'slate';
      html += '<div class="flex-1 flex flex-col items-center gap-1.5 h-full justify-end">' +
        '<span class="text-[11px] font-bold text-' + c + '-700">' + fmtPct(pct) + '</span>' +
        '<span class="text-[10px] text-slate-500">' + fmtNum(x.count) + '</span>' +
        '<div class="w-full max-w-[48px] bg-' + c + '-500 rounded-t-lg transition-all duration-500" style="height:' + Math.max(height, 2) + '%"></div>' +
        '<span class="text-[10px] font-bold text-slate-700 text-center whitespace-nowrap">' + x.label + '</span></div>';
    });
    el.innerHTML = html;
    if (window.ChartAnim) {
      window.ChartAnim.whenVisible(el, 'projectDuration', function () {
        window.ChartAnim.growBars(el.querySelectorAll('.rounded-t-lg'), { stagger: 110, duration: 800 });
      });
    }
  }

  function renderAge(a, total) {
    var el = document.getElementById('ageChart');
    if (!el) return;
    var t = total || 1;
    var colors = ['emerald', 'blue', 'amber', 'rose'];
    var html = '';
    a.forEach(function (x, i) {
      var pct = x.count / t * 100;
      var c = colors[i] || 'slate';
      html += '<div class="space-y-1"><div class="flex justify-between text-xs"><span class="font-semibold text-slate-800">' + x.label + '</span>' +
        '<span class="font-bold text-' + c + '-700">' + fmtNum(x.count) + ' (' + fmtPct(pct) + ')</span></div>' +
        '<div class="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + c + '-500 rounded-full transition-all duration-700" style="width:' + Math.min(pct, 100) + '%"></div></div></div>';
    });
    el.innerHTML = html;
  }

  function renderCost(cst, total) {
    var el = document.getElementById('costChart');
    if (!el) return;
    var t = total || 1;
    var colors = ['emerald', 'sky', 'amber', 'violet'];
    var html = '';
    cst.forEach(function (x, i) {
      var pct = x.count / t * 100;
      var c = colors[i] || 'slate';
      html += '<div class="space-y-1"><div class="flex justify-between text-xs"><span class="font-semibold text-slate-800">' + x.label + '</span>' +
        '<span class="font-bold text-' + c + '-700">' + fmtNum(x.count) + ' (' + fmtPct(pct) + ')</span></div>' +
        '<div class="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-' + c + '-500 rounded-full transition-all duration-700" style="width:' + Math.min(pct, 100) + '%"></div></div></div>';
    });
    el.innerHTML = html;
  }

  // ================= INIT =================
  document.addEventListener('DOMContentLoaded', function () {
    var stateSel = document.getElementById('stateSelect');
    var constSel = document.getElementById('constituencySelect');
    var searchInput = document.getElementById('workFilterInput');
    var sortSel = document.getElementById('workSortSelect');
    var statusSel = document.getElementById('workStatusFilter');
    var catSel = document.getElementById('workCategoryFilter');
    var resetBtn = document.getElementById('resetExploreBtn');

    // Replace native selects with searchable inputs immediately (no flash)
    if (stateSel) { enhanceSelect(stateSel, 'Search state...'); if (stateSel._setDisplay) stateSel._setDisplay(''); }
    if (constSel) { enhanceSelect(constSel, 'Search member...'); if (constSel._setDisplay) constSel._setDisplay('All Members'); }

    function applyState() {
      stateId = stateSel ? stateSel.value : '';
      memberId = '';
      page = 1;
      if (!stateId) { showEmpty(); return; }
      loadConstituencies(stateId);
      if (searchInput) searchInput.disabled = false;
      if (sortSel) sortSel.disabled = false;
      if (statusSel) statusSel.disabled = false;
      if (catSel) catSel.disabled = false;
      loadWorks();
    }

    loadSummary();

    if (stateSel) stateSel.addEventListener('change', applyState);
    if (constSel) {
      constSel.addEventListener('change', function () {
        memberId = constSel.value;
        page = 1;
        loadWorks();
      });
    }
    if (statusSel) {
      statusSel.addEventListener('change', function () { statusFilter = statusSel.value; page = 1; loadWorks(); });
    }
    if (catSel) {
      catSel.addEventListener('change', function () { categoryFilter = catSel.value; page = 1; loadWorks(); });
    }
    if (searchInput) {
      var deb = null;
      searchInput.addEventListener('input', function () {
        clearTimeout(deb);
        deb = setTimeout(function () { searchQ = searchInput.value.trim(); page = 1; loadWorks(); }, 300);
      });
    }
    if (sortSel) {
      sortSel.addEventListener('change', function () { sortBy = sortSel.value; page = 1; loadWorks(); });
    }
    if (resetBtn) {
      resetBtn.addEventListener('click', function () {
        stateId = ''; memberId = ''; searchQ = ''; sortBy = 'highest_comp'; statusFilter = 'all'; categoryFilter = ''; page = 1;
        if (stateSel) { stateSel.value = ''; if (stateSel._clear) stateSel._clear(); }
        if (constSel) { constSel.innerHTML = '<option value="">All Members</option>'; constSel.disabled = true; if (constSel._setDisplay) constSel._setDisplay('All Members'); }
        if (searchInput) { searchInput.value = ''; searchInput.disabled = true; }
        if (sortSel) { sortSel.value = 'highest_comp'; sortSel.disabled = true; }
        if (statusSel) { statusSel.value = 'all'; statusSel.disabled = true; }
        if (catSel) { catSel.value = ''; catSel.disabled = true; }
        showEmpty();
      });
    }

    // KPI info popup (was previously inline)
    var popup = document.getElementById('kpi-info-popup');
    if (popup) {
      var titleEl = document.getElementById('kpi-info-title');
      var descEl = document.getElementById('kpi-info-desc');
      var closeBtn = document.getElementById('kpi-info-close');
      var activeBtn = null;
      function positionPopup(btn) {
        var r = btn.getBoundingClientRect();
        popup.style.top = (r.bottom + 8) + 'px';
        popup.style.left = Math.min(r.left, window.innerWidth - 280) + 'px';
      }
      document.querySelectorAll('.info-btn').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          if (activeBtn === btn) { popup.classList.add('hidden'); activeBtn = null; return; }
          if (titleEl) titleEl.textContent = btn.getAttribute('data-title') || '';
          if (descEl) descEl.textContent = btn.getAttribute('data-desc') || '';
          popup.classList.remove('hidden');
          positionPopup(btn);
          activeBtn = btn;
        });
      });
      if (closeBtn) closeBtn.addEventListener('click', function () { popup.classList.add('hidden'); activeBtn = null; });
      document.addEventListener('click', function (e) { if (!popup.contains(e.target)) { popup.classList.add('hidden'); activeBtn = null; } });
      window.addEventListener('scroll', function () { if (activeBtn) positionPopup(activeBtn); }, { passive: true });
    }

    // Deep-link / test support: ?state=<id>&category=<status>&member_id=<id>
    loadStates().then(function () {
      var params = new URLSearchParams(window.location.search);
      var ps = params.get('state');
      var pc = params.get('category');
      var pm = params.get('member_id');
      if (pc && statusSel) { statusFilter = pc; statusSel.value = pc; }
      if (ps && stateSel) {
        stateSel.value = ps;
        if (stateSel._setDisplay) {
          var opt = stateSel.options[stateSel.selectedIndex];
          if (opt) stateSel._setDisplay(opt.textContent);
        }
        applyState();
        if (pm) {
          var tries = 0;
          var iv = setInterval(function () {
            tries++;
            if (constSel && constSel.querySelector('option[value="' + pm + '"]')) {
              clearInterval(iv);
              constSel.value = pm;
              if (constSel._setDisplay) { var o2 = constSel.options[constSel.selectedIndex]; if (o2) constSel._setDisplay(o2.textContent); }
              memberId = pm; page = 1; loadWorks();
            } else if (tries > 20) { clearInterval(iv); }
          }, 150);
        }
      }
    });
  });
})();

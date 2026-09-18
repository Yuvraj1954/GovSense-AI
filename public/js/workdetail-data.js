(function () {
  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';

  function fmtNum(n) {
    if (n == null || isNaN(n)) return '—';
    return Number(n).toLocaleString('en-IN');
  }

  function fmtCr(n) {
    if (n == null || isNaN(n)) return '—';
    var val = Number(n);
    if (val >= 1e7) return '₹' + (val / 1e7).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Cr';
    if (val >= 1e5) return '₹' + (val / 1e5).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' L';
    return '₹' + val.toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  function fmtPct(n) {
    if (n == null || isNaN(n)) return '—';
    return Number(n).toFixed(1) + '%';
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
    var el = document.getElementById('workLoadingState');
    if (el) el.classList.toggle('hidden', state !== 'loading');
    var err = document.getElementById('workErrorState');
    if (err) err.classList.toggle('hidden', state !== 'error');
    var main = document.getElementById('workMainContent');
    if (main) main.classList.toggle('hidden', state !== 'main');
  }

  function getStatusColor(status) {
    var s = (status || '').toLowerCase();
    if (s === 'completed' || s === 'complete') return 'emerald';
    if (s === 'ongoing' || s === 'in progress' || s === 'active') return 'blue';
    if (s === 'pending' || s === 'recommended' || s === 'sanctioned') return 'amber';
    return 'slate';
  }

  function formatDate(d) {
    if (!d) return '—';
    var s = String(d).substring(0, 10);
    if (s === 'NA' || s === 'N/A' || s.length < 8) return '—';
    try {
      var dt = new Date(s);
      var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      return dt.getDate() + ' ' + months[dt.getMonth()] + ' ' + dt.getFullYear();
    } catch (e) { return s; }
  }

  function getWorkId() {
    var params = new URLSearchParams(window.location.search);
    return params.get('work_id') || params.get('id');
  }

  function renderBenchmarkChart(w) {
    var container = document.getElementById('workBenchmarkChart');
    if (!container) return;
    var peerGroup = w.benchmark_peer_group || '';
    setText('workPeerGroup', peerGroup ? 'Peer Group: ' + peerGroup.replace(/_/g, ' ') : 'No peer group available');

    var costP25 = w.cost_p25, costP50 = w.cost_p50, costP75 = w.cost_p75, costP90 = w.cost_p90;
    var durP25 = w.duration_p25, durP50 = w.duration_p50, durP75 = w.duration_p75, durP90 = w.duration_p90;
    var actualCost = w.sanction_amount || w.recommended_amount || 0;
    var actualDur = w.execution_days || 0;

    var hasCost = costP50 != null && actualCost > 0;
    var hasDur = durP50 != null && actualDur > 0;

    if (!hasCost && !hasDur) {
      container.innerHTML = '<div class="text-xs text-slate-400 text-center py-4">No benchmark data available for this work.</div>';
      return;
    }

    function gaugeHtml(label, value, fmtValue, p25, p50, p90, color) {
      var max = p90 * 1.3 || value * 1.5 || 1;
      var pct = Math.min(value / max * 100, 100);
      var p25w = (p25 / max * 100);
      var p50w = (p50 / max * 100);
      var p90w = (p90 / max * 100);
      var status = value <= p25 ? 'Below Average' : value <= p50 ? 'Average' : value <= p90 ? 'Above Average' : 'Outlier';
      var statusColor = value <= p25 ? 'emerald' : value <= p50 ? 'slate' : value <= p90 ? 'amber' : 'rose';
      return '<div class="p-2.5 rounded-lg border border-slate-100 bg-slate-50/60">' +
        '<div class="flex items-center justify-between mb-2">' +
          '<span class="text-[11px] font-semibold text-slate-600">' + label + '</span>' +
          '<span class="text-[10px] font-bold ' + statusColor + '-700 bg-' + statusColor + '-50 px-1.5 py-0.5 rounded border border-' + statusColor + '-200">' + status + '</span>' +
        '</div>' +
        '<div class="text-base font-black text-slate-900 mb-2">' + fmtValue + '</div>' +
        '<div class="relative h-2 bg-slate-200 rounded-full overflow-hidden">' +
          '<div class="absolute inset-y-0 left-0 ' + color + ' rounded-full transition-all duration-700" style="width:' + pct + '%"></div>' +
          '<div class="absolute top-0 bottom-0 w-px bg-slate-800" style="left:' + p50w + '%" title="Median"></div>' +
        '</div>' +
        '<div class="flex justify-between text-[9px] text-slate-400 mt-1">' +
          '<span>P25: ' + (label === 'Cost' ? fmtCr(p25) : fmtNum(p25) + 'd') + '</span>' +
          '<span class="font-semibold text-slate-600">Med: ' + (label === 'Cost' ? fmtCr(p50) : fmtNum(p50) + 'd') + '</span>' +
          '<span>P90: ' + (label === 'Cost' ? fmtCr(p90) : fmtNum(p90) + 'd') + '</span>' +
        '</div>' +
      '</div>';
    }

    var html = '<div class="grid grid-cols-1 gap-2">';
    if (hasCost) html += gaugeHtml('Cost', actualCost, fmtCr(actualCost), costP25, costP50, costP90, 'bg-indigo-500');
    if (hasDur) html += gaugeHtml('Duration', actualDur, fmtNum(actualDur) + ' days', durP25, durP50, durP90, 'bg-cyan-500');
    html += '</div>';
    container.innerHTML = html;
  }

  function populateWork(w) {
    var status = w.status || 'Unknown';
    var statusColor = getStatusColor(status);

    setText('workTitle', w.work_description || w.activity_name || w.normalized_activity || 'Work Record');
    setText('workStatus', status.toUpperCase());
    var statusEl = document.getElementById('workStatus');
    if (statusEl) {
      statusEl.className = 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-' + statusColor + '-50 text-' + statusColor + '-700 border border-' + statusColor + '-200';
    }

    setText('workStateName', w.state_name || w.mp_state_name || '—');
    setText('workConstituency', w.constituency_name || ('Constituency #' + (w.constituency_id || '—')));
    setText('workMP', (w.member_name || '—') + (w.member_type ? ' (' + w.member_type + ')' : ''));
    setText('workCategory', w.work_category || w.normalized_activity || 'General');
    setText('workDescription', w.work_description || w.normalized_activity || 'No description available');

    setText('workActivity', w.normalized_activity || w.activity_name || '—');
    setText('workCategoryDetail', w.work_category || w.normalized_activity || '—');
    setText('workStateDetail', w.state_name || w.mp_state_name || '—');
    setText('workConstituencyDetail', w.constituency_name || ('Constituency #' + (w.constituency_id || '—')));
    setText('workRepresentative', (w.member_name || '—') + (w.member_type ? ' (' + w.member_type + ')' : ''));

    setText('workRecAmount', fmtCr(w.recommended_amount));
    setText('workSancAmount', fmtCr(w.sanction_amount));
    setText('workExpAmount', fmtCr(w.expenditure_amount));
    setText('workCompAmount', fmtCr(w.completion_amount));

    var compPct = Number(w.completion_percentage) || 0;
    setText('workCompPct', fmtPct(compPct));

    setText('workRecommendationDate', formatDate(w.recommendation_date));
    setText('workSanctionDate', formatDate(w.sanction_date));
    setText('workCompletionDate', formatDate(w.completion_date));

    setText('workSanctionDelay', w.sanction_delay_days != null ? Math.round(w.sanction_delay_days) + ' days' : '—');
    setText('workExecDays', w.execution_days != null ? Math.round(w.execution_days) + ' days' : '—');
    setText('workProjectAge', w.project_age_days != null ? Math.round(w.project_age_days) + ' days' : '—');

    setText('workIdDisplay', 'WORK ID: ' + (w.work_id || '—'));
    setText('workIdHeader', 'WORK ID: ' + (w.work_id || '—'));
    setText('workIdMeta', w.work_id || '—');
    setText('workIdBadge', '#' + (w.work_id || '—'));
    setText('workStatusMeta', w.status || '—');
    setText('workSanctionBadge', w.sanction_date ? 'Sanctioned: ' + formatDate(w.sanction_date) : '—');

    var riskLevel = (w.risk_level || 'N/A').toUpperCase();
    var riskColor = riskLevel === 'HIGH' ? 'rose' : riskLevel === 'MEDIUM' || riskLevel === 'MODERATE' ? 'amber' : 'emerald';
    var riskEl = document.getElementById('workRiskLevel');
    if (riskEl) {
      riskEl.textContent = riskLevel.replace(/_/g, ' ');
      riskEl.className = 'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-' + riskColor + '-50 text-' + riskColor + '-700 border border-' + riskColor + '-200';
    }
    setText('workRiskMeta', riskLevel.replace(/_/g, ' '));

    var fp = w.feature_fingerprint;
    setText('workFP', fp ? fp.substring(0, 16) + '…' : '—');

    setText('workRecToSanc', w.recommended_amount && w.sanction_amount ? fmtPct(Number(w.sanction_amount) / Number(w.recommended_amount) * 100) + ' of recommendation' : '—');

    var sanctioned = Number(w.sanction_amount) || 0;
    var expended = Number(w.expenditure_amount) || 0;
    var completed = Number(w.completion_amount) || 0;
    var allocated = Number(w.recommended_amount) || 0;

    var sancBar = document.getElementById('workSancBar');
    var sancBarFill = document.getElementById('workSancBarFill');
    if (sancBar) sancBar.textContent = fmtCr(sanctioned) + (allocated > 0 ? ' (' + fmtPct(sanctioned / allocated * 100) + ')' : '');
    if (sancBarFill) { sancBarFill.style.width = '0%'; requestAnimationFrame(function() { sancBarFill.classList.add('animate-bar-fill'); sancBarFill.style.width = (allocated > 0 ? Math.min(sanctioned / allocated * 100, 100) : 0) + '%'; }); }

    var expBar = document.getElementById('workExpBar');
    var expBarFill = document.getElementById('workExpBarFill');
    if (expBar) expBar.textContent = fmtCr(expended) + (sanctioned > 0 ? ' (' + fmtPct(expended / sanctioned * 100) + ')' : '');
    if (expBarFill) { expBarFill.style.width = '0%'; requestAnimationFrame(function() { expBarFill.classList.add('animate-bar-fill'); expBarFill.style.width = (sanctioned > 0 ? Math.min(expended / sanctioned * 100, 100) : 0) + '%'; }); }

    var compBar = document.getElementById('workCompBar');
    var compBarFill = document.getElementById('workCompBarFill');
    if (compBar) compBar.textContent = fmtCr(completed) + (sanctioned > 0 ? ' (' + fmtPct(compPct) + ')' : '');
    if (compBarFill) { compBarFill.style.width = '0%'; requestAnimationFrame(function() { compBarFill.classList.add('animate-bar-fill'); compBarFill.style.width = Math.min(compPct, 100) + '%'; }); }

    var unexpended = allocated - expended;
    setText('workUnexpended', fmtCr(unexpended > 0 ? unexpended : 0));

    setText('workSanctionDelayHealth', w.sanction_delay_days != null ? Math.round(w.sanction_delay_days) + ' days' : '—');
    setText('workExecDaysHealth', w.execution_days != null ? Math.round(w.execution_days) + ' days' : '—');
    setText('workProjectAgeHealth', w.project_age_days != null ? Math.round(w.project_age_days) + ' days' : '—');
    setText('workCostPercentile', w.cost_percentile != null ? 'P' + w.cost_percentile + (w.cost_status ? ' (' + w.cost_status + ')' : '') : '—');
    setText('workDurationPercentile', w.duration_percentile != null ? 'P' + w.duration_percentile + (w.duration_status ? ' (' + w.duration_status + ')' : '') : '—');

    var healthStatus = document.getElementById('workHealthStatus');
    if (healthStatus) {
      var hText = riskLevel === 'HIGH' ? 'At Risk' : riskLevel === 'MEDIUM' || riskLevel === 'MODERATE' ? 'Watch' : 'Nominal';
      var hColor = riskLevel === 'HIGH' ? 'rose' : riskLevel === 'MEDIUM' || riskLevel === 'MODERATE' ? 'amber' : 'emerald';
      healthStatus.textContent = hText;
      healthStatus.className = 'text-[10px] font-semibold bg-' + hColor + '-50 text-' + hColor + '-700 border border-' + hColor + '-200 px-1.5 py-0.5 rounded';
    }

    var riskFlags = w.risk_flags || [];
    var flagsContainer = document.getElementById('workRiskFlags');
    var flagsList = document.getElementById('workRiskFlagsList');
    if (riskFlags.length > 0 && flagsContainer && flagsList) {
      flagsContainer.classList.remove('hidden');
      flagsList.innerHTML = riskFlags.map(function(f) {
        return '<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">' + f.replace(/_/g, ' ') + '</span>';
      }).join('');
    }

    var timeline = document.getElementById('workTimeline');
    if (timeline) {
      var items = [];
      if (w.recommendation_date) items.push({ label: 'Recommendation', date: formatDate(w.recommendation_date), color: 'emerald', sub: 'Proposed by ' + (w.member_name || 'Representative') });
      if (w.sanction_date) items.push({ label: 'Administrative Sanction', date: formatDate(w.sanction_date), color: 'emerald', sub: fmtCr(w.sanction_amount) + ' approved' + (w.sanction_delay_days ? ' (' + Math.round(w.sanction_delay_days) + 'd delay)' : '') });
      if (w.expenditure_amount && Number(w.expenditure_amount) > 0) {
        var expDate = w.last_expenditure_date || w.first_expenditure_date;
        items.push({ label: 'Expenditure Recorded', date: expDate ? formatDate(expDate) : '—', color: 'emerald', sub: fmtCr(w.expenditure_amount) + ' disbursed' });
      }
      if (w.completion_date) items.push({ label: 'Completion', date: formatDate(w.completion_date), color: 'emerald', sub: fmtPct(compPct) + ' complete' });
      else items.push({ label: 'In Progress', date: 'Ongoing', color: 'amber', sub: fmtPct(compPct) + ' complete' });

      var thtml = '';
      items.forEach(function (it, i) {
        var isLast = i === items.length - 1;
        var dotColor = isLast && it.color === 'amber' ? 'bg-amber-400' : 'bg-emerald-500';
        thtml += '<div class="relative group timeline-item" style="animation-delay:' + (i * 120) + 'ms"><div class="absolute -left-6 top-0.5 w-4 h-4 rounded-full ' + dotColor + ' border-2 border-white shadow-xs flex items-center justify-center timeline-dot" style="animation-delay:' + (i * 120 + 100) + 'ms"><span class="w-1.5 h-1.5 rounded-full bg-white"></span></div>' +
          '<div><div class="flex items-center justify-between"><span class="font-bold text-slate-800">' + it.label + '</span><span class="text-[10px] font-mono text-slate-400">' + it.date + '</span></div>' +
          '<p class="text-[11px] text-slate-500 mt-0.5">' + it.sub + '</p></div></div>';
      });
      timeline.innerHTML = thtml;
    }

    renderBenchmarkChart(w);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var workId = getWorkId();
    if (!workId) {
      showState('error');
      setText('workErrorTitle', 'No work selected');
      setText('workErrorMsg', 'Please navigate from the Projects page to view a work record.');
      return;
    }

    showState('loading');

    fetch(API_BASE + '/api/works/detail/' + workId)
      .then(function (r) {
        if (!r.ok) throw new Error(r.status === 404 ? 'Work not found' : 'API error');
        return r.json();
      })
      .then(function (data) {
        populateWork(data);
        showState('main');
      })
      .catch(function (err) {
        showState('error');
        setText('workErrorTitle', 'Failed to load work data');
        setText('workErrorMsg', err.message || 'Please try again later.');
      });
  });
})();

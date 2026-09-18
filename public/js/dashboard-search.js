(function () {
  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  var statesList = null;
  var membersList = null;

  function esc(s) { return String(s == null ? '' : s); }

  function ensureStates() {
    if (statesList) return Promise.resolve(statesList);
    return fetch(API_BASE + '/api/states')
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (d) { statesList = d || []; return statesList; })
      .catch(function () { statesList = []; return statesList; });
  }

  function ensureMembers() {
    if (membersList) return Promise.resolve(membersList);
    return fetch(API_BASE + '/api/members/scatter?member_type=BOTH')
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (d) { membersList = d || []; return membersList; })
      .catch(function () { membersList = []; return membersList; });
  }

  function memberDetailHref(m) {
    var mt = m.member_type || m.member_type_field || 'MP';
    return 'mpdetail.html?member_id=' + encodeURIComponent(m.member_id) + '&member_type=' + encodeURIComponent(mt) + '&from=dashboard';
  }
  function stateDetailHref(id, name) {
    return 'statedetail.html?state_id=' + encodeURIComponent(id) + '&state=' + encodeURIComponent(name) + '&from=dashboard';
  }

  function render(members, states, q, dropdownId) {
    var dropdown = document.getElementById(dropdownId);
    if (!dropdown) return;
    var html = '';
    if (members.length) {
      html += '<div class="p-1 border-b border-slate-100"><div class="px-2 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">Members of Parliament</div>';
      members.forEach(function (m) {
        var href = memberDetailHref(m);
        var mt = m.member_type || m.member_type_field || '';
        var house = m.house_name || '';
        var cons = m.constituency_name || '';
        var works = m.total_works || 0;
        var parts = [mt];
        if (house) parts.push(house);
        if (cons) parts.push(cons);
        else if (m.state_name) parts.push(m.state_name);
        var extra = parts.join(' · ');
        if (works) extra += ' (' + works + ' works)';
        html += '<a class="flex items-center justify-between px-2.5 py-1.5 hover:bg-slate-50 rounded cursor-pointer transition" href="' + href + '">' +
          '<span class="font-medium text-slate-800">' + esc(m.member_name) + '</span>' +
          '<span class="text-[10px] text-slate-400">' + esc(extra) + '</span></a>';
      });
      html += '</div>';
    }
    if (states.length) {
      html += '<div class="p-1 bg-slate-50/50"><div class="px-2 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">States &amp; Union Territories</div>';
      states.forEach(function (s) {
        var href = stateDetailHref(s.state_id, s.state_name);
        html += '<a class="flex items-center justify-between px-2.5 py-1.5 hover:bg-white rounded cursor-pointer transition" href="' + href + '">' +
          '<span class="font-medium text-slate-700">' + esc(s.state_name) + '</span>' +
          '<span class="text-[10px] text-slate-400">State / UT</span></a>';
      });
      html += '</div>';
    }
    if (!members.length && !states.length) {
      html = '<div class="px-3 py-2 text-slate-400">No results for "' + esc(q) + '"</div>';
    }
    dropdown.innerHTML = html;
    dropdown.classList.remove('hidden');
  }

  function doSearch(q, dropdownId) {
    var query = q.trim();
    if (query.length < 1) return Promise.resolve();
    var lower = query.toLowerCase();
    var memberPromise = ensureMembers().then(function (all) {
      if (!all || !all.length) {
        return fetch(API_BASE + '/api/members/scatter?member_type=BOTH')
          .then(function (r) { return r.ok ? r.json() : []; })
          .then(function (d) { membersList = d || []; return membersList; })
          .catch(function () { return []; })
          .then(function (fresh) {
            return fresh.filter(function (m) {
              return (m.member_name || '').toLowerCase().indexOf(lower) !== -1;
            }).slice(0, 6);
          });
      }
      return all.filter(function (m) {
        return (m.member_name || '').toLowerCase().indexOf(lower) !== -1;
      }).slice(0, 6);
    });
    var statePromise = ensureStates().then(function (all) {
      return all.filter(function (s) { return (s.state_name || '').toLowerCase().indexOf(lower) !== -1; }).slice(0, 5);
    });
    return Promise.all([memberPromise, statePromise]).then(function (res) {
      render(res[0], res[1], query, dropdownId);
    });
  }

  function bindSearch(inputId, dropdownId, clearBtnId, containerId) {
    var input = document.getElementById(inputId);
    var dropdown = document.getElementById(dropdownId);
    var clearBtn = document.getElementById(clearBtnId);
    var container = document.getElementById(containerId);
    if (!input || !dropdown) return;

    ensureStates();
    ensureMembers();
    var deb = null;
    var seq = 0;

    input.addEventListener('input', function () {
      var val = input.value;
      if (val.trim().length > 0) { if (clearBtn) clearBtn.classList.remove('hidden'); }
      else { if (clearBtn) clearBtn.classList.add('hidden'); dropdown.classList.add('hidden'); return; }
      clearTimeout(deb);
      var my = ++seq;
      deb = setTimeout(function () { doSearch(val, dropdownId).then(function () { if (my !== seq) { /* stale */ } }); }, 220);
    });

    input.addEventListener('focus', function () {
      if (input.value.trim().length > 0) doSearch(input.value, dropdownId);
    });

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        var first = dropdown.querySelector('a[href]');
        if (first) window.location.href = first.getAttribute('href');
      }
      if (e.key === 'Escape') { dropdown.classList.add('hidden'); input.blur(); }
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        input.value = ''; clearBtn.classList.add('hidden'); dropdown.classList.add('hidden'); input.focus();
      });
    }

    document.addEventListener('click', function (e) {
      if (container && !container.contains(e.target)) dropdown.classList.add('hidden');
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    ensureStates();
    ensureMembers();

    // Desktop search (in header)
    bindSearch('headerSearchInputDesktop', 'searchResultsDropdownDesktop', 'clearSearchBtnDesktop', 'searchContainerDesktop');
    // Mobile search (in scrollable section)
    bindSearch('headerSearchInput', 'searchResultsDropdown', 'clearSearchBtn', 'searchContainer');

    // Deep-link: ?search=<query> pre-fills and runs the search
    var pre = new URLSearchParams(window.location.search).get('search');
    if (pre) {
      var desktopInput = document.getElementById('headerSearchInputDesktop');
      var mobileInput = document.getElementById('headerSearchInput');
      var activeInput = desktopInput || mobileInput;
      if (activeInput) {
        activeInput.value = pre;
        var activeClear = document.getElementById(activeInput === desktopInput ? 'clearSearchBtnDesktop' : 'clearSearchBtn');
        if (activeClear) activeClear.classList.remove('hidden');
        var activeDropdown = activeInput === desktopInput ? 'searchResultsDropdownDesktop' : 'searchResultsDropdown';
        doSearch(pre, activeDropdown);
      }
    }
  });
})();

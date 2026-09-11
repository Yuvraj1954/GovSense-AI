(function () {
  var API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  var statesList = null;

  function esc(s) { return String(s == null ? '' : s); }

  function ensureStates() {
    if (statesList) return Promise.resolve(statesList);
    return fetch(API_BASE + '/api/states')
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (d) { statesList = d || []; return statesList; })
      .catch(function () { statesList = []; return statesList; });
  }

  function memberDetailHref(m) {
    return 'mpdetail.html?member_id=' + encodeURIComponent(m.member_id) + '&from=dashboard';
  }
  function stateDetailHref(name) {
    return 'statedetail.html?state=' + encodeURIComponent(name) + '&from=dashboard';
  }

  function render(members, states, q) {
    var dropdown = document.getElementById('searchResultsDropdown');
    if (!dropdown) return;
    var html = '';
    if (members.length) {
      html += '<div class="p-1 border-b border-slate-100"><div class="px-2 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">Members of Parliament</div>';
      members.forEach(function (m) {
        var href = memberDetailHref(m);
        var mt = m.member_type || m.member_type_field || '';
        html += '<a class="flex items-center justify-between px-2.5 py-1.5 hover:bg-slate-50 rounded cursor-pointer transition" href="' + href + '">' +
          '<span class="font-medium text-slate-800">' + esc(m.member_name) + '</span>' +
          '<span class="text-[10px] text-slate-400">' + esc(mt) + ' · ' + esc(m.state_name || '') + '</span></a>';
      });
      html += '</div>';
    }
    if (states.length) {
      html += '<div class="p-1 bg-slate-50/50"><div class="px-2 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">States &amp; Union Territories</div>';
      states.forEach(function (s) {
        var href = stateDetailHref(s.state_name);
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

  function doSearch(q) {
    var query = q.trim();
    if (query.length < 1) return Promise.resolve();
    var memberPromise = fetch(API_BASE + '/api/members/search?q=' + encodeURIComponent(query) + '&member_type=BOTH&limit=6')
      .then(function (r) { return r.ok ? r.json() : { items: [] }; })
      .then(function (d) { return d.items || []; })
      .catch(function () { return []; });
    var statePromise = ensureStates().then(function (all) {
      var lower = query.toLowerCase();
      return all.filter(function (s) { return (s.state_name || '').toLowerCase().indexOf(lower) !== -1; }).slice(0, 5);
    });
    return Promise.all([memberPromise, statePromise]).then(function (res) {
      render(res[0], res[1], query);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var input = document.getElementById('headerSearchInput');
    var dropdown = document.getElementById('searchResultsDropdown');
    var clearBtn = document.getElementById('clearSearchBtn');
    var container = document.getElementById('searchContainer');
    if (!input || !dropdown) return;

    ensureStates();
    var deb = null;
    var seq = 0;

    input.addEventListener('input', function () {
      var val = input.value;
      if (val.trim().length > 0) { if (clearBtn) clearBtn.classList.remove('hidden'); }
      else { if (clearBtn) clearBtn.classList.add('hidden'); dropdown.classList.add('hidden'); return; }
      clearTimeout(deb);
      var my = ++seq;
      deb = setTimeout(function () { doSearch(val).then(function () { if (my !== seq) { /* stale */ } }); }, 220);
    });

    input.addEventListener('focus', function () {
      if (input.value.trim().length > 0) doSearch(input.value);
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

    // Deep-link: ?search=<query> pre-fills and runs the search
    var pre = new URLSearchParams(window.location.search).get('search');
    if (pre) {
      input.value = pre;
      if (clearBtn) clearBtn.classList.remove('hidden');
      doSearch(pre);
    }
  });
})();

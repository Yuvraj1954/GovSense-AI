(function () {
  const API_BASE = (typeof window.API_BASE === 'string') ? window.API_BASE : 'http://127.0.0.1:8000';
  const CACHE_KEY = 'dataUpdatedCache';
  const CACHE_TTL_MS = 24 * 60 * 60 * 1000;

  function formatIST(utcString) {
    const date = new Date(utcString);
    const istDate = new Date(date.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
    const day = istDate.getDate();
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = months[istDate.getMonth()];
    const year = istDate.getFullYear();
    const hours = String(istDate.getHours()).padStart(2, '0');
    const minutes = String(istDate.getMinutes()).padStart(2, '0');
    return day + ' ' + month + ' ' + year + ' \u00B7 ' + hours + ':' + minutes + ' IST';
  }

  function getCached() {
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const cached = JSON.parse(raw);
      if (Date.now() - cached.timestamp > CACHE_TTL_MS) return null;
      return cached;
    } catch (e) {
      return null;
    }
  }

  function setCache(completedAt) {
    localStorage.setItem(CACHE_KEY, JSON.stringify({
      completed_at: completedAt,
      timestamp: Date.now()
    }));
  }

  function updateDOM(completedAt) {
    var display = formatIST(completedAt);

    // Top header badge
    var headerBadge = document.querySelector('header span.inline-flex span.w-1\\.5');
    if (!headerBadge) {
      var spans = document.querySelectorAll('header span');
      for (var i = 0; i < spans.length; i++) {
        if (spans[i].classList.contains('w-1.5') && spans[i].classList.contains('rounded-full') && spans[i].classList.contains('bg-emerald-500')) {
          headerBadge = spans[i];
          break;
        }
      }
    }
    if (headerBadge && headerBadge.parentElement) {
      headerBadge.parentElement.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>\n        Data updated ' + display;
    }

    // Sidebar collapsed status (title attr)
    var collapsedDot = document.getElementById('sidebarCollapsedStatus');
    if (collapsedDot) {
      var dotSpan = collapsedDot.querySelector('span');
      if (dotSpan) {
        dotSpan.setAttribute('title', 'Database Synced: ' + display);
      }
    }

    // Sidebar expanded status (paragraph with "Last updated:" or "Updated")
    var expandedCard = document.getElementById('sidebarExpandedStatus');
    if (expandedCard) {
      var paragraphs = expandedCard.querySelectorAll('p');
      for (var j = 0; j < paragraphs.length; j++) {
        var text = paragraphs[j].textContent;
        if (text.indexOf('Last updated:') !== -1 || text.indexOf('Updated ') !== -1) {
          var backendReady = paragraphs[j].querySelector('.text-emerald-600');
          var suffix = backendReady ? ' ' + backendReady.outerHTML : '';
          paragraphs[j].innerHTML = 'Last updated: ' + display + suffix;
          break;
        }
      }
    }
  }

  function fetchData() {
    return fetch(API_BASE + '/api/data-updated')
      .then(function (res) {
        if (!res.ok) throw new Error('API error');
        return res.json();
      })
      .then(function (data) {
        setCache(data.completed_at);
        updateDOM(data.completed_at);
      })
      .catch(function () {
        // API unavailable — leave hardcoded values as-is
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var cached = getCached();
    if (cached) {
      updateDOM(cached.completed_at);
    } else {
      fetchData();
    }
  });
})();

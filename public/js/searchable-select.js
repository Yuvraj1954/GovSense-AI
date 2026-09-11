(function () {
  function enhanceSelect(select, placeholder) {
    if (!select || select.dataset.searchableEnhanced) return;
    select.dataset.searchableEnhanced = '1';
    select.style.display = 'none';

    var wrap = document.createElement('div');
    wrap.className = 'relative inline-block';
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);

    var baseClass = select.getAttribute('data-combo-class') ||
      'bg-white border border-slate-300 hover:border-slate-400 text-slate-700 text-xs py-1.5 pl-2.5 pr-7 rounded-lg shadow-2xs focus:ring-1 focus:ring-blue-500 focus:outline-none font-medium w-48';

    var input = document.createElement('input');
    input.type = 'text';
    input.autocomplete = 'off';
    input.placeholder = placeholder || select.getAttribute('data-placeholder') || 'Search...';
    input.className = baseClass;

    var list = document.createElement('div');
    list.className = 'hidden absolute top-full left-0 mt-1 min-w-full w-max max-w-[320px] max-h-64 overflow-y-auto bg-white border border-slate-200 rounded-lg shadow-lg z-50 text-xs';

    wrap.appendChild(input);
    wrap.appendChild(list);

    function currentText() {
      var o = select.options[select.selectedIndex];
      return o ? o.text : '';
    }

    function renderList(filter) {
      var f = (filter || '').toLowerCase().trim();
      var html = '';
      var count = 0;
      Array.prototype.slice.call(select.options).forEach(function (opt) {
        if (!opt.value) return;
        if (f && opt.text.toLowerCase().indexOf(f) === -1) return;
        count++;
        var selected = opt.value === select.value ? ' bg-blue-50 text-blue-700 font-semibold' : ' text-slate-700';
        html += '<div class="opt px-2.5 py-1.5 hover:bg-slate-50 cursor-pointer' + selected + '" data-val="' + opt.value + '">' + opt.text + '</div>';
      });
      if (!html) html = '<div class="px-2.5 py-2 text-slate-400">No matches</div>';
      list.innerHTML = html;
      list.querySelectorAll('.opt').forEach(function (el) {
        el.addEventListener('mousedown', function (e) {
          e.preventDefault();
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
    input.addEventListener('keydown', function (e) { if (e.key === 'Escape') { list.classList.add('hidden'); input.blur(); } });
    document.addEventListener('click', function (e) { if (!wrap.contains(e.target)) list.classList.add('hidden'); });

    // Initialize display
    input.value = currentText();
    input.dataset.sel = input.value;

    select._setComboDisplay = function (text) { input.value = text || ''; input.dataset.sel = text || ''; };
  }

  function init() {
    document.querySelectorAll('select[data-searchable]').forEach(function (s) { enhanceSelect(s); });
  }

  window.enhanceSearchableSelect = enhanceSelect;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

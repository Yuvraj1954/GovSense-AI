(function () {
  // Mobile shell: hides the sidebar behind a hamburger drawer on small
  // viewports and lets the existing sidebarToggleBtn continue to expand
  // /collapse on desktop. Loaded by every page after config.js.

  var DESKTOP_MIN = 768;

  // Inject critical mobile CSS SYNCHRONOUSLY
  if (!document.getElementById('mobile-shell-css')) {
    var style = document.createElement('style');
    style.id = 'mobile-shell-css';
    style.textContent = [
      '@media(max-width:767px){',
      '  #appSidebar{',
      '    position:fixed!important;',
      '    left:-264px!important;',
      '    top:0!important;',
      '    width:264px!important;',
      '    height:100vh!important;',   /* fallback for older browsers */
      '    height:100dvh!important;',  /* real visible viewport on mobile */
      '    max-height:100dvh!important;',
      '    z-index:60;',
      '    transform:none!important;',
      '    transition:left .25s ease-out;',
      '    border-right:1px solid #e2e8f0;',
      '    box-shadow:none;',
      '    display:flex!important;',
      '    flex-direction:column!important;',
      '    overflow:hidden!important;',
      '    box-sizing:border-box!important;',
      '    padding-bottom:env(safe-area-inset-bottom, 0px)!important;',
      '  }',
      '  /* Nav scrolls; Data Status footer stays pinned and reachable */',
      '  #appSidebar>nav{',
      '    flex:1 1 auto!important;',
      '    min-height:0!important;',
      '    overflow-y:auto!important;',
      '    -webkit-overflow-scrolling:touch;',
      '  }',
      '  #appSidebar>div:last-child{',
      '    flex:0 0 auto!important;',
      '  }',
      '  #appSidebar.mobile-drawer-active{',
      '    left:0!important;',
      '    box-shadow:4px 0 24px rgba(15,23,42,.18);',
      '  }',
      '  #appSidebar.mobile-drawer-active .sidebar-text-content{',
      '    display:flex!important;',
      '  }',
      '  #appSidebar.mobile-drawer-active.w-16,',
      '  #appSidebar.mobile-drawer-active.w-64,',
      '  #appSidebar.mobile-drawer-active{',
      '    width:264px!important;',
      '  }',
      '  #appSidebar.mobile-drawer-active #sidebarCollapsedStatus{',
      '    display:none!important;',
      '  }',
      '  #appSidebar.mobile-drawer-active #sidebarExpandedStatus{',
      '    display:block!important;',
      '  }',
      '  .mobile-drawer-backdrop{',
      '    display:none;',
      '    position:fixed;',
      '    inset:0;',
      '    background:rgba(15,23,42,.45);',
      '    z-index:55;',
      '    opacity:0;',
      '    transition:opacity .2s ease;',
      '  }',
      '  .mobile-drawer-backdrop.mobile-drawer-backdrop-active{',
      '    display:block;',
      '    opacity:1;',
      '  }',
      '  body.mobile-drawer-open{',
      '    overflow:hidden;',
      '  }',
      '  header.h-16 h1{',
      '    display:inline-block!important;',
      '    font-size:15px!important;',
      '    line-height:1.2!important;',
      '  }',
      '  header.h-16 h1+span,',
      '  header.h-16 .inline-flex.items-center.gap-1\\.5.text-\\[11px\\],',
      '  header.h-16 .bg-slate-100.border.border-slate-200\\/80{',
      '    display:none!important;',
      '  }',
      '  header.h-16>div>p.text-xs.text-slate-500,',
      '  header.h-16>div>div>p.text-xs.text-slate-500{',
      '    display:none!important;',
      '  }',
      '  header.h-16>div>div.hidden.sm\\:block{',
      '    display:block!important;',
      '  }',
      '  header.h-16>div{',
      '    gap:10px!important;',
      '    flex:1 1 auto!important;',
      '    min-width:0!important;',
      '  }',
      '  header.h-16 .font-mono,',
      '  section .font-mono,',
      '  section .text-\\[11px\\].text-slate-400.font-mono,',
      '  .text-slate-400.font-mono{',
      '    display:none!important;',
      '  }',
      '  .text-xs.font-bold.text-slate-700.bg-slate-100.px-2\\.5,',
      '  .px-2.py-0\\.5.rounded-full.text-\\[10px\\].font-semibold.bg-slate-100.text-slate-700{',
      '    display:none!important;',
      '  }',
      '  .flex.items-center.gap-2,',
      '  .flex.items-center.gap-1\\.5,',
      '  .flex.items-center.gap-3{',
      '    flex-wrap:wrap!important;',
      '  }',
      '  /* Header must stay a single row: hamburger + page title together */',
      '  header.h-16,',
      '  header.h-16>div{',
      '    flex-wrap:nowrap!important;',
      '  }',
      '  header.h-16{',
      '    padding-left:10px!important;',
      '    padding-right:10px!important;',
      '    gap:8px!important;',
      '  }',
      '  header.h-16>div:first-child{',
      '    gap:8px!important;',
      '    min-width:0!important;',
      '  }',
      '  header.h-16 h1{',
      '    white-space:nowrap!important;',
      '  }',
      '  /* Header right-side metadata pill (e.g. "36 States & UTs Monitored").',
      '     Only when the last header block contains just a single badge, so',
      '     we never hide the title/buttons block. */',
      '  header.h-16>div:last-child>span:only-child{',
      '    display:none!important;',
      '  }',
      '  #mpSearchInput,',
      '  #headerSearchInput,',
      '  #stateSearchInput{',
      '    width:100%!important;',
      '    max-width:100%!important;',
      '  }',
      '  .flex.flex-col.lg\\:flex-row,',
      '  .flex.flex-col.md\\:flex-row{',
      '    flex-direction:column!important;',
      '    align-items:stretch!important;',
      '  }',
      '',
      '  /* ---- Search + filter bars (mps.html, state.html) ---- */',
      '  [data-purpose="search-filters-bar"] #searchWrapper>div{',
      '    flex-wrap:nowrap!important;',
      '    min-height:42px!important;',
      '    box-sizing:border-box!important;',
      '    align-items:center!important;',
      '  }',
      '  [data-purpose="search-filters-bar"] #searchWrapper input{',
      '    min-width:0!important;',
      '  }',
      '  [data-purpose="search-filters-bar"] .flex.flex-col>div:last-child{',
      '    display:grid!important;',
      '    grid-template-columns:1fr 1fr!important;',
      '    gap:8px!important;',
      '    width:100%!important;',
      '    align-items:center!important;',
      '  }',
      '  [data-purpose="search-filters-bar"] .flex.flex-col>div:last-child>*{',
      '    min-width:0!important;',
      '    width:100%!important;',
      '  }',
      '  [data-purpose="search-filters-bar"] select{',
      '    width:100%!important;',
      '    max-width:100%!important;',
      '    min-height:42px!important;',
      '    box-sizing:border-box!important;',
      '  }',
      '  /* The "Sort:" wrapper spans both columns */',
      '  [data-purpose="search-filters-bar"] .flex.flex-col>div:last-child>div.flex.items-center.gap-1\\.5{',
      '    grid-column:1 / -1!important;',
      '  }',
      '  [data-purpose="search-filters-bar"] .flex.flex-col>div:last-child>div.flex.items-center.gap-1\\.5 select{',
      '    flex:1 1 auto!important;',
      '  }',
      '  /* Enhanced (searchable) selects: wrapper + generated input full width */',
      '  [data-purpose="search-filters-bar"] .flex.flex-col>div:last-child>div.relative>div.relative.inline-block{',
      '    width:100%!important;',
      '    display:block!important;',
      '  }',
      '  [data-purpose="search-filters-bar"] .flex.flex-col>div:last-child>div.relative>div.relative.inline-block>input{',
      '    width:100%!important;',
      '    max-width:100%!important;',
      '    min-height:42px!important;',
      '    box-sizing:border-box!important;',
      '  }',
      '  /* Last plain filter (e.g. All Classifications) spans both columns */',
      '  [data-purpose="search-filters-bar"] .flex.flex-col>div:last-child>div.relative:last-child{',
      '    grid-column:1 / -1!important;',
      '  }',
      '',
      '  /* ---- Project explore-works filter bar ---- */',
      '  [data-purpose="explore-works-section"] .flex.flex-wrap.items-center.gap-2{',
      '    display:flex!important;',
      '    flex-direction:column!important;',
      '    align-items:stretch!important;',
      '    width:100%!important;',
      '  }',
      '  [data-purpose="explore-works-section"] .flex.flex-wrap.items-center.gap-2>*{',
      '    width:100%!important;',
      '  }',
      '  [data-purpose="explore-works-section"] .flex.flex-wrap.items-center.gap-2>div.flex.items-center.gap-1\\.5{',
      '    justify-content:space-between!important;',
      '  }',
      '  [data-purpose="explore-works-section"] .flex.flex-wrap.items-center.gap-2 select,',
      '  [data-purpose="explore-works-section"] .flex.flex-wrap.items-center.gap-2 input,',
      '  [data-purpose="explore-works-section"] .flex.flex-wrap.items-center.gap-2 .relative.shrink-0 input{',
      '    width:100%!important;',
      '    max-width:100%!important;',
      '    min-height:42px!important;',
      '    box-sizing:border-box!important;',
      '  }',
      '  [data-purpose="explore-works-section"] .relative.shrink-0{',
      '    width:100%!important;',
      '    max-width:100%!important;',
      '  }',
      '  [data-purpose="explore-works-section"] .flex.items-center.gap-1\\.5.self-end{',
      '    width:100%!important;',
      '    justify-content:space-between!important;',
      '  }',
      '  [data-purpose="explore-works-section"] .flex.items-center.gap-1\\.5.self-end select{',
      '    flex:1 1 auto!important;',
      '  }',
      '  /* Project: keep the works search box on ONE line */',
      '  [data-purpose="explore-works-section"] .relative.w-full>div{',
      '    flex-wrap:nowrap!important;',
      '    min-height:42px!important;',
      '    box-sizing:border-box!important;',
      '    align-items:center!important;',
      '  }',
      '  #workFilterInput{',
      '    min-height:0!important;',
      '    height:auto!important;',
      '    padding-top:0!important;',
      '    padding-bottom:0!important;',
      '  }',
      '  /* Consistent font/weight/colour for ALL search + filter controls */',
      '  [data-purpose="search-filters-bar"] select,',
      '  [data-purpose="search-filters-bar"] input,',
      '  [data-purpose="explore-works-section"] select,',
      '  [data-purpose="explore-works-section"] input{',
      '    font-size:13px!important;',
      '    font-weight:500!important;',
      '    color:#334155!important;',
      '  }',
      '  [role="tablist"],',
      '  [data-purpose="profile-section-nav"]{',
      '    gap:16px!important;',
      '    overflow-x:auto!important;',
      '    -webkit-overflow-scrolling:touch;',
      '    scrollbar-width:thin;',
      '    flex-wrap:nowrap!important;',
      '  }',
      '  [role="tablist"] button,',
      '  [data-purpose="profile-section-nav"] button{',
      '    padding-left:0!important;',
      '    padding-right:0!important;',
      '  }',
      '  .text-\\[10px\\].text-slate-500,',
      '  .text-\\[10px\\].leading-tight,',
      '  .text-\\[11px\\].text-slate-500{',
      '    overflow-wrap:anywhere;',
      '    word-break:break-word;',
      '    white-space:normal;',
      '    max-width:100%;',
      '  }',
      '  #riskSubtitle{',
      '    display:block!important;',
      '    overflow-wrap:anywhere;',
      '    word-break:break-word;',
      '    white-space:normal;',
      '    line-height:1.35;',
      '  }',
      '  /* Search bar: single line, flexible width */',
      '  header.h-16>div:nth-child(2){',
      '    flex:1 1 auto!important;',
      '    min-width:0!important;',
      '    padding-left:0!important;',
      '    padding-right:0!important;',
      '    flex-wrap:nowrap!important;',
      '    justify-content:flex-end!important;',
      '  }',
      '  #searchContainer{',
      '    max-width:100%!important;',
      '    width:100%!important;',
      '    margin:0!important;',
      '  }',
      '  /* Keep the search field itself on one line */',
      '  #searchContainer>div{',
      '    flex-wrap:nowrap!important;',
      '    padding-top:6px!important;',
      '    padding-bottom:6px!important;',
      '  }',
      '  #searchContainer input{',
      '    font-size:13px!important;',
      '    min-width:0!important;',
      '  }',
      '  #searchContainer input::placeholder{',
      '    color:transparent!important;',
      '  }',
      '  /* Hide secondary accent badges (font-medium/semibold) — NOT the',
      '     tile titles, which use font-bold and must stay visible. */',
      '  .text-\\[10px\\].font-medium.text-emerald-600,',
      '  .text-\\[10px\\].font-medium.text-amber-600,',
      '  .text-\\[10px\\].font-medium.text-rose-600,',
      '  .text-\\[10px\\].font-medium.text-blue-600,',
      '  .text-\\[10px\\].font-semibold.text-emerald-600,',
      '  .text-\\[10px\\].font-semibold.text-amber-600,',
      '  .text-\\[10px\\].font-semibold.text-rose-600,',
      '  .text-\\[10px\\].font-semibold.text-blue-600,',
      '  .text-\\[10px\\].font-medium.text-emerald-700,',
      '  .text-\\[10px\\].font-medium.text-amber-700,',
      '  .text-\\[10px\\].font-medium.text-rose-700,',
      '  .text-\\[10px\\].font-medium.text-blue-700,',
      '  .text-\\[10px\\].font-semibold.text-emerald-700,',
      '  .text-\\[10px\\].font-semibold.text-amber-700,',
      '  .text-\\[10px\\].font-semibold.text-rose-700,',
      '  .text-\\[10px\\].font-semibold.text-blue-700,',
      '  .text-\\[10px\\].font-semibold.text-violet-700,',
      '  .text-\\[10px\\].font-semibold.text-teal-700,',
      '  .text-\\[10px\\].font-semibold.text-orange-700,',
      '  .text-\\[11px\\].font-medium.text-emerald-600,',
      '  .text-\\[11px\\].font-medium.text-emerald-700,',
      '  .text-\\[11px\\].font-medium.text-amber-700,',
      '  .text-\\[11px\\].font-medium.text-rose-700,',
      '  .text-\\[11px\\].font-medium.text-blue-700,',
      '  .text-xs.font-semibold.text-emerald-600,',
      '  .text-xs.font-semibold.text-amber-600,',
      '  .text-xs.font-semibold.text-rose-600,',
      '  .text-xs.font-semibold.text-blue-600,',
      '  .text-xs.font-semibold.text-violet-600,',
      '  .text-xs.font-semibold.text-teal-600,',
      '  .text-xs.font-semibold.text-orange-700{',
      '    display:none!important;',
      '  }',
      '  section.bg-white.border.rounded-xl,',
      '  .bg-white.border.border-slate-200.rounded-xl{',
      '    padding:12px!important;',
      '  }',
      '  .text-2xl.font-bold.tracking-tight,',
      '  .text-2xl.md\\:text-3xl.font-black{',
      '    font-size:18px!important;',
      '    line-height:1.15!important;',
      '  }',
      '  .text-3xl.font-black,',
      '  .text-2xl.md\\:text-3xl{',
      '    font-size:20px!important;',
      '  }',
      '  h2,h3,.truncate{',
      '    overflow-wrap:anywhere;',
      '  }',
      '  button[type="button"],button:not([type]){',
      '    min-height:32px;',
      '  }',
      '  svg.w-full.h-full,svg.w-44.h-44,svg.w-40.h-40{',
      '    max-width:100%;',
      '  }',
      '  select,input[type="text"],input[type="search"]{',
      '    font-size:16px;',
      '  }',
      '  .desktop-only{',
      '    display:none!important;',
      '  }',
      '}',
      '',
      '/* Print styles */',
      '@media print{',
      '  #appSidebar,',
      '  #mobileMenuBtn,',
      '  #sidebarToggleBtn,',
      '  .mobile-drawer-backdrop,',
      '  #searchContainer,',
      '  .info-btn{',
      '    display:none!important;',
      '  }',
      '  body,.flex.h-screen.w-screen.overflow-hidden,main{',
      '    overflow:visible!important;',
      '    height:auto!important;',
      '  }',
      '  main{',
      '    padding:0!important;',
      '  }',
      '  section,.bg-white.border{',
      '    break-inside:avoid;',
      '    page-break-inside:avoid;',
      '  }',
      '  svg{',
      '    max-width:100%!important;',
      '    height:auto!important;',
      '  }',
      '  *{',
      '    -webkit-print-color-adjust:exact!important;',
      '    print-color-adjust:exact!important;',
      '  }',
      '  h1,h2,h3,h4,p,span,td,th{',
      '    color:#000!important;',
      '  }',
      '  header.h-16{',
      '    height:auto!important;',
      '    padding:8px 0!important;',
      '    border-bottom:2px solid #000!important;',
      '  }',
      '  .grid-cols-2,.grid-cols-3,.grid-cols-4{',
      '    grid-template-columns:repeat(2,1fr)!important;',
      '  }',
      '}'
    ].join('\n');
    document.head.appendChild(style);
  }

  function isMobile() {
    return window.matchMedia && window.matchMedia('(max-width: ' + (DESKTOP_MIN - 1) + 'px)').matches;
  }

  function init() {
    var sidebar = document.getElementById('appSidebar');
    var toggleBtn = document.getElementById('sidebarToggleBtn');
    var menuBtn = document.getElementById('mobileMenuBtn');
    if (!sidebar) return;

    // On mobile: hide the desktop toggle button via JS (overrides inline styles)
    // and show the mobile menu button
    if (isMobile()) {
      if (toggleBtn) {
        toggleBtn.style.setProperty('display', 'none', 'important');
      }
      if (menuBtn) {
        menuBtn.style.setProperty('display', 'inline-flex', 'important');
      }
    }

    var backdrop = document.createElement('div');
    backdrop.className = 'mobile-drawer-backdrop';
    backdrop.setAttribute('aria-hidden', 'true');
    document.body.appendChild(backdrop);

    var textEls = document.querySelectorAll('.sidebar-text-content');

    function openDrawer() {
      document.body.classList.add('mobile-drawer-open');
      sidebar.classList.add('mobile-drawer-active');
      backdrop.classList.add('mobile-drawer-backdrop-active');
      if (menuBtn) menuBtn.setAttribute('aria-expanded', 'true');
      // Use inline !important so ordering/specificity of stylesheets can
      // never prevent the drawer from sliding in. Disable the transition
      // while repositioning so the value commits immediately and cannot
      // get stuck mid-transition on some browsers/headless environments.
      sidebar.style.setProperty('transition', 'none', 'important');
      sidebar.style.setProperty('left', '0', 'important');
      sidebar.style.setProperty('width', '264px', 'important');
      sidebar.style.setProperty('transform', 'none', 'important');
      textEls.forEach(function (el) { el.style.setProperty('display', 'flex', 'important'); });
      var collapsedStatusEl = document.getElementById('sidebarCollapsedStatus');
      var expandedStatusEl = document.getElementById('sidebarExpandedStatus');
      if (collapsedStatusEl) collapsedStatusEl.style.setProperty('display', 'none', 'important');
      if (expandedStatusEl) expandedStatusEl.style.setProperty('display', 'block', 'important');
    }
    function closeDrawer() {
      document.body.classList.remove('mobile-drawer-open');
      sidebar.classList.remove('mobile-drawer-active');
      backdrop.classList.remove('mobile-drawer-backdrop-active');
      if (menuBtn) menuBtn.setAttribute('aria-expanded', 'false');
      if (isMobile()) {
        sidebar.style.setProperty('transition', 'none', 'important');
        sidebar.style.setProperty('left', '-264px', 'important');
      } else {
        sidebar.style.removeProperty('transition');
        sidebar.style.removeProperty('left');
        sidebar.style.removeProperty('width');
        sidebar.style.removeProperty('transform');
      }
      textEls.forEach(function (el) { el.style.removeProperty('display'); });
      var collapsedStatusEl = document.getElementById('sidebarCollapsedStatus');
      var expandedStatusEl = document.getElementById('sidebarExpandedStatus');
      if (collapsedStatusEl) collapsedStatusEl.style.removeProperty('display');
      if (expandedStatusEl) expandedStatusEl.style.removeProperty('display');
    }
    function isOpen() {
      return sidebar.classList.contains('mobile-drawer-active');
    }

    // Attach click handler to mobile menu button
    if (menuBtn) {
      menuBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        e.preventDefault();
        if (isOpen()) closeDrawer();
        else openDrawer();
      });
    }

    // Also handle the desktop toggle button on mobile (fallback)
    if (toggleBtn) {
      toggleBtn.addEventListener('click', function (e) {
        if (isMobile()) {
          e.stopImmediatePropagation();
          e.preventDefault();
          if (isOpen()) closeDrawer();
          else openDrawer();
        }
      }, true); // Use capture phase to run before other handlers
    }

    backdrop.addEventListener('click', closeDrawer);

    sidebar.querySelectorAll('a[href]').forEach(function (a) {
      a.addEventListener('click', function () {
        if (isMobile()) closeDrawer();
      });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) closeDrawer();
    });

    window.addEventListener('resize', function () {
      if (!isMobile()) {
        closeDrawer();
        // Restore desktop toggle button
        if (toggleBtn) toggleBtn.style.removeProperty('display');
        if (menuBtn) menuBtn.style.removeProperty('display');
      } else {
        // Re-hide on mobile
        if (toggleBtn) toggleBtn.style.setProperty('display', 'none', 'important');
        if (menuBtn) menuBtn.style.setProperty('display', 'inline-flex', 'important');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

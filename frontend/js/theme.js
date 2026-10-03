/* BuyerBridge theme switcher — UI only. Stores one preference key in localStorage.
   Does not touch the API, auth, session or any other stored data. */
(function () {
  var KEY = 'buyerbridge-ui-theme';
  var THEMES = [
    { id: 'emerald', name: 'Emerald', a: '#12a37a', b: '#0b6b82', meta: '#f3f7f4' },
    { id: 'ocean', name: 'Ocean', a: '#0ea5e9', b: '#4f46e5', meta: '#f0f7fc' },
    { id: 'sunset', name: 'Sunset', a: '#f97316', b: '#e11d48', meta: '#fff7f0' },
    { id: 'orchid', name: 'Orchid', a: '#a855f7', b: '#ec4899', meta: '#f8f4fe' },
    { id: 'midnight', name: 'Midnight', a: '#818cf8', b: '#38bdf8', meta: '#0b1020' },
    { id: 'ember', name: 'Ember', a: '#fb923c', b: '#f43f5e', meta: '#141211' }
  ];

  function read() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function write(v) { try { localStorage.setItem(KEY, v); } catch (e) { /* ignore */ } }
  function find(id) { return THEMES.filter(function (t) { return t.id === id; })[0]; }

  function apply(id) {
    var t = find(id) || THEMES[0];
    document.documentElement.setAttribute('data-theme', t.id);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) { meta = document.createElement('meta'); meta.name = 'theme-color'; document.head.appendChild(meta); }
    meta.content = t.meta;
    return t;
  }

  var saved = read();
  var initial = saved && find(saved) ? saved
    : (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'midnight' : 'emerald');
  var current = apply(initial);

  function dot(t) { return '<span class="bb-dot" style="background:linear-gradient(135deg,' + t.a + ',' + t.b + ')"></span>'; }

  document.addEventListener('DOMContentLoaded', function () {
    var wrap = document.createElement('div');
    wrap.className = 'bb-theme';
    wrap.innerHTML =
      '<button type="button" class="bb-theme-toggle" aria-haspopup="true" aria-expanded="false" aria-label="Change theme">' +
      dot(current) + '<span class="bb-label">Theme</span></button>' +
      '<div class="bb-theme-menu" role="group" aria-label="Choose a theme" hidden>' +
      THEMES.map(function (t) {
        return '<button type="button" class="bb-theme-opt" data-theme-id="' + t.id + '" aria-pressed="' + (t.id === current.id) + '">' + dot(t) + t.name + '</button>';
      }).join('') + '</div>';
    document.body.appendChild(wrap);

    var toggle = wrap.querySelector('.bb-theme-toggle');
    var menu = wrap.querySelector('.bb-theme-menu');

    function setOpen(open) { menu.hidden = !open; toggle.setAttribute('aria-expanded', String(open)); }

    toggle.addEventListener('click', function () { setOpen(menu.hidden); });
    document.addEventListener('click', function (e) { if (!wrap.contains(e.target)) setOpen(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });

    menu.addEventListener('click', function (e) {
      var btn = e.target.closest('.bb-theme-opt');
      if (!btn) return;
      var t = apply(btn.getAttribute('data-theme-id'));
      write(t.id);
      menu.querySelectorAll('.bb-theme-opt').forEach(function (o) {
        o.setAttribute('aria-pressed', String(o === btn));
      });
      toggle.querySelector('.bb-dot').outerHTML = dot(t);
      setOpen(false);
    });
  });
})();

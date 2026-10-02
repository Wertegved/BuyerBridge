document.addEventListener('DOMContentLoaded', () => {
  const currentPath = window.location.pathname.split('/').pop() || 'index.html';

  document.querySelectorAll('.main-nav a').forEach((link) => {
    const href = link.getAttribute('href');
    if (!href) return;
    const pageName = href.split('/').pop();
    if (pageName === currentPath) {
      link.classList.add('active');
    }
  });

  const toggle = document.querySelector('[data-mobile-toggle]');
  const mobileMenu = document.getElementById('mobile-menu');

  if (!toggle || !mobileMenu) return;

  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!expanded));
    mobileMenu.hidden = expanded;
  });

  mobileMenu.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      mobileMenu.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
    });
  });
});

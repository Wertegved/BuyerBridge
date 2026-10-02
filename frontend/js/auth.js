const DEFAULT_AUTH_REDIRECT = '/index.html';
const PROTECTED_PATHS = ['/pages/dashboard.html', '/pages/buyers.html', '/pages/campaigns.html'];
const AUTH_ONLY_PATHS = ['/pages/login.html', '/pages/signup.html', '/pages/forgot-password.html'];
const ALLOWED_NEXT_PATHS = new Set([
  '/index.html',
  '/pages/dashboard.html',
  '/pages/buyers.html',
  '/pages/campaigns.html',
]);

function getAppRelativePath() {
  const pathname = (window.location.pathname || '/').split('\\').join('/');

  if (pathname.includes('/frontend/')) {
    return pathname.slice(pathname.indexOf('/frontend/') + '/frontend'.length);
  }

  if (pathname.includes('/pages/')) {
    return pathname.slice(pathname.indexOf('/pages/'));
  }

  const lastSegment = pathname.split('/').pop() || 'index.html';
  return lastSegment === 'index.html' ? '/index.html' : `/${lastSegment}`;
}

function isInPagesFolder() {
  return getAppRelativePath().includes('/pages/');
}

function getHomePath() {
  return isInPagesFolder() ? '../index.html' : 'index.html';
}

function getLoginPath() {
  return isInPagesFolder() ? 'login.html' : 'pages/login.html';
}

function normalizeAppRoute(target) {
  if (!target) return DEFAULT_AUTH_REDIRECT;

  const raw = String(target).trim().replace(/\\/g, '/');

  if (!raw || raw === '/') return DEFAULT_AUTH_REDIRECT;
  if (raw.startsWith('//') || /^https?:\/\//i.test(raw) || raw.startsWith('file:') || raw.startsWith('javascript:') || raw.startsWith('data:')) {
    return DEFAULT_AUTH_REDIRECT;
  }

  let resolvedPath = raw;
  try {
    resolvedPath = new URL(raw, window.location.href).pathname.replace(/\\/g, '/');
  } catch (error) {
    resolvedPath = raw;
  }

  if (resolvedPath.includes('/frontend/')) {
    resolvedPath = resolvedPath.slice(resolvedPath.indexOf('/frontend/') + '/frontend'.length);
  }

  if (resolvedPath.startsWith('/')) {
    if (resolvedPath.includes('/pages/')) {
      return resolvedPath.slice(resolvedPath.lastIndexOf('/pages/'));
    }
    if (resolvedPath === '/index.html' || resolvedPath === '/index.htm') return '/index.html';
    if (resolvedPath.endsWith('/')) return `${resolvedPath}index.html`;
    return resolvedPath;
  }

  if (resolvedPath.includes('/pages/')) {
    return `/${resolvedPath.slice(resolvedPath.lastIndexOf('/pages/'))}`;
  }

  if (resolvedPath === 'index.html' || resolvedPath === './index.html' || resolvedPath === '../index.html') {
    return '/index.html';
  }

  return `/${resolvedPath.replace(/^\.\//, '').replace(/^\.\.\//, '')}`;
}

function resolveInternalToUrl(target) {
  const route = normalizeAppRoute(target);

  if (route === '/index.html') {
    return isInPagesFolder() ? '../index.html' : 'index.html';
  }

  if (route.startsWith('/pages/')) {
    const pageName = route.split('/').pop();
    return isInPagesFolder() ? pageName : `pages/${pageName}`;
  }

  return route.replace(/^\//, '');
}

function getSafeRedirectTarget(defaultValue = DEFAULT_AUTH_REDIRECT) {
  const next = new URL(window.location.href).searchParams.get('next');
  const allowedDefault = normalizeAppRoute(defaultValue);

  if (!next) return resolveInternalToUrl(allowedDefault);

  const safeTarget = normalizeAppRoute(next);
  if (ALLOWED_NEXT_PATHS.has(safeTarget)) {
    return resolveInternalToUrl(safeTarget);
  }

  return resolveInternalToUrl(allowedDefault);
}

function buildProtectedRedirect(target = DEFAULT_AUTH_REDIRECT) {
  const safeTarget = normalizeAppRoute(target);
  const nextTarget = ALLOWED_NEXT_PATHS.has(safeTarget) ? safeTarget : DEFAULT_AUTH_REDIRECT;
  return `${getLoginPath()}?next=${encodeURIComponent(nextTarget)}`;
}

function getCurrentAppPath() {
  return getAppRelativePath();
}

function getAuthLinkPath(pageName) {
  return isInPagesFolder() ? pageName : `pages/${pageName}`;
}

function setBrandLinks() {
  document.querySelectorAll('[data-brand-link]').forEach((link) => {
    link.setAttribute('href', getHomePath());
  });
}

function isAuthenticated() {
  return document.cookie.split('; ').some((cookie) => cookie.startsWith('buyerbridge_session='));
}

function setAuthToken() {
  return null;
}

function clearAuthToken() {
  document.cookie = 'buyerbridge_session=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
}

function renderAuthButtonGroup(container) {
  const isLoggedIn = isAuthenticated();

  if (isLoggedIn) {
    container.innerHTML = `
      <button type="button" class="button button-primary" data-logout-button>Logout</button>
    `;
  } else {
    container.innerHTML = `
      <a class="button button-secondary" href="${getAuthLinkPath('login.html')}">Login</a>
      <a class="button button-primary" href="${getAuthLinkPath('signup.html')}">Sign Up</a>
    `;
  }

  const logoutButton = container.querySelector('[data-logout-button]');
  if (logoutButton) {
    logoutButton.addEventListener('click', async () => {
      await logout();
      window.location.href = getHomePath();
    });
  }
}

function syncAuthActions() {
  document.querySelectorAll('[data-auth-actions]').forEach((container) => renderAuthButtonGroup(container));
  document.querySelectorAll('[data-mobile-auth]').forEach((container) => renderAuthButtonGroup(container));
}

function initializeProtectedNavLinks() {
  document.querySelectorAll('[data-protected-nav]').forEach((link) => {
    if (isAuthenticated()) {
      return;
    }

    link.addEventListener('click', (event) => {
      event.preventDefault();
      const href = link.getAttribute('href') || '/index.html';
      const safeTarget = normalizeAppRoute(href);
      window.location.href = buildProtectedRedirect(safeTarget);
    });
  });
}

function initializeHomeCtas() {
  document.querySelectorAll('[data-home-cta]').forEach((link) => {
    link.addEventListener('click', (event) => {
      const target = link.dataset.homeCta === 'buyers' ? '/pages/buyers.html' : '/pages/dashboard.html';
      if (isAuthenticated()) {
        return;
      }
      event.preventDefault();
      window.location.href = buildProtectedRedirect(target);
    });
  });
}

function handleProtectedPageAccess() {
  const currentPath = getCurrentAppPath();

  if (PROTECTED_PATHS.includes(currentPath) && !isAuthenticated()) {
    window.location.href = buildProtectedRedirect(currentPath);
    return;
  }

  if (AUTH_ONLY_PATHS.includes(currentPath) && isAuthenticated()) {
    window.location.href = getSafeRedirectTarget(DEFAULT_AUTH_REDIRECT);
  }
}

function showNotice(target, message, type = 'error') {
  if (!target) return;

  if (!message || !String(message).trim()) {
    target.textContent = '';
    target.hidden = true;
    target.className = 'auth-notice';
    return;
  }

  target.hidden = false;
  target.textContent = message;
  target.className = `auth-notice ${type}`;
}

function syncAuthLinkPreservation() {
  const next = new URLSearchParams(window.location.search).get('next');
  const nextValue = next ? `?next=${encodeURIComponent(next)}` : '';

  document.querySelectorAll('[data-auth-link]').forEach((link) => {
    const target = link.dataset.authLink || 'login.html';
    const route = target === 'home' ? getHomePath() : getAuthLinkPath(target);
    link.href = route + nextValue;
  });
}

async function handleLoginSubmit(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const notice = form.querySelector('[data-auth-message]');
  const email = form.email.value.trim();
  const password = form.password.value;

  if (!email || !password) {
    showNotice(notice, 'Please enter both email and password.', 'error');
    return;
  }

  try {
    await login({ email, password });
    showNotice(notice, 'Login successful. Redirecting...', 'success');
    window.location.href = getSafeRedirectTarget(DEFAULT_AUTH_REDIRECT);
  } catch (error) {
    showNotice(notice, error.message || 'Email or password is incorrect.', 'error');
  }
}

async function handleSignupSubmit(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const notice = form.querySelector('[data-auth-message]');
  const payload = {
    name: form.name.value.trim(),
    email: form.email.value.trim(),
    password: form.password.value,
    confirm_password: form.confirm_password.value,
  };

  if (!payload.name || !payload.email || !payload.password || !payload.confirm_password) {
    showNotice(notice, 'Please complete all fields before continuing.', 'error');
    return;
  }

  if (payload.password !== payload.confirm_password) {
    showNotice(notice, 'Passwords do not match.', 'error');
    return;
  }

  try {
    await signup(payload);
    showNotice(notice, 'Account created successfully. Redirecting...', 'success');
    window.location.href = getSafeRedirectTarget(DEFAULT_AUTH_REDIRECT);
  } catch (error) {
    showNotice(notice, error.message || 'We could not create your account right now.', 'error');
  }
}

async function handleForgotPasswordSubmit(event) {
  event.preventDefault();

  const form = event.currentTarget;
  const notice = form.querySelector('[data-auth-message]');
  const email = form.email.value.trim();

  if (!email) {
    showNotice(notice, 'Please enter your email address.', 'error');
    return;
  }

  try {
    const response = await requestPasswordReset(email);
    const message = response && response.message ? response.message : 'Password reset email service is not configured yet.';
    showNotice(notice, message, 'error');
  } catch (error) {
    showNotice(notice, error.message || 'Password reset email service is not configured yet.', 'error');
  }
}

function initializeBuyerBridgeAuth() {
  setBrandLinks();
  syncAuthActions();
  syncAuthLinkPreservation();
  initializeProtectedNavLinks();
  handleProtectedPageAccess();
  initializeHomeCtas();

  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', handleLoginSubmit);
  }

  const signupForm = document.getElementById('signup-form');
  if (signupForm) {
    signupForm.addEventListener('submit', handleSignupSubmit);
  }

  const forgotForm = document.getElementById('forgot-password-form');
  if (forgotForm) {
    forgotForm.addEventListener('submit', handleForgotPasswordSubmit);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeBuyerBridgeAuth);
} else {
  initializeBuyerBridgeAuth();
}

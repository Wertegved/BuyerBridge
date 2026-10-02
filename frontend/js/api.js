const API_BASE_URL = 'http://localhost:8000';
const AUTH_TOKEN_KEY = 'buyerbridge_token';

function getAuthHeaders() {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message = body.detail || 'Request failed. Please try again.';
    throw new Error(message);
  }

  return response.json();
}

async function healthCheck() {
  return requestJson(`${API_BASE_URL}/health`);
}

async function searchBuyers(payload) {
  return requestJson(`${API_BASE_URL}/api/search-buyers`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

async function getDashboardData() {
  return requestJson(`${API_BASE_URL}/api/dashboard`);
}

async function getSearchHistory() {
  return requestJson(`${API_BASE_URL}/api/search-history`);
}

async function getEmailHistory() {
  return requestJson(`${API_BASE_URL}/api/email-history`);
}

async function getBuyerDetail(buyerId) {
  return requestJson(`${API_BASE_URL}/api/buyers/${buyerId}`);
}

async function sendEmail(payload) {
  return requestJson(`${API_BASE_URL}/api/email/send`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

async function signup(payload) {
  return requestJson(`${API_BASE_URL}/api/auth/signup`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

async function login(payload) {
  return requestJson(`${API_BASE_URL}/api/auth/login`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

async function logout() {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (!token) {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    return { status: 'ok' };
  }

  try {
    await requestJson(`${API_BASE_URL}/api/auth/logout`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });
  } catch (error) {
    console.warn('Logout request failed:', error.message);
  }

  localStorage.removeItem(AUTH_TOKEN_KEY);
  return { status: 'ok' };
}

async function requestPasswordReset(email) {
  return requestJson(`${API_BASE_URL}/api/auth/forgot-password`, {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

async function fetchCurrentUser() {
  return requestJson(`${API_BASE_URL}/api/auth/me`, {
    method: 'GET',
    headers: getAuthHeaders(),
  });
}

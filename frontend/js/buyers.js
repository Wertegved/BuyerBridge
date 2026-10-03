const form = document.getElementById('search-form');
const resultContainer = document.getElementById('results-container');
const resultsTitle = document.getElementById('results-title');
const resultsSummary = document.getElementById('results-summary');
const filterToggle = document.getElementById('filter-toggle');
const filterPanel = document.getElementById('buyer-filter-panel');
const filterText = document.getElementById('buyer-filter-text');
const emailFilter = document.getElementById('buyer-email-filter');
const websiteFilter = document.getElementById('buyer-website-filter');
const sortSelect = document.getElementById('sort-by');
const selectAllButton = document.getElementById('select-all-button');
const selectedCount = document.getElementById('selected-count');
const contactSelectedButton = document.getElementById('contact-selected-button');
const detailsDialog = document.getElementById('buyer-details-dialog');
const detailsTitle = document.getElementById('buyer-detail-title');
const detailsFields = document.getElementById('buyer-detail-fields');
const closeDetailsButton = document.getElementById('close-buyer-details');

let savedBuyers = [];
let selectedBuyerIds = new Set();
let storageScope = null;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function readSessionValue(key, fallback) {
  try {
    const value = sessionStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch (error) {
    return fallback;
  }
}

function writeSessionValue(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    return;
  }
}

function storageKey(name) {
  return `buyerbridge.${name}.${storageScope}`;
}

function renderStatus(message, type = 'notice') {
  if (!resultsSummary) return;

  const notice = document.createElement('div');
  notice.className = type;
  notice.textContent = message;
  resultsSummary.replaceChildren(notice);
}

function renderLoadingStatus() {
  if (!resultsSummary) return;

  const notice = document.createElement('div');
  notice.className = 'notice';
  const loader = document.createElement('span');
  loader.className = 'loader';
  loader.textContent = 'Finding potential buyers...';
  notice.append(loader);
  resultsSummary.replaceChildren(notice);
}

function searchErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please log in again.';
  if (error.status === 422) return error.message || 'Check the required search fields and try again.';
  if (error.status === 503) return 'Buyer discovery is temporarily unavailable. Please try again shortly.';
  if (!error.status) return 'Could not connect to buyer discovery. Check your connection and try again.';
  return error.message || 'Buyer discovery failed. Please try again.';
}

function isEmailUsable(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(email || '').trim());
}

function visibleBuyers() {
  const query = (filterText?.value || '').trim().toLowerCase();
  const emailAvailability = emailFilter?.value || 'all';
  const websiteAvailability = websiteFilter?.value || 'all';

  const filtered = savedBuyers.filter((buyer) => {
    const searchable = [buyer.category, buyer.city, buyer.state].filter(Boolean).join(' ').toLowerCase();
    if (query && !searchable.includes(query)) return false;
    const hasEmail = isEmailUsable(buyer.email);
    const hasWebsite = Boolean(String(buyer.website || '').trim());
    if (emailAvailability === 'available' && !hasEmail) return false;
    if (emailAvailability === 'unavailable' && hasEmail) return false;
    if (websiteAvailability === 'available' && !hasWebsite) return false;
    if (websiteAvailability === 'unavailable' && hasWebsite) return false;
    return true;
  });

  const sortMode = sortSelect?.value || 'relevance';
  return filtered.sort((left, right) => {
    if (sortMode === 'name') {
      return String(left.business_name || '').localeCompare(String(right.business_name || ''));
    }
    if (sortMode === 'location') {
      const leftLocation = `${left.city || ''} ${left.state || ''}`.trim();
      const rightLocation = `${right.city || ''} ${right.state || ''}`.trim();
      return leftLocation.localeCompare(rightLocation) || String(left.business_name || '').localeCompare(String(right.business_name || ''));
    }
    return (right.relevance_score || 0) - (left.relevance_score || 0);
  });
}

function renderEmptyState(message) {
  resultContainer.innerHTML = `
    <div class="empty-state-box">
      <h3>${escapeHtml(message)}</h3>
      <p>${savedBuyers.length ? 'Change the current filters to see more saved buyers.' : 'Run a search to discover real businesses from OpenStreetMap.'}</p>
    </div>
  `;
}

function renderResults() {
  const results = visibleBuyers();
  if (!results.length) {
    renderEmptyState(savedBuyers.length ? 'No buyers match these filters.' : 'No saved buyers found.');
    resultsTitle.textContent = savedBuyers.length ? 'No matching buyers' : 'No results yet';
    updateSelectionControls(results);
    return;
  }

  resultContainer.innerHTML = results.map((buyer) => {
    const id = String(buyer.id || '');
    const name = buyer.business_name || 'Business name unavailable';
    const selected = selectedBuyerIds.has(id);
    return `
      <article class="result-card${selected ? ' selected' : ''}" data-buyer-id="${escapeHtml(id)}">
        <div class="result-top">
          <h3>${escapeHtml(name)}</h3>
          <input class="buyer-selection" type="checkbox" aria-label="Select ${escapeHtml(name)}" ${selected ? 'checked' : ''} />
        </div>
        <div class="result-meta">
          <span class="meta-row">${escapeHtml(buyer.category || 'Business type unavailable')}</span>
          <span class="meta-row">${escapeHtml(buyer.city || buyer.state || 'Location unavailable')}</span>
          <span class="meta-row">${escapeHtml(buyer.website || 'Website unavailable')}</span>
          <span class="meta-row">${escapeHtml(isEmailUsable(buyer.email) ? buyer.email : 'Email not available')}</span>
        </div>
        <span class="lead-score">Lead Relevance ${escapeHtml(buyer.relevance_score || 0)} / 100</span>
        <div class="result-actions">
          <button class="button button-secondary" type="button" data-buyer-action="details">View Details</button>
          <button class="button button-primary" type="button" data-buyer-action="select" aria-pressed="${selected}">${selected ? 'Selected' : 'Select'}</button>
        </div>
      </article>
    `;
  }).join('');

  resultsTitle.textContent = `${results.length} businesses found`;
  updateSelectionControls(results);
}

function updateSelectionControls(displayedBuyers = visibleBuyers()) {
  const displayedIds = displayedBuyers.map((buyer) => String(buyer.id || '')).filter(Boolean);
  const allDisplayedSelected = displayedIds.length > 0 && displayedIds.every((id) => selectedBuyerIds.has(id));
  if (selectAllButton) {
    selectAllButton.disabled = displayedIds.length === 0;
    selectAllButton.textContent = allDisplayedSelected ? 'Clear Selection' : 'Select All';
  }
  if (selectedCount) selectedCount.textContent = `${selectedBuyerIds.size} selected`;
  if (contactSelectedButton) contactSelectedButton.hidden = selectedBuyerIds.size === 0;
}

function persistSelection() {
  if (storageScope) writeSessionValue(storageKey('selectedBuyerIds'), [...selectedBuyerIds]);
}

function setBuyerSelected(id, selected) {
  if (!id) return;
  if (selected) selectedBuyerIds.add(id);
  else selectedBuyerIds.delete(id);
  persistSelection();
  renderResults();
}

function openBuyerDetails(buyer) {
  detailsTitle.textContent = buyer.business_name || 'Business details';
  const emailStatus = isEmailUsable(buyer.email) ? 'Available' : buyer.email ? 'Invalid email' : 'Not available';
  const fields = [
    ['Business name', buyer.business_name],
    ['Category', buyer.category],
    ['Address', buyer.address],
    ['City', buyer.city],
    ['State', buyer.state],
    ['Country', buyer.country],
    ['Website', buyer.website],
    ['Phone', buyer.phone],
    ['Email', isEmailUsable(buyer.email) ? buyer.email : null],
    ['Email availability', emailStatus],
    ['Source', buyer.source],
    ['Relevance score', buyer.relevance_score == null ? null : `${buyer.relevance_score} / 100`],
  ];

  detailsFields.replaceChildren();
  fields.forEach(([label, value]) => {
    const term = document.createElement('dt');
    term.textContent = label;
    const description = document.createElement('dd');
    description.textContent = value == null || value === '' ? 'Not available' : String(value);
    detailsFields.append(term, description);
  });
  detailsDialog.showModal();
}

function restoreSearchContext() {
  const context = readSessionValue(storageKey('searchContext'), null);
  if (!context) return;
  ['product_category', 'product_description', 'buyer_type', 'location'].forEach((name) => {
    const input = form.elements.namedItem(name);
    if (input && typeof context[name] === 'string' && context[name].trim()) input.value = context[name];
  });
  const limit = form.elements.namedItem('limit');
  if (limit && context.limit) limit.value = String(context.limit);
}

function restoreBuyerControls() {
  const state = readSessionValue(storageKey('buyerControls'), {});
  if (filterText) filterText.value = state.filterText || '';
  if (emailFilter && state.emailFilter) emailFilter.value = state.emailFilter;
  if (websiteFilter && state.websiteFilter) websiteFilter.value = state.websiteFilter;
  if (sortSelect && state.sortMode) sortSelect.value = state.sortMode;
}

function persistBuyerControls() {
  if (!storageScope) return;
  writeSessionValue(storageKey('buyerControls'), {
    filterText: filterText?.value || '',
    emailFilter: emailFilter?.value || 'all',
    websiteFilter: websiteFilter?.value || 'all',
    sortMode: sortSelect?.value || 'relevance',
  });
}

async function loadSavedBuyers() {
  const user = await fetchCurrentUser();
  storageScope = String(user.id);
  restoreSearchContext();
  restoreBuyerControls();

  const response = await getBuyers();
  const allSavedBuyers = Array.isArray(response.buyers) ? response.buyers : [];
  const displayedIds = readSessionValue(storageKey('displayedBuyerIds'), null);
  if (Array.isArray(displayedIds)) {
    const buyersById = new Map(allSavedBuyers.map((buyer) => [String(buyer.id), buyer]));
    savedBuyers = displayedIds.map((id) => buyersById.get(String(id))).filter(Boolean);
  } else {
    savedBuyers = allSavedBuyers;
  }
  selectedBuyerIds = new Set(
    readSessionValue(storageKey('selectedBuyerIds'), []).map(String)
  );
  persistSelection();
  renderResults();
  renderStatus(savedBuyers.length ? `Loaded ${savedBuyers.length} saved buyers.` : 'No saved buyers yet. Start a search to discover real businesses.');
}

function resetBuyerSearchState() {
  if (filterText) filterText.value = '';
  if (emailFilter) emailFilter.value = 'all';
  if (websiteFilter) websiteFilter.value = 'all';
  if (sortSelect) sortSelect.value = 'relevance';
  if (filterToggle) filterToggle.setAttribute('aria-expanded', 'false');
  if (filterPanel) filterPanel.hidden = true;
  persistBuyerControls();
  persistSelection();
}

function getSearchPayload() {
  return {
    product_category: String(form.elements.namedItem('product_category')?.value || '').trim(),
    product_description: String(form.elements.namedItem('product_description')?.value || '').trim(),
    buyer_type: String(form.elements.namedItem('buyer_type')?.value || '').trim(),
    location: String(form.elements.namedItem('location')?.value || '').trim(),
    country: 'United States',
    limit: Number(form.elements.namedItem('limit')?.value || 10),
  };
}

function validateSearchPayload(payload) {
  if (!payload.product_category || !payload.buyer_type || !payload.location || !payload.product_description) {
    return 'Complete each search field before continuing.';
  }
  if (payload.product_description.length < 10) return 'Product description must contain at least 10 characters.';
  if (!Number.isInteger(payload.limit) || payload.limit < 1 || payload.limit > 100) return 'Choose a valid result limit.';
  return '';
}

resultContainer?.addEventListener('click', (event) => {
  const button = event.target.closest('[data-buyer-action]');
  if (!button) return;
  const card = button.closest('[data-buyer-id]');
  const buyer = savedBuyers.find((item) => String(item.id) === card?.dataset.buyerId);
  if (!buyer) return;

  if (button.dataset.buyerAction === 'details') {
    openBuyerDetails(buyer);
  } else if (button.dataset.buyerAction === 'select') {
    setBuyerSelected(String(buyer.id), !selectedBuyerIds.has(String(buyer.id)));
  }
});

resultContainer?.addEventListener('change', (event) => {
  if (!event.target.matches('.buyer-selection')) return;
  const id = event.target.closest('[data-buyer-id]')?.dataset.buyerId;
  setBuyerSelected(id, event.target.checked);
});

filterToggle?.addEventListener('click', () => {
  const expanded = filterToggle.getAttribute('aria-expanded') === 'true';
  filterToggle.setAttribute('aria-expanded', String(!expanded));
  filterPanel.hidden = expanded;
});

[filterText, emailFilter, websiteFilter].forEach((control) => {
  control?.addEventListener('input', () => {
    persistBuyerControls();
    renderResults();
  });
  control?.addEventListener('change', () => {
    persistBuyerControls();
    renderResults();
  });
});

sortSelect?.addEventListener('change', () => {
  persistBuyerControls();
  renderResults();
});

document.getElementById('clear-buyer-filters')?.addEventListener('click', () => {
  filterText.value = '';
  emailFilter.value = 'all';
  websiteFilter.value = 'all';
  sortSelect.value = 'relevance';
  persistBuyerControls();
  renderResults();
});

selectAllButton?.addEventListener('click', () => {
  const displayed = visibleBuyers();
  const ids = displayed.map((buyer) => String(buyer.id || '')).filter(Boolean);
  const clear = ids.length > 0 && ids.every((id) => selectedBuyerIds.has(id));
  ids.forEach((id) => clear ? selectedBuyerIds.delete(id) : selectedBuyerIds.add(id));
  persistSelection();
  renderResults();
});

closeDetailsButton?.addEventListener('click', () => detailsDialog.close());

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && detailsDialog?.open) detailsDialog.close();
});

form?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = getSearchPayload();
  const validationMessage = validateSearchPayload(payload);
  if (validationMessage) {
    renderStatus(validationMessage, 'notice error');
    return;
  }

  const submitButton = form.querySelector('[type="submit"]');
  if (submitButton) submitButton.disabled = true;
  writeSessionValue(storageKey('searchContext'), payload);
  renderLoadingStatus();

  try {
    const response = await searchBuyers(payload);
    const currentResults = Array.isArray(response.results) ? response.results : [];

    resetBuyerSearchState();
    savedBuyers = [];
    resultContainer.replaceChildren();
    resultsTitle.textContent = 'Loading current search results...';

    const savedResponse = await getBuyers();
    const allSavedBuyers = Array.isArray(savedResponse.buyers) ? savedResponse.buyers : [];
    savedBuyers = allSavedBuyers.slice(0, currentResults.length);
    writeSessionValue(storageKey('displayedBuyerIds'), savedBuyers.map((buyer) => String(buyer.id)));
    renderResults();

    const resultCount = savedBuyers.length;
    if (resultCount === 0) {
      renderStatus(`No mapped businesses matched ${payload.buyer_type} in ${payload.location}.`);
    } else {
      renderStatus(`Searching businesses in ${payload.location} for ${payload.buyer_type}.`);
    }
  } catch (error) {
    const message = searchErrorMessage(error);
    renderStatus(message, 'notice error');
    resultContainer.innerHTML = `<div class="empty-state-box"><h3>Search unavailable</h3><p>${escapeHtml(message)}</p></div>`;
    resultsTitle.textContent = 'Search unavailable';
  } finally {
    if (submitButton) submitButton.disabled = false;
  }
});

async function initializeBuyerResults() {
  try {
    await loadSavedBuyers();
  } catch (error) {
    renderStatus(error.status === 401 ? 'Your session has expired. Please log in again.' : 'Saved buyers could not be loaded. Please try again.', 'notice error');
    if (error.status !== 401) renderEmptyState('Saved buyers unavailable.');
  }
}

initializeBuyerResults();

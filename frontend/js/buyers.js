const form = document.getElementById('search-form');
const resultContainer = document.getElementById('results-container');
const resultsTitle = document.getElementById('results-title');
const resultsSummary = document.getElementById('results-summary');

function renderStatus(message, type = 'notice') {
  if (!resultsSummary) return;

  resultsSummary.innerHTML = `<div class="${type}">${message}</div>`;
}

function renderEmptyState() {
  resultContainer.innerHTML = `
    <div class="empty-state-box">
      <h3>No potential buyers found.</h3>
      <p>Try another buyer type or expand your location to continue the search.</p>
    </div>
  `;
}

function renderResults(results) {
  if (!Array.isArray(results) || results.length === 0) {
    renderEmptyState();
    resultsTitle.textContent = 'No results yet';
    return;
  }

  resultContainer.innerHTML = results
    .map(
      (buyer) => `
        <article class="result-card">
          <div class="result-top">
            <h3>${buyer.business_name || 'Business name unavailable'}</h3>
            <input type="checkbox" aria-label="Select ${buyer.business_name || 'lead'}" />
          </div>
          <div class="result-meta">
            <span class="meta-row">${buyer.category || 'Business type unavailable'}</span>
            <span class="meta-row">${buyer.city || buyer.state || 'Location unavailable'}</span>
            <span class="meta-row">${buyer.website ? buyer.website : 'Website unavailable'}</span>
            <span class="meta-row">${buyer.email ? buyer.email : 'Email not available'}</span>
          </div>
          <span class="lead-score">Lead Relevance ${buyer.relevance_score || 0} / 100</span>
          <div class="result-actions">
            <button class="button button-secondary" type="button">View Details</button>
            <button class="button button-primary" type="button">Select</button>
          </div>
        </article>
      `
    )
    .join('');

  resultsTitle.textContent = `${results.length} businesses found`;
}

form?.addEventListener('submit', async (event) => {
  event.preventDefault();

  const data = new FormData(form);
  const payload = {
    product_category: data.get('product_category'),
    product_description: data.get('product_description'),
    buyer_type: data.get('buyer_type'),
    location: data.get('location'),
    country: 'United States',
    limit: Number(data.get('limit') || 20),
  };

  renderStatus('<span class="loader">Finding potential buyers...</span>');

  try {
    const response = await searchBuyers(payload);
    const results = response.results || [];
    renderResults(results);
    renderStatus(`Searching businesses in ${payload.location} for ${payload.buyer_type}.`);
  } catch (error) {
    renderStatus(`We couldn't retrieve buyer results right now. Please try again in a moment.`, 'notice error');
    resultContainer.innerHTML = `
      <div class="empty-state-box">
        <h3>Search unavailable</h3>
        <p>${error.message}</p>
      </div>
    `;
    resultsTitle.textContent = 'Search unavailable';
  }
});

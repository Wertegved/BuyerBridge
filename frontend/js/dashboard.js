async function loadDashboard() {
  const leadsNode = document.getElementById('stat-leads');
  const emailsNode = document.getElementById('stat-emails');
  const searchesNode = document.getElementById('stat-searches');
  const searchHistoryNode = document.getElementById('search-history');
  const emailHistoryNode = document.getElementById('email-history');

  try {
    const dashboard = await getDashboardData();
    const searches = await getSearchHistory();
    const emails = await getEmailHistory();

    if (leadsNode) leadsNode.textContent = dashboard.total_leads ?? '0';
    if (emailsNode) emailsNode.textContent = dashboard.emails_sent ?? '0';
    if (searchesNode) searchesNode.textContent = dashboard.searches ?? searches.searches?.length ?? '0';

    if (searchHistoryNode) {
      const items = searches.searches && searches.searches.length ? searches.searches : [];
      searchHistoryNode.innerHTML = items.length
        ? items
            .slice(0, 5)
            .map(
              (item) => `
                <li>
                  <strong>${item.product_category || 'Unknown category'}</strong>
                  <div>${item.buyer_type || 'Unknown buyer type'} · ${item.location || 'No location'}</div>
                </li>
              `
            )
            .join('')
        : '<li class="empty-state">No searches yet.</li>';
    }

    if (emailHistoryNode) {
      const items = emails.emails && emails.emails.length ? emails.emails : [];
      emailHistoryNode.innerHTML = items.length
        ? items
            .slice(0, 5)
            .map(
              (item) => `
                <li>
                  <strong>${item.subject || 'No subject'}</strong>
                  <div>${item.status || 'Pending'} · ${item.sent_at || 'No date'}</div>
                </li>
              `
            )
            .join('')
        : '<li class="empty-state">No outreach activity yet.</li>';
    }
    return true;
  } catch (error) {
    if (searchHistoryNode) {
      searchHistoryNode.innerHTML = '<li class="empty-state">No searches yet.</li>';
    }
    if (emailHistoryNode) {
      emailHistoryNode.innerHTML = '<li class="empty-state">No outreach activity yet.</li>';
    }
    return false;
  }
}

const clearDataButton = document.getElementById('clear-all-data-button');
const clearDataStatus = document.getElementById('clear-data-status');

document.addEventListener('DOMContentLoaded', () => {
  const clearDataButton = document.getElementById('clear-all-data-button');
  const clearDataStatus = document.getElementById('clear-data-status');

  if (!clearDataButton) {
    console.error('BuyerBridge: Clear All Data button not found.');
    return;
  }

  clearDataButton.addEventListener('click', async (event) => {
    event.preventDefault();

    const confirmed = window.confirm(
      'Clear all of your search history, saved buyers from those searches, and outreach history? This cannot be undone.'
    );

    if (!confirmed) {
      return;
    }

    clearDataButton.disabled = true;

    if (clearDataStatus) {
      clearDataStatus.className = '';
      clearDataStatus.textContent = 'Clearing your data...';
    }

    try {
      const user = await fetchCurrentUser();

      if (!user || !user.id) {
        throw new Error('Authentication required. Please log in again.');
      }

      await clearDashboardData();

      // Clear only frontend selection/UI state.
      sessionStorage.removeItem(`buyerbridge.selectedBuyerIds.${user.id}`);

      // Refresh dashboard data from backend.
      const refreshed = await loadDashboard();

      if (!refreshed) {
        throw new Error(
          'Your data was cleared, but the dashboard could not be refreshed. Please reload the page.'
        );
      }

      if (clearDataStatus) {
        clearDataStatus.className = 'notice success';
        clearDataStatus.textContent =
          'Your search, buyer, and outreach data has been cleared.';
      }
    } catch (error) {
      console.error('BuyerBridge: Clear All Data failed:', error);

      if (clearDataStatus) {
        clearDataStatus.className = 'notice error';
        clearDataStatus.textContent =
          error?.message || 'Your data could not be cleared. Please try again.';
      }
    } finally {
      clearDataButton.disabled = false;
    }
  });
});
loadDashboard();

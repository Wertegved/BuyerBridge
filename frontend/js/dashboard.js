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
  } catch (error) {
    if (searchHistoryNode) {
      searchHistoryNode.innerHTML = '<li class="empty-state">No searches yet.</li>';
    }
    if (emailHistoryNode) {
      emailHistoryNode.innerHTML = '<li class="empty-state">No outreach activity yet.</li>';
    }
  }
}

loadDashboard();

const campaignStoragePrefix = 'buyerbridge.selectedBuyerIds.';
const campaignEmptyState = document.getElementById('campaign-empty-state');
const campaignWorkspace = document.getElementById('campaign-workspace');
const emptyRecipientCount = document.getElementById('empty-recipient-count');
const recipientCount = document.getElementById('recipient-count');
const selectedRecipients = document.getElementById('selected-recipients');
const addMoreRecipientsButton = document.getElementById('add-more-recipients');
const clearAllRecipientsButton = document.getElementById('clear-all-recipients');
const campaignForm = document.getElementById('campaign-compose-form');
const campaignStatus = document.getElementById('campaign-status');
const sendButton = document.getElementById('send-campaign-button');
const emailHistoryList = document.getElementById('email-history-list');

let selectedBuyers = [];
let selectedBuyerIds = [];
let isSending = false;
let selectedIdsStorageKey = '';

function isUsableEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || '').trim());
}

function escapeCampaignText(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function readSelectedIds(userId) {
  try {
    const raw = sessionStorage.getItem(`${campaignStoragePrefix}${userId}`);
    const value = raw ? JSON.parse(raw) : [];
    return Array.isArray(value) ? [...new Set(value.map(String))] : [];
  } catch (error) {
    return [];
  }
}

function persistSelectedIds(ids) {
  try {
    selectedBuyerIds = [...new Set(ids.map(String))];
    if (selectedBuyerIds.length) {
      sessionStorage.setItem(selectedIdsStorageKey, JSON.stringify(selectedBuyerIds));
    } else {
      sessionStorage.removeItem(selectedIdsStorageKey);
    }
    return true;
  } catch (error) {
    setCampaignStatus('Recipient changes could not be saved in this session. Please keep this page open.', 'notice error');
    return false;
  }
}

function setCampaignStatus(message, type = '') {
  campaignStatus.textContent = message;
  campaignStatus.className = type;
}

function showRecipientWorkspace() {
  campaignEmptyState.hidden = true;
  campaignWorkspace.hidden = false;
}

function updateSendButtonState() {
  sendButton.disabled = isSending
    || selectedBuyers.length === 0
    || selectedBuyers.length !== selectedBuyerIds.length
    || selectedBuyerIds.some(
      (id) => !selectedBuyers.some((buyer) => String(buyer.id) === id)
    )
    || selectedBuyers.some((buyer) => !isUsableEmail(buyer.email));
}

function removeRecipient(id) {
  selectedBuyers = selectedBuyers.filter((buyer) => String(buyer.id) !== id);
  persistSelectedIds(selectedBuyerIds.filter((selectedId) => selectedId !== id));
  if (!selectedBuyers.length) {
    campaignWorkspace.hidden = true;
    campaignEmptyState.hidden = false;
    selectedRecipients.replaceChildren();
    recipientCount.textContent = '';
    emptyRecipientCount.textContent = '0 selected';
    updateSendButtonState();
    return;
  }
  renderSelectedRecipients();
}

function clearRecipients() {
  selectedBuyers = [];
  persistSelectedIds([]);
  campaignWorkspace.hidden = true;
  campaignEmptyState.hidden = false;
  selectedRecipients.replaceChildren();
  recipientCount.textContent = '';
  emptyRecipientCount.textContent = '0 selected';
  updateSendButtonState();
}

function renderEmailHistory(emails) {
  if (!Array.isArray(emails) || emails.length === 0) {
    emailHistoryList.innerHTML = '<li class="empty-state">No email activity yet.</li>';
    return;
  }

  emailHistoryList.innerHTML = emails.map((email) => `
    <li>
      <strong>${escapeCampaignText(email.subject || 'No subject')}</strong>
      <small>Status: ${escapeCampaignText(email.status || 'Unknown')} · ${escapeCampaignText(email.sent_at || email.created_at || 'Date unavailable')}</small>
    </li>
  `).join('');
}

function renderSelectedRecipients() {
  addMoreRecipientsButton.hidden = selectedBuyers.length === 0;
  clearAllRecipientsButton.hidden = selectedBuyers.length === 0;
  selectedRecipients.replaceChildren();
  selectedBuyers.forEach((buyer) => {
    const item = document.createElement('li');
    const details = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = buyer.business_name || 'Business name unavailable';
    const website = document.createElement('small');
    website.textContent = String(buyer.website || '').trim() || 'Website unavailable';
    const email = document.createElement('small');
    email.textContent = isUsableEmail(buyer.email) ? buyer.email : 'Email not available';
    const removeButton = document.createElement('button');
    removeButton.className = 'button button-secondary';
    removeButton.type = 'button';
    removeButton.textContent = 'Remove';
    removeButton.setAttribute('aria-label', `Remove ${name.textContent}`);
    removeButton.addEventListener('click', () => removeRecipient(String(buyer.id)));
    details.append(name, website, email);
    item.append(details, removeButton);
    selectedRecipients.append(item);
  });

  const sendableCount = selectedBuyers.filter((buyer) => isUsableEmail(buyer.email)).length;
  recipientCount.textContent = `${selectedBuyers.length} selected · ${sendableCount} with a valid email address`;
  if (sendableCount !== selectedBuyers.length) {
    setCampaignStatus('Every selected recipient must have a valid email address before sending.');
  } else if (
    campaignStatus.textContent === 'Every selected recipient must have a valid email address before sending.'
  ) {
    setCampaignStatus('');
  }
  updateSendButtonState();
}

function campaignErrorMessage(error) {
  if (error.status === 401) return 'Your session has expired. Please log in again.';
  if (error.status === 422) return error.message || 'Check the subject and message fields.';
  if (error.status === 503) return 'Email provider is unavailable or not configured. No email was sent.';
  return error.message || 'Email request failed. Please try again.';
}

async function loadEmailHistory() {
  try {
    const response = await getEmailHistory();
    renderEmailHistory(response.emails || []);
  } catch (error) {
    emailHistoryList.innerHTML = `<li class="empty-state">${escapeCampaignText(campaignErrorMessage(error))}</li>`;
  }
}

async function refreshSelectedRecipients() {
  const selectedIds = selectedIdsStorageKey
    ? readSelectedIds(selectedIdsStorageKey.slice(campaignStoragePrefix.length))
    : [];
  selectedBuyerIds = selectedIds;
  if (!selectedIds.length) {
    selectedBuyers = [];
    campaignEmptyState.hidden = false;
    campaignWorkspace.hidden = true;
    selectedRecipients.replaceChildren();
    recipientCount.textContent = '';
    emptyRecipientCount.textContent = '0 selected';
    updateSendButtonState();
    return;
  }

  const response = await getBuyers(selectedIds);
  const selectedIdSet = new Set(selectedIds);
  const renderedIds = new Set();
  selectedBuyers = (response.buyers || []).filter((buyer) => {
    const id = String(buyer.id);
    if (!selectedIdSet.has(id) || renderedIds.has(id)) return false;
    renderedIds.add(id);
    return true;
  });
  showRecipientWorkspace();
  renderSelectedRecipients();
}

async function initializeCampaigns() {
  loadEmailHistory();

  try {
    const user = await fetchCurrentUser();
    selectedIdsStorageKey = `${campaignStoragePrefix}${user.id}`;
    await refreshSelectedRecipients();
  } catch (error) {
    campaignEmptyState.hidden = true;
    campaignWorkspace.hidden = false;
    recipientCount.textContent = 'Selected recipients could not be loaded.';
    selectedRecipients.replaceChildren();
    updateSendButtonState();
    const message = campaignErrorMessage(error);
    setCampaignStatus(message, 'notice error');
  }
}

window.addEventListener('pageshow', async (event) => {
  if (!event.persisted || !selectedIdsStorageKey) return;
  try {
    await refreshSelectedRecipients();
  } catch (error) {
    selectedBuyers = [];
    selectedRecipients.replaceChildren();
    updateSendButtonState();
    setCampaignStatus(campaignErrorMessage(error), 'notice error');
  }
});

addMoreRecipientsButton?.addEventListener('click', () => {
  window.location.href = 'buyers.html';
});

clearAllRecipientsButton?.addEventListener('click', clearRecipients);

campaignForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const subject = campaignForm.elements.subject.value.trim();
  const message = campaignForm.elements.message.value.trim();

  if (!subject || subject.length < 3 || !message || message.length < 10) {
    setCampaignStatus('Enter a subject of at least 3 characters and a message of at least 10 characters.', 'notice error');
    return;
  }
  if (
    !selectedBuyers.length
    || selectedBuyers.length !== selectedBuyerIds.length
    || selectedBuyerIds.some(
      (id) => !selectedBuyers.some((buyer) => String(buyer.id) === id)
    )
    || selectedBuyers.some((buyer) => !isUsableEmail(buyer.email))
  ) {
    setCampaignStatus('Every selected recipient must have a valid email address before sending.', 'notice error');
    return;
  }

  isSending = true;
  sendButton.disabled = true;
  setCampaignStatus('Sending email to selected recipients...');
  try {
    const response = await sendEmail({
      buyer_ids: selectedBuyerIds,
      subject,
      message,
    });
    const results = Array.isArray(response.results) ? response.results : [];
    const sent = results.filter((result) => result.status === 'sent').length;
    const failed = results.filter((result) => result.status === 'failed').length;
    setCampaignStatus(`Email results: ${sent} sent, ${failed} failed.`);
    await loadEmailHistory();
  } catch (error) {
    setCampaignStatus(campaignErrorMessage(error), 'notice error');
  } finally {
    isSending = false;
    renderSelectedRecipients();
  }
});

initializeCampaigns();

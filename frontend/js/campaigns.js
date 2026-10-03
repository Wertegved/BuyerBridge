const campaignStoragePrefix = 'buyerbridge.selectedBuyerIds.';
const campaignEmptyState = document.getElementById('campaign-empty-state');
const campaignWorkspace = document.getElementById('campaign-workspace');
const recipientCount = document.getElementById('recipient-count');
const selectedRecipients = document.getElementById('selected-recipients');
const campaignForm = document.getElementById('campaign-compose-form');
const campaignStatus = document.getElementById('campaign-status');
const sendButton = document.getElementById('send-campaign-button');
const emailHistoryList = document.getElementById('email-history-list');

let selectedBuyers = [];
let isSending = false;

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
    return Array.isArray(value) ? value.map(String) : [];
  } catch (error) {
    return [];
  }
}

function setCampaignStatus(message, type = '') {
  campaignStatus.textContent = message;
  campaignStatus.className = type;
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
  selectedRecipients.replaceChildren();
  selectedBuyers.forEach((buyer) => {
    const item = document.createElement('li');
    const name = document.createElement('strong');
    name.textContent = buyer.business_name || 'Business name unavailable';
    const email = document.createElement('small');
    email.textContent = isUsableEmail(buyer.email) ? buyer.email : buyer.email ? 'Invalid email address' : 'Email not available';
    item.append(name, email);
    selectedRecipients.append(item);
  });

  const sendableCount = selectedBuyers.filter((buyer) => isUsableEmail(buyer.email)).length;
  recipientCount.textContent = `${selectedBuyers.length} selected · ${sendableCount} with a valid email address`;
  if (sendableCount === 0) {
    setCampaignStatus('No selected recipients have a usable email address. Nothing will be sent.');
  }
  sendButton.disabled = isSending || sendableCount === 0;
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

async function initializeCampaigns() {
  loadEmailHistory();

  try {
    const user = await fetchCurrentUser();
    const selectedIds = readSelectedIds(user.id);
    if (!selectedIds.length) {
      campaignEmptyState.hidden = false;
      campaignWorkspace.hidden = true;
      return;
    }

    const response = await getBuyers();
    const selectedIdSet = new Set(selectedIds);
    selectedBuyers = (response.buyers || []).filter((buyer) => selectedIdSet.has(String(buyer.id)));
    if (!selectedBuyers.length) {
      sessionStorage.removeItem(`${campaignStoragePrefix}${user.id}`);
      campaignEmptyState.hidden = false;
      campaignWorkspace.hidden = true;
      return;
    }

    campaignEmptyState.hidden = true;
    campaignWorkspace.hidden = false;
    renderSelectedRecipients();
  } catch (error) {
    campaignEmptyState.hidden = true;
    campaignWorkspace.hidden = false;
    recipientCount.textContent = 'Selected recipients could not be loaded.';
    selectedRecipients.replaceChildren();
    sendButton.disabled = true;
    const message = campaignErrorMessage(error);
    setCampaignStatus(message, 'notice error');
  }
}

campaignForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const subject = campaignForm.elements.subject.value.trim();
  const message = campaignForm.elements.message.value.trim();
  const recipients = selectedBuyers.filter((buyer) => isUsableEmail(buyer.email));

  if (!subject || subject.length < 3 || !message || message.length < 10) {
    setCampaignStatus('Enter a subject of at least 3 characters and a message of at least 10 characters.', 'notice error');
    return;
  }
  if (!recipients.length) {
    setCampaignStatus('No selected recipients have a usable email address. Nothing will be sent.', 'notice error');
    return;
  }

  isSending = true;
  sendButton.disabled = true;
  setCampaignStatus('Sending email to selected recipients...');
  try {
    const response = await sendEmail({
      buyer_ids: recipients.map((buyer) => String(buyer.id)),
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

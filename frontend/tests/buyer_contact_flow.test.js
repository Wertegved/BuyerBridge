import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function makeElement(id = '') {
  const listeners = new Map();
  return {
    id,
    hidden: false,
    disabled: false,
    textContent: '',
    className: '',
    innerHTML: '',
    children: [],
    attributes: {},
    elements: {
      namedItem(name) {
        return {
          value: {
            product_category: 'Furniture',
            product_description: 'Commercial furniture for design projects',
            buyer_type: 'Interior Designers',
            location: 'New York, NY',
            limit: '10',
          }[name],
        };
      },
    },
    querySelector() {
      return makeElement('submit');
    },
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    getListener(type) {
      return listeners.get(type);
    },
    append(...children) {
      this.children.push(...children);
    },
    replaceChildren(...children) {
      this.children = children;
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    showModal() {},
    close() {},
  };
}

function makeSessionStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

function makeDocument(ids) {
  const elements = new Map(ids.map((id) => [id, makeElement(id)]));
  return {
    elements,
    getElementById(id) {
      return elements.get(id) || null;
    },
    createElement() {
      return makeElement();
    },
    addEventListener() {},
  };
}

function runScript(file, context) {
  vm.runInNewContext(
    fs.readFileSync(path.join(root, 'js', file), 'utf8'),
    context,
    { filename: file },
  );
}

function nextTurn() {
  return new Promise((resolve) => setImmediate(resolve));
}

test('Find Buyers renders the current search response without refetching or stale cached records', async () => {
  const document = makeDocument([
    'search-form',
    'results-container',
    'results-title',
    'results-summary',
    'filter-toggle',
    'buyer-filter-panel',
    'buyer-filter-text',
    'buyer-email-filter',
    'buyer-website-filter',
    'sort-by',
    'select-all-button',
    'selected-count',
    'contact-selected-button',
    'buyer-details-dialog',
    'buyer-detail-title',
    'buyer-detail-fields',
    'close-buyer-details',
    'clear-buyer-filters',
  ]);
  const sessionStorage = makeSessionStorage({
    'buyerbridge.displayedBuyerIds.7': JSON.stringify(['old-id']),
  });
  let savedBuyerFetches = 0;
  const currentSearchBuyer = {
    id: 'current-id',
    business_name: 'Current Search Studio',
    category: 'Interior Design',
    city: 'New York',
    website: 'https://current.example',
    email: 'current@example.com',
    relevance_score: 92,
  };
  const context = {
    document,
    sessionStorage,
    fetchCurrentUser: async () => ({ id: 7 }),
    getBuyers: async () => {
      savedBuyerFetches += 1;
      return {
        buyers: [{
          id: 'old-id',
          business_name: 'Stale Studio',
          website: 'https://stale.example',
          email: 'stale@example.com',
        }],
      };
    },
    searchBuyers: async () => ({ results: [currentSearchBuyer] }),
    window: { location: { href: '' } },
  };

  runScript('buyers.js', context);
  await nextTurn();
  await nextTurn();
  const form = document.getElementById('search-form');
  await form.getListener('submit')({ preventDefault() {} });

  const renderedCards = document.getElementById('results-container').innerHTML;
  assert.match(renderedCards, /Current Search Studio/);
  assert.match(renderedCards, /https:\/\/current\.example/);
  assert.match(renderedCards, /current@example\.com/);
  assert.doesNotMatch(renderedCards, /Stale Studio|stale@example\.com|old-id/);
  assert.equal(savedBuyerFetches, 1, 'only the initial saved-buyer page load may fetch /api/buyers');
});

test('Campaigns fetches selected IDs and renders latest persisted contact fields', async () => {
  const document = makeDocument([
    'campaign-empty-state',
    'campaign-workspace',
    'empty-recipient-count',
    'recipient-count',
    'selected-recipients',
    'add-more-recipients',
    'clear-all-recipients',
    'campaign-compose-form',
    'campaign-status',
    'send-campaign-button',
    'email-history-list',
  ]);
  const selectedIds = ['buyer-1', 'buyer-2'];
  const sessionStorage = makeSessionStorage({
    'buyerbridge.selectedBuyerIds.7': JSON.stringify(selectedIds),
  });
  const fetchedIdLists = [];
  const context = {
    document,
    sessionStorage,
    window: { addEventListener() {} },
    fetchCurrentUser: async () => ({ id: 7 }),
    getEmailHistory: async () => ({ emails: [] }),
    getBuyers: async (ids) => {
      fetchedIdLists.push(ids);
      return {
        buyers: [
          {
            id: 'buyer-1',
            business_name: 'Latest One',
            website: 'https://latest-one.example',
            email: 'latest-one@example.com',
          },
          {
            id: 'buyer-2',
            business_name: 'Latest Two',
            website: null,
            email: null,
          },
        ],
      };
    },
    sendEmail: async () => ({ results: [] }),
  };

  runScript('campaigns.js', context);
  await nextTurn();
  await nextTurn();

  assert.equal(JSON.stringify(fetchedIdLists), JSON.stringify([selectedIds]));
  const listItems = document.getElementById('selected-recipients').children;
  assert.equal(listItems.length, 2, 'recipients without email remain visible');
  assert.deepEqual(
    listItems.map((item) => item.children[0].children.map((child) => child.textContent)),
    [
      ['Latest One', 'https://latest-one.example', 'latest-one@example.com'],
      ['Latest Two', 'Website unavailable', 'Email not available'],
    ],
  );
  assert.equal(document.getElementById('send-campaign-button').disabled, true);
});

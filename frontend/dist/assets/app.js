const endpointSpecs = [
  {
    key: 'health',
    label: 'Platform',
    url: '/api/platform/health',
    target: '[data-metric="health"]',
    noteTarget: '[data-note="health"]',
    format: (payload) => payload.status || 'unknown',
    note: (payload) => payload.status === 'ok' ? 'platform is healthy' : 'check backend logs',
  },
  {
    key: 'storage',
    label: 'Storage',
    url: '/api/storage/overview',
    target: '[data-metric="storage"]',
    noteTarget: '[data-note="storage"]',
    format: (payload) => `${payload.public_file_count} public / ${payload.upload_file_count} uploads`,
    note: (payload) => `${payload.vault_dir} mounted`,
  },
  {
    key: 'models',
    label: 'Models',
    url: '/api/models/catalog',
    target: '[data-metric="models"]',
    noteTarget: '[data-note="models"]',
    format: (payload) => `${payload.summary.bundle_count} bundles`,
    note: (payload) => `${payload.summary.selectable_bundle_count} selectable`,
  },
  {
    key: 'knowledge',
    label: 'Knowledge',
    url: '/api/knowledge/overview',
    target: '[data-metric="knowledge"]',
    noteTarget: '[data-note="knowledge"]',
    format: (payload) => `${payload.item_count} items`,
    note: (payload) => `${payload.engram_count ?? 0} engrams`,
  },
];

const consoleEl = document.querySelector('[data-console]');
const runtimeBadge = document.querySelector('[data-runtime-status]');
const runtimeNote = document.querySelector('[data-runtime-note]');

const nowLabel = () =>
  new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date());

const setText = (selector, text) => {
  const element = document.querySelector(selector);
  if (element) {
    element.textContent = text;
  }
};

const appendLog = (message, tone = 'muted') => {
  if (!consoleEl) {
    return;
  }

  const line = document.createElement('div');
  line.className = `console-line ${tone}`;
  line.textContent = message;
  consoleEl.appendChild(line);
};

const loadJson = async (url) => {
  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return response.json();
};

const updateBadge = (status) => {
  if (!runtimeBadge) {
    return;
  }

  runtimeBadge.textContent = status.label;
  runtimeBadge.dataset.tone = status.tone;
};

const hydrateEndpoint = async (spec) => {
  setText(spec.target, 'loading');
  setText(spec.noteTarget, `fetching ${spec.url}`);

  try {
    const payload = await loadJson(spec.url);
    const value = spec.format(payload);
    const note = spec.note(payload);
    setText(spec.target, value);
    setText(spec.noteTarget, note);
    appendLog(`${spec.label}: ${value} (${note})`, 'ok');
    return { ok: true, payload };
  } catch (error) {
    const fallback = 'offline';
    setText(spec.target, fallback);
    setText(spec.noteTarget, error.message);
    appendLog(`${spec.label} failed: ${error.message}`, 'bad');
    return { ok: false, error };
  }
};

const boot = async () => {
  appendLog(`frontend shell ready at ${nowLabel()}`, 'muted');

  const results = await Promise.all(endpointSpecs.map((spec) => hydrateEndpoint(spec)));
  const successCount = results.filter((result) => result.ok).length;

  if (successCount === endpointSpecs.length) {
    updateBadge({ label: 'Live', tone: 'ok' });
    if (runtimeNote) {
      runtimeNote.textContent = 'All backend endpoints responded successfully.';
    }
    appendLog('all monitored endpoints are responding', 'ok');
    return;
  }

  if (successCount > 0) {
    updateBadge({ label: 'Partial', tone: 'warn' });
    if (runtimeNote) {
      runtimeNote.textContent = 'Some endpoints responded, some are offline or still initializing.';
    }
    appendLog('runtime is partially available', 'warn');
    return;
  }

  updateBadge({ label: 'Offline', tone: 'bad' });
  if (runtimeNote) {
    runtimeNote.textContent = 'No monitored endpoint responded. Check the API service and mounts.';
  }
  appendLog('no backend endpoints responded', 'bad');
};

document.addEventListener('DOMContentLoaded', boot);

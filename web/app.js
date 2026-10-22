// TenderMatch Salesperson Review Interface Logic

const STATE = {
  token: localStorage.getItem('tendermatch_token') || 'tendermatch-local-review',
  reviewer: localStorage.getItem('tendermatch_reviewer') || '',
  tenders: [],
  reviewers: [],
  currentFilter: 'all',
  searchQuery: '',
};

document.addEventListener('DOMContentLoaded', () => {
  initAuth();
  setupEventListeners();
  loadReviewers();
  loadTenders();
});

function initAuth() {
  updateAuthUI();
  if (!STATE.token || !STATE.reviewer) {
    showAuthModal();
  }
}

function updateAuthUI() {
  const dot = document.getElementById('auth-dot');
  const label = document.getElementById('auth-user-label');
  if (STATE.token && STATE.reviewer) {
    dot.classList.add('active');
    label.textContent = STATE.reviewer;
  } else {
    dot.classList.remove('active');
    label.textContent = 'Unauthenticated';
  }
}

function setupEventListeners() {
  document.getElementById('auth-modal-btn').addEventListener('click', showAuthModal);
  document.getElementById('auth-modal-close').addEventListener('click', hideAuthModal);
  document.getElementById('auth-cancel-btn').addEventListener('click', hideAuthModal);
  document.getElementById('auth-save-btn').addEventListener('click', saveAuth);

  document.getElementById('tender-search').addEventListener('input', (e) => {
    STATE.searchQuery = e.target.value.toLowerCase().trim();
    renderTenders();
  });

  const filterButtons = document.querySelectorAll('.filter-chip');
  filterButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      filterButtons.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      STATE.currentFilter = btn.dataset.filter;
      renderTenders();
    });
  });
}

function showAuthModal() {
  document.getElementById('auth-token-input').value = STATE.token;
  document.getElementById('reviewer-select').value = STATE.reviewer;
  document.getElementById('auth-modal').style.display = 'flex';
}

function hideAuthModal() {
  document.getElementById('auth-modal').style.display = 'none';
}

function saveAuth() {
  const token = document.getElementById('auth-token-input').value.trim();
  const reviewer = document.getElementById('reviewer-select').value.trim();
  if (!token || !reviewer) {
    showToast('Please enter both security token and reviewer identity', true);
    return;
  }
  STATE.token = token;
  STATE.reviewer = reviewer;
  localStorage.setItem('tendermatch_token', token);
  localStorage.setItem('tendermatch_reviewer', reviewer);
  updateAuthUI();
  hideAuthModal();
  showToast(`Authenticated as ${reviewer}`);
  loadTenders();
}

async function apiFetch(endpoint, options = {}) {
  const headers = options.headers || {};
  if (STATE.token) {
    headers['Authorization'] = `Bearer ${STATE.token}`;
  }
  options.headers = headers;
  const res = await fetch(endpoint, options);
  if (res.status === 401) {
    showAuthModal();
    throw new Error('Unauthorized');
  }
  return res.json();
}

async function loadReviewers() {
  try {
    const data = await apiFetch('/api/reviewers');
    STATE.reviewers = data.reviewers || [];
    const select = document.getElementById('reviewer-select');
    select.innerHTML = '<option value="">Select an authorized reviewer...</option>';
    STATE.reviewers.forEach((rev) => {
      const opt = document.createElement('option');
      opt.value = rev;
      opt.textContent = rev;
      select.appendChild(opt);
    });
    if (STATE.reviewer) {
      select.value = STATE.reviewer;
    }
  } catch (err) {
    console.warn('Failed to load reviewers list', err);
  }
}

async function loadTenders() {
  const container = document.getElementById('tender-cards-list');
  container.innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Loading opportunities...</p>
    </div>
  `;

  try {
    const data = await apiFetch('/api/tenders');
    STATE.tenders = data.tenders || [];
    updateFilterCounts();
    renderTenders();
  } catch (err) {
    container.innerHTML = `
      <div class="loading-state">
        <p style="color: var(--accent-rose);">Failed to load opportunities. Verify authentication token.</p>
      </div>
    `;
  }
}

function updateFilterCounts() {
  const allCount = STATE.tenders.length;
  const unreviewedCount = STATE.tenders.filter((t) => !t.feedback || t.feedback.length === 0).length;
  const amendedCount = STATE.tenders.filter((t) => t.amendment).length;
  const reviewedCount = STATE.tenders.filter((t) => t.feedback && t.feedback.length > 0).length;

  document.getElementById('count-all').textContent = allCount;
  document.getElementById('count-unreviewed').textContent = unreviewedCount;
  document.getElementById('count-amended').textContent = amendedCount;
  document.getElementById('count-reviewed').textContent = reviewedCount;
}

function renderTenders() {
  const container = document.getElementById('tender-cards-list');
  container.innerHTML = '';

  let filtered = STATE.tenders;

  // Apply chip filter
  if (STATE.currentFilter === 'unreviewed') {
    filtered = filtered.filter((t) => !t.feedback || t.feedback.length === 0);
  } else if (STATE.currentFilter === 'amended') {
    filtered = filtered.filter((t) => t.amendment);
  } else if (STATE.currentFilter === 'reviewed') {
    filtered = filtered.filter((t) => t.feedback && t.feedback.length > 0);
  }

  // Apply search query
  if (STATE.searchQuery) {
    filtered = filtered.filter((t) => {
      const text = `${t.title || ''} ${t.organization || ''} ${t.tender_id || ''}`.toLowerCase();
      return text.includes(STATE.searchQuery);
    });
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="loading-state">
        <p>No matching opportunities found for current filter.</p>
      </div>
    `;
    return;
  }

  filtered.forEach((t) => {
    const card = createTenderCard(t);
    container.appendChild(card);
  });
}

function createTenderCard(tender) {
  const card = document.createElement('article');
  card.className = 'tender-card';
  card.id = `tender-card-${tender.id}`;

  const isAmended = !!tender.amendment;
  const hasFeedback = tender.feedback && tender.feedback.length > 0;
  const topMatch = (tender.matches && tender.matches[0]) || null;
  const mfgName = topMatch ? topMatch.manufacturer_name : 'No manufacturer matched';
  const mfgId = topMatch ? topMatch.manufacturer_id : 'unassigned';

  // Badge determination
  let badgeHtml = '';
  if (isAmended) {
    badgeHtml = '<span class="badge badge-updated">Corrigendum / Updated</span>';
  } else if (topMatch && topMatch.score >= 0.70) {
    badgeHtml = '<span class="badge badge-high">High Signal</span>';
  } else {
    badgeHtml = '<span class="badge badge-explore">Exploration Candidate</span>';
  }

  // Decision 6 questions
  const q1Worth = topMatch && topMatch.score >= 0.70 ? 'High probability fit' : 'Moderate signal; review requirements';
  const q2Mfg = topMatch ? `${mfgName} (ID: ${mfgId})` : 'Unassigned manufacturer';
  const q3Why = topMatch ? `Semantic score: ${(topMatch.score * 100).toFixed(0)}%` : 'General keywords in listing';
  const q4Unproven = tender.unverified_requirements ? tender.unverified_requirements.join('; ') : 'Document specs unverified natively';
  const q5Changed = isAmended ? `Amendment: ${tender.amendment.change_types.join(', ')}` : 'Initial publication';
  const q6Action = isAmended ? 'Recheck amendment terms & deadline' : 'Review manufacturer fit and submit feedback';

  let feedbackHistoryHtml = '';
  if (hasFeedback) {
    const latest = tender.feedback[0];
    feedbackHistoryHtml = `
      <div class="feedback-history-badge">
        Reviewed: <strong>${latest.label.replace(/_/g, ' ')}</strong> by ${latest.reviewer}
      </div>
    `;
  }

  card.innerHTML = `
    <div class="card-top">
      <div class="card-title-group">
        <div class="badge-row">
          ${badgeHtml}
          ${feedbackHistoryHtml}
        </div>
        <h3 class="tender-title">${escapeHtml(tender.title || 'Untitled Tender')}</h3>
        <div class="tender-meta">
          <span>🏛️ ${escapeHtml(tender.organization || 'Unknown Organization')}</span>
          <span>📄 Ref: ${escapeHtml(tender.tender_id || 'Not specified')}</span>
          <span>📅 Due: ${escapeHtml(tender.closing_date || 'Not listed')}</span>
          ${tender.source_url ? `<a href="${escapeHtml(tender.source_url)}" target="_blank" rel="noopener" style="color: var(--accent-cyan);">Official Portal ↗</a>` : ''}
        </div>
      </div>
    </div>

    <!-- 6 Key Salesperson Decision Questions -->
    <div class="decision-matrix">
      <div class="decision-item">
        <span class="decision-label">1. Worth Reviewing?</span>
        <span class="decision-value highlight">${q1Worth}</span>
      </div>
      <div class="decision-item">
        <span class="decision-label">2. Recommended Fit</span>
        <span class="decision-value">${escapeHtml(q2Mfg)}</span>
      </div>
      <div class="decision-item">
        <span class="decision-label">3. Why it matched</span>
        <span class="decision-value">${escapeHtml(q3Why)}</span>
      </div>
      <div class="decision-item">
        <span class="decision-label">4. Not Yet Proven</span>
        <span class="decision-value warning">${escapeHtml(q4Unproven)}</span>
      </div>
      <div class="decision-item">
        <span class="decision-label">5. What Changed</span>
        <span class="decision-value">${escapeHtml(q5Changed)}</span>
      </div>
      <div class="decision-item">
        <span class="decision-label">6. Practical Action</span>
        <span class="decision-value">${escapeHtml(q6Action)}</span>
      </div>
    </div>

    <!-- Feedback Action Panel -->
    <div class="feedback-panel">
      <div class="feedback-header">
        <span>Salesperson Adjudication</span>
        <span style="font-size: 0.75rem; color: var(--text-muted);">One-click audit capture</span>
      </div>

      <div class="action-buttons-grid">
        <button class="btn-feedback btn-relevant" data-label="relevant">✓ Relevant</button>
        <button class="btn-feedback btn-worth-pursuing" data-label="worth_pursuing">★ Pursue</button>
        <button class="btn-feedback btn-not-relevant" data-label="not_relevant">✗ Not Relevant</button>
        <button class="btn-feedback btn-wrong-manufacturer" data-label="wrong_manufacturer">Wrong Mfg</button>
        <button class="btn-feedback btn-incorrect-product-category" data-label="incorrect_product_category">Wrong Category</button>
        <button class="btn-feedback btn-missing-evidence" data-label="missing_technical_evidence">Missing Evidence</button>
        <button class="btn-feedback btn-already-known" data-label="already_known">Already Known</button>
        <button class="btn-feedback btn-eligibility-not-met" data-label="eligibility_not_met">Ineligible</button>
      </div>

      <div class="feedback-reason-row">
        <input type="text" class="reason-input" placeholder="Optional notes (e.g. specs match Korvus HEX series; client contacted)..." aria-label="Reviewer notes">
      </div>
    </div>
  `;

  // Attach button click handlers
  const buttons = card.querySelectorAll('.btn-feedback');
  const reasonInput = card.querySelector('.reason-input');

  buttons.forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!STATE.reviewer) {
        showToast('Please select your reviewer identity first', true);
        showAuthModal();
        return;
      }

      const label = btn.dataset.label;
      const reason = reasonInput.value.trim();

      try {
        btn.disabled = true;
        await submitFeedback({
          tender_identity_key: tender.identity_key,
          manufacturer_id: mfgId,
          label: label,
          reviewer: STATE.reviewer,
          reason: reason || undefined,
          tender_version: tender.version_fingerprint,
        });

        showToast(`Feedback recorded: ${label.replace(/_/g, ' ')}`);
        // Update local tender state optimistically
        if (!tender.feedback) tender.feedback = [];
        tender.feedback.unshift({
          label: label,
          reviewer: STATE.reviewer,
          reviewed_at: new Date().toISOString(),
          reason: reason,
          manufacturer_id: mfgId,
        });
        updateFilterCounts();
        renderTenders();
      } catch (err) {
        showToast(`Failed to record feedback: ${err.message}`, true);
        btn.disabled = false;
      }
    });
  });

  return card;
}

async function submitFeedback(payload) {
  const result = await apiFetch('/api/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringifySafe(payload),
  });
  if (result.error) {
    throw new Error(result.error);
  }
  return result;
}

function showToast(message, isError = false) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.style.borderColor = isError ? 'var(--accent-rose)' : 'var(--accent-emerald)';
  toast.style.display = 'block';
  setTimeout(() => {
    toast.style.display = 'none';
  }, 3500);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function jsonStringifySafe(obj) {
  return JSON.stringify(obj);
}

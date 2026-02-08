/* ═══════════════════════════════════════════════════════════
   AU Property Ops Copilot — Client-Side Logic
   ═══════════════════════════════════════════════════════════ */

// ── Utilities ───────────────────────────────────────────────

function showLoading(text = 'Processing…') {
  document.getElementById('loading-text').textContent = text;
  document.getElementById('loading').classList.add('visible');
}

function hideLoading() {
  document.getElementById('loading').classList.remove('visible');
}

function toast(message, type = 'success') {
  const container = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function openModal(id) {
  document.getElementById(id).classList.add('visible');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('visible');
}

// ── Deal Management ─────────────────────────────────────────

async function createDeal(event) {
  event.preventDefault();
  const form = document.getElementById('newDealForm');
  const data = new FormData(form);

  showLoading('Creating deal…');
  try {
    const resp = await fetch('/api/deals', { method: 'POST', body: data });
    const result = await resp.json();
    closeModal('newDealModal');
    toast('Deal created: ' + result.address);
    window.location.href = '/deals/' + result.id;
  } catch (e) {
    toast('Failed to create deal: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

// ── Photo Upload ────────────────────────────────────────────

async function uploadPhotos(files, dealId) {
  if (!files || files.length === 0) return;

  const formData = new FormData();
  for (const f of files) {
    formData.append('files', f);
  }

  showLoading(`Uploading ${files.length} photo(s)…`);
  try {
    const resp = await fetch(`/api/deals/${dealId}/photos`, {
      method: 'POST', body: formData
    });
    const result = await resp.json();
    toast(`${result.count} photo(s) uploaded`);
    window.location.reload();
  } catch (e) {
    toast('Upload failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

function handlePhotoDrop(event, dealId) {
  event.preventDefault();
  event.currentTarget.classList.remove('dragover');
  const files = event.dataTransfer.files;
  uploadPhotos(files, dealId);
}

// ── Wizard Navigation ───────────────────────────────────────

function goToStep(step) {
  // Update step indicators
  document.querySelectorAll('.wizard-step').forEach(el => {
    const s = parseInt(el.dataset.step);
    el.classList.remove('active', 'completed');
    if (s === step) el.classList.add('active');
    else if (s < step) el.classList.add('completed');
  });

  // Show/hide panels
  document.querySelectorAll('.wizard-panel').forEach(el => {
    el.classList.remove('active');
  });
  const panel = document.getElementById('step' + step);
  if (panel) panel.classList.add('active');
}

// ── CMA: Vision Extraction ─────────────────────────────────

async function runVision(dealId) {
  showLoading('Running Gemini vision extraction… This may take 15-30 seconds.');
  try {
    const resp = await fetch(`/api/deals/${dealId}/cma/vision`, { method: 'POST' });
    const result = await resp.json();

    if (result.error) {
      toast(result.error, 'error');
      return;
    }

    toast('Vision extraction complete');
    window.location.reload();
  } catch (e) {
    toast('Vision failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

// ── CMA: Comps ──────────────────────────────────────────────

function addCompRow() {
  const list = document.getElementById('compsList');
  const index = list.children.length;
  const html = `
    <div class="comp-entry" data-index="${index}">
      <div class="comp-entry-header">
        <span class="comp-entry-num">Comp #${index + 1}</span>
        <button class="btn btn-ghost btn-sm" onclick="this.closest('.comp-entry').remove()">Remove</button>
      </div>
      <div class="form-row">
        <div class="form-group"><label class="form-label">Address</label><input class="form-input comp-address" placeholder="e.g. 10 Smith St, Suburb"></div>
        <div class="form-group"><label class="form-label">Sold Price ($)</label><input class="form-input comp-price" type="number" placeholder="850000"></div>
        <div class="form-group"><label class="form-label">Sold Date</label><input class="form-input comp-date" type="date"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label class="form-label">Beds</label><input class="form-input comp-beds" type="number" value="3"></div>
        <div class="form-group"><label class="form-label">Baths</label><input class="form-input comp-baths" type="number" value="1"></div>
        <div class="form-group"><label class="form-label">Cars</label><input class="form-input comp-cars" type="number" value="1"></div>
        <div class="form-group"><label class="form-label">Land (sqm)</label><input class="form-input comp-land" type="number" placeholder="500"></div>
        <div class="form-group"><label class="form-label">Distance (km)</label><input class="form-input comp-dist" type="number" step="0.1" placeholder="0.5"></div>
      </div>
      <div class="form-group"><label class="form-label">Condition Notes</label><input class="form-input comp-notes" placeholder="e.g. recently renovated, original condition"></div>
    </div>
  `;
  list.insertAdjacentHTML('beforeend', html);
}

function collectComps() {
  const entries = document.querySelectorAll('.comp-entry');
  const comps = [];
  entries.forEach(entry => {
    const address = entry.querySelector('.comp-address')?.value;
    if (!address) return;
    comps.push({
      address: address,
      sold_price: parseInt(entry.querySelector('.comp-price')?.value || '0'),
      sold_date: entry.querySelector('.comp-date')?.value || '',
      beds: parseInt(entry.querySelector('.comp-beds')?.value || '0'),
      baths: parseInt(entry.querySelector('.comp-baths')?.value || '0'),
      cars: parseInt(entry.querySelector('.comp-cars')?.value || '0'),
      land_sqm: parseFloat(entry.querySelector('.comp-land')?.value || '0'),
      building_sqm: 0,
      property_type: 'house',
      condition_notes: entry.querySelector('.comp-notes')?.value || '',
      distance_km: parseFloat(entry.querySelector('.comp-dist')?.value || '0'),
    });
  });
  return comps;
}

async function saveComps(dealId) {
  const comps = collectComps();
  if (comps.length === 0) {
    toast('No comps to save', 'info');
    return;
  }

  try {
    await fetch(`/api/deals/${dealId}/cma/comps`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comps }),
    });
    toast(`${comps.length} comp(s) saved`);
  } catch (e) {
    toast('Failed to save comps: ' + e.message, 'error');
  }
}

async function uploadCompsFile(file, dealId) {
  if (!file) return;
  const text = await file.text();
  try {
    let data = JSON.parse(text);
    if (!Array.isArray(data)) data = data.comps || [];

    // Add to existing comps in the UI
    data.forEach(c => {
      const list = document.getElementById('compsList');
      const index = list.children.length;
      const entry = document.createElement('div');
      entry.className = 'comp-entry';
      entry.dataset.index = index;
      entry.innerHTML = `
        <div class="comp-entry-header">
          <span class="comp-entry-num">Comp #${index + 1}</span>
          <button class="btn btn-ghost btn-sm" onclick="this.closest('.comp-entry').remove()">Remove</button>
        </div>
        <div class="form-row">
          <div class="form-group"><label class="form-label">Address</label><input class="form-input comp-address" value="${c.address || ''}"></div>
          <div class="form-group"><label class="form-label">Sold Price ($)</label><input class="form-input comp-price" type="number" value="${c.sold_price || 0}"></div>
          <div class="form-group"><label class="form-label">Sold Date</label><input class="form-input comp-date" type="date" value="${c.sold_date || ''}"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label class="form-label">Beds</label><input class="form-input comp-beds" type="number" value="${c.beds || 0}"></div>
          <div class="form-group"><label class="form-label">Baths</label><input class="form-input comp-baths" type="number" value="${c.baths || 0}"></div>
          <div class="form-group"><label class="form-label">Cars</label><input class="form-input comp-cars" type="number" value="${c.cars || 0}"></div>
          <div class="form-group"><label class="form-label">Land (sqm)</label><input class="form-input comp-land" type="number" value="${c.land_sqm || 0}"></div>
          <div class="form-group"><label class="form-label">Distance (km)</label><input class="form-input comp-dist" type="number" step="0.1" value="${c.distance_km || 0}"></div>
        </div>
        <div class="form-group"><label class="form-label">Condition Notes</label><input class="form-input comp-notes" value="${c.condition_notes || ''}"></div>
      `;
      list.appendChild(entry);
    });

    toast(`${data.length} comp(s) loaded from file`);
  } catch (e) {
    toast('Invalid JSON file: ' + e.message, 'error');
  }
}

async function uploadCompsSpreadsheet(file, dealId) {
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);

  showLoading('Converting spreadsheet to comps…');
  try {
    const resp = await fetch(`/api/deals/${dealId}/cma/comps/upload`, {
      method: 'POST', body: formData
    });
    const result = await resp.json();

    if (result.error) {
      toast(result.error, 'error');
      return;
    }

    // Add imported comps to the UI
    const comps = result.comps || [];
    comps.forEach(c => {
      const list = document.getElementById('compsList');
      const index = list.children.length;
      const entry = document.createElement('div');
      entry.className = 'comp-entry';
      entry.dataset.index = index;
      entry.innerHTML = `
        <div class="comp-entry-header">
          <span class="comp-entry-num">Comp #${index + 1}</span>
          <button class="btn btn-ghost btn-sm" onclick="this.closest('.comp-entry').remove()">Remove</button>
        </div>
        <div class="form-row">
          <div class="form-group"><label class="form-label">Address</label><input class="form-input comp-address" value="${c.address || ''}"></div>
          <div class="form-group"><label class="form-label">Sold Price ($)</label><input class="form-input comp-price" type="number" value="${c.sold_price || 0}"></div>
          <div class="form-group"><label class="form-label">Sold Date</label><input class="form-input comp-date" type="date" value="${c.sold_date || ''}"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label class="form-label">Beds</label><input class="form-input comp-beds" type="number" value="${c.beds || 0}"></div>
          <div class="form-group"><label class="form-label">Baths</label><input class="form-input comp-baths" type="number" value="${c.baths || 0}"></div>
          <div class="form-group"><label class="form-label">Cars</label><input class="form-input comp-cars" type="number" value="${c.cars || 0}"></div>
          <div class="form-group"><label class="form-label">Land (sqm)</label><input class="form-input comp-land" type="number" value="${c.land_sqm || 0}"></div>
          <div class="form-group"><label class="form-label">Distance (km)</label><input class="form-input comp-dist" type="number" step="0.1" value="${c.distance_km || 0}"></div>
        </div>
        <div class="form-group"><label class="form-label">Condition Notes</label><input class="form-input comp-notes" value="${c.condition_notes || ''}"></div>
      `;
      list.appendChild(entry);
    });

    toast(result.message);
  } catch (e) {
    toast('Spreadsheet import failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

// ── CMA: Analysis ───────────────────────────────────────────

async function runCMA(dealId) {
  // Auto-save comps first
  await saveComps(dealId);

  showLoading('Running Claude CMA analysis… This may take 30-60 seconds.');
  try {
    const resp = await fetch(`/api/deals/${dealId}/cma/analyze`, { method: 'POST' });
    const result = await resp.json();

    if (result.error) {
      toast(result.error, 'error');
      return;
    }

    toast('CMA analysis complete');
    window.location.reload();
  } catch (e) {
    toast('CMA analysis failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

async function approveCMA(dealId, approved) {
  try {
    await fetch(`/api/deals/${dealId}/cma/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved }),
    });
    toast(approved ? 'CMA approved ✓' : 'CMA kept as draft');
    window.location.href = '/deals/' + dealId;
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

// ── Feasibility ─────────────────────────────────────────────

async function runFeasibility(event, dealId) {
  event.preventDefault();
  const form = document.getElementById('feasibilityForm');
  const formData = new FormData(form);
  const data = Object.fromEntries(formData.entries());

  showLoading('Running feasibility calculation + Claude analysis…');
  try {
    const resp = await fetch(`/api/deals/${dealId}/feasibility/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const result = await resp.json();

    if (result.error) {
      toast(result.error, 'error');
      return;
    }

    toast('Feasibility complete');
    window.location.reload();
  } catch (e) {
    toast('Feasibility failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

async function approveFeasibility(dealId, approved) {
  try {
    await fetch(`/api/deals/${dealId}/feasibility/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved }),
    });
    toast(approved ? 'Feasibility approved ✓' : 'Kept as draft');
    window.location.href = '/deals/' + dealId;
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

// ── Due Diligence ───────────────────────────────────────────

async function generateDDPrompt(dealId) {
  const state = document.getElementById('ddState').value;
  const council = document.getElementById('ddCouncil').value;

  showLoading('Generating DD prompt…');
  try {
    const resp = await fetch(`/api/deals/${dealId}/dd/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state, council }),
    });
    const result = await resp.json();

    document.getElementById('ddPromptText').value = result.prompt;
    document.getElementById('ddPromptResult').classList.remove('hidden');
    toast('DD prompt generated');
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

function copyDDPrompt() {
  const text = document.getElementById('ddPromptText').value;
  navigator.clipboard.writeText(text);
  toast('Copied to clipboard');
}

async function uploadDDResults(file, dealId) {
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);

  showLoading('Uploading DD results…');
  try {
    await fetch(`/api/deals/${dealId}/dd/results`, { method: 'POST', body: formData });
    toast('DD results uploaded');
    window.location.reload();
  } catch (e) {
    toast('Upload failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

// ── Reno Planner Chat ───────────────────────────────────────

let renoMessages = [];

async function startInterview(dealId) {
  document.getElementById('chatEmpty').classList.add('hidden');
  document.getElementById('chatInput').disabled = false;
  document.getElementById('chatSendBtn').disabled = false;
  document.getElementById('startInterviewBtn').classList.add('hidden');
  document.getElementById('finishInterviewBtn').classList.remove('hidden');

  // Initial message
  const meta = document.querySelector('.breadcrumb a:nth-child(3)')?.textContent || 'the property';
  renoMessages = [{
    role: 'user',
    content: `I'm planning a renovation for ${meta}. Please guide me through a room-by-room interview to define the scope.`
  }];

  showLoading('Starting interview with Claude…');
  try {
    const resp = await fetch(`/api/deals/${dealId}/reno/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: renoMessages }),
    });
    const result = await resp.json();
    renoMessages.push({ role: 'assistant', content: result.response });
    appendChatMessage('assistant', result.response);
  } catch (e) {
    toast('Failed to start: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

async function sendChat(dealId) {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text) return;

  appendChatMessage('user', text);
  input.value = '';
  renoMessages.push({ role: 'user', content: text });

  showLoading('Claude is thinking…');
  try {
    const resp = await fetch(`/api/deals/${dealId}/reno/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: renoMessages }),
    });
    const result = await resp.json();
    renoMessages.push({ role: 'assistant', content: result.response });
    appendChatMessage('assistant', result.response);
  } catch (e) {
    toast('Chat failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

async function finishInterview(dealId) {
  showLoading('Generating renovation plan… This may take a minute.');
  try {
    const resp = await fetch(`/api/deals/${dealId}/reno/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: renoMessages }),
    });
    const result = await resp.json();

    if (result.error) {
      toast(result.error, 'error');
      return;
    }

    toast('Renovation plan generated');
    document.getElementById('renoOutputs').classList.remove('hidden');
  } catch (e) {
    toast('Plan generation failed: ' + e.message, 'error');
  } finally {
    hideLoading();
  }
}

function appendChatMessage(role, text) {
  const container = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.style.marginBottom = '16px';
  div.innerHTML = `
    <div style="font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:var(--text-secondary); margin-bottom:4px">
      ${role === 'user' ? 'You' : 'Claude'}
    </div>
    <div style="font-size:13px; color:var(--text); line-height:1.6; white-space:pre-wrap; ${role === 'assistant' ? 'background:var(--gray-50); padding:12px; border-radius:8px' : ''}">${escapeHtml(text)}</div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

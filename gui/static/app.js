'use strict';

// ── State ─────────────────────────────────────────────
const state = {
  pendingFile: null,
  jobId: null,
  pollInterval: null,
};

// ── DOM refs (populated in init) ──────────────────────
let dropZone, fileInput, fileChosen, fileName, fileSize, fileClear;
let passwordGroup, passwordInput;
let systemSelect;
let outputModeRadios, pathGroup, outputPathInput, browseBtn;
let exportBtn;
let statusCard, statusRunning, statusDone, statusError;
let successMsg, statPersons, statProps, downloadArea;
let errorTrace;
let themeBtn;
// Char review panel
let charReview, charScanning, charTable, charTbody, reviewFooter, saveMappings;
// Subcat review panel
let subcatSection, subcatTbody;
// Prof / Orgao review panels
let profSection, profTbody, orgaoSection, orgaoTbody;

// Scan state
const scan = {
  pending: false,       // scan in-flight
  canonicals: [],       // list of all canonical char names (for dropdowns)
  subcatOptions: [],    // list of {value, label} for subcategoria dropdowns
  profOptions: [],      // list of canonical profession names
  orgaoOptions: [],     // list of canonical issuing institution names
  hasIssues: false,     // true when review panel is shown
  resolved: false,      // true when all rows have a selection
};

const LAST_PATH_KEY = 'msys-last-output-path';

// ── Init ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  dropZone      = document.getElementById('drop-zone');
  fileInput     = document.getElementById('file-input');
  fileChosen    = document.getElementById('file-chosen');
  fileName      = document.getElementById('file-name');
  fileSize      = document.getElementById('file-size');
  fileClear     = document.getElementById('file-clear');
  passwordGroup = document.getElementById('password-group');
  passwordInput = document.getElementById('password-input');
  systemSelect  = document.getElementById('system-select');
  pathGroup       = document.getElementById('path-group');
  outputPathInput = document.getElementById('output-path');
  browseBtn       = document.getElementById('browse-btn');
  exportBtn       = document.getElementById('export-btn');
  statusCard    = document.getElementById('status-card');
  statusRunning = document.getElementById('status-running');
  statusDone    = document.getElementById('status-done');
  statusError   = document.getElementById('status-error');
  successMsg    = document.getElementById('success-msg');
  statPersons   = document.getElementById('stat-persons');
  statProps     = document.getElementById('stat-props');
  downloadArea  = document.getElementById('download-area');
  errorTrace    = document.getElementById('error-trace');
  themeBtn      = document.getElementById('theme-btn');
  outputModeRadios = document.querySelectorAll('input[name="output_mode"]');

  charReview    = document.getElementById('char-review');
  charScanning  = document.getElementById('char-scanning');
  charTable     = document.getElementById('char-table');
  charTbody     = document.getElementById('char-tbody');
  reviewFooter  = document.getElementById('review-footer');
  saveMappings  = document.getElementById('save-mappings');
  subcatSection = document.getElementById('subcat-section');
  subcatTbody   = document.getElementById('subcat-tbody');
  profSection   = document.getElementById('prof-section');
  profTbody     = document.getElementById('prof-tbody');
  orgaoSection  = document.getElementById('orgao-section');
  orgaoTbody    = document.getElementById('orgao-tbody');

  applyTheme(localStorage.getItem('msys-theme') || 'dark');
  loadSystems();
  bindEvents();
});

// ── Theme ─────────────────────────────────────────────
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  themeBtn.textContent = theme === 'dark' ? '☀' : '☾';
  localStorage.setItem('msys-theme', theme);
}

// ── Systems ───────────────────────────────────────────
async function loadSystems() {
  try {
    const res = await fetch('/api/systems');
    const data = await res.json();
    data.systems.forEach(name => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      systemSelect.appendChild(opt);
    });
  } catch {
    const opt = document.createElement('option');
    opt.textContent = 'Erro ao carregar sistemas';
    opt.disabled = true;
    systemSelect.appendChild(opt);
  }
}

// ── Events ────────────────────────────────────────────
function bindEvents() {
  // Theme toggle
  themeBtn.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme');
    applyTheme(cur === 'dark' ? 'light' : 'dark');
  });

  // Drop zone — click opens file picker
  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });
  dropZone.setAttribute('tabindex', '0');

  // Drag events
  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  });

  // File input change
  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) setFile(fileInput.files[0]);
  });

  // Clear file
  fileClear.addEventListener('click', e => { e.stopPropagation(); clearFile(); });

  // Output mode radios
  outputModeRadios.forEach(r => r.addEventListener('change', onOutputModeChange));
  // Set initial state
  onOutputModeChange();

  // Browse folder button
  browseBtn.addEventListener('click', browseFolder);

  // System select — re-trigger scan when system changes
  systemSelect.addEventListener('change', maybeStartScan);

  // Export button
  exportBtn.addEventListener('click', startExport);
}

// ── File handling ─────────────────────────────────────
function setFile(file) {
  state.pendingFile = file;
  fileName.textContent = file.name;
  fileSize.textContent = formatSize(file.size);
  fileChosen.classList.add('visible');
  dropZone.classList.add('has-file');

  const isZip = file.name.toLowerCase().endsWith('.zip');
  passwordGroup.classList.toggle('visible', isZip);
  if (!isZip) passwordInput.value = '';

  resetStatus();
  maybeStartScan();
}

function clearFile() {
  state.pendingFile = null;
  fileInput.value = '';
  fileChosen.classList.remove('visible');
  dropZone.classList.remove('has-file');
  passwordGroup.classList.remove('visible');
  passwordInput.value = '';
  hideCharReview();
  resetStatus();
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

// ── Output mode ───────────────────────────────────────
function onOutputModeChange() {
  const mode = getOutputMode();
  const show = mode === 'path';
  pathGroup.classList.toggle('visible', show);
  if (show) {
    const saved = localStorage.getItem(LAST_PATH_KEY);
    if (saved) {
      outputPathInput.value = saved;
    } else if (!outputPathInput.value.trim()) {
      // Nenhum caminho salvo — abre o seletor de pasta automaticamente
      browseFolder();
    }
  }
}

// ── Browse folder ─────────────────────────────────────
async function browseFolder() {
  browseBtn.disabled = true;
  const initial = encodeURIComponent(outputPathInput.value.trim());
  try {
    const res = await fetch(`/api/browse-folder?initial=${initial}`);
    const data = await res.json();
    if (data.path) {
      outputPathInput.value = data.path;
      localStorage.setItem(LAST_PATH_KEY, data.path);
    }
  } catch {
    // dialog cancelled or error — keep current value
  } finally {
    browseBtn.disabled = false;
    outputPathInput.focus();
  }
}

function getOutputMode() {
  for (const r of outputModeRadios) {
    if (r.checked) return r.value;
  }
  return 'download';
}

// ── Scan & review ─────────────────────────────────────
function maybeStartScan() {
  if (!state.pendingFile || !systemSelect.value) return;
  triggerScan();
}

async function triggerScan() {
  hideCharReview();
  scan.hasIssues = false;
  scan.resolved = false;
  scan.pending = true;
  updateExportBtn();

  charReview.style.display = '';
  charScanning.style.display = '';
  charTable.style.display = 'none';
  reviewFooter.style.display = 'none';

  const fd = new FormData();
  fd.append('file', state.pendingFile);
  fd.append('system', systemSelect.value);
  fd.append('password', passwordInput.value);

  try {
    const res = await fetch('/api/scan', { method: 'POST', body: fd });
    const data = await res.json();
    scan.pending = false;

    if (!res.ok || data.error) {
      // scan failed — hide panel and allow export (server will catch errors)
      hideCharReview();
      scan.resolved = true;
      updateExportBtn();
      return;
    }

    scan.canonicals   = data.canonicals    || [];
    scan.subcatOptions = data.subcat_options || [];
    scan.profOptions   = data.prof_options   || [];
    scan.orgaoOptions  = data.orgao_options  || [];

    if (!data.has_issues) {
      hideCharReview();
      scan.resolved = true;
      updateExportBtn();
      return;
    }

    scan.hasIssues = true;
    renderCharReview(data);
    renderSubcatReview(data.subcats || []);
    renderProfReview(data);
    renderOrgaoReview(data);
  } catch {
    scan.pending = false;
    hideCharReview();
    scan.resolved = true;
    updateExportBtn();
  }
}

function hideCharReview() {
  charReview.style.display = 'none';
  charScanning.style.display = 'none';
  charTable.style.display = 'none';
  reviewFooter.style.display = 'none';
  charTbody.innerHTML = '';
  subcatSection.style.display = 'none';
  subcatTbody.innerHTML = '';
  profSection.style.display = 'none';
  profTbody.innerHTML = '';
  orgaoSection.style.display = 'none';
  orgaoTbody.innerHTML = '';
  scan.hasIssues = false;
}

function renderCharReview(data) {
  charScanning.style.display = 'none';
  charTbody.innerHTML = '';

  const rows = [
    ...(data.uncertain || []).map(r => ({ ...r, type: 'uncertain' })),
    ...(data.unmatched || []).map(r => ({ ...r, type: 'unmatched' })),
  ];

  for (const row of rows) {
    const tr = document.createElement('tr');

    // Source name
    const tdSrc = document.createElement('td');
    tdSrc.textContent = row.source;
    tr.appendChild(tdSrc);

    // Suggestion
    const tdSug = document.createElement('td');
    if (row.type === 'uncertain') {
      const pct = Math.round((row.score || 0) * 100);
      tdSug.innerHTML = `<span class="sug-name">${row.suggested}</span> <span class="sug-score">${pct}%</span>`;
    } else {
      tdSug.innerHTML = '<span class="sug-none">—</span>';
    }
    tr.appendChild(tdSug);

    // Mapping combo
    const tdSel = document.createElement('td');
    let preValue = '';
    if (row.type === 'uncertain' && row.suggested) preValue = row.suggested;
    else if (row.pre_ignore) preValue = '__ignore__';
    tdSel.appendChild(createCombo(row.source, preValue));
    tr.appendChild(tdSel);

    charTbody.appendChild(tr);
  }

  charTable.style.display = '';
  reviewFooter.style.display = '';
  checkAllResolved();
}

function renderSubcatReview(subcats) {
  subcatTbody.innerHTML = '';
  if (!subcats.length) {
    subcatSection.style.display = 'none';
    return;
  }
  for (const row of subcats) {
    const tr = document.createElement('tr');
    const tdSrc = document.createElement('td');
    tdSrc.textContent = row.source.replace('|', ' + ');
    tr.appendChild(tdSrc);
    const tdSel = document.createElement('td');
    tdSel.appendChild(createCombo(row.source, '', scan.subcatOptions));
    tr.appendChild(tdSel);
    subcatTbody.appendChild(tr);
  }
  subcatSection.style.display = '';
  reviewFooter.style.display = '';
  checkAllResolved();
}

function renderProfReview(data) {
  profTbody.innerHTML = '';
  const items = data.prof_uncertain || [];
  if (!items.length) {
    profSection.style.display = 'none';
    return;
  }
  const optList = [
    { value: '__keep__', label: 'Manter original' },
    ...scan.profOptions.map(n => ({ value: n, label: n })),
  ];
  for (const row of items) {
    const tr = document.createElement('tr');

    const tdSrc = document.createElement('td');
    tdSrc.textContent = row.source;
    tr.appendChild(tdSrc);

    const tdSug = document.createElement('td');
    tdSug.innerHTML = `<span class="sug-name">${row.suggested}</span> <span class="sug-score">${row.score}%</span>`;
    tr.appendChild(tdSug);

    const tdSel = document.createElement('td');
    tdSel.appendChild(createCombo(row.source, row.suggested || '__keep__', optList));
    tr.appendChild(tdSel);

    profTbody.appendChild(tr);
  }
  profSection.style.display = '';
  reviewFooter.style.display = '';
  checkAllResolved();
}

function renderOrgaoReview(data) {
  orgaoTbody.innerHTML = '';
  const items = data.orgao_uncertain || [];
  if (!items.length) {
    orgaoSection.style.display = 'none';
    return;
  }
  const optList = [
    { value: '__keep__', label: 'Manter original' },
    ...scan.orgaoOptions.map(n => ({ value: n, label: n })),
  ];
  for (const row of items) {
    const tr = document.createElement('tr');

    const tdSrc = document.createElement('td');
    tdSrc.textContent = row.source;
    tr.appendChild(tdSrc);

    const tdSug = document.createElement('td');
    tdSug.innerHTML = `<span class="sug-name">${row.suggested}</span> <span class="sug-score">${row.score}%</span>`;
    tr.appendChild(tdSug);

    const tdSel = document.createElement('td');
    tdSel.appendChild(createCombo(row.source, row.suggested || '__keep__', optList));
    tr.appendChild(tdSel);

    orgaoTbody.appendChild(tr);
  }
  orgaoSection.style.display = '';
  reviewFooter.style.display = '';
  checkAllResolved();
}

// ── Searchable combobox ───────────────────────────────
function createCombo(source, preValue, optList = null) {
  const wrapper = document.createElement('div');
  wrapper.className = 'char-combo';
  wrapper.dataset.source = source;
  wrapper.dataset.value = '';

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'char-combo-input';
  input.placeholder = optList ? 'Buscar subcategoria…' : 'Buscar característica…';
  input.autocomplete = 'off';

  const list = document.createElement('div');
  list.className = 'char-combo-list';
  list.style.display = 'none';
  document.body.appendChild(list);

  function positionList() {
    const r = input.getBoundingClientRect();
    list.style.position = 'fixed';
    list.style.top  = r.bottom + 2 + 'px';
    list.style.left = r.left + 'px';
    list.style.width = r.width + 'px';
  }

  function buildList(filter) {
    list.innerHTML = '';
    const q = filter.trim().toLowerCase();

    if (optList) {
      // Subcategory mode: {value, label} options, no "Ignorar sempre"
      for (const item of optList) {
        if (q && !item.label.toLowerCase().includes(q)) continue;
        const opt = document.createElement('div');
        opt.className = 'char-combo-opt';
        opt.dataset.value = item.value;
        opt.textContent = item.label;
        list.appendChild(opt);
      }
    } else {
      // Characteristics mode: "Ignorar sempre" first, then canonical names
      const ignEl = document.createElement('div');
      ignEl.className = 'char-combo-opt';
      ignEl.dataset.value = '__ignore__';
      ignEl.textContent = 'Ignorar sempre';
      list.appendChild(ignEl);

      for (const c of scan.canonicals) {
        if (q && !c.toLowerCase().includes(q)) continue;
        const opt = document.createElement('div');
        opt.className = 'char-combo-opt';
        opt.dataset.value = c;
        opt.textContent = c;
        list.appendChild(opt);
      }
    }
  }

  function openList() {
    buildList(input.value);
    positionList();
    list.style.display = '';
    // close other open dropdowns
    document.querySelectorAll('.char-combo-list').forEach(l => {
      if (l !== list) l.style.display = 'none';
    });
  }

  function selectValue(value) {
    wrapper.dataset.value = value;
    input.value = value === '__ignore__' ? 'Ignorar sempre' : value;
    list.style.display = 'none';
    checkAllResolved();
  }

  input.addEventListener('focus', () => openList());

  input.addEventListener('input', () => {
    wrapper.dataset.value = '';  // clear selection while typing
    if (list.style.display === 'none') openList();
    else buildList(input.value);
    checkAllResolved();
  });

  // mousedown (not click) so it fires before blur
  list.addEventListener('mousedown', e => {
    e.preventDefault();
    const opt = e.target.closest('.char-combo-opt');
    if (opt) selectValue(opt.dataset.value);
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') { list.style.display = 'none'; input.blur(); }
    if (e.key === 'Enter') {
      const first = list.querySelector('.char-combo-opt');
      if (first) selectValue(first.dataset.value);
    }
  });

  input.addEventListener('blur', () => {
    // small delay so mousedown on option fires first
    setTimeout(() => { list.style.display = 'none'; }, 150);
  });

  // reposition on scroll/resize
  const reposition = () => { if (list.style.display !== 'none') positionList(); };
  window.addEventListener('scroll', reposition, true);
  window.addEventListener('resize', reposition);

  wrapper.appendChild(input);
  // list is already appended to body

  if (preValue) selectValue(preValue);

  return wrapper;
}

// Close any open combo when clicking outside the input or list
document.addEventListener('click', e => {
  if (!e.target.closest('.char-combo') && !e.target.closest('.char-combo-list')) {
    document.querySelectorAll('.char-combo-list').forEach(l => l.style.display = 'none');
  }
});

function checkAllResolved() {
  const allCombos = [
    ...charTbody.querySelectorAll('.char-combo'),
    ...subcatTbody.querySelectorAll('.char-combo'),
    ...profTbody.querySelectorAll('.char-combo'),
    ...orgaoTbody.querySelectorAll('.char-combo'),
  ];
  scan.resolved = allCombos.every(c => c.dataset.value !== '');
  updateExportBtn();
}

function collectResolvedMappings() {
  const combos = charTbody.querySelectorAll('.char-combo');
  return [...combos].map(c => ({
    source: c.dataset.source,
    canonical: c.dataset.value === '__ignore__' ? null : c.dataset.value,
  }));
}

function collectSubcatMappings() {
  const combos = subcatTbody.querySelectorAll('.char-combo');
  return [...combos].map(c => ({
    source: c.dataset.source,
    id: c.dataset.value,
  }));
}

function collectProfMappings() {
  const combos = profTbody.querySelectorAll('.char-combo');
  return [...combos].map(c => ({
    source: c.dataset.source,
    canonical: c.dataset.value === '__keep__' ? null : c.dataset.value,
  }));
}

function collectOrgaoMappings() {
  const combos = orgaoTbody.querySelectorAll('.char-combo');
  return [...combos].map(c => ({
    source: c.dataset.source,
    canonical: c.dataset.value === '__keep__' ? null : c.dataset.value,
  }));
}

function updateExportBtn() {
  const blocked = scan.pending || (scan.hasIssues && !scan.resolved);
  exportBtn.disabled = blocked;
}

// ── Export ────────────────────────────────────────────
async function startExport() {
  if (!state.pendingFile) { alert('Selecione um arquivo de origem.'); return; }
  if (!systemSelect.value) { alert('Selecione o sistema.'); return; }
  if (getOutputMode() === 'path' && !outputPathInput.value.trim()) {
    alert('Informe o caminho da pasta de saída.');
    return;
  }

  // Save resolved mappings before exporting (if review panel was shown)
  if (scan.hasIssues && saveMappings && saveMappings.checked) {
    try {
      const mappings = collectResolvedMappings();
      if (mappings.length) {
        await fetch('/api/mappings/caracteristicas', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mappings }),
        });
      }
      const subcatMappings = collectSubcatMappings();
      if (subcatMappings.length) {
        await fetch('/api/mappings/subcategorias', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mappings: subcatMappings }),
        });
      }
      const profMappings = collectProfMappings();
      if (profMappings.length) {
        await fetch('/api/mappings/profissoes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mappings: profMappings }),
        });
      }
      const orgaoMappings = collectOrgaoMappings();
      if (orgaoMappings.length) {
        await fetch('/api/mappings/orgaos', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mappings: orgaoMappings }),
        });
      }
    } catch { /* non-fatal */ }
  }

  const fd = new FormData();
  fd.append('file', state.pendingFile);
  fd.append('system', systemSelect.value);
  fd.append('password', passwordInput.value);
  fd.append('output_mode', getOutputMode());
  fd.append('output_path', outputPathInput.value.trim());
  fd.append('imob_cpf_cnpj', document.getElementById('imob-cpf-cnpj').value.trim());
  fd.append('imob_nome', document.getElementById('imob-nome').value.trim());

  setUIState('running');

  try {
    const res = await fetch('/api/export', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) {
      setUIState('error', data.error || 'Erro desconhecido.');
      return;
    }
    state.jobId = data.job_id;
    state.pollInterval = setInterval(pollJob, 800);
  } catch (err) {
    setUIState('error', String(err));
  }
}

async function pollJob() {
  try {
    const res = await fetch(`/api/job/${state.jobId}`);
    const job = await res.json();

    if (job.status === 'running') return;

    clearInterval(state.pollInterval);
    state.pollInterval = null;

    if (job.status === 'done') {
      setUIState('done', job);
    } else {
      setUIState('error', job.message);
    }
  } catch {
    clearInterval(state.pollInterval);
    state.pollInterval = null;
    setUIState('error', 'Falha na comunicação com o servidor.');
  }
}

// ── UI state machine ──────────────────────────────────
function setUIState(s, data) {
  statusCard.classList.add('visible');
  exportBtn.disabled = s === 'running';

  statusRunning.style.display = s === 'running' ? 'flex' : 'none';
  statusDone.classList.toggle('visible', s === 'done');
  statusError.classList.toggle('visible', s === 'error');

  if (s === 'done') {
    successMsg.textContent = data.message || '';
    statPersons.textContent = data.persons ?? 0;
    statProps.textContent   = data.properties ?? 0;
    downloadArea.innerHTML  = '';
    if (getOutputMode() === 'path' && outputPathInput.value.trim()) {
      localStorage.setItem(LAST_PATH_KEY, outputPathInput.value.trim());
    }
    if (data.download_url) {
      const a = document.createElement('a');
      a.href = data.download_url;
      a.download = '';
      a.className = 'download-btn';
      a.innerHTML = '⬇ Baixar exportacao_msys.zip';
      downloadArea.appendChild(a);
    }
    if (getOutputMode() === 'path') {
      const path = outputPathInput.value.trim();
      if (path) {
        const btn = document.createElement('button');
        btn.className = 'open-folder-btn';
        btn.innerHTML = '📂 Abrir pasta';
        btn.addEventListener('click', async () => {
          btn.disabled = true;
          try {
            await fetch(`/api/open-folder?path=${encodeURIComponent(path)}`);
          } catch { /* non-fatal */ }
          finally { btn.disabled = false; }
        });
        downloadArea.appendChild(btn);
      }
    }
  }

  if (s === 'error') {
    errorTrace.textContent = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
  }
}

function resetStatus() {
  if (state.pollInterval) { clearInterval(state.pollInterval); state.pollInterval = null; }
  state.jobId = null;
  statusCard.classList.remove('visible');
  statusDone.classList.remove('visible');
  statusError.classList.remove('visible');
  exportBtn.disabled = false;
}

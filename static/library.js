/* ──────────────────────────────────────────────────────────────────────────
 * library.js — report search & filters, live report pickers, revision loop.
 * Loaded after app.js and workspace.js.
 * ────────────────────────────────────────────────────────────────────────── */
(() => {
  const FILTER_KEY = 'finreview.libraryFilters';
  const $ = (id) => document.getElementById(id);
  const role = () => (window.currentRole ? window.currentRole() : 'Executive');
  let lastQuery = '';

  /* ── API helpers ──────────────────────────────────────────────────────── */
  async function getJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url} → ${r.status}`);
    return r.json();
  }
  async function postJSON(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok && !data.message) throw new Error(`${url} → ${r.status}`);
    return data;
  }
  const changed = () => { if (window.notifyDataChanged) window.notifyDataChanged(); };

  /* ── Report pickers (were hard-coded to 101–103) ─────────────────────── */
  async function populateSelects() {
    let reports;
    try { reports = await getJSON('/api/list_reports?sort=id'); } catch (_) { return; }
    const label = (r) => `${r.report_id} — ${r.title}${r.status === 'Superseded' ? ' (superseded)' : ''}`;
    const fill = (id, keep = []) => {
      const sel = $(id);
      if (!sel) return;
      const prev = sel.value;
      const fixed = keep.map(v => sel.querySelector(`option[value="${v}"]`)).filter(Boolean).map(o => o.cloneNode(true));
      sel.replaceChildren(...fixed, ...reports.map(r => new Option(id === 'compare-a' || id === 'compare-b' ? `${r.report_id} — ${r.title}` : label(r), r.report_id)));
      if ([...sel.options].some(o => o.value === prev)) sel.value = prev;
    };
    fill('report-id-select');
    fill('quick-report-id');
    fill('compare-a');
    fill('compare-b');
    fill('audit-report-select', ['', 'financial']);
    // keep compare-b different from compare-a on first fill
    const a = $('compare-a'), b = $('compare-b');
    if (a && b && a.value === b.value && b.options.length > 1) b.selectedIndex = 1;
  }

  /* ── Library: search + filters ───────────────────────────────────────── */
  function readFilters() {
    return {
      q: $('lib-q').value.trim(), status: $('lib-status').value, from: $('lib-from').value,
      to: $('lib-to').value, sort: $('lib-sort').value, latest: $('lib-latest').checked,
    };
  }
  function writeFilters(f) {
    $('lib-q').value = f.q || ''; $('lib-status').value = f.status || ''; $('lib-from').value = f.from || '';
    $('lib-to').value = f.to || ''; $('lib-sort').value = f.sort || 'date_desc'; $('lib-latest').checked = f.latest !== false;
  }

  async function refreshLibrary() {
    const box = $('lib-results');
    if (!box) return;
    const f = readFilters();
    try { localStorage.setItem(FILTER_KEY, JSON.stringify(f)); } catch (_) {}
    if (f.from && f.to && f.from > f.to) {
      $('lib-count').textContent = '"From" is after "To" — no dates match.';
      box.replaceChildren();
      return;
    }
    const params = new URLSearchParams({ sort: f.sort, latest: f.latest ? '1' : '0' });
    if (f.q) params.set('q', f.q);
    if (f.status) params.set('status', f.status);
    if (f.from) params.set('from', f.from);
    if (f.to) params.set('to', f.to);
    const query = params.toString();
    lastQuery = query;

    let rows;
    try { rows = await getJSON('/api/list_reports?' + query); }
    catch (e) { box.innerHTML = `<p class="placeholder">Could not load reports (${escHtml(e.message)}).</p>`; return; }
    if (query !== lastQuery) return;   // a newer search already started

    const active = [f.q, f.status, f.from, f.to].filter(Boolean).length + (f.latest ? 0 : 1);
    $('lib-count').textContent = `${rows.length} report${rows.length === 1 ? '' : 's'}` +
      (active ? ` match${rows.length === 1 ? 'es' : ''} your filters` : '');

    if (!rows.length) {
      box.innerHTML = `<p class="queue-empty">No reports match. <button class="btn-link" type="button" data-act="clear">Clear filters</button></p>`;
      return;
    }
    box.innerHTML = rows.map(r => `
      <div class="lib-row" data-id="${r.report_id}">
        <div class="lib-main">
          <div class="lib-title">
            <span class="lib-id">#${r.report_id}</span>
            ${highlight(r.title, f.q)}
            ${r.version > 1 ? `<span class="ver-badge">v${r.version}</span>` : ''}
          </div>
          <div class="lib-sub">${highlight(r.summary, f.q)}</div>
          ${r.change_note ? `<div class="lib-note">Change: ${highlight(r.change_note, f.q)}</div>` : ''}
        </div>
        <div class="lib-meta">
          <span class="status-badge ${statusBadgeClass(r.status)}">${escHtml(r.status)}</span>
          <span class="lib-date-val">${escHtml(r.date)}</span>
        </div>
        <div class="lib-actions">
          <button class="btn-primary" type="button" data-act="open">Open</button>
          ${r.parent_id ? `<button class="btn-link" type="button" data-act="diff" data-parent="${r.parent_id}">Compare with v${r.version - 1}</button>` : ''}
        </div>
      </div>`).join('');
  }

  function highlight(text, q) {
    const safe = escHtml(text || '');
    const needle = (q || '').trim().replace(/^#/, '');
    if (!needle) return safe;
    const re = new RegExp(escHtml(needle).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    return safe.replace(re, m => `<mark>${m}</mark>`);
  }

  let debounce;
  const refreshSoon = () => { clearTimeout(debounce); debounce = setTimeout(refreshLibrary, 250); };

  /* ── Navigation helpers ──────────────────────────────────────────────── */
  async function openReport(id) {
    await populateSelects();
    if (typeof switchView === 'function') switchView('reports');
    $('report-id-select').value = String(id);
    await fetchReport();
    $('report-output').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  window.openReportById = openReport;

  async function compareVersions(a, b) {
    await populateSelects();
    if (typeof switchView === 'function') switchView('compare');
    $('compare-a').value = String(a);
    $('compare-b').value = String(b);
    await compareReports();
  }
  window.compareReportVersions = compareVersions;

  /* ── Report card extras: version info + revision actions ─────────────── */
  window.reportCardExtras = (r) => {
    setTimeout(() => fillVersionStrip(r), 0);
    const actions = [];
    if (r.status === 'Pending Review') {
      actions.push(`<button class="btn-warning" type="button" onclick="libShowRequestForm(${r.report_id})">&#8617; Request Revision</button>`);
    }
    if (r.status === 'Revision Requested') {
      actions.push(`<button class="btn-primary" type="button" onclick="libShowSubmitForm(${r.report_id})">&#9998; Submit Revised Version</button>`);
    }
    if (r.parent_id) {
      actions.push(`<button class="btn-link" type="button" onclick="compareReportVersions(${r.parent_id}, ${r.report_id})">Compare with v${r.version - 1}</button>`);
    }
    return `
      <div class="rev-block">
        ${r.version > 1 || r.change_note ? `<div class="rev-info">
          <span class="ver-badge">v${r.version}</span>
          ${r.parent_id ? `Replaces Report #${r.parent_id}.` : ''}
          ${r.change_note ? ` What changed: <em>${escHtml(r.change_note)}</em>` : ''}
        </div>` : ''}
        ${actions.length ? `<div class="rev-actions">${actions.join('')}</div>` : ''}
        <div class="rev-form" id="rev-form-${r.report_id}"></div>
        <div class="ver-strip" id="ver-strip-${r.report_id}"></div>
      </div>`;
  };

  async function fillVersionStrip(r) {
    const strip = $(`ver-strip-${r.report_id}`);
    if (!strip) return;
    let chain;
    try { chain = await getJSON(`/api/report_versions?report_id=${r.report_id}`); } catch (_) { return; }
    const latest = chain[chain.length - 1];
    const lastRevisionNote = [...chain].reverse()
      .flatMap(v => [...v.history].reverse()).find(h => h.decision === 'Revision Requested' && h.notes);
    if (chain.length < 2) {
      // Single version: only worth showing the reviewer's note while it's waiting for a revision.
      if (r.status === 'Revision Requested' && lastRevisionNote) {
        strip.innerHTML = `<div class="rev-info rev-request">Revision requested by ${escHtml(lastRevisionNote.decided_by)}: <em>${escHtml(lastRevisionNote.notes)}</em></div>`;
      } else strip.remove();
      return;
    }
    strip.innerHTML = `
      <div class="field-label">Version history</div>
      <div class="ver-chips">
        ${chain.map(v => `<button type="button" class="ver-chip ${v.report_id === r.report_id ? 'current' : ''}"
            onclick="openReportById(${v.report_id})" title="${escHtml(v.status)} · ${escHtml(v.date)}">
            v${v.version} · #${v.report_id} <span class="ver-chip-status">${escHtml(v.status)}</span></button>`).join('<span class="ver-arrow">&rarr;</span>')}
      </div>
      ${r.status === 'Superseded' ? `<div class="rev-info">This version was replaced. <button class="btn-link" type="button" onclick="openReportById(${latest.report_id})">Open latest (v${latest.version})</button></div>` : ''}
      ${lastRevisionNote ? `<div class="rev-info">Revision requested by ${escHtml(lastRevisionNote.decided_by)}: <em>${escHtml(lastRevisionNote.notes)}</em></div>` : ''}`;
  }

  window.libShowRequestForm = (id) => {
    const box = $(`rev-form-${id}`);
    box.innerHTML = `
      <label class="field-label" for="rev-notes-${id}">What needs to change?</label>
      <textarea id="rev-notes-${id}" rows="3" placeholder="e.g. Add a root-cause analysis for the latency warnings"></textarea>
      <div class="rev-actions">
        <button class="btn-warning" type="button" id="rev-send-${id}">Send back for revision</button>
        <button class="btn-link" type="button" onclick="this.closest('.rev-form').innerHTML=''">Cancel</button>
      </div>`;
    $(`rev-notes-${id}`).focus();
    $(`rev-send-${id}`).addEventListener('click', async (e) => {
      e.target.disabled = true;
      try {
        const r = await postJSON('/api/request_revision', { report_id: id, notes: $(`rev-notes-${id}`).value, decided_by: role() });
        showToast(r.message, r.ok ? 'success' : 'error');
        if (r.ok) {
          if (typeof auditRecord === 'function') auditRecord(String(id), 'decision', { detail: 'Revision requested', reason: $(`rev-notes-${id}`).value || null });
          changed();
          await openReport(id);
        }
      } catch (err) { showToast(err.message, 'error'); }
      finally { e.target.disabled = false; }
    });
  };

  window.libShowSubmitForm = async (id) => {
    const box = $(`rev-form-${id}`);
    const rep = await getJSON(`/api/get_report?report_id=${id}`);
    box.innerHTML = `
      <div class="field-label">Revised version (v${(rep.version || 1) + 1})</div>
      <label class="rev-label" for="rev-sum-${id}">Summary</label>
      <textarea id="rev-sum-${id}" rows="3"></textarea>
      <label class="rev-label" for="rev-rec-${id}">Recommendation</label>
      <textarea id="rev-rec-${id}" rows="2"></textarea>
      <label class="rev-label" for="rev-note-${id}">What changed?</label>
      <input type="text" id="rev-note-${id}" placeholder="e.g. Added root cause for latency warnings" />
      <div class="rev-actions">
        <button class="btn-primary" type="button" id="rev-submit-${id}">Submit v${(rep.version || 1) + 1}</button>
        <button class="btn-link" type="button" onclick="this.closest('.rev-form').innerHTML=''">Cancel</button>
      </div>`;
    $(`rev-sum-${id}`).value = rep.summary;          // set via .value, never via HTML
    $(`rev-rec-${id}`).value = rep.recommendation;
    $(`rev-sum-${id}`).focus();
    $(`rev-submit-${id}`).addEventListener('click', async (e) => {
      e.target.disabled = true;
      try {
        const r = await postJSON('/api/submit_revision', {
          report_id: id, summary: $(`rev-sum-${id}`).value, recommendation: $(`rev-rec-${id}`).value,
          change_note: $(`rev-note-${id}`).value, submitted_by: role(),
        });
        showToast(r.message, r.ok ? 'success' : 'error');
        if (r.ok) {
          if (typeof auditRecord === 'function') {
            auditRecord(String(id), 'submitted', { detail: `Superseded by #${r.report.report_id} (v${r.report.version})` });
            auditRecord(String(r.report.report_id), 'submitted', { detail: r.report.title });
          }
          changed();
          await compareVersions(id, r.report.report_id);
        }
      } catch (err) { showToast(err.message, 'error'); }
      finally { e.target.disabled = false; }
    });
  };

  /* ── Wire up ──────────────────────────────────────────────────────────── */
  function init() {
    try { const saved = JSON.parse(localStorage.getItem(FILTER_KEY) || 'null'); if (saved) writeFilters(saved); } catch (_) {}
    ['lib-q'].forEach(id => $(id).addEventListener('input', refreshSoon));
    ['lib-status', 'lib-from', 'lib-to', 'lib-sort', 'lib-latest'].forEach(id => $(id).addEventListener('change', refreshLibrary));
    $('lib-clear').addEventListener('click', () => { writeFilters({}); refreshLibrary(); });
    $('lib-results').addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-act]');
      if (!btn) return;
      if (btn.dataset.act === 'clear') { writeFilters({}); refreshLibrary(); return; }
      const id = Number(btn.closest('.lib-row').dataset.id);
      if (btn.dataset.act === 'open') openReport(id);
      if (btn.dataset.act === 'diff') compareVersions(Number(btn.dataset.parent), id);
    });
    document.addEventListener('datachange', () => { populateSelects(); refreshLibrary(); });
    populateSelects();
    refreshLibrary();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

/* ── Navigation ── */

const VIEW_TITLES = {
  dashboard: 'Dashboard',
  reports:   'System Reports',
  financial: 'Financial Analysis',
  compare:   'Compare Reports',
  approve:   'Approve / Reject',
  audit:     'Audit Trail',
  inbox:     'Email Inbox',
};

function switchView(id) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const view = document.getElementById('view-' + id);
  if (view) view.classList.add('active');
  const btn = document.querySelector(`.nav-item[data-view="${id}"]`);
  if (btn) btn.classList.add('active');
  document.getElementById('view-title').textContent = VIEW_TITLES[id] || id;
  // Auto-refresh the audit trail when navigating to it
  if (id === 'audit') showAuditTrail();
  // Auto-refresh the inbox when navigating to it
  if (id === 'inbox') loadEmailInbox();
}

document.querySelectorAll('.nav-item[data-view]').forEach(btn => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

/* ── Clock ── */
function tick() {
  const now = new Date();
  const el = document.getElementById('current-time');
  if (el) el.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
setInterval(tick, 1000);
tick();

/* ── Toast ── */
function showToast(msg, type = 'success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + type;
  clearTimeout(t._timeout);
  t._timeout = setTimeout(() => { t.className = 'toast hidden'; }, 3500);
}

/* ── Helpers ── */
function setLoading(el) {
  el.innerHTML = '<div class="loading"><span class="spinner"></span>Loading…</div>';
}

function fmtUSD(v) {
  return '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(v) {
  return (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '%';
}

function statusBadgeClass(s) {
  const lower = (s || '').toLowerCase();
  if (lower.includes('pending')) return 'status-pending';
  if (lower.includes('accept'))  return 'status-accepted';
  if (lower.includes('approve')) return 'status-approved';
  if (lower.includes('declin'))  return 'status-declined';
  return 'status-not-found';
}

/* ── Dashboard Stats ── */
async function loadDashboardStats() {
  try {
    const res = await fetch('/api/list_reports');
    const reports = await res.json();
    const pending  = reports.filter(r => r.status === 'Pending Review').length;
    const accepted = reports.filter(r => ['Accepted','Approved'].includes(r.status)).length;
    const declined = reports.filter(r => r.status === 'Declined').length;
    document.getElementById('stat-total').textContent    = reports.length;
    document.getElementById('stat-pending').textContent  = pending;
    document.getElementById('stat-accepted').textContent = accepted;
    document.getElementById('stat-declined').textContent = declined;
  } catch (_) { /* silent */ }
}
loadDashboardStats();

/* ── Fetch Report ── */
async function fetchReport() {
  const id = document.getElementById('report-id-select').value;
  const out = document.getElementById('report-output');
  setLoading(out);
  try {
    const res = await fetch(`/api/get_report?report_id=${id}`);
    const r = await res.json();
    out.innerHTML = renderReportCard(r);
    auditRecord(id, 'viewed', { detail: r.title });
    loadDashboardStats();
  } catch (e) {
    out.innerHTML = `<p class="placeholder">Error fetching report: ${e.message}</p>`;
  }
}

function renderReportCard(r) {
  return `
    <div class="report-card">
      <h4>${escHtml(r.title)}</h4>
      <div class="meta-row">
        <div class="meta-item">
          <span>Report ID</span>
          <span>#${r.report_id}</span>
        </div>
        <div class="meta-item">
          <span>Date</span>
          <span>${escHtml(r.date)}</span>
        </div>
        <div class="meta-item">
          <span>Status</span>
          <span class="status-badge ${statusBadgeClass(r.status)}">${escHtml(r.status)}</span>
        </div>
      </div>
      <div class="field-block">
        <div class="field-label">Summary</div>
        <div class="field-value">${escHtml(r.summary)}</div>
      </div>
      <div class="field-block">
        <div class="field-label">Recommendation</div>
        <div class="field-value">${escHtml(r.recommendation)}</div>
      </div>
      <div style="margin-top:1.1rem;display:flex;gap:0.6rem;flex-wrap:wrap;">
        <button class="btn-success" onclick="quickDecisionById(${r.report_id},'Accept')">&#10003; Accept Report</button>
        <button class="btn-danger"  onclick="quickDecisionById(${r.report_id},'Decline')">&#10007; Decline Report</button>
        ${memoLink(/^(approved|accepted)$/i.test(r.status) ? `/api/memo.pdf?report_id=${r.report_id}` : null)}
      </div>
    </div>`;
}

/* ── Generate + Analyze Financial Report ── */
async function generateFinancialReport() {
  const reportType = document.getElementById('report-type-select').value;
  const dept = document.getElementById('dept-input').value.trim() || 'Corporate';
  const out = document.getElementById('financial-output');
  setLoading(out);
  try {
    const genRes = await fetch(`/api/generate_sample_report?report_type=${encodeURIComponent(reportType)}&department=${encodeURIComponent(dept)}`);
    const report = await genRes.json();

    const analyzeRes = await fetch('/api/analyze_financial_report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_title:       report.report_title,
        total_budgeted_usd: report.total_budgeted_usd,
        total_actual_usd:   report.total_actual_usd,
        line_items:         report.line_items,
      }),
    });
    const analysis = await analyzeRes.json();
    out.innerHTML = renderFinancialReport(report, analysis);
    auditRecord('financial', 'generated', {
      detail: `${report.report_title} — ${dept} | Status: ${analysis.overall_status}`,
    });
  } catch (e) {
    out.innerHTML = `<p class="placeholder">Error: ${e.message}</p>`;
  }
}

function renderFinancialReport(report, analysis) {
  const bannerClass = {
    'Critical Overrun':    'banner-critical',
    'Requires Scrutiny':   'banner-scrutiny',
    'Approved for Review': 'banner-approved-review',
  }[analysis.overall_status] || 'banner-approved-review';

  const summaryRows = report.line_items.map(li => {
    const chip = li.status === 'Over Budget'  ? 'chip-over'
               : li.status === 'Under Budget' ? 'chip-under'
               : 'chip-ok';
    return `<tr>
      <td>${escHtml(li.category)}</td>
      <td>${fmtUSD(li.budgeted_usd)}</td>
      <td>${fmtUSD(li.actual_usd)}</td>
      <td>${fmtUSD(li.variance_usd)}</td>
      <td>${fmtPct(li.variance_pct)}</td>
      <td><span class="chip ${chip}">${escHtml(li.status)}</span></td>
    </tr>`;
  }).join('');

  const riskRows = analysis.executive_risk_assessment.map(b => {
    const dot = b.toLowerCase().includes('high')   ? 'risk-high'
              : b.toLowerCase().includes('over')   ? 'risk-medium'
              : b.toLowerCase().includes('no mate') ? 'risk-ok'
              : 'risk-low';
    return `<div class="risk-bullet"><div class="risk-dot ${dot}"></div><span>${escHtml(b)}</span></div>`;
  }).join('');

  const flagRows = analysis.flags.length
    ? analysis.flags.map(f => `<tr>
        <td>${escHtml(f.category)}</td>
        <td>${fmtPct(f.variance_pct)}</td>
        <td><span class="chip ${f.severity === 'High' ? 'chip-over' : f.severity === 'Medium' ? 'chip-over' : 'chip-ok'}">${escHtml(f.severity)}</span></td>
        <td style="font-size:12.5px;">${escHtml(f.note)}</td>
      </tr>`).join('')
    : '<tr><td colspan="4" style="color:var(--muted);font-style:italic;">No flags raised.</td></tr>';

  return `
    <div>
      <div class="status-banner ${bannerClass}">${escHtml(analysis.overall_status)} — ${escHtml(report.report_title)}</div>
      <div class="meta-row" style="margin-bottom:1.2rem;">
        <div class="meta-item"><span>Department</span><span>${escHtml(report.department)}</span></div>
        <div class="meta-item"><span>Period</span><span>${escHtml(report.report_period)}</span></div>
        <div class="meta-item"><span>Total Budgeted</span><span>${fmtUSD(report.total_budgeted_usd)}</span></div>
        <div class="meta-item"><span>Total Actual</span><span>${fmtUSD(report.total_actual_usd)}</span></div>
        <div class="meta-item"><span>Variance</span><span>${fmtUSD(report.total_variance_usd)} (${fmtPct(report.total_variance_pct)})</span></div>
      </div>

      <h5 style="font-size:12px;text-transform:uppercase;color:var(--muted);letter-spacing:.4px;margin-bottom:.5rem;">Line Items</h5>
      <table>
        <thead><tr>
          <th>Category</th><th>Budgeted</th><th>Actual</th><th>Variance $</th><th>Variance %</th><th>Status</th>
        </tr></thead>
        <tbody>${summaryRows}</tbody>
      </table>

      <div class="risk-section">
        <h5>Executive Risk Assessment</h5>
        ${riskRows}
      </div>

      <div style="margin-top:1.25rem;">
        <h5 style="font-size:12px;text-transform:uppercase;color:var(--muted);letter-spacing:.4px;margin-bottom:.5rem;">Variance Flags</h5>
        <table>
          <thead><tr><th>Category</th><th>Variance %</th><th>Severity</th><th>Note</th></tr></thead>
          <tbody>${flagRows}</tbody>
        </table>
      </div>

      <div class="field-block" style="margin-top:1.25rem;">
        <div class="field-label">Recommendation</div>
        <div class="field-value">${escHtml(analysis.recommendation)}</div>
      </div>
    </div>`;
}

/* ── Compare Reports ── */
async function compareReports() {
  const idA = document.getElementById('compare-a').value;
  const idB = document.getElementById('compare-b').value;
  const out = document.getElementById('compare-output');
  if (idA === idB) { showToast('Please select two different reports.', 'error'); return; }
  setLoading(out);
  try {
    const res = await fetch(`/api/compare_reports?report_id_a=${idA}&report_id_b=${idB}`);
    const cmp = await res.json();
    out.innerHTML = renderComparison(cmp);
    auditRecord(idA, 'compared', { detail: `Compared with Report #${idB}` });
    auditRecord(idB, 'compared', { detail: `Compared with Report #${idA}` });
  } catch (e) {
    out.innerHTML = `<p class="placeholder">Error: ${e.message}</p>`;
  }
}

function renderComparison(cmp) {
  const rows = cmp.field_differences.map(d => `<tr>
    <td>${escHtml(d.field)}</td>
    <td>${escHtml(d.report_a_value)}</td>
    <td>${escHtml(d.report_b_value)}</td>
    <td class="${d.differs ? 'diff-yes' : 'diff-no'}">${d.differs ? 'Yes' : 'No'}</td>
  </tr>`).join('');

  const takeaways = cmp.key_takeaways.map(t => `<div class="takeaway-item">${escHtml(t)}</div>`).join('');

  return `
    <div>
      <div class="meta-row" style="margin-bottom:1rem;">
        <div class="meta-item"><span>Report A</span><span>#${cmp.report_a_id} — ${escHtml(cmp.report_a_title)}</span></div>
        <div class="meta-item"><span>Report B</span><span>#${cmp.report_b_id} — ${escHtml(cmp.report_b_title)}</span></div>
      </div>
      <table>
        <thead><tr>
          <th>Field</th>
          <th>Report A (#${cmp.report_a_id})</th>
          <th>Report B (#${cmp.report_b_id})</th>
          <th>Differs?</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="takeaway-list">
        <h5>Key Takeaways</h5>
        ${takeaways}
      </div>
      <div class="field-block" style="margin-top:1rem;">
        <div class="field-label">Recommendation Variance</div>
        <div class="field-value">${escHtml(cmp.recommendation_variance)}</div>
      </div>
    </div>`;
}

/* ── Record Approval Decision ── */
async function recordDecision() {
  const title  = document.getElementById('approve-title').value.trim();
  const dec    = document.getElementById('approve-decision').value;
  const by     = document.getElementById('approve-by').value.trim();
  const notes  = document.getElementById('approve-notes').value.trim();
  const dual   = !!document.getElementById('approve-dual')?.checked;
  const out    = document.getElementById('approve-output');

  if (!title) { showToast('Please enter a report title.', 'error'); return; }
  if (!by)    { showToast('Please enter who is making the decision.', 'error'); return; }

  setLoading(out);
  try {
    const res = await fetch('/api/record_approval_decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_title: title, decision: dec, decided_by: by, notes: notes || null, requires_dual_signature: dual }),
    });
    const r = await res.json();
    out.innerHTML = renderApprovalConfirm(r);
    // Record decision event against a synthetic key derived from the title
    const auditKey = 'decision:' + title.toLowerCase().replace(/\s+/g, '-');
    const eventType = dec === 'Rejected' ? 'declined' : 'decision';
    auditRecord(auditKey, eventType, {
      actor:  by,
      detail: `${dec} — ${title}`,
      reason: (dec === 'Rejected' && notes) ? notes : null,
    });
    showToast('Decision recorded.');
    loadDashboardStats();
    if (window.notifyDataChanged) window.notifyDataChanged();
  } catch (e) {
    out.innerHTML = `<p class="placeholder">Error: ${e.message}</p>`;
  }
}

function renderApprovalConfirm(r) {
  const cls = r.decision === 'Approved' ? 'confirm-approved'
            : r.decision === 'Rejected' || r.decision === 'Signature Not Accepted' ? 'confirm-rejected'
            : 'confirm-revision';
  const steps = r.next_steps.map(s => `<li>${escHtml(s)}</li>`).join('');
  return `
    <div class="confirm-card ${cls}">
      <div class="confirm-msg">${escHtml(String(r.confirmation_message).replace(/\*\*/g, ''))}</div>
      <div style="color:var(--muted);font-size:12px;margin-bottom:.75rem;">Recorded: ${escHtml(r.timestamp_utc)}${r.notes ? ' | Notes: ' + escHtml(r.notes) : ''}</div>
      <div class="field-label" style="margin-bottom:.4rem;">Next Steps</div>
      <ul class="next-steps-list">${steps}</ul>
      ${r.memo_url ? `<div style="margin-top:.9rem;">${memoLink(r.memo_url)}</div>` : ''}
    </div>`;
}

/* ── Quick Accept / Decline ── */
async function quickDecision(dec) {
  const id = document.getElementById('quick-report-id').value;
  const reason = document.getElementById('quick-reason').value.trim();
  await _postDecision(id, dec, reason || null, document.getElementById('quick-output'));
}

async function quickDecisionById(reportId, dec) {
  const out = document.getElementById('report-output');
  await _postDecision(reportId, dec, null, out, true);
}

async function _postDecision(reportId, dec, reason, out, append = false) {
  setLoading(out);
  try {
    const res = await fetch('/api/update_report_status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_id: parseInt(reportId), decision: dec, reason: reason,
                             decided_by: window.currentRole ? window.currentRole() : 'Executive' }),
    });
    const r = await res.json();
    const cls = dec === 'Accept' ? 'confirm-accept' : 'confirm-decline';
    const html = `
      <div class="confirm-card ${cls}">
        <div class="confirm-msg">${escHtml(r.confirmation_message)}</div>
        <div style="color:var(--muted);font-size:12px;">
          ${escHtml(r.report_title)} | ${escHtml(r.previous_status)} → <strong>${escHtml(r.new_status)}</strong> at ${escHtml(r.timestamp_utc)}
        </div>
        ${r.memo_url ? `<div style="margin-top:.75rem;">${memoLink(r.memo_url)}</div>` : ''}
      </div>`;
    if (append) {
      out.innerHTML = html + out.innerHTML;
    } else {
      out.innerHTML = html;
    }
    // Audit
    const id = String(reportId);
    if (dec === 'Accept') {
      auditRecord(id, 'signed', { detail: r.report_title });
    } else {
      auditRecord(id, 'declined', {
        detail: r.report_title,
        reason: reason || null,
      });
    }
    showToast(`Report ${reportId} ${dec.toLowerCase()}ed.`);
    loadDashboardStats();
    if (window.notifyDataChanged) window.notifyDataChanged();
  } catch (e) {
    out.innerHTML = `<p class="placeholder">Error: ${e.message}</p>`;
  }
}

/* ── Decision memo download link ── */
function memoLink(url) {
  if (!url) return '';
  return `<a class="btn-memo" href="${escHtml(url)}" download>&#128196; Download decision memo (PDF)</a>`;
}

/* ── XSS Guard ── */
function escHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/* ── Audit Trail ── */

/**
 * Event type definitions.
 * type key → { label, dotClass }
 */
const AUDIT_EVENT_TYPES = {
  viewed:        { label: 'Report Viewed',          dotClass: 'audit-dot-viewed'        },
  routed:        { label: 'Routed for Approval',    dotClass: 'audit-dot-routed'        },
  signed:        { label: 'First Signature (CFO)',  dotClass: 'audit-dot-signed'        },
  countersigned: { label: 'Countersigned (VP)',     dotClass: 'audit-dot-countersigned' },
  declined:      { label: 'Declined',               dotClass: 'audit-dot-declined'      },
  cleared:       { label: 'Auto-Cleared',           dotClass: 'audit-dot-cleared'       },
  submitted:     { label: 'Submitted for Approval', dotClass: 'audit-dot-submitted'     },
  generated:     { label: 'Financial Report Generated', dotClass: 'audit-dot-generated' },
  compared:      { label: 'Reports Compared',       dotClass: 'audit-dot-compared'      },
  decision:      { label: 'Decision Recorded',      dotClass: 'audit-dot-decision'      },
};

/**
 * In-memory store: Map<reportId, AuditEntry[]>
 * reportId is a string key; financial analyses use 'financial'.
 * AuditEntry: { type, actor, detail, reason, ts }
 */
const _auditStore = new Map();

/**
 * Record one audit event.
 * @param {string}      reportId  — e.g. '101', '103', 'financial'
 * @param {string}      type      — key in AUDIT_EVENT_TYPES
 * @param {object}      opts      — { actor?, detail?, reason? }
 */
function auditRecord(reportId, type, opts = {}) {
  if (!_auditStore.has(reportId)) _auditStore.set(reportId, []);
  _auditStore.get(reportId).push({
    type,
    actor:  opts.actor  || (window.currentRole ? window.currentRole() : 'Executive'),
    detail: opts.detail || null,
    reason: opts.reason || null,
    ts:     new Date(),
  });
}

/** Format a Date as HH:MM:SS */
function _fmtTs(d) {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/** Format a Date as a short date+time string */
function _fmtFull(d) {
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
       + ' ' + _fmtTs(d);
}

/** Build HTML for a single audit event row */
function _renderAuditEvent(entry) {
  const def = AUDIT_EVENT_TYPES[entry.type] || { label: entry.type, dotClass: 'audit-dot-viewed' };
  const detailHtml = entry.detail
    ? `<div class="audit-event-detail">${escHtml(entry.detail)}</div>` : '';
  const reasonHtml = entry.reason
    ? `<div class="audit-event-reason">Reason: ${escHtml(entry.reason)}</div>` : '';
  return `
    <div class="audit-event">
      <span class="audit-dot ${def.dotClass}"></span>
      <div class="audit-event-header">
        <span class="audit-event-label">${escHtml(def.label)}</span>
        <span class="audit-event-time">${_fmtFull(entry.ts)}</span>
      </div>
      <div class="audit-event-actor">by ${escHtml(entry.actor)}</div>
      ${detailHtml}
      ${reasonHtml}
    </div>`;
}

/** Build HTML for one report's timeline group */
function _renderAuditGroup(reportId, entries) {
  const label = reportId === 'financial' ? 'Financial Analysis'
              : `Report #${reportId}`;
  const events = entries.map(_renderAuditEvent).join('');
  return `
    <div class="audit-group">
      <div class="audit-group-title">${escHtml(label)} — ${entries.length} event${entries.length !== 1 ? 's' : ''}</div>
      <div class="audit-timeline">${events}</div>
    </div>`;
}

/** Render the audit trail view for a given filter */
function showAuditTrail() {
  const filter = document.getElementById('audit-report-select').value;
  const out    = document.getElementById('audit-output');

  let groups = [];

  if (filter === '') {
    // All reports, sorted by earliest event ts
    const sorted = [..._auditStore.entries()].sort((a, b) => {
      const aTs = a[1][0]?.ts || 0;
      const bTs = b[1][0]?.ts || 0;
      return aTs - bTs;
    });
    groups = sorted;
  } else {
    const entries = _auditStore.get(filter);
    if (entries && entries.length) groups = [[filter, entries]];
  }

  if (!groups.length) {
    out.innerHTML = '<p class="audit-empty">No audit events recorded yet for this selection. Interact with reports first.</p>';
    return;
  }

  out.innerHTML = groups.map(([id, entries]) => _renderAuditGroup(id, entries)).join('');
}

/** Clear the entire audit store and reset the view */
function clearAuditTrail() {
  _auditStore.clear();
  const out = document.getElementById('audit-output');
  out.innerHTML = '<p class="audit-empty">Audit trail cleared.</p>';
  showToast('Audit trail cleared.', 'success');
}

/* ── File Upload ── */

/** Parsed line-items held between parse and analyze steps */
let _uploadedParsed = null;   // { line_items, total_budgeted_usd, total_actual_usd, ... }

// ── Drag-and-drop wiring ──
(function () {
  const zone = document.getElementById('upload-zone');
  if (!zone) return;

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  ['dragleave', 'dragend'].forEach(ev =>
    zone.addEventListener(ev, () => zone.classList.remove('drag-over'))
  );
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer?.files?.[0];
    if (file) handleFileSelect(file);
  });
})();

/** Entry point: called by <input onchange> and drag-drop */
async function handleFileSelect(file) {
  if (!file) return;

  _setUploadError(null);
  _uploadedParsed = null;

  const name = file.name.toLowerCase();
  if (!name.endsWith('.csv') && !name.endsWith('.xlsx')) {
    _setUploadError('Unsupported file type. Please upload a .csv or .xlsx file.');
    return;
  }

  const zone = document.getElementById('upload-zone');
  zone.classList.add('has-file');

  // Show the meta bar immediately with the filename
  document.getElementById('upload-filename').textContent = file.name;
  document.getElementById('upload-meta').classList.remove('hidden');
  // Pre-fill title from filename (strip extension)
  const titleGuess = file.name.replace(/\.[^.]+$/, '').replace(/[-_]/g, ' ');
  const titleEl = document.getElementById('upload-title');
  if (!titleEl.value) titleEl.value = titleGuess;

  // Show loading state in the preview area
  const preview = document.getElementById('upload-preview');
  preview.classList.remove('hidden');
  preview.innerHTML = '<div class="loading"><span class="spinner"></span>Parsing file…</div>';

  try {
    if (name.endsWith('.csv')) {
      _uploadedParsed = await _parseCsvClient(file);
    } else {
      _uploadedParsed = await _parseXlsxServer(file);
    }
  } catch (err) {
    _setUploadError(err.message);
    preview.classList.add('hidden');
    return;
  }

  _renderUploadWarnings(_uploadedParsed.warnings || []);
  _renderPreviewTable(_uploadedParsed.line_items);
  auditRecord('financial', 'viewed', { detail: `File uploaded: ${file.name}` });
}

/** Parse a CSV file in the browser — no server round-trip */
async function _parseCsvClient(file) {
  const text = await file.text();
  const rows = _csvToRows(text);
  if (!rows.length) throw new Error('File appears to be empty.');

  const headers = rows[0].map(h => h.trim().toLowerCase());
  const colMap  = _mapColumns(headers);
  _assertColumns(colMap, headers);

  const lineItems = [];
  const warnings  = [];

  for (let i = 1; i < rows.length; i++) {
    const raw  = rows[i];
    const cat  = (raw[colMap.category] || '').trim();
    const SKIP = new Set(['total','subtotal','sub-total','grand total','sum','']);
    if (SKIP.has(cat.toLowerCase())) continue;

    let budgeted, actual;
    try {
      budgeted = _parseNum(raw[colMap.budgeted] ?? '');
      actual   = _parseNum(raw[colMap.actual]   ?? '');
    } catch {
      warnings.push(`Row ${i + 1}: skipped — non-numeric value.`);
      continue;
    }
    if (budgeted === 0 && actual === 0) continue;

    const variance     = Math.round((actual - budgeted) * 100) / 100;
    const variancePct  = budgeted ? Math.round((variance / budgeted) * 10000) / 100 : 0;
    const status       = variancePct > 5 ? 'Over Budget' : variancePct < -5 ? 'Under Budget' : 'On Track';

    lineItems.push({
      category:     cat,
      budgeted_usd: budgeted,
      actual_usd:   actual,
      variance_usd: variance,
      variance_pct: variancePct,
      status,
    });
  }

  if (!lineItems.length) throw new Error('No valid data rows found. Check column headers and numeric values.');

  const totalBudgeted = lineItems.reduce((s, r) => s + r.budgeted_usd, 0);
  const totalActual   = lineItems.reduce((s, r) => s + r.actual_usd,   0);
  const totalVariance = Math.round((totalActual - totalBudgeted) * 100) / 100;
  const totalPct      = totalBudgeted ? Math.round((totalVariance / totalBudgeted) * 10000) / 100 : 0;

  return {
    line_items:         lineItems,
    total_budgeted_usd: totalBudgeted,
    total_actual_usd:   totalActual,
    total_variance_usd: totalVariance,
    total_variance_pct: totalPct,
    warnings,
  };
}

/** Upload an xlsx to the server and return normalised data */
async function _parseXlsxServer(file) {
  const body = new FormData();
  body.append('file', file);
  const res = await fetch('/api/parse_upload', { method: 'POST', body });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Server could not parse the file.');
  return data;
}

/** Minimal RFC-4180 CSV tokenizer — handles quoted fields with embedded commas/newlines */
function _csvToRows(text) {
  const rows = [];
  let row = [], field = '', inQuote = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inQuote) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQuote = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      inQuote = true;
    } else if (ch === ',') {
      row.push(field); field = '';
    } else if (ch === '\n') {
      row.push(field); field = '';
      if (row.some(c => c.trim())) rows.push(row);
      row = [];
    } else if (ch === '\r') {
      // skip bare CR
    } else {
      field += ch;
    }
  }
  if (field || row.length) { row.push(field); if (row.some(c => c.trim())) rows.push(row); }
  return rows;
}

/** Map lowercased header array → { category: colIdx, budgeted: colIdx, actual: colIdx } */
const _UPLOAD_ALIASES = {
  category:    ['category','line item','line_item','description','account','item','name'],
  budgeted:    ['budgeted','budgeted_usd','budget','budget usd','budget ($)','planned','planned_usd','forecast'],
  actual:      ['actual','actual_usd','actual usd','actual ($)','spend','spent','cost','costs','amount'],
};

function _mapColumns(headers) {
  const result = {};
  for (const [canonical, aliases] of Object.entries(_UPLOAD_ALIASES)) {
    for (const alias of aliases) {
      const idx = headers.indexOf(alias);
      if (idx !== -1) { result[canonical] = idx; break; }
    }
  }
  return result;
}

function _assertColumns(colMap, headers) {
  const missing = ['category','budgeted','actual'].filter(k => !(k in colMap));
  if (missing.length) {
    throw new Error(
      `Could not find required column${missing.length > 1 ? 's' : ''}: ${missing.join(', ')}. ` +
      `Headers found: ${headers.join(', ')}`
    );
  }
}

/** Strip $, commas; parse float */
function _parseNum(v) {
  const s = String(v).replace(/[$,\s]/g, '').trim();
  if (s === '' || s === '-' || s === '—') return 0;
  const n = parseFloat(s);
  if (isNaN(n)) throw new Error(`"${v}" is not a number`);
  return Math.round(n * 100) / 100;
}

/** Render a compact preview table of parsed line items */
function _renderPreviewTable(lineItems) {
  const preview = document.getElementById('upload-preview');
  const rows = lineItems.map(li => {
    const chip = li.status === 'Over Budget'  ? 'chip-over'
               : li.status === 'Under Budget' ? 'chip-under' : 'chip-ok';
    return `<tr>
      <td>${escHtml(li.category)}</td>
      <td>${fmtUSD(li.budgeted_usd)}</td>
      <td>${fmtUSD(li.actual_usd)}</td>
      <td>${fmtUSD(li.variance_usd)}</td>
      <td>${fmtPct(li.variance_pct)}</td>
      <td><span class="chip ${chip}">${escHtml(li.status)}</span></td>
    </tr>`;
  }).join('');

  preview.innerHTML = `
    <div class="upload-preview-title">${lineItems.length} rows parsed — review below, then click Analyze Report</div>
    <table>
      <thead><tr>
        <th>Category</th><th>Budgeted</th><th>Actual</th><th>Variance $</th><th>Variance %</th><th>Status</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function _renderUploadWarnings(warnings) {
  const el = document.getElementById('upload-warnings');
  if (!warnings.length) { el.classList.add('hidden'); return; }
  el.classList.remove('hidden');
  el.innerHTML = '⚠ ' + warnings.map(escHtml).join('<br>⚠ ');
}

function _setUploadError(msg) {
  const zone    = document.getElementById('upload-zone');
  const preview = document.getElementById('upload-preview');
  const meta    = document.getElementById('upload-meta');
  // Remove any existing error banner
  const existing = document.getElementById('upload-error-msg');
  if (existing) existing.remove();

  if (!msg) return;

  zone.classList.remove('has-file');
  meta.classList.add('hidden');
  preview.classList.add('hidden');

  const div = document.createElement('div');
  div.id = 'upload-error-msg';
  div.className = 'upload-error';
  div.textContent = msg;
  zone.insertAdjacentElement('afterend', div);
}

/** Reset the upload zone to its initial state */
function resetUpload() {
  _uploadedParsed = null;
  document.getElementById('file-input').value = '';
  document.getElementById('upload-zone').classList.remove('has-file', 'drag-over');
  document.getElementById('upload-meta').classList.add('hidden');
  document.getElementById('upload-preview').classList.add('hidden');
  document.getElementById('upload-warnings').classList.add('hidden');
  document.getElementById('upload-title').value = '';
  document.getElementById('upload-dept').value  = '';
  const err = document.getElementById('upload-error-msg');
  if (err) err.remove();
}

/** Send parsed data to analyze_financial_report and render results */
async function analyzeUploadedReport() {
  if (!_uploadedParsed) {
    showToast('No file parsed yet — please upload a file first.', 'error');
    return;
  }

  const title = document.getElementById('upload-title').value.trim() || 'Uploaded Report';
  const dept  = document.getElementById('upload-dept').value.trim()  || 'Uploaded';
  const out   = document.getElementById('financial-output');

  // Scroll to result area
  out.scrollIntoView({ behavior: 'smooth', block: 'start' });
  setLoading(out);

  try {
    const res = await fetch('/api/analyze_financial_report', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_title:       title,
        total_budgeted_usd: _uploadedParsed.total_budgeted_usd,
        total_actual_usd:   _uploadedParsed.total_actual_usd,
        line_items:         _uploadedParsed.line_items,
      }),
    });
    const analysis = await res.json();

    // Build a synthetic report object that renderFinancialReport understands
    const report = {
      report_title:        title,
      department:          dept,
      report_period:       'Uploaded',
      total_budgeted_usd:  _uploadedParsed.total_budgeted_usd,
      total_actual_usd:    _uploadedParsed.total_actual_usd,
      total_variance_usd:  _uploadedParsed.total_variance_usd,
      total_variance_pct:  _uploadedParsed.total_variance_pct,
      line_items:          _uploadedParsed.line_items,
    };

    out.innerHTML = renderFinancialReport(report, analysis);

    auditRecord('financial', 'generated', {
      detail: `${title} — ${dept} | ${_uploadedParsed.line_items.length} rows | Status: ${analysis.overall_status}`,
    });

    // Update approval routing card
    const tier = analysis.overall_status === 'Critical Overrun' ? 'dual'
               : analysis.overall_status === 'Requires Scrutiny' ? 'standard'
               : 'auto';
    renderApprovalCard(tier, { id: null, title, status: 'Pending Review' });
    if (tier !== 'auto') {
      auditRecord('financial', 'routed', {
        detail: `Routed as ${APPROVAL_TIERS[tier].label} — ${title}`,
      });
    }

    showToast(`Analyzed "${title}" — ${_uploadedParsed.line_items.length} line items.`);
  } catch (e) {
    out.innerHTML = `<p class="placeholder">Error: ${e.message}</p>`;
  }
}

/* ── Approval Routing Card ── */

/**
 * Tier definitions.
 * Each tier carries: label, badgeClass, approvers[], nextActionLabel,
 * and optional dualSig flag for the two-step tracker.
 */
const APPROVAL_TIERS = {
  'auto': {
    label:           'Auto-Clear',
    badgeClass:      'tier-auto',
    approvers:       ['System Auto-Approval'],
    nextAction:      'Mark as Cleared',
    dualSig:         false,
  },
  'standard': {
    label:           'Standard',
    badgeClass:      'tier-standard',
    approvers:       ['VP Finance'],
    nextAction:      'Submit for Approval',
    dualSig:         false,
  },
  'dual': {
    label:           'Dual-Sig',
    badgeClass:      'tier-dual',
    approvers:       ['CFO', 'VP Finance'],
    nextAction:      'Sign',
    dualSig:         true,
  },
};

/** Derive approval tier from a report object returned by the API */
function deriveTier(report) {
  const status = (report.status || '').toLowerCase();
  // Already actioned reports → auto display
  if (status === 'accepted' || status === 'approved') return 'auto';

  const title = (report.title || '').toLowerCase();
  // Security / compliance → dual-sig
  if (title.includes('security') || title.includes('compliance') || title.includes('annual')) return 'dual';
  // Default → standard
  return 'standard';
}

/** Current routing state (updated when a report is fetched) */
let _currentTier = null;
let _currentReport = null;

/** Render the routing card for a given tier key */
function renderApprovalCard(tierKey, report) {
  _currentTier   = tierKey;
  _currentReport = report;

  const tier      = APPROVAL_TIERS[tierKey];
  const badge     = document.getElementById('tier-badge');
  const list      = document.getElementById('approvers-list');
  const tracker   = document.getElementById('dual-sig-tracker');
  const nextBtn   = document.getElementById('approval-next-btn');

  // Tier badge
  badge.textContent = tier.label;
  badge.className   = 'tier-badge ' + tier.badgeClass;

  // Approvers list
  list.innerHTML = tier.approvers
    .map(a => `<li>${escHtml(a)}</li>`)
    .join('');

  // Dual-sig tracker: driven by the shared store (/api/pending_signatures)
  if (tier.dualSig) {
    tracker.classList.remove('hidden');
  } else {
    tracker.classList.add('hidden');
  }

  // Next-action button
  nextBtn.disabled    = false;
  nextBtn.textContent = tier.nextAction;
  nextBtn.style.background = '';

  if (tier.dualSig) syncDualTracker();
}

/* ── Dual-signature tracker (real state, role-aware) ── */
const DUAL_ROLES = ['CFO', 'VP Finance'];

function _setStep(stepId, signed) {
  const dot    = document.querySelector(`#${stepId} .step-dot`);
  const status = document.querySelector(`#${stepId} .step-status`);
  if (dot)    { dot.className = 'step-dot ' + (signed ? 'step-done' : 'step-pending'); dot.textContent = signed ? '✓' : ''; }
  if (status) { status.className = 'step-status ' + (signed ? 'step-status-done' : 'step-status-pending'); status.textContent = signed ? 'Signed' : 'Pending'; }
}

async function syncDualTracker() {
  if (_currentTier !== 'dual' || !_currentReport) return;
  const title   = _currentReport.title;
  const nextBtn = document.getElementById('approval-next-btn');
  const conn    = document.querySelector('.tracker-connector');
  const role    = window.currentRole ? window.currentRole() : 'Boss';

  const same = (t) => t.trim().toLowerCase() === title.trim().toLowerCase();
  let pending = null, done = false;
  try {
    const sigs = await (await fetch('/api/dual_signatures')).json();
    pending = sigs.pending.find(p => same(p.report_title)) || null;
    done    = !pending && sigs.completed.some(c => same(c.report_title));
  } catch (_) { return; /* leave tracker as-is */ }
  if (_currentTier !== 'dual' || !_currentReport || _currentReport.title !== title) return;  // card changed meanwhile

  const signed = new Set(done ? DUAL_ROLES : pending ? [pending.first_role] : []);
  _setStep('tracker-step-cfo', signed.has('CFO'));
  _setStep('tracker-step-vp',  signed.has('VP Finance'));
  if (conn) conn.style.background = done ? 'var(--success)' : '';

  nextBtn.style.background = '';
  if (done) {
    nextBtn.textContent = 'Dual-Sig Complete';
    nextBtn.style.background = 'var(--success)';
    nextBtn.disabled = true;
  } else if (!DUAL_ROLES.includes(role)) {
    const who = pending ? DUAL_ROLES.find(r => r !== pending.first_role) : 'CFO or VP Finance';
    nextBtn.textContent = `Awaiting ${who}`;
    nextBtn.disabled = true;
  } else if (signed.has(role)) {
    nextBtn.textContent = `Awaiting ${DUAL_ROLES.find(r => r !== role)}`;
    nextBtn.disabled = true;
  } else {
    nextBtn.textContent = pending ? `Countersign as ${role}` : `Sign as ${role}`;
    nextBtn.style.background = 'rgba(245,158,11,0.8)';
    nextBtn.disabled = false;
  }
}

document.addEventListener('rolechange', syncDualTracker);
document.addEventListener('datachange', syncDualTracker);

/** Reset card to idle state (no report selected) */
function resetApprovalCard() {
  _currentTier   = null;
  _currentReport = null;

  const badge   = document.getElementById('tier-badge');
  const list    = document.getElementById('approvers-list');
  const tracker = document.getElementById('dual-sig-tracker');
  const nextBtn = document.getElementById('approval-next-btn');

  badge.textContent = '—';
  badge.className   = 'tier-badge tier-none';
  list.innerHTML    = '';
  tracker.classList.add('hidden');
  nextBtn.disabled    = true;
  nextBtn.textContent = 'Select a report first';
  nextBtn.style.background = '';
}

/** Called by the Next-Action button */
function approvalNextAction() {
  if (!_currentTier || !_currentReport) return;
  const tier = APPROVAL_TIERS[_currentTier];
  // Use report id if available, otherwise fall back to 'financial'
  const auditId = _currentReport.id ? String(_currentReport.id) : 'financial';

  if (_currentTier === 'auto') {
    auditRecord(auditId, 'cleared', { detail: _currentReport.title });
    showToast('Report auto-cleared — no manual signature required.', 'success');
  } else if (_currentTier === 'standard') {
    auditRecord(auditId, 'routed',    { detail: _currentReport.title });
    auditRecord(auditId, 'submitted', { detail: 'Sent to VP Finance' });
    showToast(`Submitted "${_currentReport.title}" to VP Finance.`, 'success');
  } else if (_currentTier === 'dual') {
    const title = _currentReport.title;
    const btn = document.getElementById('approval-next-btn');
    btn.disabled = true;
    window.signDualAsCurrentRole(title).then(() => syncDualTracker()).catch(e => { showToast(`Could not record signature: ${e.message}`, 'error'); syncDualTracker(); });
  }
}

// ── Hook into existing fetch flows ──

// Patch fetchReport so the card updates after a report loads
const _origFetchReport = fetchReport;
fetchReport = async function () {
  await _origFetchReport();
  // After DOM update, read the rendered report title from the output heading
  const heading = document.querySelector('#report-output .report-card h4');
  if (heading) {
    const id = document.getElementById('report-id-select').value;
    const fakeReport = { id, title: heading.textContent, status: 'Pending Review' };
    // Report 103 is the Annual Security Compliance Review → dual-sig
    const tierKey = id === '103' ? 'dual' : id === '101' ? 'standard' : 'auto';
    renderApprovalCard(tierKey, fakeReport);
    // Emit routing event when report is first loaded into the card
    if (tierKey !== 'auto') {
      auditRecord(id, 'routed', { detail: `Routed as ${APPROVAL_TIERS[tierKey].label} — ${fakeReport.title}` });
    }
  }
};

// Patch generateFinancialReport so the card updates after analysis
const _origGenFinancial = generateFinancialReport;
generateFinancialReport = async function () {
  await _origGenFinancial();
  const banner = document.querySelector('#financial-output .status-banner');
  if (banner) {
    const text = banner.textContent || '';
    // Use the report type as the title so signatures line up with the chat agent's records
    const reportType = document.getElementById('report-type-select')?.value || text;
    const fakeReport = { id: null, title: reportType, status: 'Pending Review' };
    const tier = text.toLowerCase().includes('critical') ? 'dual'
               : text.toLowerCase().includes('scrutiny') ? 'standard'
               : 'auto';
    renderApprovalCard(tier, fakeReport);
    if (tier !== 'auto') {
      auditRecord('financial', 'routed', { detail: `Routed as ${APPROVAL_TIERS[tier].label} — ${text}` });
    }
  }
};

// Initialise card in idle state on page load
resetApprovalCard();

/* ── Email Inbox ── */

/** Show the webhook URL in the setup pane */
(function () {
  const el = document.getElementById('inbox-webhook-url');
  if (el) el.textContent = window.location.origin + '/api/email_ingest';
})();

/**
 * Load all inbound email reports from the server.
 * Called on page load (boot poll) and on every inbox navigation.
 */
async function loadEmailInbox() {
  const tray    = document.getElementById('inbox-tray');
  const setup   = document.getElementById('inbox-setup');
  const detail  = document.getElementById('inbox-detail');

  tray.innerHTML = '<div class="loading"><span class="spinner"></span>Loading inbox…</div>';
  tray.classList.remove('hidden');
  setup.style.display = 'none';
  if (detail) detail.classList.add('hidden');

  try {
    const res   = await fetch('/api/list_email_reports');
    const emails = await res.json();

    _updateInboxBadge(emails);

    if (!emails.length) {
      tray.classList.add('hidden');
      setup.style.display = '';
      return;
    }

    setup.style.display = 'none';
    tray.innerHTML = emails.map(e => _renderInboxCard(e)).join('');
  } catch (err) {
    tray.innerHTML = `<p class="placeholder">Could not load inbox: ${escHtml(err.message)}</p>`;
  }
}

/** Render a single email tray card */
function _renderInboxCard(e) {
  const initial  = (e.sender || '?').trim()[0].toUpperCase();
  const hasData  = e.line_items && e.line_items.length > 0;
  const isUnread = e.status === 'Unread';
  const cardCls  = [
    'inbox-card',
    isUnread  ? 'unread'   : '',
    hasData   ? 'has-data' : '',
  ].filter(Boolean).join(' ');

  const statusChip = isUnread
    ? `<span class="inbox-chip inbox-chip-unread">Unread</span>`
    : `<span class="inbox-chip inbox-chip-read">Read</span>`;

  const dataChip = hasData
    ? `<span class="inbox-chip inbox-chip-data">${e.line_items.length} rows</span>`
    : `<span class="inbox-chip inbox-chip-nodata">No data</span>`;

  const attBadge = e.attachment_name
    ? `<span style="font-size:11px;">📎 ${escHtml(e.attachment_name)}</span>` : '';

  const time = _fmtInboxTime(e.received_at);

  return `
    <div class="${cardCls}" onclick="openEmailReport(${e.id})">
      <div class="inbox-card-left">
        <div class="inbox-avatar">${escHtml(initial)}</div>
      </div>
      <div class="inbox-card-body">
        <div class="inbox-card-subject">${escHtml(e.subject)}</div>
        <div class="inbox-card-meta">
          <span>${escHtml(e.sender)}</span>
          ${statusChip}
          ${dataChip}
          ${attBadge}
          <span class="inbox-card-time">${escHtml(time)}</span>
        </div>
      </div>
    </div>`;
}

/** Open an email report: fetch full detail, mark read, optionally analyze */
async function openEmailReport(emailId) {
  const detail = document.getElementById('inbox-detail');
  detail.classList.remove('hidden');
  detail.innerHTML = '<div class="loading"><span class="spinner"></span>Opening…</div>';

  // Scroll detail into view
  detail.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const res = await fetch(`/api/get_email_report?id=${emailId}`);
    if (!res.ok) throw new Error('Could not load email.');
    const e = await res.json();

    const hasData = e.line_items && e.line_items.length > 0;

    // Re-render tray card as Read
    await loadEmailInbox();

    // Audit
    auditRecord('financial', 'viewed', { detail: `Email opened: ${e.subject} from ${e.sender}` });

    // Render preview rows if we have data
    const previewHtml = hasData ? (() => {
      const rows = e.line_items.map(li => {
        const chip = li.status === 'Over Budget'  ? 'chip-over'
                   : li.status === 'Under Budget' ? 'chip-under' : 'chip-ok';
        return `<tr>
          <td>${escHtml(li.category)}</td>
          <td>${fmtUSD(li.budgeted_usd)}</td>
          <td>${fmtUSD(li.actual_usd)}</td>
          <td>${fmtUSD(li.variance_usd)}</td>
          <td>${fmtPct(li.variance_pct)}</td>
          <td><span class="chip ${chip}">${escHtml(li.status)}</span></td>
        </tr>`;
      }).join('');
      return `
        <div class="upload-preview-title">${e.line_items.length} line items parsed from email</div>
        <div style="overflow-x:auto;margin-bottom:1rem;">
          <table>
            <thead><tr>
              <th>Category</th><th>Budgeted</th><th>Actual</th>
              <th>Variance $</th><th>Variance %</th><th>Status</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
    })() : `<p class="inbox-no-data-note">No structured data could be parsed from this email.
      The employee may not have included a CSV attachment or pasted a CSV table in the body.</p>`;

    const warningsHtml = (e.warnings && e.warnings.length)
      ? `<div class="upload-warnings" style="margin-bottom:1rem;">
           ⚠ ${e.warnings.map(escHtml).join('<br>⚠ ')}
         </div>` : '';

    const analyzeBtn = hasData
      ? `<button class="btn-primary" onclick="analyzeEmailReport(${emailId})">
           &#128200; Analyze Report
         </button>` : '';

    detail.innerHTML = `
      <div class="inbox-detail-header">
        <div style="flex:1;">
          <div class="inbox-detail-subject">${escHtml(e.subject)}</div>
          <div class="inbox-detail-sender">From: ${escHtml(e.sender)} &nbsp;·&nbsp; ${escHtml(_fmtInboxTime(e.received_at))}</div>
        </div>
        <button class="btn-danger" style="padding:0.4rem 0.75rem;flex-shrink:0;"
                onclick="deleteEmailReport(${emailId})">&#128465; Delete</button>
      </div>
      ${e.body_text ? `<div class="inbox-detail-body">${escHtml(e.body_text)}</div>` : ''}
      ${warningsHtml}
      ${previewHtml}
      <div class="inbox-detail-actions">
        ${analyzeBtn}
        <button class="btn-danger" onclick="deleteEmailReport(${emailId})" style="margin-left:auto;">
          &#128465; Delete
        </button>
      </div>`;
  } catch (err) {
    detail.innerHTML = `<p class="placeholder">Error: ${escHtml(err.message)}</p>`;
  }
}

/** Run analyze_financial_report on a stored email report's line items */
async function analyzeEmailReport(emailId) {
  const out = document.getElementById('financial-output');

  // Navigate to financial view so the result is visible
  switchView('financial');
  setLoading(out);

  try {
    const res = await fetch(`/api/get_email_report?id=${emailId}`);
    const e   = await res.json();

    if (!e.line_items || !e.line_items.length) {
      out.innerHTML = '<p class="placeholder">No line items to analyze in this email.</p>';
      return;
    }

    const title = e.subject || 'Email Report';
    const totalBudgeted = e.line_items.reduce((s, r) => s + r.budgeted_usd, 0);
    const totalActual   = e.line_items.reduce((s, r) => s + r.actual_usd,   0);
    const totalVariance = Math.round((totalActual - totalBudgeted) * 100) / 100;
    const totalPct      = totalBudgeted
      ? Math.round((totalVariance / totalBudgeted) * 10000) / 100 : 0;

    const analyzeRes = await fetch('/api/analyze_financial_report', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_title:       title,
        total_budgeted_usd: totalBudgeted,
        total_actual_usd:   totalActual,
        line_items:         e.line_items,
      }),
    });
    const analysis = await analyzeRes.json();

    const report = {
      report_title:       title,
      department:         e.sender,
      report_period:      'Email',
      total_budgeted_usd: totalBudgeted,
      total_actual_usd:   totalActual,
      total_variance_usd: totalVariance,
      total_variance_pct: totalPct,
      line_items:         e.line_items,
    };

    out.innerHTML = renderFinancialReport(report, analysis);

    auditRecord('financial', 'generated', {
      detail: `${title} (email from ${e.sender}) | ${e.line_items.length} rows | ${analysis.overall_status}`,
    });

    // Update approval routing card
    const tier = analysis.overall_status === 'Critical Overrun'  ? 'dual'
               : analysis.overall_status === 'Requires Scrutiny' ? 'standard'
               : 'auto';
    renderApprovalCard(tier, { id: null, title, status: 'Pending Review' });
    if (tier !== 'auto') {
      auditRecord('financial', 'routed', {
        detail: `Routed as ${APPROVAL_TIERS[tier].label} — ${title}`,
      });
    }

    showToast(`Analyzed "${title}" — ${e.line_items.length} line items.`);
  } catch (err) {
    out.innerHTML = `<p class="placeholder">Error: ${escHtml(err.message)}</p>`;
  }
}

/** Delete an email report */
async function deleteEmailReport(emailId) {
  try {
    await fetch('/api/delete_email_report', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ id: emailId }),
    });
    document.getElementById('inbox-detail').classList.add('hidden');
    await loadEmailInbox();
    showToast('Email deleted.');
  } catch (err) {
    showToast('Could not delete email.', 'error');
  }
}

/** Update the red unread badge on the nav item */
function _updateInboxBadge(emails) {
  const badge  = document.getElementById('inbox-unread-badge');
  if (!badge) return;
  const unread = emails.filter(e => e.status === 'Unread').length;
  if (unread > 0) {
    badge.textContent = unread > 99 ? '99+' : String(unread);
    badge.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
  }
}

/** Format an ISO timestamp as a friendly relative or absolute string */
function _fmtInboxTime(iso) {
  if (!iso) return '';
  const d   = new Date(iso);
  const now = new Date();
  const diffMs  = now - d;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1)  return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH  < 24)  return `${diffH}h ago`;
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

// ── Boot poll: check inbox on page load and every 60 seconds ──
loadEmailInbox();
setInterval(async () => {
  try {
    const res    = await fetch('/api/list_email_reports');
    const emails = await res.json();
    _updateInboxBadge(emails);
    // If already on the inbox view, refresh the tray silently
    if (document.getElementById('view-inbox')?.classList.contains('active')) {
      loadEmailInbox();
    }
  } catch { /* silent — badge just won't update */ }
}, 60_000);

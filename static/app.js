/* ── Navigation ── */

const VIEW_TITLES = {
  dashboard: 'Dashboard',
  reports:   'System Reports',
  financial: 'Financial Analysis',
  compare:   'Compare Reports',
  approve:   'Approve / Reject',
};

function switchView(id) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const view = document.getElementById('view-' + id);
  if (view) view.classList.add('active');
  const btn = document.querySelector(`.nav-item[data-view="${id}"]`);
  if (btn) btn.classList.add('active');
  document.getElementById('view-title').textContent = VIEW_TITLES[id] || id;
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
      <div style="margin-top:1.1rem;display:flex;gap:0.6rem;">
        <button class="btn-success" onclick="quickDecisionById(${r.report_id},'Accept')">&#10003; Accept Report</button>
        <button class="btn-danger"  onclick="quickDecisionById(${r.report_id},'Decline')">&#10007; Decline Report</button>
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
  const out    = document.getElementById('approve-output');

  if (!title) { showToast('Please enter a report title.', 'error'); return; }
  if (!by)    { showToast('Please enter who is making the decision.', 'error'); return; }

  setLoading(out);
  try {
    const res = await fetch('/api/record_approval_decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_title: title, decision: dec, decided_by: by, notes: notes || null }),
    });
    const r = await res.json();
    out.innerHTML = renderApprovalConfirm(r);
    showToast('Decision recorded.');
    loadDashboardStats();
  } catch (e) {
    out.innerHTML = `<p class="placeholder">Error: ${e.message}</p>`;
  }
}

function renderApprovalConfirm(r) {
  const cls = r.decision === 'Approved' ? 'confirm-approved'
            : r.decision === 'Rejected' ? 'confirm-rejected'
            : 'confirm-revision';
  const steps = r.next_steps.map(s => `<li>${escHtml(s)}</li>`).join('');
  return `
    <div class="confirm-card ${cls}">
      <div class="confirm-msg">${escHtml(r.confirmation_message)}</div>
      <div style="color:var(--muted);font-size:12px;margin-bottom:.75rem;">Recorded: ${escHtml(r.timestamp_utc)}${r.notes ? ' | Notes: ' + escHtml(r.notes) : ''}</div>
      <div class="field-label" style="margin-bottom:.4rem;">Next Steps</div>
      <ul class="next-steps-list">${steps}</ul>
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
      body: JSON.stringify({ report_id: parseInt(reportId), decision: dec, reason: reason }),
    });
    const r = await res.json();
    const cls = dec === 'Accept' ? 'confirm-accept' : 'confirm-decline';
    const html = `
      <div class="confirm-card ${cls}">
        <div class="confirm-msg">${escHtml(r.confirmation_message)}</div>
        <div style="color:var(--muted);font-size:12px;">
          ${escHtml(r.report_title)} | ${escHtml(r.previous_status)} → <strong>${escHtml(r.new_status)}</strong> at ${escHtml(r.timestamp_utc)}
        </div>
      </div>`;
    if (append) {
      out.innerHTML = html + out.innerHTML;
    } else {
      out.innerHTML = html;
    }
    showToast(`Report ${reportId} ${dec.toLowerCase()}ed.`);
    loadDashboardStats();
  } catch (e) {
    out.innerHTML = `<p class="placeholder">Error: ${e.message}</p>`;
  }
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

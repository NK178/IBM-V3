/* ──────────────────────────────────────────────────────────────────────────
 * workspace.js — role switcher, "Waiting on you" queue, and embedded agent chat.
 * Loaded after app.js. Talks to the shared store (/api/*) so the dashboard,
 * the chat agent, and other people's browsers all see the same state.
 * ────────────────────────────────────────────────────────────────────────── */
(() => {
  const ROLES = ['Boss', 'CFO', 'VP Finance'];
  const DUAL_ROLES = ['CFO', 'VP Finance'];
  const ROLE_KEY = 'finreview.role';
  const POLL_MS = 15000;

  /* ── Role state ───────────────────────────────────────────────────────── */
  let role = 'Boss';
  try { const saved = localStorage.getItem(ROLE_KEY); if (ROLES.includes(saved)) role = saved; } catch (_) {}

  window.currentRole = () => role;

  function setRole(next) {
    if (!ROLES.includes(next) || next === role) return;
    const prev = role;
    role = next;
    try { localStorage.setItem(ROLE_KEY, role); } catch (_) {}

    // Keep the "Decided By" field in step with the role, unless the user typed something custom.
    const by = document.getElementById('approve-by');
    if (by && (!by.value.trim() || by.value.trim() === prev)) by.value = role;

    document.getElementById('role-select').value = role;
    document.body.dataset.role = role;
    document.dispatchEvent(new CustomEvent('rolechange', { detail: { role, prev } }));
    showToast(`Now acting as ${role}.`);
    refreshQueue();
  }

  /* ── Shared-state refresh ─────────────────────────────────────────────── */
  let refreshTimer = null;
  function dataChanged() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => {
      if (typeof loadDashboardStats === 'function') loadDashboardStats();
      refreshQueue();
      refreshMemos();
      document.dispatchEvent(new CustomEvent('datachange'));
    }, 600);
  }
  window.notifyDataChanged = dataChanged;

  async function getJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url} → ${r.status}`);
    return r.json();
  }

  /* ── "Waiting on you" queue ───────────────────────────────────────────── */
  async function refreshQueue() {
    const box = document.getElementById('my-queue');
    if (!box) return;
    let reports = [], pending = [];
    try {
      [reports, pending] = await Promise.all([getJSON('/api/list_reports'), getJSON('/api/pending_signatures')]);
    } catch (e) {
      box.innerHTML = `<p class="placeholder">Could not load your queue (${escHtml(e.message)}).</p>`;
      return;
    }

    const items = [];
    if (role === 'Boss') {
      reports.filter(r => r.status === 'Pending Review').forEach(r => items.push({
        kind: 'review', title: `Report #${r.report_id} — ${r.title}`, sub: `Submitted ${r.date} · needs Accept / Decline`, report: r,
      }));
      reports.filter(r => r.status === 'Revision Requested').forEach(r => items.push({
        kind: 'watch', title: `Report #${r.report_id} — ${r.title}`, sub: 'Sent back for revision · awaiting a revised version', report: r,
      }));
    }
    pending.forEach(p => {
      const awaiting = DUAL_ROLES.find(x => x !== p.first_role);
      const mine = awaiting === role;
      if (mine || role === 'Boss') items.push({
        kind: mine ? 'sign' : 'watch',
        title: p.report_title,
        sub: `${p.first_role} signed ${fmtWhen(p.first_timestamp)} · awaiting ${awaiting}`,
        pending: p,
      });
    });

    const actionable = items.filter(i => i.kind !== 'watch').length;
    const count = document.getElementById('role-count');
    count.textContent = actionable ? String(actionable) : '';
    count.hidden = !actionable;

    if (!items.length) {
      box.innerHTML = `<p class="queue-empty">Nothing is waiting on the ${escHtml(role)} right now.</p>`;
      return;
    }

    box.replaceChildren(...items.map(renderQueueItem));
  }

  /* ── Decision memos (approved reports → PDF) ──────────────────────────── */
  async function refreshMemos() {
    const box = document.getElementById('memo-list');
    if (!box) return;
    let items;
    try { items = await getJSON('/api/approved'); }
    catch (e) { box.innerHTML = `<p class="placeholder">Could not load memos (${escHtml(e.message)}).</p>`; return; }
    if (!items.length) {
      box.innerHTML = '<p class="queue-empty">No approved reports yet. Memos appear here once something is approved.</p>';
      return;
    }
    box.innerHTML = items.map(a => `
      <div class="queue-item queue-approved">
        <div class="queue-text">
          <div class="queue-title">${a.report_id ? `Report #${a.report_id} — ` : ''}${escHtml(a.report_title)}</div>
          <div class="queue-sub">${escHtml(a.decision)} by ${escHtml(a.decided_by)} · ${escHtml(fmtWhen(a.timestamp))}</div>
        </div>
        <div class="queue-actions">${memoLink(a.memo_url)}</div>
      </div>`).join('');
  }

  function fmtWhen(iso) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {   // date only — don't invent a time
      return new Date(iso + 'T00:00:00').toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
    }
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  function renderQueueItem(item) {
    const row = document.createElement('div');
    row.className = `queue-item queue-${item.kind}`;
    row.innerHTML = `
      <div class="queue-text">
        <div class="queue-title">${escHtml(item.title)}</div>
        <div class="queue-sub">${escHtml(item.sub)}</div>
      </div>
      <div class="queue-actions"></div>`;
    const actions = row.querySelector('.queue-actions');

    if (item.kind === 'review') {
      const id = item.report.report_id;
      actions.append(
        button('Accept', 'btn-success', () => reviewReport(id, 'Accept')),
        button('Decline', 'btn-danger', () => {
          const reason = prompt(`Reason for declining Report ${id}? (optional)`);
          if (reason !== null) reviewReport(id, 'Decline', reason.trim() || null);
        }),
      );
    } else if (item.kind === 'sign') {
      actions.append(button(`Countersign as ${role}`, 'btn-primary', () => signDual(item.pending.report_title)));
    } else if (item.report && window.openReportById) {
      actions.append(button('Open', 'btn-link', () => window.openReportById(item.report.report_id)));
    } else {
      actions.innerHTML = '<span class="queue-tag">Waiting on others</span>';
    }
    return row;
  }

  function button(label, cls, onClick) {
    const b = document.createElement('button');
    b.className = cls;
    b.textContent = label;
    b.addEventListener('click', async () => {
      b.disabled = true;
      try { await onClick(); } finally { b.disabled = false; }
    });
    return b;
  }

  async function reviewReport(id, decision, reason = null) {
    const r = await postJSON('/api/update_report_status', { report_id: id, decision, reason, decided_by: role });
    if (typeof auditRecord === 'function') {
      auditRecord(String(id), decision === 'Accept' ? 'decision' : 'declined',
        { detail: `${decision}ed — ${r.report_title}`, reason });
    }
    showToast(r.confirmation_message, decision === 'Accept' ? 'success' : 'error');
    dataChanged();
  }

  /** Sign a dual-signature approval as the current role. Returns the API record. */
  async function signDual(reportTitle, notes = null) {
    if (!DUAL_ROLES.includes(role)) {
      showToast('Switch to CFO or VP Finance to sign.', 'error');
      return null;
    }
    const r = await postJSON('/api/record_approval_decision', {
      report_title: reportTitle, decision: 'Approved', decided_by: role, notes, requires_dual_signature: true,
    });
    if (typeof auditRecord === 'function' && /^(Approved|Pending Second Signature)$/.test(r.decision)
        && !/DUPLICATE/.test(r.confirmation_message)) {
      auditRecord(auditKeyForTitle(reportTitle), r.dual_signature_complete ? 'countersigned' : 'signed',
        { actor: role, detail: reportTitle });
    }
    showToast(stripMd(r.confirmation_message), r.decision === 'Signature Not Accepted' ? 'error' : 'success');
    dataChanged();
    return r;
  }
  window.signDualAsCurrentRole = signDual;

  // System reports are audited under their numeric id; anything else under a title key.
  function auditKeyForTitle(title) {
    const m =[...document.querySelectorAll('#report-id-select option')]
      .find(o => o.textContent.split('—')[1]?.trim() === title);
    return m ? m.value : 'decision:' + title.toLowerCase().replace(/\s+/g, '-');
  }

  const stripMd = (s) => String(s || '').replace(/\*\*/g, '');

  async function postJSON(url, body) {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!res.ok) throw new Error(`${url} → ${res.status}`);
    return res.json();
  }

  /* ── Embedded agent chat ──────────────────────────────────────────────── */
  let chatBooted = false;

  function toggleChat(open) {
    const drawer = document.getElementById('chat-drawer');
    const willOpen = open ?? !drawer.classList.contains('open');
    drawer.classList.toggle('open', willOpen);
    document.body.classList.toggle('chat-open', willOpen);
    document.getElementById('chat-toggle').setAttribute('aria-expanded', String(willOpen));
    if (willOpen && !chatBooted) bootChat();
  }
  window.toggleChat = toggleChat;

  /** Open the chat and send a message as the current role. */
  window.askAgent = async (text) => {
    toggleChat(true);
    const inst = await chatReady;
    await inst.send(text);
  };

  let resolveChat;
  const chatReady = new Promise(r => { resolveChat = r; });

  async function bootChat() {
    chatBooted = true;
    const status = document.getElementById('chat-status');
    try {
      const cfg = await getJSON('/chat/config');
      if (!cfg.enabled) {
        status.innerHTML = `<strong>Chat isn't configured yet.</strong><br>Set these on the Render service: ${cfg.missing.map(escHtml).join(', ')}.`;
        return;
      }
      const token = await fetchToken();
      window.wxOConfiguration = {
        orchestrationID: cfg.orchestrationID,
        hostURL: cfg.hostURL,
        deploymentPlatform: cfg.deploymentPlatform,
        crn: cfg.crn,
        showLauncher: false,
        token,
        layout: { form: 'custom', customElement: document.getElementById('chat-mount') },
        chatOptions: {
          agentId: cfg.agentId,
          ...(cfg.agentEnvironmentId ? { agentEnvironmentId: cfg.agentEnvironmentId } : {}),
          onLoad(instance) {
            status.remove();
            // Tell the agent who is acting, on every message (role can change mid-chat).
            instance.on('pre:send', (event) => {
              event.message.context = { ...(event.message.context || {}), current_role: role };
            });
            // Anything the agent does may have changed shared state.
            instance.on('receive', dataChanged);
            instance.on('authTokenNeeded', async (event) => { event.authToken = await fetchToken(); });
            resolveChat(instance);
          },
        },
      };
      const s = document.createElement('script');
      s.src = `${cfg.hostURL}/wxochat/wxoLoader.js?embed=true`;
      s.onload = () => wxoLoader.init();
      s.onerror = () => { status.textContent = 'Could not load the watsonx Orchestrate chat.'; };
      document.head.appendChild(s);
    } catch (e) {
      status.textContent = `Chat failed to start: ${e.message}`;
    }
  }

  async function fetchToken() {
    const r = await fetch('/chat/token', { credentials: 'same-origin' });
    if (!r.ok) throw new Error(await r.text());
    return r.text();
  }

  /* ── Wire up ──────────────────────────────────────────────────────────── */
  function init() {
    const sel = document.getElementById('role-select');
    sel.value = role;
    sel.addEventListener('change', () => setRole(sel.value));
    document.body.dataset.role = role;

    const by = document.getElementById('approve-by');
    if (by && !by.value.trim()) by.value = role;

    document.getElementById('chat-toggle').addEventListener('click', () => toggleChat());
    document.getElementById('chat-close').addEventListener('click', () => toggleChat(false));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') toggleChat(false); });

    refreshQueue();
    refreshMemos();
    // Pick up changes made by other people (e.g. the CFO signing on another laptop).
    setInterval(() => { if (!document.hidden) dataChanged(); }, POLL_MS);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) dataChanged(); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

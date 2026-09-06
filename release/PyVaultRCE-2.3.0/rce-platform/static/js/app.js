const MAX_LINES = 10000;

const editor = CodeMirror.fromTextArea(document.getElementById('codeEditor'), {
  mode: 'python',
  theme: 'dracula',
  lineNumbers: true,
  matchBrackets: true,
  autoCloseBrackets: true,
  lineWrapping: true,
  indentUnit: 4,
  tabSize: 4,
  indentWithTabs: false,
  extraKeys: { Tab: cm => cm.replaceSelection('    ', 'end') },
});
editor.setSize(null, 380);

const saveBtn       = document.getElementById('saveBtn');
const clearBtn      = document.getElementById('clearBtn');
const formatBtn     = document.getElementById('formatBtn');
const charCounter   = document.getElementById('charCounter');
const fileUpload    = document.getElementById('fileUpload');
const uploadName    = document.getElementById('uploadName');
const resultBox     = document.getElementById('resultBox');
const errorBox      = document.getElementById('errorBox');
const sessionIdText = document.getElementById('sessionIdText');
const resultBadge   = document.getElementById('resultBadge');
const resultTime    = document.getElementById('resultTime');
const codeLength    = document.getElementById('codeLength');
const usageCode     = document.getElementById('usageCode');
const copyBtn       = document.getElementById('copyBtn');
const lookupBtn     = document.getElementById('lookupBtn');
const lookupId      = document.getElementById('lookupId');
const lookupResult  = document.getElementById('lookupResult');
const expiresDisplay = document.getElementById('expiresDisplay');
const ownerTokenBox = document.getElementById('ownerTokenBox');
const ownerTokenText = document.getElementById('ownerTokenText');
const copyTokenBtn  = document.getElementById('copyTokenBtn');

// ── Line counter ───────────────────────────────────────────────────────────────

function updateCounter() {
  const lines = editor.lineCount();
  charCounter.textContent = `${lines.toLocaleString()} / 10,000 lines`;
  charCounter.classList.toggle('char-warn',  lines >= 8000 && lines < MAX_LINES);
  charCounter.classList.toggle('char-limit', lines >= MAX_LINES);
}
editor.on('change', updateCounter);
updateCounter();

// ── Error / Result display ─────────────────────────────────────────────────────

function showError(msg) {
  errorBox.style.display = 'flex';
  document.getElementById('errorMsg').textContent = msg;
  resultBox.style.display = 'none';
  setTimeout(() => { errorBox.style.display = 'none'; }, 7000);
}

function showResult(sid, ownerToken, lineCount, expiresAt) {
  errorBox.style.display  = 'none';
  resultBox.style.display = 'block';
  sessionIdText.textContent = sid;
  resultBadge.textContent   = 'NEW SESSION';
  resultBadge.style.color   = '#3ddfa0';
  resultBadge.style.borderColor = 'rgba(61,223,160,0.3)';
  resultTime.textContent    = new Date().toLocaleTimeString();
  codeLength.textContent    = lineCount.toLocaleString() + ' lines';
  expiresDisplay.textContent = expiresAt
    ? new Date(expiresAt).toLocaleString()
    : 'Never';
  usageCode.textContent =
`from pyvaultrce import CodeManager

# Execute remotely — source stays encrypted server-side:
CodeManager.run("${sid}")`;

  if (ownerToken) {
    ownerTokenText.textContent  = ownerToken;
    ownerTokenBox.style.display = 'block';
    document.getElementById('myDeleteSid').value  = sid;
    document.getElementById('myEditSid').value    = sid;
  } else {
    ownerTokenBox.style.display = 'none';
  }
}

// ── Save button ────────────────────────────────────────────────────────────────

saveBtn.addEventListener('click', async () => {
  const code = editor.getValue().trim();
  if (!code) { showError('Please paste some Python code first.'); return; }
  const lineCount = editor.lineCount();
  if (lineCount > MAX_LINES) {
    showError(`Code is too long (${lineCount.toLocaleString()} lines). Maximum is 10,000 lines.`);
    return;
  }
  const expiryVal  = document.getElementById('expirySelect')?.value || '';
  const maxExecVal = parseInt(document.getElementById('maxExecInput')?.value || '0') || 0;

  const body = { code };
  if (expiryVal)  body.expires_in_hours = parseFloat(expiryVal);
  if (maxExecVal) body.max_executions   = maxExecVal;

  try {
    saveBtn.disabled    = true;
    saveBtn.textContent = 'Saving…';
    const res  = await fetch('/pyv/save', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) { showError(data.error || 'Save failed.'); return; }
    showResult(data.session_id, data.owner_token, lineCount, data.expires_at || null);
  } catch (e) {
    showError('Network error: ' + e.message);
  } finally {
    saveBtn.disabled    = false;
    saveBtn.innerHTML   = '<span class="btn-icon">↑</span> Save & Get Session ID';
  }
});

// ── Clear / Format ─────────────────────────────────────────────────────────────

clearBtn.addEventListener('click', () => {
  editor.setValue('');
  uploadName.textContent  = '';
  fileUpload.value        = '';
  resultBox.style.display = 'none';
  errorBox.style.display  = 'none';
});

formatBtn.addEventListener('click', () => {
  const lines   = editor.getValue().split('\n');
  const trimmed = lines.map(l => l.trimEnd()).join('\n').replace(/\n{3,}/g, '\n\n');
  editor.setValue(trimmed);
});

// ── File upload ────────────────────────────────────────────────────────────────

fileUpload.addEventListener('change', () => {
  const file = fileUpload.files[0];
  if (!file) return;
  if (!file.name.endsWith('.py')) {
    showError('Only .py files are accepted.');
    fileUpload.value = '';
    return;
  }
  const reader = new FileReader();
  reader.onload = e => {
    const content   = e.target.result;
    const fileLines = content.split('\n').length;
    if (fileLines > MAX_LINES) {
      showError(`File is too large (${fileLines.toLocaleString()} lines). Maximum is 10,000 lines.`);
      fileUpload.value = '';
      return;
    }
    editor.setValue(content);
    uploadName.textContent = file.name;
  };
  reader.readAsText(file, 'utf-8');
});

document.querySelector('.upload-label').addEventListener('click', () => fileUpload.click());

// ── Copy buttons ───────────────────────────────────────────────────────────────

function makeCopyHandler(btn, getText) {
  btn.addEventListener('click', () => {
    navigator.clipboard.writeText(getText()).then(() => {
      const orig = btn.innerHTML;
      btn.innerHTML = '<span style="font-size:12px;font-weight:700;">✓</span>';
      setTimeout(() => { btn.innerHTML = orig; }, 2000);
    });
  });
}

makeCopyHandler(copyBtn,      () => sessionIdText.textContent);
makeCopyHandler(copyTokenBtn, () => ownerTokenText.textContent);

// ── Lookup ─────────────────────────────────────────────────────────────────────

lookupBtn.addEventListener('click', async () => {
  const sid = lookupId.value.trim();
  if (!sid) { lookupResult.style.display = 'none'; return; }
  if (sid.length !== 21) {
    lookupResult.style.display = 'block';
    lookupResult.innerHTML = `<span style="color:var(--red)">Session ID must be exactly 21 hex characters.</span>`;
    return;
  }
  lookupResult.style.display = 'block';
  lookupResult.innerHTML     = '<span style="color:var(--text3)">Looking up…</span>';
  try {
    const res  = await fetch(`/pyv/info/${sid}`);
    const data = await res.json();
    if (!res.ok) {
      lookupResult.innerHTML = `<span style="color:var(--red)">✕ ${data.error}</span>`;
    } else {
      const statusColor = data.status === 'active' ? 'var(--green)' : 'var(--red)';
      const expiryStr   = data.expires_at ? new Date(data.expires_at).toLocaleString() : 'Never';
      const maxStr      = (data.max_executions && data.max_executions > 0)
                          ? data.max_executions : '∞';
      lookupResult.innerHTML = `
        <div style="display:flex;flex-direction:column;gap:0.5rem;">
          <div style="display:flex;gap:1rem;flex-wrap:wrap;align-items:center;">
            <span style="color:${statusColor};font-weight:600;">● ${data.status?.toUpperCase()}</span>
            <span style="color:var(--text3);font-size:12px;">Executions: <strong style="color:var(--yellow)">${data.execution_count} / ${maxStr}</strong></span>
            <span style="color:var(--text3);font-size:12px;">Created: ${data.created_at?.slice(0,16)}</span>
          </div>
          <div style="font-size:12px;color:var(--text2);">Expires: ${expiryStr}</div>
        </div>`;
    }
  } catch (e) {
    lookupResult.innerHTML = `<span style="color:var(--red)">Network error: ${e.message}</span>`;
  }
});

lookupId.addEventListener('keydown', e => { if (e.key === 'Enter') lookupBtn.click(); });

// ── Manage My Session tabs ─────────────────────────────────────────────────────

document.querySelectorAll('.manage-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.manage-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.manage-panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(tab.dataset.panel).classList.add('active');
  });
});

// ── Owner: Delete My Session ───────────────────────────────────────────────────

document.getElementById('myDeleteBtn').addEventListener('click', async () => {
  const sid   = document.getElementById('myDeleteSid').value.trim();
  const token = document.getElementById('myDeleteToken').value.trim();
  const st    = document.getElementById('deleteStatus');
  if (!sid || sid.length !== 21) { st.textContent = '✕ Enter a valid 21-char Session ID.'; st.style.color = 'var(--red)'; return; }
  if (!token) { st.textContent = '✕ Owner token is required.'; st.style.color = 'var(--red)'; return; }
  if (!confirm(`Delete session ${sid}? This cannot be undone.`)) return;
  try {
    document.getElementById('myDeleteBtn').disabled = true;
    st.textContent = 'Deleting…'; st.style.color = 'var(--text3)';
    const res  = await fetch(`/pyv/my/${sid}`, {
      method:  'DELETE',
      headers: { 'X-Owner-Token': token },
    });
    const data = await res.json();
    if (res.ok) {
      st.textContent = `✓ Session ${sid} deleted successfully.`;
      st.style.color = 'var(--green)';
      document.getElementById('myDeleteSid').value  = '';
      document.getElementById('myDeleteToken').value = '';
    } else {
      st.textContent = '✕ ' + data.error;
      st.style.color = 'var(--red)';
    }
  } catch (e) {
    st.textContent = 'Network error: ' + e.message; st.style.color = 'var(--red)';
  } finally {
    document.getElementById('myDeleteBtn').disabled = false;
  }
});

// ── Owner: Edit My Session ─────────────────────────────────────────────────────

document.getElementById('myEditBtn').addEventListener('click', async () => {
  const sid   = document.getElementById('myEditSid').value.trim();
  const token = document.getElementById('myEditToken').value.trim();
  const code  = document.getElementById('myEditCode').value.trim();
  const st    = document.getElementById('editStatus2');
  if (!sid || sid.length !== 21) { st.textContent = '✕ Enter a valid 21-char Session ID.'; st.style.color = 'var(--red)'; return; }
  if (!token) { st.textContent = '✕ Owner token is required.'; st.style.color = 'var(--red)'; return; }
  if (!code)  { st.textContent = '✕ New code cannot be empty.'; st.style.color = 'var(--red)'; return; }
  try {
    document.getElementById('myEditBtn').disabled = true;
    st.textContent = 'Updating…'; st.style.color = 'var(--text3)';
    const res  = await fetch(`/pyv/my/${sid}`, {
      method:  'PUT',
      headers: { 'Content-Type': 'application/json', 'X-Owner-Token': token },
      body:    JSON.stringify({ code }),
    });
    const data = await res.json();
    if (res.ok) { st.textContent = '✓ Code updated.'; st.style.color = 'var(--green)'; }
    else        { st.textContent = '✕ ' + data.error; st.style.color = 'var(--red)'; }
  } catch (e) {
    st.textContent = 'Network error: ' + e.message; st.style.color = 'var(--red)';
  } finally {
    document.getElementById('myEditBtn').disabled = false;
  }
});

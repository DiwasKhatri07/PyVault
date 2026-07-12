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

const saveBtn      = document.getElementById('saveBtn');
const clearBtn     = document.getElementById('clearBtn');
const formatBtn    = document.getElementById('formatBtn');
const charCounter  = document.getElementById('charCounter');
const fileUpload   = document.getElementById('fileUpload');
const uploadName   = document.getElementById('uploadName');
const resultBox    = document.getElementById('resultBox');
const errorBox     = document.getElementById('errorBox');
const sessionIdText= document.getElementById('sessionIdText');
const resultBadge  = document.getElementById('resultBadge');
const resultTime   = document.getElementById('resultTime');
const codeLength   = document.getElementById('codeLength');
const usageCode    = document.getElementById('usageCode');
const copyBtn      = document.getElementById('copyBtn');
const lookupBtn    = document.getElementById('lookupBtn');
const lookupId     = document.getElementById('lookupId');
const lookupResult = document.getElementById('lookupResult');

function updateCounter() {
  const lines = editor.lineCount();
  charCounter.textContent = `${lines.toLocaleString()} / 10,000 lines`;
  charCounter.classList.toggle('char-warn',  lines >= 8000 && lines < MAX_LINES);
  charCounter.classList.toggle('char-limit', lines >= MAX_LINES);
}
editor.on('change', updateCounter);
updateCounter();

function showError(msg) {
  errorBox.style.display = 'flex';
  document.getElementById('errorMsg').textContent = msg;
  resultBox.style.display = 'none';
  setTimeout(() => { errorBox.style.display = 'none'; }, 7000);
}

function showResult(sid, codeLen) {
  errorBox.style.display = 'none';
  resultBox.style.display = 'block';
  sessionIdText.textContent = sid;
  resultBadge.textContent = 'NEW SESSION';
  resultBadge.style.color = '#3ddfa0';
  resultBadge.style.borderColor = 'rgba(61,223,160,0.3)';
  resultTime.textContent = new Date().toLocaleTimeString();
  codeLength.textContent = codeLen.toLocaleString() + ' chars';
  usageCode.textContent =
`from pyvaultrce import CodeManager

# Execute remotely — source stays server-side:
CodeManager.run("${sid}")`;
}

saveBtn.addEventListener('click', async () => {
  const code = editor.getValue().trim();
  if (!code) { showError('Please paste some Python code first.'); return; }
  const lineCount = editor.lineCount();
  if (lineCount > MAX_LINES) {
    showError(`Code is too long (${lineCount.toLocaleString()} lines). Maximum is 10,000 lines.`);
    return;
  }
  try {
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving…';
    const res = await fetch('/pyv/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    const data = await res.json();
    if (!res.ok) { showError(data.error || 'Save failed.'); return; }
    showResult(data.session_id, code.length);
  } catch (e) {
    showError('Network error: ' + e.message);
  } finally {
    saveBtn.disabled = false;
    saveBtn.innerHTML = '<span class="btn-icon">↑</span> Save & Get Session ID';
  }
});

clearBtn.addEventListener('click', () => {
  editor.setValue('');
  uploadName.textContent = '';
  fileUpload.value = '';
  resultBox.style.display = 'none';
  errorBox.style.display = 'none';
});

formatBtn.addEventListener('click', () => {
  const lines = editor.getValue().split('\n');
  const trimmed = lines.map(l => l.trimEnd()).join('\n').replace(/\n{3,}/g, '\n\n');
  editor.setValue(trimmed);
});

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
    const content = e.target.result;
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

copyBtn.addEventListener('click', () => {
  navigator.clipboard.writeText(sessionIdText.textContent).then(() => {
    copyBtn.innerHTML = '<span style="font-size:12px;font-weight:700;">✓</span>';
    setTimeout(() => {
      copyBtn.innerHTML = `<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
    }, 2000);
  });
});

lookupBtn.addEventListener('click', async () => {
  const sid = lookupId.value.trim();
  if (!sid) { lookupResult.style.display = 'none'; return; }
  if (sid.length !== 21) {
    lookupResult.style.display = 'block';
    lookupResult.innerHTML = `<span style="color:var(--red)">Session ID must be exactly 21 hex characters.</span>`;
    return;
  }
  lookupResult.style.display = 'block';
  lookupResult.innerHTML = '<span style="color:var(--text3)">Looking up…</span>';
  try {
    const res = await fetch(`/pyv/info/${sid}`);
    const data = await res.json();
    if (!res.ok) {
      lookupResult.innerHTML = `<span style="color:var(--red)">✕ ${data.error}</span>`;
    } else {
      lookupResult.innerHTML = `
        <div style="display:flex;flex-direction:column;gap:0.5rem;">
          <div style="display:flex;gap:1rem;flex-wrap:wrap;">
            <span style="color:var(--green);font-weight:600;">✓ Session Found</span>
            <span style="color:var(--text3);font-size:12px;">Executions: <strong style="color:var(--yellow)">${data.execution_count}</strong></span>
            <span style="color:var(--text3);font-size:12px;">Created: ${data.created_at}</span>
          </div>
          <div style="font-size:12px;color:var(--text2);">Code size: ${data.code_size.toLocaleString()} characters</div>
        </div>`;
    }
  } catch (e) {
    lookupResult.innerHTML = `<span style="color:var(--red)">Network error: ${e.message}</span>`;
  }
});

lookupId.addEventListener('keydown', e => { if (e.key === 'Enter') lookupBtn.click(); });

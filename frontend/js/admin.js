/**
 * KTU Admin Studio Engine
 * Handles Admin Authentication, Live Traffic & Cache Monitoring,
 * Bulk CSV/Excel Importer with Worker Polling, and Redis Pre-Warming.
 */

let selectedFile = null;
let statsInterval = null;

document.addEventListener('DOMContentLoaded', () => {
  initAdminAuth();
  setupDropzone();
});

// ----------------- Auth Management -----------------
function initAdminAuth() {
  const token = localStorage.getItem('ktu_admin_token');
  const loginForm = document.getElementById('adminLoginForm');

  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    await handleLogin();
  });

  if (token) {
    verifyTokenAndLoadDashboard(token);
  }
}

async function handleLogin() {
  const username = document.getElementById('adminUsername').value.trim();
  const password = document.getElementById('adminPassword').value.trim();
  const errBanner = document.getElementById('loginError');
  const btnLogin = document.getElementById('btnLogin');

  errBanner.style.display = 'none';
  btnLogin.disabled = true;

  try {
    const res = await fetch('/api/v1/admin/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const json = await res.json();
    if (!res.ok || !json.success) {
      document.getElementById('loginErrorText').textContent = json.detail || 'Invalid username or password.';
      errBanner.style.display = 'block';
      return;
    }

    localStorage.setItem('ktu_admin_token', json.access_token);
    showDashboard();
  } catch (err) {
    console.error('Login error:', err);
    document.getElementById('loginErrorText').textContent = 'Server unreachable. Please check backend connection.';
    errBanner.style.display = 'block';
  } finally {
    btnLogin.disabled = false;
  }
}

async function verifyTokenAndLoadDashboard(token) {
  try {
    const res = await fetch('/api/v1/admin/auth/me', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
      showDashboard();
    } else {
      adminLogout();
    }
  } catch (err) {
    console.error('Token verify failed:', err);
  }
}

function showDashboard() {
  document.getElementById('loginSection').style.display = 'none';
  document.getElementById('dashboardSection').style.display = 'block';
  document.getElementById('btnLogout').style.display = 'inline-flex';

  loadAdminExams();
  loadLiveStats();

  if (statsInterval) clearInterval(statsInterval);
  statsInterval = setInterval(loadLiveStats, 3000);
}

function adminLogout() {
  localStorage.removeItem('ktu_admin_token');
  if (statsInterval) clearInterval(statsInterval);
  document.getElementById('loginSection').style.display = 'block';
  document.getElementById('dashboardSection').style.display = 'none';
  document.getElementById('btnLogout').style.display = 'none';
}

function getAuthHeaders() {
  const token = localStorage.getItem('ktu_admin_token');
  return { 'Authorization': `Bearer ${token}` };
}

// ----------------- Tabs & Navigation -----------------
function switchAdminTab(tabName) {
  document.querySelectorAll('.admin-tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.admin-tab-content').forEach(c => c.style.display = 'none');

  const activeBtn = Array.from(document.querySelectorAll('.admin-tab-btn')).find(b => b.getAttribute('onclick').includes(tabName));
  if (activeBtn) activeBtn.classList.add('active');

  const content = document.getElementById(`tab-${tabName}`);
  if (content) content.style.display = 'block';
}

// ----------------- Live Stats Poller -----------------
async function loadLiveStats() {
  try {
    const res = await fetch('/api/v1/admin/stats', { headers: getAuthHeaders() });
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById('statCacheHitRate').textContent = `${data.cache.hit_rate_pct}%`;
    document.getElementById('statCoalesced').textContent = data.coalescer.stampede_queries_prevented;
    document.getElementById('statTotalStudents').textContent = data.database.total_students.toLocaleString();
    document.getElementById('statL1Size').textContent = data.cache.l1_items_count;
  } catch (err) {
    console.error('Error fetching live stats:', err);
  }
}

// ----------------- Exams & Publication Controls -----------------
async function loadAdminExams() {
  try {
    const res = await fetch('/api/v1/admin/exams', { headers: getAuthHeaders() });
    const json = await res.json();
    if (!json.success) return;

    const exams = json.data;
    
    // Populate dropdowns
    const warmSelect = document.getElementById('warmExamSelect');
    const uploadSelect = document.getElementById('uploadExamSelect');
    
    const optionsHtml = exams.map(e => `<option value="${e.id}">${e.title} (${e.session})</option>`).join('');
    if (warmSelect) warmSelect.innerHTML = optionsHtml;
    if (uploadSelect) uploadSelect.innerHTML = optionsHtml;

    // Populate table
    const tbody = document.getElementById('adminExamsTableBody');
    tbody.innerHTML = exams.map(e => `
      <tr>
        <td><strong>${e.title}</strong><br><span style="font-size: 0.75rem; color: var(--text-muted);">${e.code}</span></td>
        <td>${e.session}</td>
        <td>Semester ${e.semester}</td>
        <td style="text-align: center; font-weight: 700;">${e.total_students.toLocaleString()}</td>
        <td style="text-align: center; font-weight: 700; color: var(--success);">${e.pass_rate}%</td>
        <td style="text-align: center; font-weight: 700;">${e.avg_sgpa.toFixed(2)}</td>
        <td style="text-align: center;">
          <label class="toggle-switch">
            <input type="checkbox" ${e.is_published ? 'checked' : ''} onchange="togglePublish('${e.id}', this.checked)">
            <span class="slider"></span>
          </label>
        </td>
      </tr>
    `).join('');

  } catch (err) {
    console.error('Error loading admin exams:', err);
  }
}

async function togglePublish(examId, isPublished) {
  try {
    const res = await fetch(`/api/v1/admin/exams/${examId}/publish`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_published: isPublished })
    });
    if (res.ok) {
      loadAdminExams();
    }
  } catch (err) {
    console.error('Error toggling publish status:', err);
  }
}

// ----------------- Cache Pre-Warming -----------------
async function triggerCacheWarm() {
  const examId = document.getElementById('warmExamSelect').value;
  const btn = document.getElementById('btnWarmCache');
  const box = document.getElementById('warmProgressBox');
  const bar = document.getElementById('warmProgressBar');
  const txt = document.getElementById('warmProgressText');
  const pct = document.getElementById('warmProgressPct');

  btn.disabled = true;
  box.style.display = 'block';
  bar.style.width = '0%';
  txt.textContent = 'Initializing cache warming...';

  try {
    const res = await fetch('/api/v1/admin/cache/warm', {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ exam_id: examId })
    });
    const json = await res.json();
    if (!json.success) throw new Error(json.detail);

    const jobId = json.job_id;
    // Poll job status
    const pollWarm = setInterval(async () => {
      try {
        const pollRes = await fetch(`/api/v1/admin/cache/warm/${jobId}`, { headers: getAuthHeaders() });
        const pollJson = await pollRes.json();
        if (pollJson.success && pollJson.data) {
          const st = pollJson.data;
          bar.style.width = `${st.pct}%`;
          pct.textContent = `${st.pct}%`;
          txt.textContent = st.message;

          if (st.status === 'completed' || st.status === 'failed') {
            clearInterval(pollWarm);
            btn.disabled = false;
            loadLiveStats();
          }
        }
      } catch (e) {
        clearInterval(pollWarm);
        btn.disabled = false;
      }
    }, 500);

  } catch (err) {
    console.error('Error warming cache:', err);
    txt.textContent = 'Cache warming failed.';
    btn.disabled = false;
  }
}

// ----------------- Dropzone & Bulk Import -----------------
function setupDropzone() {
  const dropzone = document.getElementById('dropzone');
  if (!dropzone) return;

  ['dragenter', 'dragover'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
    });
  });

  dropzone.addEventListener('drop', (e) => {
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processSelectedFile(e.dataTransfer.files[0]);
    }
  });
}

function handleFileSelected(event) {
  if (event.target.files && event.target.files[0]) {
    processSelectedFile(event.target.files[0]);
  }
}

function processSelectedFile(file) {
  selectedFile = file;
  const label = document.getElementById('selectedFileLabel');
  const btn = document.getElementById('btnStartImport');
  label.textContent = `📄 Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  label.style.display = 'block';
  btn.style.display = 'block';
}

async function startBulkImport() {
  if (!selectedFile) return;

  const examId = document.getElementById('uploadExamSelect').value;
  const btn = document.getElementById('btnStartImport');
  const box = document.getElementById('importProgressBox');
  const bar = document.getElementById('importProgressBar');
  const txt = document.getElementById('importProgressText');
  const pct = document.getElementById('importProgressPct');
  const errBox = document.getElementById('importErrorsBox');

  btn.disabled = true;
  box.style.display = 'block';
  errBox.style.display = 'none';
  bar.style.width = '0%';
  txt.textContent = 'Uploading and streaming file to server...';

  const formData = new FormData();
  formData.append('exam_id', examId);
  formData.append('file', selectedFile);

  try {
    const res = await fetch('/api/v1/admin/results/upload', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData
    });

    const json = await res.json();
    if (!json.success) throw new Error(json.detail || 'Upload failed');

    const jobId = json.job_id;
    // Poll import job status
    const pollImport = setInterval(async () => {
      try {
        const pollRes = await fetch(`/api/v1/admin/results/import-jobs/${jobId}`, { headers: getAuthHeaders() });
        const pollJson = await pollRes.json();
        if (pollJson.success && pollJson.data) {
          const st = pollJson.data;
          bar.style.width = `${st.pct}%`;
          pct.textContent = `${st.pct}%`;
          txt.textContent = `Processed ${st.processed_rows} students...`;

          if (st.status === 'completed' || st.status === 'failed') {
            clearInterval(pollImport);
            btn.disabled = false;
            txt.textContent = `✅ Successfully imported ${st.processed_rows} student results!`;
            
            if (st.error_count > 0 && st.errors && st.errors.length > 0) {
              errBox.style.display = 'block';
              errBox.innerHTML = `<strong>Warnings/Errors (${st.error_count}):</strong><br>${st.errors.join('<br>')}`;
            }

            loadAdminExams();
            loadLiveStats();
          }
        }
      } catch (e) {
        clearInterval(pollImport);
        btn.disabled = false;
      }
    }, 500);

  } catch (err) {
    console.error('Import error:', err);
    txt.textContent = `Error: ${err.message}`;
    btn.disabled = false;
  }
}

let currentJob = null;
let timer = null;
let lastScan = null;

const PANEL_COPY = {
  workbench: {
    title: '扫描、识别并生成安全脱敏副本',
    subtitle: '输入本机目录后先扫描文件数量和类型，确认后再创建同级 _desensitized 目录。'
  },
  progress: {
    title: '执行进度',
    subtitle: '查看当前任务状态、目标目录、正在处理的文件和整体进度。'
  },
  results: {
    title: '扫描结果',
    subtitle: '查看本次扫描发现的可处理文件、跳过文件、文件类型和跳过原因。'
  },
  rules: {
    title: '脱敏规则',
    subtitle: '按安全管理要求展示当前启用的规则组和对应敏感信息类型。'
  },
  scope: {
    title: '文件范围',
    subtitle: '查看当前版本支持处理、跳过或暂不支持的文件类型。'
  },
  'report-generator': {
    title: '统一报告生成',
    subtitle: '一次指定台账数据源和交付文档目录，按日期范围生成周报、月报、季度报或年度报告。'
  },
  report: {
    title: '报告说明',
    subtitle: '任务完成后会生成 JSON 报告，用于审计处理数量、失败文件和规则命中次数。'
  },
  risk: {
    title: '风险提示',
    subtitle: '说明规则脱敏的边界、可能漏判的场景，以及正式使用前需要人工抽查的内容。'
  }
};

function sourceDir() { return document.getElementById('sourceDir').value.trim(); }
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }
function extOf(path) { const i = path.lastIndexOf('.'); return i >= 0 ? path.slice(i).toLowerCase() : '(无扩展名)'; }
function setStartDisabled(disabled) {
  document.getElementById('startBtn').disabled = disabled;
  document.getElementById('resultStartBtn').disabled = disabled;
}

function setStep(name) {
  for (const id of ['stepInput', 'stepScan', 'stepRun']) document.getElementById(id).classList.remove('active');
  document.getElementById(name).classList.add('active');
}

function setStatus(text, state = 'neutral') {
  document.getElementById('status').textContent = text;
  const badge = document.getElementById('statusBadge');
  badge.textContent = text.length > 12 ? text.slice(0, 12) : text;
  badge.className = `tag ${state}`;
}

function setProgress(processed, total) {
  const pct = total ? Math.round(processed * 100 / total) : 0;
  document.getElementById('bar').style.width = pct + '%';
}

function setTypeCounts(supported, skipped) {
  const items = [];
  for (const [ext, count] of Object.entries(supported || {})) items.push(`<span class="pill ok">可处理 ${escapeHtml(ext)}：${count}</span>`);
  for (const [ext, count] of Object.entries(skipped || {})) items.push(`<span class="pill skip">跳过 ${escapeHtml(ext)}：${count}</span>`);
  document.getElementById('typeCounts').innerHTML = items.join('') || '<span class="pill">暂无类型统计</span>';
}

function setRows(files, skipped) {
  const rows = [];
  for (const file of files || []) {
    rows.push(`<tr><td>${escapeHtml(file)}</td><td>${escapeHtml(extOf(file))}</td><td><span class="state ok">可处理</span></td><td>将参与脱敏</td></tr>`);
  }
  for (const item of skipped || []) {
    rows.push(`<tr><td>${escapeHtml(item.path)}</td><td>${escapeHtml(extOf(item.path))}</td><td><span class="state skip">跳过</span></td><td>${escapeHtml(item.reason)}</td></tr>`);
  }
  document.getElementById('fileRows').innerHTML = rows.join('') || '<tr><td colspan="4" class="muted">没有扫描到文件。</td></tr>';
  document.getElementById('tableSummary').textContent = `共 ${(files || []).length + (skipped || []).length} 个文件，${(files || []).length} 个可处理，${(skipped || []).length} 个跳过`;
}

async function postJson(url, payload) {
  const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || '请求失败');
  return data;
}

function setReportDefaults() {
  const start = document.getElementById('reportStartDate');
  const end = document.getElementById('reportEndDate');
  if (!start || !end || start.value || end.value) return;
  const today = new Date();
  const day = today.getDay() || 7;
  const monday = new Date(today);
  monday.setDate(today.getDate() - day + 1);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  start.value = monday.toISOString().slice(0, 10);
  end.value = sunday.toISOString().slice(0, 10);
}

function selectedReportType() {
  return document.querySelector('.reportType.active')?.dataset.reportType || 'weekly';
}

function renderReportResult(data) {
  const categoryRows = (data.category_counts || []).map(([name, count]) => `<span>${escapeHtml(name)}：${count}</span>`).join('');
  const docSummaries = (data.delivery_document_summaries || []).map(item => `
    <details class="docSummary" open>
      <summary>${escapeHtml(item.name)}</summary>
      <p class="muted">${escapeHtml(item.path)}</p>
      <ul>${(item.summary || []).map(line => `<li>${escapeHtml(line)}</li>`).join('') || '<li>未提取到有效文本。</li>'}</ul>
    </details>
  `).join('');
  const missingDocs = (data.missing_delivery_documents || []).map(name => `<span>${escapeHtml(name)}</span>`).join('');
  document.getElementById('reportResult').innerHTML = `
    <div class="reportSummary">
      <div><b>${data.total_records}</b><span>周期内记录</span></div>
      <div><b>${data.reportable_records}</b><span>纳入汇报</span></div>
      <div><b>${data.completed_records}</b><span>已完成</span></div>
      <div><b>${data.delivery_document_count}</b><span>交付文档</span></div>
    </div>
    <div class="generatedPath"><b>报告类型</b><span>${escapeHtml(data.report_title || '')}</span></div>
    <div class="generatedPath"><b>Markdown 文件</b><span>${escapeHtml(data.report_path)}</span></div>
    <div class="generatedPath"><b>Word 文件</b><span>${escapeHtml(data.word_path || '')}</span></div>
    <div class="panelActions">
      <a class="downloadButton" href="/download?path=${encodeURIComponent(data.word_path || '')}">下载 Word</a>
    </div>
    <div class="generatedPath"><b>文档搜索目录</b><span>${escapeHtml(data.document_root || '')}</span></div>
    <div class="reportOptions">${categoryRows || '<span>无类别统计</span>'}</div>
    <div class="documentSummaryBlock">
      <h3>交付文档重点内容</h3>
      ${docSummaries || '<p class="hint">本周期台账记录未填写或未匹配到交付文档。</p>'}
      ${missingDocs ? `<div class="missingDocs"><b>未找到：</b>${missingDocs}</div>` : ''}
    </div>
    <pre class="reportPreview">${escapeHtml(data.preview || '')}</pre>
  `;
}

async function generateUnifiedReport() {
  const button = document.getElementById('reportGenerateBtn');
  const result = document.getElementById('reportResult');
  try {
    button.disabled = true;
    result.innerHTML = '<p class="hint">正在读取 Excel 台账、查找交付文档并生成报告...</p>';
    const data = await postJson('/reports/generate', {
      report_type: selectedReportType(),
      ledger_path: document.getElementById('reportLedgerPath').value.trim(),
      document_root: document.getElementById('reportDocumentRoot').value.trim(),
      start_date: document.getElementById('reportStartDate').value,
      end_date: document.getElementById('reportEndDate').value
    });
    renderReportResult(data);
  } catch (e) {
    result.innerHTML = `<p class="errorText">${escapeHtml(e.message)}</p>`;
  } finally {
    button.disabled = false;
  }
}

async function scan() {
  try {
    setStep('stepScan');
    setStatus('扫描中', 'neutral');
    setStartDisabled(true);
    const data = await postJson('/scan', {source_dir: sourceDir()});
    lastScan = data;
    document.getElementById('total').textContent = data.total;
    document.getElementById('processed').textContent = 0;
    document.getElementById('skipped').textContent = data.skipped_count;
    document.getElementById('failed').textContent = 0;
    document.getElementById('targetDir').textContent = data.target_dir;
    document.getElementById('currentFile').textContent = '-';
    setStatus('扫描完成，尚未脱敏', 'ok');
    setStartDisabled(data.total === 0);
    setProgress(0, data.total);
    setTypeCounts(data.supported_extension_counts, data.skipped_extension_counts);
    setRows(data.files || [], data.skipped || []);
    activatePanel('results');
  } catch (e) {
    setStep('stepInput');
    setStatus(e.message, 'danger');
    setStartDisabled(true);
  }
}

async function startJob() {
  try {
    setStep('stepRun');
    setStartDisabled(true);
    const data = await postJson('/start', {source_dir: sourceDir()});
    currentJob = data.job_id;
    setStatus('脱敏中', 'neutral');
    activatePanel('progress');
    if (timer) clearInterval(timer);
    timer = setInterval(poll, 350);
    poll();
  } catch (e) {
    setStatus(e.message, 'danger');
    setStartDisabled(false);
  }
}

async function poll() {
  if (!currentJob) return;
  const res = await fetch('/status?job_id=' + encodeURIComponent(currentJob));
  const data = await res.json();
  setStatus(data.status + (data.error ? '：' + data.error : ''), data.status === 'failed' ? 'danger' : 'neutral');
  document.getElementById('total').textContent = data.total || 0;
  document.getElementById('processed').textContent = data.processed || 0;
  document.getElementById('skipped').textContent = (data.skipped || []).length;
  document.getElementById('failed').textContent = (data.failed || []).length;
  document.getElementById('targetDir').textContent = data.target_dir || '-';
  document.getElementById('currentFile').textContent = data.current_file || '-';
  setProgress(data.processed || 0, data.total || 0);
  if (data.status === 'done' || data.status === 'failed') {
    clearInterval(timer);
    setStartDisabled(false);
    if (data.status === 'done') setStatus('脱敏完成，报告已生成', 'ok');
  }
}

function activatePanel(panelName) {
  document.querySelectorAll('.navItem').forEach(item => item.classList.toggle('active', item.dataset.panel === panelName));
  document.querySelectorAll('.panel').forEach(panel => panel.classList.toggle('activePanel', panel.id === `panel-${panelName}`));
  const copy = PANEL_COPY[panelName];
  if (copy) {
    document.getElementById('pageTitle').textContent = copy.title;
    document.getElementById('pageSubtitle').textContent = copy.subtitle;
  }
  const panel = document.getElementById(`panel-${panelName}`);
  if (panel) window.scrollTo({top: 0, behavior: 'smooth'});
}

document.querySelectorAll('.navItem').forEach(item => {
  item.addEventListener('click', () => activatePanel(item.dataset.panel));
});

document.querySelectorAll('.reportType').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.reportType').forEach(item => item.classList.remove('active'));
    button.classList.add('active');
  });
});

setReportDefaults();

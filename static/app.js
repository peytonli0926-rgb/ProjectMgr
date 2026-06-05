let currentJob = null;
let timer = null;
let lastScan = null;

const PANEL_COPY = {
  workbench: {
    title: '扫描所有文件并生成安全脱敏副本',
    subtitle: '输入本机目录后扫描全部文件（不限类型），确认后再创建同级 _desensitized 目录。'
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
    title: '文件范围（全类型脱敏）',
    subtitle: '当前版本扫描所有文件，不限类型，全部参与脱敏处理。'
  },
  'report-generator': {
    title: '统一报告生成',
    subtitle: '一次指定台账数据源和交付文档目录，按日期范围生成周报、月报、季度报或年度报告。'
  },
  'deepseek-config': {
    title: 'DeepSeek 模型设置',
    subtitle: '配置本地或联网模型服务的连接参数，选择要使用的模型进行分析。'
  },
  'awr-analysis': {
    title: 'AWR 性能分析',
    subtitle: '读取 Oracle .lst 性能对比文件或 AWR HTML 报告，调用 DeepSeek 本地模型生成分析报告。'
  },
  'tfa-analysis': {
    title: 'TFA 日志自动分析',
    subtitle: '输入已脱敏的 Oracle TFA zip 包，自动解压并分析八大方向，生成 evidence.json 和 Word 报告。'
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
  for (const [ext, count] of Object.entries(supported || {})) items.push(`<span class="pill ok">${escapeHtml(ext)}：${count}</span>`);
  for (const [ext, count] of Object.entries(skipped || {})) items.push(`<span class="pill skip">排除 ${escapeHtml(ext)}：${count}</span>`);
  document.getElementById('typeCounts').innerHTML = items.join('') || '<span class="pill">暂无类型统计</span>';
}

function setRows(files, skipped) {
  const rows = [];
  for (const file of files || []) {
    rows.push(`<tr><td>${escapeHtml(file)}</td><td>${escapeHtml(extOf(file))}</td><td><span class="state ok">待脱敏</span></td><td>参与脱敏</td></tr>`);
  }
  for (const item of skipped || []) {
    rows.push(`<tr><td>${escapeHtml(item.path)}</td><td>${escapeHtml(extOf(item.path))}</td><td><span class="state skip">排除</span></td><td>${escapeHtml(item.reason)}</td></tr>`);
  }
  document.getElementById('fileRows').innerHTML = rows.join('') || '<tr><td colspan="4" class="muted">没有扫描到文件。</td></tr>';
  document.getElementById('tableSummary').textContent = `共 ${(files || []).length + (skipped || []).length} 个文件，${(files || []).length} 个待脱敏，${(skipped || []).length} 个排除`;
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

function renderReportResult(data, aiEnabled) {
  const categoryRows = (data.category_counts || []).map(([name, count]) => `<span>${escapeHtml(name)}：${count}</span>`).join('');
  const docSummaries = (data.delivery_document_summaries || []).map(item => `
    <details class="docSummary" open>
      <summary>${escapeHtml(item.name)}</summary>
      <p class="muted">${escapeHtml(item.path)}</p>
      <ul>${(item.summary || []).map(line => `<li>${escapeHtml(line)}</li>`).join('') || '<li>未提取到有效文本。</li>'}</ul>
    </details>
  `).join('');
  const missingDocs = (data.missing_delivery_documents || []).map(name => `<span>${escapeHtml(name)}</span>`).join('');

  // AI 增强信息
  let aiBadge = '';
  let aiWarning = '';
  if (aiEnabled) {
    if (data.ai_enhanced) {
      aiBadge = `<div class="aiBadge aiSuccess">🤖 AI 增强已应用${data.chart_count ? ' · 图表 ' + data.chart_count + ' 张' : ''}</div>`;
    } else if (data.error_warning) {
      aiWarning = `<div class="aiBadge aiWarning">⚠️ ${escapeHtml(data.error_warning)}</div>`;
    }
  }

  document.getElementById('reportResult').innerHTML = `
    ${aiBadge}
    ${aiWarning}
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

function renderSingleFileResult(data) {
  const countItems = Object.entries(data.counts || {}).map(([name, count]) => `<span>${escapeHtml(name)}：${count}</span>`).join('');
  document.getElementById('singleFileResult').innerHTML = `
    <div class="generatedPath"><b>源文件</b><span>${escapeHtml(data.source_file || '')}</span></div>
    <div class="generatedPath"><b>脱敏文件</b><span>${escapeHtml(data.target_file || '')}</span></div>
    <div class="generatedPath"><b>报告文件</b><span>${escapeHtml(data.report_path || '')}</span></div>
    <div class="panelActions singleActions">
      <a class="downloadButton" href="/download?path=${encodeURIComponent(data.target_file || '')}">下载脱敏文件</a>
      <a class="downloadButton secondaryLink" href="/download?path=${encodeURIComponent(data.report_path || '')}">下载处理报告</a>
    </div>
    <div class="reportOptions">${countItems || '<span>未命中敏感规则</span>'}</div>
  `;
}

async function redactSingleFile() {
  const result = document.getElementById('singleFileResult');
  try {
    result.innerHTML = '<p class="hint">正在按金融行业规则脱敏该文件...</p>';
    const data = await postJson('/redact-file', {
      file_path: document.getElementById('singleFilePath').value.trim()
    });
    renderSingleFileResult(data);
  } catch (e) {
    result.innerHTML = `<p class="errorText">${escapeHtml(e.message)}</p>`;
  }
}

// ── 双面板模式切换 ──
function toggleDsMode() {
  const mode = document.querySelector('input[name="dsMode"]:checked')?.value || 'local';
  document.getElementById('dsPanelLocal').style.display = mode === 'local' ? 'block' : 'none';
  document.getElementById('dsPanelOnline').style.display = mode === 'online' ? 'block' : 'none';
  document.getElementById('dsModeLocalLabel').classList.toggle('dsModeActive', mode === 'local');
  document.getElementById('dsModeOnlineLabel').classList.toggle('dsModeActive', mode === 'online');
}

// ── 获取当前激活面板的配置 ──
function getActiveDsConfig() {
  const mode = document.querySelector('input[name="dsMode"]:checked')?.value || 'local';
  return {
    active_mode: mode,
    local: {
      url: document.getElementById('dsLocalUrl').value.trim(),
      model: document.getElementById('dsLocalModel').value.trim(),
    },
    online: {
      url: document.getElementById('dsOnlineUrl').value.trim(),
      model: document.getElementById('dsOnlineModel').value.trim(),
      api_key: document.getElementById('dsOnlineApiKey').value.trim(),
    },
  };
}

// ── 获取当前生效的单组配置（供分析端使用） ──
function getActiveDsEndpoint() {
  const cfg = getActiveDsConfig();
  const panel = cfg[cfg.active_mode] || {};
  return {
    url: panel.url || '',
    model: panel.model || '',
    api_key: cfg.active_mode === 'online' ? (panel.api_key || '') : '',
  };
}

// ── 从下拉菜单获取选定模型的配置（支持 AWR 分析和报告生成） ──
function getSelectedDsEndpoint(selectId) {
  selectId = selectId || 'dsAnalysisMode';
  const modeSelect = document.getElementById(selectId);
  const selectedMode = modeSelect ? modeSelect.value : '';
  // 空值 = 使用 DeepSeek 设置中当前激活的配置
  if (!selectedMode) {
    return getActiveDsEndpoint();
  }
  // "local" 或 "online" = 强制使用指定面板的配置
  const cfg = getActiveDsConfig();
  const panel = cfg[selectedMode] || {};
  return {
    url: panel.url || '',
    model: panel.model || '',
    api_key: selectedMode === 'online' ? (panel.api_key || '') : '',
  };
}

// ── 保存双面板配置 ──
async function saveDeepseekConfig() {
  const hint = document.getElementById('dsSaveHint');
  const config = getActiveDsConfig();
  const activeUrl = config[config.active_mode].url;
  if (!activeUrl) {
    hint.textContent = '⚠️ 当前激活的地址不能为空';
    hint.className = 'dsSaveHint dsSaveError';
    setTimeout(() => { hint.textContent = ''; hint.className = 'dsSaveHint'; }, 3000);
    return;
  }
  try {
    hint.textContent = '⏳ 保存中...';
    hint.className = 'dsSaveHint';
    const data = await postJson('/oracle/save-deepseek-config', config);
    hint.textContent = '✅ 配置已保存（' + (config.active_mode === 'local' ? '本地' : '联网') + '）';
    hint.className = 'dsSaveHint dsSaveOk';
    setTimeout(() => { hint.textContent = ''; hint.className = 'dsSaveHint'; }, 3000);
  } catch (e) {
    hint.textContent = '❌ 保存失败：' + escapeHtml(e.message);
    hint.className = 'dsSaveHint dsSaveError';
    setTimeout(() => { hint.textContent = ''; hint.className = 'dsSaveHint'; }, 4000);
  }
}

// ── 加载双面板配置 ──
async function loadDeepseekConfig() {
  try {
    const res = await fetch('/oracle/load-deepseek-config');
    const cfg = await res.json();
    if (!res.ok) return;
    // 设置本地面板
    const localCfg = cfg.local || {};
    if (localCfg.url !== undefined) document.getElementById('dsLocalUrl').value = localCfg.url;
    if (localCfg.model !== undefined) {
      setTimeout(() => {
        const sel = document.getElementById('dsLocalModel');
        if (sel.querySelector(`option[value="${escapeHtml(localCfg.model)}"]`)) {
          sel.value = localCfg.model;
        }
      }, 150);
    }
    // 设置联网面板
    const onlineCfg = cfg.online || {};
    if (onlineCfg.url !== undefined) document.getElementById('dsOnlineUrl').value = onlineCfg.url;
    if (onlineCfg.model !== undefined) document.getElementById('dsOnlineModel').value = onlineCfg.model;
    if (onlineCfg.api_key !== undefined) document.getElementById('dsOnlineApiKey').value = onlineCfg.api_key;
    // 设置激活模式
    const active = cfg.active_mode || 'local';
    const radio = document.querySelector(`input[name="dsMode"][value="${active}"]`);
    if (radio) radio.checked = true;
    toggleDsMode();
  } catch (e) {
    // Silent — saved config is optional
  }
}

async function loadOracleLstFiles() {
  const select = document.getElementById('oracleLstPath');
  if (!select) return;
  try {
    const res = await fetch('/oracle/lst-files');
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '加载 .lst 文件失败');
    const savedCfg = data.saved_config || {};
    const savedLocal = savedCfg.local || {};
    const savedOnline = savedCfg.online || {};

    // ── 本地面板 ──
    const localUrlEl = document.getElementById('dsLocalUrl');
    if (localUrlEl) localUrlEl.value = savedLocal.url || data.default_url || localUrlEl.value || '';
    const modelSelect = document.getElementById('dsLocalModel');
    const models = data.models || [];
    modelSelect.innerHTML = models.length
      ? models.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('')
      : `<option value="${escapeHtml(data.default_model || '')}">${escapeHtml(data.default_model || '未发现本地模型')}</option>`;
    const preferredModel = savedLocal.model || data.default_model;
    modelSelect.value = models.includes(preferredModel) ? preferredModel : (models[0] || data.default_model || '');

    // ── 联网面板 ──
    const onlineUrlEl = document.getElementById('dsOnlineUrl');
    if (onlineUrlEl && savedOnline.url) onlineUrlEl.value = savedOnline.url;
    const onlineModelEl = document.getElementById('dsOnlineModel');
    if (onlineModelEl && savedOnline.model) onlineModelEl.value = savedOnline.model;
    const onlineKeyEl = document.getElementById('dsOnlineApiKey');
    if (onlineKeyEl && savedOnline.api_key) onlineKeyEl.value = savedOnline.api_key;

    // ── 激活模式 ──
    const active = savedCfg.active_mode || 'local';
    const radio = document.querySelector(`input[name="dsMode"][value="${active}"]`);
    if (radio) radio.checked = true;
    toggleDsMode();

    // ── .lst 文件列表 ──
    select.innerHTML = (data.files || []).map(file => {
      const sizeKb = Math.max(1, Math.round((file.size || 0) / 1024));
      return `<option value="${escapeHtml(file.path)}">${escapeHtml(file.name)} · ${sizeKb} KB · ${escapeHtml(file.modified_at)}</option>`;
    }).join('') || '<option value="">data 目录下暂无 .lst 文件</option>';
    const awrSelect = document.getElementById('oracleAwrSelect');
    const awrFiles = data.awr_files || [];
    awrSelect.innerHTML = awrFiles.map(file => {
      const sizeKb = Math.max(1, Math.round((file.size || 0) / 1024));
      return `<option value="${escapeHtml(file.path)}">${escapeHtml(file.name)} · ${sizeKb} KB · ${escapeHtml(file.modified_at)}</option>`;
    }).join('') || '<option value="">未发现 AWR 文件，可手动输入路径</option>';
    if (awrFiles[0] && !document.getElementById('oracleAwrPath').value) {
      document.getElementById('oracleAwrPath').value = awrFiles[0].path;
    }
    const templateSelect = document.getElementById('oracleReportTemplate');
    const templates = data.templates || [];
    templateSelect.innerHTML = '<option value="">不使用模板</option>' + templates.map(t => {
      const sizeKb = Math.max(1, Math.round((t.size || 0) / 1024));
      return `<option value="${escapeHtml(t.path)}">${escapeHtml(t.name)} · ${sizeKb} KB</option>`;
    }).join('');
    const preferred = templates.find(t => t.name.startsWith('OPT_')) || templates[0];
    if (preferred) templateSelect.value = preferred.path;
  } catch (e) {
    select.innerHTML = '<option value="">加载失败</option>';
    document.getElementById('oracleAnalysisResult').innerHTML = `<p class="errorText">${escapeHtml(e.message)}</p>`;
  }
}

function fillSelectedAwrFile() {
  const selected = document.getElementById('oracleAwrSelect').value;
  if (selected) document.getElementById('oracleAwrPath').value = selected;
}

function chooseAwrUpload() {
  document.getElementById('awrUploadInput').click();
}

async function uploadSelectedAwrFile(file) {
  if (!file) return;
  const result = document.getElementById('oracleAnalysisResult');
  try {
    const form = new FormData();
    form.append('awr_file', file);
    result.innerHTML = '<p class="hint">正在上传 AWR 报告...</p>';
    const res = await fetch('/oracle/upload-awr', {method: 'POST', body: form});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '上传失败');
    await loadOracleLstFiles();
    document.getElementById('oracleAwrPath').value = data.file?.path || '';
    const awrSelect = document.getElementById('oracleAwrSelect');
    if (data.file?.path) awrSelect.value = data.file.path;
    result.innerHTML = `<p class="hint">上传成功：${escapeHtml(data.file?.name || file.name)}</p>`;
  } catch (e) {
    result.innerHTML = `<p class="errorText">${escapeHtml(e.message)}</p>`;
  } finally {
    document.getElementById('awrUploadInput').value = '';
  }
}

function renderOracleAnalysis(data) {
  const summary = data.parsed_summary || {};
  document.getElementById('oracleAnalysisResult').innerHTML = `
    <div class="reportSummary">
      <div><b>${summary.line_count || 0}</b><span>报告行数</span></div>
      <div><b>${summary.sections || 0}</b><span>解析章节</span></div>
      <div><b>${summary.tables || 0}</b><span>结构表格</span></div>
      <div><b>${escapeHtml(data.generated_at || '-')}</b><span>生成时间</span></div>
    </div>
    <div class="generatedPath"><b>源文件</b><span>${escapeHtml(data.source_file || '')}</span></div>
    <div class="generatedPath"><b>报告模板</b><span>${escapeHtml((data.template || {}).name || '未使用模板')}</span></div>
    <div class="generatedPath"><b>问题窗口</b><span>${escapeHtml((summary.windows || {})['问题时间窗口'] || '-')}</span></div>
    <div class="generatedPath"><b>对比窗口</b><span>${escapeHtml((summary.windows || {})['对比时间窗口'] || '-')}</span></div>
    <div class="panelActions">
      <a class="downloadButton" href="/download?path=${encodeURIComponent(data.word_path || '')}">下载 Word 报告</a>
      <a class="downloadButton" href="/download?path=${encodeURIComponent(data.markdown_path || '')}">下载 Markdown</a>
      <a class="downloadButton secondaryLink" href="/download?path=${encodeURIComponent(data.json_path || '')}">下载 JSON</a>
    </div>
    <div class="documentSummaryBlock">
      <h3>本地模型生成报告预览</h3>
      <pre class="reportPreview lightPreview">${escapeHtml(data.deepseek_answer || '')}</pre>
    </div>
  `;
}

function renderAwrSummaryResult(data) {
  document.getElementById('oracleAnalysisResult').innerHTML = `
    <div class="generatedPath"><b>源文件</b><span>${escapeHtml(data.source_file || '')}</span></div>
    <div class="generatedPath"><b>状态</b><span>${escapeHtml(data.message || 'AWR 分析完成')}</span></div>
    <div class="generatedPath"><b>本地模型</b><span>${escapeHtml(data.model || '-')}</span></div>
    <div class="generatedPath"><b>AWR 分析报告</b><span>${escapeHtml(data.markdown_path || '')}</span></div>
    <div class="generatedPath"><b>结构化摘要</b><span>${escapeHtml(data.summary_markdown_path || '')}</span></div>
    <div class="generatedPath"><b>规则发现</b><span>${escapeHtml(data.rule_findings_markdown_path || '')}</span></div>
    <div class="panelActions">
      <a class="downloadButton" href="/download?path=${encodeURIComponent(data.markdown_path || '')}">下载 AWR Markdown 分析报告</a>
      <a class="downloadButton secondaryLink" href="/download?path=${encodeURIComponent(data.summary_markdown_path || '')}">下载 awr_summary.md</a>
      <a class="downloadButton secondaryLink" href="/download?path=${encodeURIComponent(data.rule_findings_markdown_path || '')}">下载 awr_rule_findings.md</a>
      <a class="downloadButton secondaryLink" href="/download?path=${encodeURIComponent(data.json_path || '')}">下载 AWR JSON 分析结果</a>
    </div>
    <div class="documentSummaryBlock">
      <h3>本地模型生成报告预览</h3>
      <pre class="reportPreview lightPreview">${escapeHtml(data.deepseek_answer || '')}</pre>
    </div>
  `;
}

function renderAwrWordResult(data) {
  document.getElementById('oracleAnalysisResult').innerHTML = `
    <div class="generatedPath"><b>状态</b><span>${escapeHtml(data.message || 'Word 报告生成成功')}</span></div>
    <div class="generatedPath"><b>Markdown 报告</b><span>${escapeHtml(data.markdown_path || '')}</span></div>
    <div class="generatedPath"><b>Word 报告</b><span>${escapeHtml(data.word_path || '')}</span></div>
    <div class="panelActions">
      <a class="downloadButton" href="/download?path=${encodeURIComponent(data.word_path || '')}">下载 AWR Word 分析报告</a>
    </div>
  `;
}

async function analyzeOracleLst() {
  const result = document.getElementById('oracleAnalysisResult');
  const ep = getSelectedDsEndpoint();
  const modeSelect = document.getElementById('dsAnalysisMode');
  const selectedLabel = modeSelect ? (modeSelect.options[modeSelect.selectedIndex]?.text || '默认') : '默认';
  try {
    result.innerHTML = '<p class="hint">正在解析 .lst 并使用「' + selectedLabel + '」生成 Word 报告，复杂报告可能需要等待一段时间...</p>';
    const data = await postJson('/oracle/analyze', {
      use_latest: document.getElementById('oracleUseLatest').checked,
      lst_path: document.getElementById('oracleLstPath').value,
      template_path: document.getElementById('oracleReportTemplate').value,
      url: ep.url,
      model: ep.model,
      api_key: ep.api_key
    });
    renderOracleAnalysis(data);
  } catch (e) {
    result.innerHTML = `<p class="errorText">${escapeHtml(e.message)}</p>`;
  }
}

async function analyzeOracleAwr() {
  const result = document.getElementById('oracleAnalysisResult');
  const ep = getSelectedDsEndpoint();
  const modeSelect = document.getElementById('dsAnalysisMode');
  const selectedLabel = modeSelect ? (modeSelect.options[modeSelect.selectedIndex]?.text || '默认') : '默认';
  try {
    result.innerHTML = '<p class="hint">正在解析 AWR HTML，并使用「' + selectedLabel + '」生成分析报告...</p>';
    const data = await postJson('/oracle/analyze-awr', {
      awr_path: document.getElementById('oracleAwrPath').value.trim(),
      template_path: document.getElementById('oracleReportTemplate').value,
      url: ep.url,
      model: ep.model,
      api_key: ep.api_key
    });
    renderAwrSummaryResult(data);
  } catch (e) {
    result.innerHTML = `<p class="errorText">${escapeHtml(e.message)}</p>`;
  }
}

async function generateAwrWordReport() {
  const result = document.getElementById('oracleAnalysisResult');
  try {
    result.innerHTML = '<p class="hint">正在生成 AWR Word 分析报告...</p>';
    const data = await postJson('/oracle/awr-word-report', {});
    renderAwrWordResult(data);
  } catch (e) {
    result.innerHTML = `<p class="errorText">${escapeHtml(e.message)}</p>`;
  }
}

function toggleReportAi() {
  const enabled = document.getElementById('reportAiEnable').checked;
  const config = document.getElementById('reportAiConfig');
  config.style.display = enabled ? 'block' : 'none';
}

async function generateUnifiedReport() {
  const button = document.getElementById('reportGenerateBtn');
  const result = document.getElementById('reportResult');
  const aiEnabled = document.getElementById('reportAiEnable')?.checked;
  try {
    button.disabled = true;
    const label = aiEnabled ? '（AI 增强模式）' : '';
    result.innerHTML = '<p class="hint">正在读取 Excel 台账、查找交付文档并生成报告' + label + '...</p>';
    
    const payload = {
      report_type: selectedReportType(),
      ledger_path: document.getElementById('reportLedgerPath').value.trim(),
      document_root: document.getElementById('reportDocumentRoot').value.trim(),
      start_date: document.getElementById('reportStartDate').value,
      end_date: document.getElementById('reportEndDate').value
    };

    if (aiEnabled) {
      const ep = getSelectedDsEndpoint('reportDsMode');
      payload.url = ep.url;
      payload.model = ep.model;
      payload.api_key = ep.api_key;
    }

    const data = await postJson('/reports/generate', payload);
    renderReportResult(data, aiEnabled);
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

    // ── 自动执行脱敏 ──
    if (data.total > 0 && document.getElementById('autoRun')?.checked) {
      setStatus('扫描完成，自动执行脱敏...', 'neutral');
      await startJob();
    }
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

document.getElementById('awrUploadInput')?.addEventListener('change', event => {
  uploadSelectedAwrFile(event.target.files?.[0]);
});

document.querySelectorAll('.awrTab').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.awrTab').forEach(item => item.classList.remove('active'));
    document.querySelectorAll('.awrTabPanel').forEach(panel => panel.classList.remove('active'));
    button.classList.add('active');
    const tabName = button.dataset.awrTab;
    const target = document.getElementById('awrTab-' + tabName);
    if (target) target.classList.add('active');
  });
});

// ── 测试连接（本地或在线） ──
async function testDsConnection(mode) {
  const resultEl = document.getElementById('dsTestResult' + mode.charAt(0).toUpperCase() + mode.slice(1));
  const urlEl = document.getElementById(mode === 'local' ? 'dsLocalUrl' : 'dsOnlineUrl');
  const keyEl = document.getElementById('dsOnlineApiKey');
  const url = urlEl?.value?.trim();
  if (!url) {
    resultEl.style.display = 'block';
    resultEl.className = 'dsTestResult dsTestErr';
    resultEl.textContent = '⚠️ 请先填写接口地址';
    return;
  }
  resultEl.style.display = 'block';
  resultEl.className = 'dsTestResult dsTestWarn';
  resultEl.textContent = '⏳ 正在测试连接 ' + escapeHtml(url) + ' ...';
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (mode === 'online' && keyEl?.value?.trim()) {
      headers['Authorization'] = 'Bearer ' + keyEl.value.trim();
    }
    const res = await fetch(url, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ model: mode === 'local' ? '' : 'deepseek-chat', messages: [{ role: 'user', content: 'hi' }] })
    });
    if (res.ok || res.status === 400) {
      resultEl.className = 'dsTestResult dsTestOk';
      resultEl.textContent = '✅ 连接成功！服务可正常访问';
    } else {
      const errText = await res.text().catch(() => '');
      resultEl.className = 'dsTestResult dsTestErr';
      resultEl.textContent = '❌ 连接失败：HTTP ' + res.status + (errText ? ' - ' + errText.slice(0, 200) : '');
    }
  } catch (err) {
    resultEl.className = 'dsTestResult dsTestErr';
    resultEl.textContent = '❌ 无法连接：' + err.message;
  }
}

// ── 更新全局连接状态（基于当前激活面板） ──
function updateConnectionStatus() {
  const dot = document.getElementById('dsConnDot');
  const label = document.getElementById('dsConnLabel');
  const desc = document.getElementById('dsConnDesc');
  if (!dot || !label || !desc) return;
  const ep = getActiveDsEndpoint();
  if (!ep.url) {
    dot.className = 'dsConnDot dsConnOff';
    label.textContent = '未配置';
    desc.textContent = '请在当前激活面板中填写接口地址';
    return;
  }
  dot.className = 'dsConnDot dsConnUnknown';
  label.textContent = '检测中...';
  desc.textContent = '正在尝试连接 ' + escapeHtml(ep.url);
  const headers = { 'Content-Type': 'application/json' };
  if (ep.api_key) headers['Authorization'] = 'Bearer ' + ep.api_key;
  fetch(ep.url, { method: 'POST', headers: headers, body: JSON.stringify({ model: ep.model || '', messages: [] }) })
    .then(res => {
      if (res.ok || res.status === 400) {
        dot.className = 'dsConnDot dsConnOk';
        label.textContent = '已连接';
        desc.textContent = ep.url.includes('/api/chat') ? '本地 Ollama 服务可正常访问' : '在线 API 可正常访问';
      } else {
        dot.className = 'dsConnDot dsConnErr';
        label.textContent = '连接失败';
        desc.textContent = 'HTTP ' + res.status + '：' + res.statusText;
      }
    })
    .catch(err => {
      dot.className = 'dsConnDot dsConnErr';
      label.textContent = '无法连接';
      desc.textContent = err.message;
    });
}

// ── 事件绑定 ──
document.getElementById('dsLocalUrl')?.addEventListener('blur', updateConnectionStatus);
document.getElementById('dsLocalUrl')?.addEventListener('change', updateConnectionStatus);
document.getElementById('dsOnlineUrl')?.addEventListener('blur', updateConnectionStatus);
document.getElementById('dsOnlineUrl')?.addEventListener('change', updateConnectionStatus);
document.getElementById('dsAnalysisMode')?.addEventListener('change', updateConnectionStatus);

// 增强 loadOracleLstFiles 自动检测连接状态
const _origLoadOracleLstFiles = loadOracleLstFiles;
loadOracleLstFiles = function() {
  return _origLoadOracleLstFiles.apply(this, arguments).then(result => {
    setTimeout(updateConnectionStatus, 500);
    return result;
  }).catch(e => {
    setTimeout(updateConnectionStatus, 500);
    throw e;
  });
};

setReportDefaults();
loadOracleLstFiles();
loadDeepseekConfig();

// ── TFA 日志分析 ──
function chooseTfaUpload() {
  document.getElementById('tfaUploadInput').click();
}

async function uploadTfaZip(file) {
  if (!file) return;
  const result = document.getElementById('tfaResult');
  // ── 上传新文件时，清除旧的 job_id 和面板，避免显示过时结果 ──
  document.getElementById('tfaJobId').value = '';
  const tlBlock = document.getElementById('tfaTimelineBlock');
  if (tlBlock) tlBlock.style.display = 'none';
  const chBlock = document.getElementById('tfaChainBlock');
  if (chBlock) chBlock.style.display = 'none';
  try {
    const form = new FormData();
    form.append('tfa_file', file);
    result.innerHTML = '<p class="hint">正在上传 TFA zip 包...</p>';
    const res = await fetch('/tfa/upload', {method: 'POST', body: form});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '上传失败');
    document.getElementById('tfaZipPath').value = data.file_path || '';
    result.innerHTML = `<p class="hint">上传成功：${escapeHtml(data.file_name || file.name)}</p>`;
  } catch (e) {
    result.innerHTML = `<p class="errorText">${escapeHtml(e.message)}</p>`;
  } finally {
    document.getElementById('tfaUploadInput').value = '';
  }
}

function renderTfaResult(data) {
  const byCategory = data.by_category || {};
  const categories = Object.keys(byCategory);
  const categoryCards = categories.map(cat => {
    const items = byCategory[cat] || [];
    return `<div class="tfaEvidCard"><b>${escapeHtml(cat)}</b><span class="tfaEvidCount">${items.length} 条证据</span></div>`;
  }).join('');

  document.getElementById('tfaResult').innerHTML = `
    <div class="reportSummary">
      <div><b>${categories.length}</b><span>分析方向</span></div>
      <div><b>${data.evidence_count || 0}</b><span>证据条目</span></div>
      <div><b>${data.risk_high || 0}</b><span>高风险</span></div>
      <div><b>${data.risk_medium || 0}</b><span>中风险</span></div>
    </div>
    <div class="generatedPath"><b>源 zip 包</b><span>${escapeHtml(data.source_zip || '')}</span></div>
    <div class="generatedPath"><b>evidence.json</b><span>${escapeHtml(data.evidence_path || '')}</span></div>
    <div class="generatedPath"><b>领导汇报版</b><span>${escapeHtml(data.executive_path || '')}</span></div>
    <div class="generatedPath"><b>技术专家版</b><span>${escapeHtml(data.technical_path || '')}</span></div>
    <div class="panelActions">
      <a class="downloadButton" href="/download?path=${encodeURIComponent(data.evidence_path || '')}">下载 evidence.json</a>
      <a class="downloadButton" href="/download?path=${encodeURIComponent(data.executive_path || '')}">下载领导汇报版</a>
      <a class="downloadButton secondaryLink" href="/download?path=${encodeURIComponent(data.technical_path || '')}">下载技术专家版</a>
    </div>
    <div class="tfaCategorySummary">${categoryCards}</div>
  `;
}

let tfaPollTimer = null;

function renderTfaProgress(job) {
  const phase = job.phase || '';
  const message = job.message || '';
  const current = job.current || 0;
  const total = job.total || 100;
  const pct = total > 0 ? Math.round(current * 100 / total) : 0;

  const phaseLabels = {
    extract: '📦 解压 TFA zip',
    analyze: '🔍 规则分析',
    report: '📄 生成 Word 报告',
    done: '✅ 完成',
    error: '❌ 出错',
  };
  const phaseLabel = phaseLabels[phase] || '⏳ 处理中';

  let stepsHtml = '';
  const steps = [
    {key: 'extract', label: '解压 TFA zip'},
    {key: 'analyze', label: '扫描 & 规则分析'},
    {key: 'report', label: '生成 Word 报告'},
    {key: 'done', label: '完成'},
  ];
  const phases = ['extract', 'analyze', 'report', 'done'];
  const currentIdx = phases.indexOf(phase);
  stepsHtml = steps.map((s, i) => {
    let cls = 'tfaStep';
    if (i < currentIdx) cls += ' done';
    else if (i === currentIdx) cls += ' active';
    return `<div class="${cls}"><b>${i + 1}</b>${s.label}</div>`;
  }).join('');

  document.getElementById('tfaResult').innerHTML = `
    <div class="tfaSteps">${stepsHtml}</div>
    <div class="tfaProgressBlock">
      <div class="tfaProgressBar">
        <div class="tfaProgressFill" style="width:${Math.max(1, pct)}%"></div>
      </div>
      <div class="tfaProgressLabel">
        <b>${phaseLabel}</b>
        <span>${escapeHtml(message)}</span>
      </div>
      <div class="tfaProgressPct">${pct}%</div>
    </div>
  `;
}

async function pollTfaJob() {
  const tfaJobId = document.getElementById('tfaJobId')?.value;
  if (!tfaJobId) return;
  try {
    const res = await fetch('/tfa/status?job_id=' + encodeURIComponent(tfaJobId));
    const job = await res.json();
    if (!res.ok) throw new Error(job.error || '查询 TFA 状态失败');
    // ── 防止竞态：检查当前 job_id 是否还是最初请求的那个 ──
    const currentId = document.getElementById('tfaJobId')?.value;
    if (currentId !== tfaJobId) return; // 用户已经启动了新任务，忽略旧响应
    renderTfaProgress(job);
    if (job.status === 'done') {
      clearInterval(tfaPollTimer);
      tfaPollTimer = null;
      document.getElementById('tfaAnalyzeBtn').disabled = false;
      // 再次检查：停止计时器后确认 job_id 仍然匹配
      if (document.getElementById('tfaJobId')?.value !== tfaJobId) return;
      renderTfaResult(job.result || {});
    } else if (job.status === 'failed') {
      clearInterval(tfaPollTimer);
      tfaPollTimer = null;
      document.getElementById('tfaAnalyzeBtn').disabled = false;
      if (document.getElementById('tfaJobId')?.value !== tfaJobId) return;
      document.getElementById('tfaResult').innerHTML = `<p class="errorText">分析失败：${escapeHtml(job.error || job.message || '未知错误')}</p>`;
    }
  } catch (e) {
    // 不做太多处理，让下一次轮询再试
  }
}

function getTfaTimeFilter() {
  const active = document.querySelector('#tfaTimeFilterOptions .tfaTimeOption.active');
  if (!active) return {};
  const mode = active.dataset.mode;
  if (mode === 'today') {
    return { time_filter_days: 1 };
  } else if (mode === 'custom') {
    const start = document.getElementById('tfaDateStart').value;
    const end = document.getElementById('tfaDateEnd').value;
    if (start && end) {
      return { time_start: start, time_end: end };
    }
    if (start && !end) {
      return { time_start: start, time_end: start };
    }
    return {};
  }
  // mode === 'all' — 不限时间：不传时间参数，但标记 first_match_only
  return { first_match_only: true };
}

async function analyzeTfa() {
  const btn = document.getElementById('tfaAnalyzeBtn');
  const result = document.getElementById('tfaResult');
  // ── 清除上一轮的旧面板（时间线 + 分析链），避免用户看到过时数据 ──
  const tlBlock = document.getElementById('tfaTimelineBlock');
  if (tlBlock) tlBlock.style.display = 'none';
  const chBlock = document.getElementById('tfaChainBlock');
  if (chBlock) chBlock.style.display = 'none';
  // ── 停止上一轮的旧轮询，避免旧 job 完成时覆盖新结果 ──
  if (tfaPollTimer) {
    clearInterval(tfaPollTimer);
    tfaPollTimer = null;
  }
  try {
    btn.disabled = true;
    const filter = getTfaTimeFilter();
    let msg = '';
    if (filter.time_filter_days) {
      msg = '（仅分析当天数据）';
    } else if (filter.time_start && filter.time_end) {
      msg = `（${filter.time_start} → ${filter.time_end}）`;
    } else if (filter.first_match_only) {
      msg = '（不限时间，找到第一个问题即停止分析）';
    } else {
      msg = '（全量数据，不过滤时间）';
    }
    result.innerHTML = `<p class="hint">正在启动 TFA 分析任务 ${msg}...</p>`;
    const data = await postJson('/tfa/analyze', {
      zip_path: document.getElementById('tfaZipPath').value.trim(),
      ...filter,
    });
    document.getElementById('tfaJobId').value = data.job_id;
    renderTfaProgress({phase: 'extract', message: '等待分析引擎启动...', current: 0, total: 100});
    tfaPollTimer = setInterval(pollTfaJob, 500);
    pollTfaJob();
  } catch (e) {
    result.innerHTML = `<p class="errorText">${escapeHtml(e.message)}</p>`;
    btn.disabled = false;
  }
}

function setupTfaTimeFilter() {
  const options = document.querySelectorAll('#tfaTimeFilterOptions .tfaTimeOption');
  const customRow = document.getElementById('tfaCustomDateRow');
  const today = new Date();
  const todayStr = today.toISOString().slice(0, 10);
  document.getElementById('tfaDateStart').value = todayStr;
  document.getElementById('tfaDateEnd').value = todayStr;

  options.forEach(opt => {
    opt.addEventListener('click', () => {
      options.forEach(o => o.classList.remove('active'));
      opt.classList.add('active');
      if (opt.dataset.mode === 'custom') {
        customRow.style.display = 'block';
      } else {
        customRow.style.display = 'none';
      }
    });
  });
}

document.getElementById('tfaUploadInput')?.addEventListener('change', event => {
  uploadTfaZip(event.target.files?.[0]);
});

// 初始化 TFA 时间过滤器
setupTfaTimeFilter();

// ── TFA 故障时间线 ──

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>').replace(/"/g,'"');
}

function fmtTime(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    const y = d.getFullYear();
    const mo = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    const s = String(d.getSeconds()).padStart(2, '0');
    return `${y}-${mo}-${dd} ${h}:${mi}:${s}`;
  } catch { return isoStr; }
}

function fmtShortTime(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    const mo = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    return `${mo}-${dd} ${h}:${mi}`;
  } catch { return isoStr; }
}

function severityLabel(sev) {
  const map = {critical: '严重', high: '高', medium: '中', low: '低', info: '信息'};
  return map[sev] || sev;
}

function renderSvgTimeline(clusters) {
  if (!clusters || clusters.length === 0) {
    return '<p style="color:#6b7280;font-size:13px;text-align:center;padding:20px 0;">暂无故障时间线数据</p>';
  }

  // 计算时间范围
  let minT = Infinity, maxT = -Infinity;
  clusters.forEach(c => {
    if (c.start_time) { const t = new Date(c.start_time).getTime(); if (t < minT) minT = t; }
    if (c.end_time) { const t = new Date(c.end_time).getTime(); if (t > maxT) maxT = t; }
  });
  if (minT === Infinity || maxT === -Infinity) return '';
  const range = maxT - minT || 1;
  const padding = range * 0.05;
  const xMin = minT - padding;
  const xMax = maxT + padding;
  const totalWidth = xMax - xMin;

  const svgW = Math.max(600, clusters.length * 180);
  const svgH = 80;
  const yLine = 35;

  // 生成颜色映射
  const sevColors = {critical: '#7f1d1d', high: '#dc2626', medium: '#f59e0b', low: '#3b82f6', info: '#9ca3af'};

  let dotsHtml = '';
  clusters.forEach((c, i) => {
    const t = new Date(c.start_time).getTime();
    const x = ((t - xMin) / totalWidth) * svgW;
    const color = sevColors[c.severity] || '#9ca3af';
    const label = fmtShortTime(c.start_time);
    dotsHtml += `<circle cx="${x}" cy="${yLine}" r="7" fill="${color}" stroke="white" stroke-width="2" onclick="event.target.closest('.tfaClusterCard')?.querySelector('.tfaClusterHeader')?.click()" style="cursor:pointer" />`;
    dotsHtml += `<text x="${x}" y="${yLine - 14}" text-anchor="middle" font-size="10" fill="#6b7280">${escapeHtml(label)}</text>`;
  });

  return `<svg class="tfaTimelineSvg" viewBox="0 0 ${svgW} ${svgH}" xmlns="http://www.w3.org/2000/svg">
    <line x1="20" y1="${yLine}" x2="${svgW - 20}" y2="${yLine}" stroke="#d1d5db" stroke-width="2" stroke-dasharray="4,4" />
    ${dotsHtml}
  </svg>`;
}

function renderClusterCard(cluster) {
  const sevColors = {critical: '#7f1d1d', high: '#dc2626', medium: '#f59e0b', low: '#3b82f6', info: '#9ca3af'};
  const sevColor = sevColors[cluster.severity] || '#9ca3af';

  // 事件列表
  let eventsHtml = '<ul class="tfaTimelineEvents">';
  (cluster.events || []).forEach(ev => {
    eventsHtml += `<li>
      <span class="evTime">${escapeHtml(fmtTime(ev.time))}</span>
      <span class="evSeverity ${ev.severity}">${severityLabel(ev.severity)}</span>
      <span class="evContent">
        <b>${escapeHtml(ev.rule_id)}</b>
        ${escapeHtml(ev.description || '').slice(0, 120)}
        <span style="display:block;font-size:10px;color:#9ca3af;font-family:monospace;">${escapeHtml(ev.source_file || '')}</span>
      </span>
    </li>`;
  });
  eventsHtml += '</ul>';

  // 关联快照
  let snapHtml = '';
  const snaps = cluster.related_snapshots || [];
  if (snaps.length > 0) {
    snapHtml = `<details class="tfaRelatedSnapshots">
      <summary>📁 关联快照文件（${snaps.length}）</summary>
      <div class="snapFiles">`;
    snaps.forEach(s => {
      snapHtml += `<span class="snapFileTag">${escapeHtml(s.file || s.filename || '')}</span>`;
    });
    snapHtml += `</div></details>`;
  }

  // 源文件列表
  const srcFiles = cluster.source_files || [];
  let srcHtml = '';
  if (srcFiles.length > 0) {
    srcHtml = `<details class="tfaRelatedSnapshots">
      <summary>📄 涉及文件（${srcFiles.length}）</summary>
      <div class="snapFiles">`;
    srcFiles.forEach(f => {
      srcHtml += `<span class="snapFileTag">${escapeHtml(f)}</span>`;
    });
    srcHtml += `</div></details>`;
  }

  const cid = 'cluster-' + (cluster.cluster_id || 0);

  return `<div class="tfaClusterCard" id="${cid}">
    <div class="tfaClusterHeader" onclick="toggleTfaCluster('${cid}')">
      <span class="severityDot ${cluster.severity}"></span>
      <span class="tfaClusterTitle">${escapeHtml(cluster.title || '故障簇')}</span>
      <span class="tfaClusterMeta">
        <span>${escapeHtml(fmtTime(cluster.start_time))} → ${escapeHtml(fmtTime(cluster.end_time))}</span>
        <span class="tag">${cluster.event_count} 事件</span>
        <span class="tag" style="background:${sevColor};color:white;">${severityLabel(cluster.severity)}</span>
      </span>
      <span style="font-size:16px;color:#9ca3af;">▸</span>
    </div>
    <div class="tfaClusterBody">
      <div class="tfaRootCause">
        <b>🔍 根因</b>
        <p><strong>${escapeHtml(cluster.root_cause?.rule_id || '')}</strong> ${escapeHtml(cluster.root_cause?.description || '')}</p>
        <p style="margin-top:4px;font-size:11px;color:#6b7280;">
          时间: ${escapeHtml(fmtTime(cluster.root_cause?.time) || '')}
          <span style="display:block;font-family:monospace;">来源: ${escapeHtml(cluster.root_cause?.source_file || '')}</span>
        </p>
      </div>
      ${eventsHtml}
      ${srcHtml}
      ${snapHtml}
    </div>
  </div>`;
}

function toggleTfaCluster(clusterId) {
  const card = document.getElementById(clusterId);
  if (!card) return;
  const body = card.querySelector('.tfaClusterBody');
  if (body) body.classList.toggle('open');
}

async function loadTfaTimeline() {
  const tfaJobId = document.getElementById('tfaJobId')?.value;
  if (!tfaJobId) return;
  try {
    const res = await fetch('/tfa/timeline?job_id=' + encodeURIComponent(tfaJobId));
    const data = await res.json();
    if (!res.ok) return;
    renderTfaTimeline(data);
  } catch (e) {
    console.warn('加载时间线失败:', e);
  }
}

function renderTfaTimeline(data) {
  const block = document.getElementById('tfaTimelineBlock');
  if (!block) return;
  const clusters = data.fault_clusters || [];
  const meta = data.metadata || {};

  if (!clusters || clusters.length === 0) {
    block.style.display = 'none';
    return;
  }

  block.style.display = 'block';

  // Badge
  document.getElementById('tfaTimelineBadge').textContent = clusters.length + ' 簇';

  // Summary
  const summary = document.getElementById('tfaTimelineSummary');
  const sev = meta.severity_summary || {};
  summary.innerHTML = `
    <div><b>${meta.clusters_found || clusters.length}</b><span>故障簇</span></div>
    <div><b>${sev.critical || 0}</b><span>严重</span></div>
    <div><b>${sev.high || 0}</b><span>高</span></div>
    <div><b>${sev.medium || 0}</b><span>中</span></div>
    <div><b>${meta.total_evidence || 0}</b><span>证据总数</span></div>
    <div><b>${meta.files_analyzed || 0}</b><span>文件数</span></div>
  `;

  // SVG Timeline
  document.getElementById('tfaTimelineCanvas').innerHTML = renderSvgTimeline(clusters);

  // Cluster cards
  const list = document.getElementById('tfaClusterList');
  list.innerHTML = clusters.map(c => renderClusterCard(c)).join('');

  // 自动展开第一个
  const firstCard = list.querySelector('.tfaClusterCard');
  if (firstCard) {
    const body = firstCard.querySelector('.tfaClusterBody');
    if (body) body.classList.add('open');
  }
}

// Patch: 在 renderTfaResult 完成后自动调用 loadTfaTimeline 和 loadTfaChains
const _origRenderTfaResult2 = renderTfaResult;
renderTfaResult = function(data) {
  _origRenderTfaResult2(data);
  setTimeout(() => {
    loadTfaTimeline();
    loadTfaChains();
  }, 100);
};

// ── 分析链看板 ──

function escapeChainHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>').replace(/"/g,'"');
}

function fmtChainTime(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    const y = d.getFullYear();
    const mo = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    return `${y}-${mo}-${dd} ${h}:${mi}`;
  } catch { return isoStr; }
}

function chainSevColor(sev) {
  const map = {critical: '#7f1d1d', high: '#dc2626', medium: '#f59e0b', low: '#3b82f6', info: '#9ca3af'};
  return map[sev] || '#9ca3af';
}

function chainSevLabel(sev) {
  const map = {critical: '严重', high: '高', medium: '中', low: '低', info: '信息'};
  return map[sev] || sev;
}

function fmtTimeGap(a, b) {
  if (!a || !b) return '';
  const diffSec = Math.round((new Date(b) - new Date(a)) / 1000);
  if (diffSec <= 0) return '';
  if (diffSec < 60) return `+${diffSec}s`;
  const min = Math.floor(diffSec / 60);
  const sec = diffSec % 60;
  if (min < 60) return sec ? `+${min}m ${sec}s` : `+${min}m`;
  const hr = Math.floor(min / 60);
  const rm = min % 60;
  if (hr < 24) return rm ? `+${hr}h ${rm}m` : `+${hr}h`;
  const day = Math.floor(hr / 24);
  const rh = hr % 24;
  return rh ? `+${day}d ${rh}h` : `+${day}d`;
}

function fmtStepGap(before, after) {
  if (!before || !after) return '';
  const diffSec = Math.round((new Date(after) - new Date(before)) / 1000);
  if (diffSec <= 0) return '';
  if (diffSec < 60) return `+${diffSec}s`;
  const min = Math.floor(diffSec / 60);
  const sec = diffSec % 60;
  if (min < 60) return sec ? `+${min}m ${sec}s` : `+${min}m`;
  const hr = Math.floor(min / 60);
  const rm = min % 60;
  if (hr < 24) return rm ? `+${hr}h ${rm}m` : `+${hr}h`;
  return `${Math.floor(hr / 24)}d`;
}

function renderChainSvgOverview(chains) {
  if (!chains || chains.length === 0) return '';
  const svgW = Math.max(600, chains.length * 200);
  const svgH = 160;
  const yLine = 55;

  let html = `<svg class="tfaChainSvg" viewBox="0 0 ${svgW} ${svgH}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <marker id="chainArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#6366f1"/></marker>
    </defs>
    <line x1="30" y1="${yLine}" x2="${svgW - 30}" y2="${yLine}" stroke="#e0e7ff" stroke-width="2" stroke-dasharray="4,4"/>`;

  chains.forEach((chain, i) => {
    const label = chain.entry_label || '入口';
    const color = chainSevColor(chain.severity);
    const x = 30 + (i * (svgW - 60) / Math.max(chains.length - 1, 1));
    const y = yLine;
    const tStart = chain.time_range ? fmtChainTime(chain.time_range.start) : '';
    const tEnd = chain.time_range ? fmtChainTime(chain.time_range.end) : '';
    // 计算链内时间跨度
    const tlEvents = chain.chain_timeline || [];
    const chainSpan = tlEvents.length >= 2 ? fmtTimeGap(tlEvents[0].time, tlEvents[tlEvents.length - 1].time) : '';

    html += `<circle cx="${x}" cy="${y}" r="12" fill="${color}" stroke="white" stroke-width="3" style="cursor:pointer" onclick="document.querySelectorAll('.tfaChainCard')[${i}]?.scrollIntoView({behavior:'smooth',block:'start'});"/>`;
    html += `<text x="${x}" y="${y - 22}" text-anchor="middle" font-size="11" font-weight="600" fill="#374151">${escapeChainHtml(label.slice(0, 14))}</text>`;
    html += `<text x="${x}" y="${y + 24}" text-anchor="middle" font-size="10" fill="${color}" font-weight="600">${chainSevLabel(chain.severity)}</text>`;
    if (tStart) {
      html += `<text x="${x}" y="${y + 42}" text-anchor="middle" font-size="10" fill="#6b7280" font-weight="500">⏱ ${escapeChainHtml(tStart)}</text>`;
    }
    if (chainSpan) {
      html += `<text x="${x}" y="${y + 58}" text-anchor="middle" font-size="9" fill="#9ca3af">跨度 ${escapeChainHtml(chainSpan)}</text>`;
    }
    if (tEnd && tEnd !== tStart) {
      html += `<text x="${x}" y="${y + 72}" text-anchor="middle" font-size="9" fill="#9ca3af">~ ${escapeChainHtml(tEnd)}</text>`;
    }

    if (i < chains.length - 1) {
      const x2 = 30 + ((i + 1) * (svgW - 60) / Math.max(chains.length - 1, 1));
      html += `<line x1="${x + 14}" y1="${y}" x2="${x2 - 14}" y2="${y}" stroke="#6366f1" stroke-width="2" marker-end="url(#chainArrow)"/>`;
    }
  });

  html += '</svg>';
  return html;
}

function renderChainCard(chain, index) {
  const color = chainSevColor(chain.severity);

  const entryFilesHtml = (chain.entry_files || []).map(f =>
    `<span class="tfaChainFileTag">${escapeChainHtml(f)}</span>`
  ).join('');

  const rulesHtml = (chain.rules_involved || []).map(r => {
    const rc = chainSevColor(r.severity);
    return `<span class="tfaChainRuleTag" style="border-color:${rc};color:${rc};">${escapeChainHtml(r.rule_id)}: ${escapeChainHtml(r.title)}</span>`;
  }).join('');

  let fileDetailsHtml = '<div class="tfaChainEvidenceSection">';
  (chain.file_details || []).forEach(fd => {
    const evItems = (fd.evidence_items || []).map(ev => {
      const ec = chainSevColor(ev.severity);
      return `<div class="tfaChainEvItem">
        <span class="tfaChainEvSev" style="background:${ec};">${chainSevLabel(ev.severity)}</span>
        <b>${escapeChainHtml(ev.rule_id)}</b>
        <span class="tfaChainEvDesc">${escapeChainHtml((ev.description || '').slice(0, 100))}</span>
        <span class="tfaChainEvTime">${escapeChainHtml(fmtChainTime(ev.discovered_at))}</span>
      </div>`;
    }).join('');
    // 计算文件内证据的时间范围
    const fdTimes = (fd.evidence_items || []).map(ev => ev.discovered_at).filter(Boolean).sort();
    const fdTimeStr = fdTimes.length > 0
      ? `<span class="tfaChainFileTime">${escapeChainHtml(fmtChainTime(fdTimes[0]))}${fdTimes.length > 1 ? ' ~ ' + escapeChainHtml(fmtChainTime(fdTimes[fdTimes.length - 1])) : ''}</span>`
      : '';
    fileDetailsHtml += `
      <details class="tfaChainFileDetail" ${index === 0 ? 'open' : ''}>
        <summary><span class="tfaChainFileIcon">📄</span> ${escapeChainHtml(fd.file)} <span class="tfaChainEvCount">${fd.evidence_count} 条证据</span> ${fdTimeStr}</summary>
        ${evItems || '<p class="hint" style="margin:4px 0 0 16px;">无具体证据条目</p>'}
      </details>`;
  });
  fileDetailsHtml += '</div>';

  let snapHtml = '';
  const snaps = chain.related_snapshots || [];
  if (snaps.length > 0) {
    snapHtml = `<details class="tfaChainSnapSection">
      <summary>📁 交叉验证快照（${snaps.length}）</summary>
      <div class="tfaChainSnapList">`;
    const seenSnapCats = new Set();
    snaps.forEach(s => {
      const cat = s.category || '';
      if (!seenSnapCats.has(cat)) {
        seenSnapCats.add(cat);
        snapHtml += `<span class="tfaChainSnapCatTag" title="${escapeChainHtml(s.file)}">${escapeChainHtml(cat)}</span>`;
      }
    });
    snapHtml += `</div></details>`;
  }

  let relEvHtml = '';
  const relEv = chain.related_evidence || [];
  if (relEv.length > 0) {
    relEvHtml = `<details class="tfaChainRelEvSection">
      <summary>🔗 跨文件关联证据（${relEv.length}）</summary>
      <div class="tfaChainRelEvList">`;
    relEv.slice(0, 10).forEach(ev => {
      relEvHtml += `<div class="tfaChainRelEvItem">
        <span class="tfaChainRelEvSev ${ev.severity}">${chainSevLabel(ev.severity)}</span>
        <b>${escapeChainHtml(ev.rule_id)}</b>
        <span>${escapeChainHtml((ev.description || '').slice(0, 80))}</span>
        <span class="tfaChainRelEvTime">${escapeChainHtml(fmtChainTime(ev.discovered_at))}</span>
      </div>`;
    });
    if (relEv.length > 10) {
      relEvHtml += `<p class="hint" style="margin:4px 0 0 0;">...还有 ${relEv.length - 10} 条</p>`;
    }
    relEvHtml += `</div></details>`;
  }

  // ── 文件审计步骤链（将 analysis_steps 渲染为可视化步骤） ──
  const steps = chain.analysis_steps || [];
  let stepsHtml = '';
  if (steps.length > 0) {
    const actionColors = {
      entry_scan: '#6366f1', rule_hit: '#dc2626', cross_validate: '#f59e0b',
      correlation: '#3b82f6', root_cause: '#16a34a', conclusion: '#6b7280',
    };

    // 计算所有步骤的时间范围（用于时间比例条）
    const stepTimes = steps.map(s => s.time_ref ? new Date(s.time_ref).getTime() : null).filter(t => t !== null);
    const timeMin = stepTimes.length > 0 ? Math.min(...stepTimes) : 0;
    const timeMax = stepTimes.length > 0 ? Math.max(...stepTimes) : 0;
    const timeSpan = (timeMax - timeMin) || 1;

    // 构建时间比例条 HTML（只在有 2+ 个时间戳时展示）
    let timeBarHtml = '';
    if (stepTimes.length >= 2) {
      const barSegments = steps.map((s, i) => {
        const t = s.time_ref ? new Date(s.time_ref).getTime() : null;
        if (t === null) return '';
        const pct = ((t - timeMin) / timeSpan) * 100;
        const ac = actionColors[s.action] || '#9ca3af';
        return `<div class="tfaChainTimeBarSeg" style="left:${pct.toFixed(1)}%;background:${ac}" title="步骤 ${s.step}: ${escapeChainHtml(s.action_label)} @ ${escapeChainHtml(fmtChainTime(s.time_ref))}"></div>`;
      }).join('');
      const startLabel = fmtChainTime(steps.find(s => s.time_ref)?.time_ref || '');
      const endLabel = fmtChainTime(steps.filter(s => s.time_ref).pop()?.time_ref || '');
      timeBarHtml = `<div class="tfaChainTimeBar"><div class="tfaChainTimeBarTrack">${barSegments}</div><div class="tfaChainTimeBarLabels"><span>${escapeChainHtml(startLabel)}</span><span>${escapeChainHtml(endLabel)}</span></div></div>`;
    }

    // 每个步骤的上一个有效时间（用于计算间隔）
    let prevTimeRef = null;

    const stepItems = steps.map(s => {
      const ac = actionColors[s.action] || '#9ca3af';

      // 步骤时间差
      const gapStr = s.time_ref && prevTimeRef ? fmtTimeGap(prevTimeRef, s.time_ref) : '';
      if (s.time_ref) prevTimeRef = s.time_ref;

      let targetFilesHtml = '';
      if (s.target_files && s.target_files.length > 0) {
        targetFilesHtml = `<div class="tfaChainStepFiles">${s.target_files.map(f => `<span class="tfaChainStepFileTag">${escapeChainHtml(f)}</span>`).join('')}</div>`;
      }
      let metaHtml = '';
      if (s.rule_id) {
        const sc = chainSevColor(s.severity || 'info');
        metaHtml += `<span class="tfaChainStepMeta" style="color:${sc}">${escapeChainHtml(s.rule_id)}</span>`;
      }
      if (s.ev_count !== undefined) {
        metaHtml += `<span class="tfaChainStepMeta hint">${s.ev_count} 条证据</span>`;
      }
      if (s.snapshot_count !== undefined) {
        metaHtml += `<span class="tfaChainStepMeta hint">${s.snapshot_count} 个快照</span>`;
      }
      if (s.evidence_count !== undefined) {
        metaHtml += `<span class="tfaChainStepMeta hint">${s.evidence_count} 条关联</span>`;
      }
      if (s.correlation_guide) {
        metaHtml += `<span class="tfaChainStepMeta tfaChainStepMethod" style="border:1px solid #3b82f6;color:#3b82f6" title="${escapeChainHtml(s.correlation_guide)}">🔗 关联链</span>`;
      }
      if (s.known_rules && s.known_rules.length > 0) {
        metaHtml += s.known_rules.map(rid => `<span class="tfaChainStepMeta" style="color:#6366f1">${escapeChainHtml(rid)}</span>`).join('');
      }
      if (s.severity && s.action === 'conclusion') {
        metaHtml += `<span class="tfaChainStepMeta tfaChainStepSev" style="background:${chainSevColor(s.severity)}">${chainSevLabel(s.severity)}</span>`;
      }
      if (s.rc_confidence) {
        const confColor = {high: '#16a34a', medium: '#f59e0b', low: '#9ca3af'};
        metaHtml += `<span class="tfaChainStepMeta tfaChainStepConf" style="background:${confColor[s.rc_confidence] || '#9ca3af'}">可信度 ${escapeChainHtml(s.rc_confidence)}</span>`;
      }
      if (s.file_count !== undefined) {
        metaHtml += `<span class="tfaChainStepMeta hint">${s.file_count} 个文件</span>`;
      }
      if (s.what_to_look_for) {
        metaHtml += `<span class="tfaChainStepMeta tfaChainStepMethod" title="${escapeChainHtml(s.what_to_look_for)}" style="border:1px solid ${ac};color:${ac}">🔍 查</span>`;
      }

      // 增强时间显示：大号 badge + 间隔
      const timeRefBadge = s.time_ref ? `<span class="tfaChainStepTimeBadge" style="--badge-color:${ac}"><span class="tfaChainStepTimeIcon">⏱</span><span class="tfaChainStepTimeVal">${escapeChainHtml(fmtChainTime(s.time_ref))}</span></span>` : '';
      const gapBadge = gapStr ? `<span class="tfaChainStepGap">${gapStr}</span>` : '';

      return `<div class="tfaChainStepItem" style="--step-color:${ac}">
        <div class="tfaChainStepDot" style="background:${ac}"><span class="tfaChainStepNum">${s.step}</span></div>
        <div class="tfaChainStepContent">
          <div class="tfaChainStepHead">
            <span class="tfaChainStepIcon">${s.action_icon || ''}</span>
            <span class="tfaChainStepLabel" style="color:${ac}">${escapeChainHtml(s.action_label)}</span>
            ${metaHtml}
          </div>
          <div class="tfaChainStepTimeRow">${timeRefBadge}${gapBadge}</div>
          <div class="tfaChainStepDetail">${escapeChainHtml(s.detail)}</div>
          ${s.what_to_look_for ? `<div class="tfaChainStepExtraRow"><span class="tfaChainStepExtraLabel">🔍 查找:</span><span class="tfaChainStepExtraVal">${escapeChainHtml(s.what_to_look_for)}</span></div>` : ''}
          ${s.analysis_action ? `<div class="tfaChainStepExtraRow"><span class="tfaChainStepExtraLabel">⚙️ 分析:</span><span class="tfaChainStepExtraVal">${escapeChainHtml(s.analysis_action)}</span></div>` : ''}
          ${targetFilesHtml}
        </div>
      </div>`;
    }).join('');
    stepsHtml = `<div class="tfaChainStepsSection">
      ${timeBarHtml}
      <div class="tfaChainStepsList">${stepItems}</div>
    </div>`;
  }

  const timeStr = chain.time_range && (chain.time_range.start || chain.time_range.end) ?
    `${escapeChainHtml(fmtChainTime(chain.time_range.start))} → ${escapeChainHtml(fmtChainTime(chain.time_range.end))}` : '';

  // ── 根因看板（新） ──
  const rc = chain.root_cause;
  let rootCauseHtml = '';
  if (rc && rc.summary) {
    const confLabel = {high: '高', medium: '中', low: '低'};
    const confColor = {high: '#16a34a', medium: '#f59e0b', low: '#9ca3af'};
    // 根因时间：取时间线最早事件时间
    const tlEvents = chain.chain_timeline || [];
    const rcTimeStr = tlEvents.length > 0 ? fmtChainTime(tlEvents[0].time) : (chain.time_range ? fmtChainTime(chain.time_range.start) : '');
    rootCauseHtml = `<div class="tfaChainRcSection">
      <div class="tfaChainRcHeader" onclick="event.stopPropagation();this.parentElement.classList.toggle('collapsed')">
        <span class="tfaChainRcIcon">🔍</span>
        <div class="tfaChainRcSummary">
          <b>根因推断</b>
          <span>${escapeChainHtml(rc.summary)}</span>
          ${rcTimeStr ? `<span class="tfaChainRcTime">⏱ ${escapeChainHtml(rcTimeStr)}</span>` : ''}
        </div>
        <span class="tfaChainRcConf" style="background:${confColor[rc.confidence] || '#9ca3af'}">可信度 ${confLabel[rc.confidence] || rc.confidence}</span>
        <span class="tfaChainToggle" style="margin-left:8px;">▸</span>
      </div>
      ${rc.detail ? `<div class="tfaChainRcDetail">${escapeChainHtml(rc.detail)}</div>` : ''}
      ${rc.key_rules && rc.key_rules.length > 0 ? `<div class="tfaChainRcRules"><b>关键规则：</b>${rc.key_rules.map(r => `<code>${escapeChainHtml(r)}</code>`).join(' ')}</div>` : ''}
    </div>`;
  }

  // ── 事件时间线（新） ──
  const tl = chain.chain_timeline || [];
  let timelineHtml = '';
  if (tl.length > 1) {
    let tlPrevTime = null;
    const tlItems = tl.slice(0, 15).map((e, i) => {
      const ec = chainSevColor(e.severity);
      const typeIcon = e.type === 'entry' ? '🔹' : '🔸';
      // 事件间时间间隔
      const tlGap = e.time && tlPrevTime ? fmtTimeGap(tlPrevTime, e.time) : '';
      if (e.time) tlPrevTime = e.time;
      return `<div class="tfaChainTlItem">
        <div class="tfaChainTlDot" style="background:${ec}"></div>
        <div class="tfaChainTlContent">
          <div class="tfaChainTlHead">
            <span class="tfaChainTlStep">步骤 ${e.step}</span>
            <span class="tfaChainTlTimeBadge">${escapeChainHtml(fmtChainTime(e.time))}</span>
            ${tlGap ? `<span class="tfaChainTlGap">${escapeChainHtml(tlGap)}</span>` : ''}
            <span class="tfaChainTlSev" style="color:${ec}">${chainSevLabel(e.severity)}</span>
            <span class="tfaChainTlType">${typeIcon} ${e.type === 'entry' ? '入口文件' : '关联文件'}</span>
          </div>
          <div class="tfaChainTlBody">
            <b>${escapeChainHtml(e.rule_id)}</b>
            <span>${escapeChainHtml((e.description || '').slice(0, 120))}</span>
            <span class="tfaChainTlFile">${escapeChainHtml(e.source_file || '')}</span>
          </div>
          ${e.log_snippet ? `<pre class="tfaChainTlLog" onclick="this.classList.toggle('expanded')"><code>${escapeChainHtml(e.log_snippet.slice(0, 300))}</code></pre>` : ''}
        </div>
      </div>`;
    }).join('');
    if (tl.length > 15) tlItems += `<p class="hint" style="margin:8px 0 0 0;">...还有 ${tl.length - 15} 条事件</p>`;
    timelineHtml = `<details class="tfaChainTlSection" open>
      <summary>⏱ 事件时间线（${tl.length} 个事件）${tl.length >= 2 ? ' · 跨度 ' + escapeChainHtml(fmtTimeGap(tl[0].time, tl[tl.length - 1].time)) : ''}</summary>
      <div class="tfaChainTlList">${tlItems}</div>
    </details>`;
  }

  // ── 日志查看面板（新）- 所有证据项的日志片段 ──
  let logViewerHtml = '';
  const allLogLines = [];
  (chain.file_details || []).forEach(fd => {
    (fd.evidence_items || []).forEach(ev => {
      const lines = ev.log_lines || [];
      if (lines.length > 0) {
        allLogLines.push({
          file: fd.file,
          rule_id: ev.rule_id,
          severity: ev.severity,
          lines: lines,
          line_number: ev.line_number || 0,
          discovered_at: ev.discovered_at,
        });
      }
    });
  });
  if (allLogLines.length > 0) {
    const logPanels = allLogLines.slice(0, 5).map(lg => {
      const ec = chainSevColor(lg.severity);
      const lineCodes = lg.lines.map((ln, li) => `<span class="tfaChainLogLine">${lg.line_number ? `<span class="tfaChainLogLineNo">${lg.line_number + li}</span>` : ''}<span class="tfaChainLogText">${escapeChainHtml(ln.slice(0, 200))}</span></span>`).join('');
      return `<div class="tfaChainLogPanel">
        <div class="tfaChainLogHeader">
          <span class="tfaChainLogRule" style="color:${ec}">${escapeChainHtml(lg.rule_id)}</span>
          <span class="tfaChainLogFile">${escapeChainHtml(lg.file)}</span>
          <span class="tfaChainLogTime">${escapeChainHtml(fmtChainTime(lg.discovered_at))}</span>
        </div>
        <pre class="tfaChainLogContent"><code>${lineCodes}</code></pre>
      </div>`;
    }).join('');
    logViewerHtml = `<details class="tfaChainLogSection">
      <summary>📄 日志查看器（${allLogLines.length} 段）</summary>
      <div class="tfaChainLogList">${logPanels}</div>
    </details>`;
  }

  return `<div class="tfaChainCard" style="border-left-color:${color}">
    <div class="tfaChainCardHeader" onclick="toggleTfaChain(this)">
      <div class="tfaChainCardTitleRow">
        <span class="tfaChainLabel">${escapeChainHtml(chain.entry_label)}</span>
        <span class="tfaChainSevBadge" style="background:${color};">${chainSevLabel(chain.severity)}</span>
        <span class="tfaChainCounts">
          <span title="证据数量">📋 ${chain.evidence_count}</span>
          <span title="规则数量">⚙️ ${(chain.rules_involved || []).length}</span>
          <span title="事件时间线">⏱ ${(chain.chain_timeline || []).length}</span>
          <span title="关联快照">📁 ${(chain.related_snapshots || []).length}</span>
        </span>
      </div>
      ${timeStr ? `<div class="tfaChainTime">${timeStr}</div>` : ''}
      <span class="tfaChainToggle">▸</span>
    </div>
    <div class="tfaChainCardBody">
      ${stepsHtml}
      ${rootCauseHtml}
      <div class="tfaChainDivider"></div>
      <div class="tfaChainFilesRow">
        <b>入口文件</b>
        <div>${entryFilesHtml}</div>
      </div>
      <div class="tfaChainRulesRow">
        <b>命中规则</b>
        <div>${rulesHtml || '<span class="hint">无规则命中</span>'}</div>
      </div>
      <div class="tfaChainDivider"></div>
      ${timelineHtml}
      <div class="tfaChainDivider"></div>
      <b style="display:block;margin-bottom:6px;">📋 文件详情 & 证据</b>
      ${fileDetailsHtml}
      ${logViewerHtml}
      ${snapHtml}
      ${relEvHtml}
    </div>
  </div>`;
}

function toggleTfaChain(headerEl) {
  const card = headerEl.closest('.tfaChainCard');
  if (!card) return;
  const body = card.querySelector('.tfaChainCardBody');
  const toggle = card.querySelector('.tfaChainToggle');
  if (body) {
    body.classList.toggle('open');
    if (toggle) toggle.classList.toggle('open');
  }
}

async function loadTfaChains() {
  const tfaJobId = document.getElementById('tfaJobId')?.value;
  if (!tfaJobId) return;
  try {
    const res = await fetch('/tfa/analysis-chains?job_id=' + encodeURIComponent(tfaJobId));
    const chains = await res.json();
    if (!res.ok) return;
    renderTfaChains(chains);
  } catch (e) {
    console.warn('加载分析链失败:', e);
  }
}

function renderTfaChains(chains) {
  const block = document.getElementById('tfaChainBlock');
  if (!block) return;

  if (!chains || chains.length === 0) {
    block.style.display = 'none';
    return;
  }

  block.style.display = 'block';
  document.getElementById('tfaChainBadge').textContent = chains.length + ' 链';
  const overview = document.getElementById('tfaChainOverview');
  if (overview) overview.innerHTML = renderChainSvgOverview(chains);
  const list = document.getElementById('tfaChainList');
  list.innerHTML = chains.map((c, i) => renderChainCard(c, i)).join('');

  const firstCard = list.querySelector('.tfaChainCard');
  if (firstCard) {
    const body = firstCard.querySelector('.tfaChainCardBody');
    const toggle = firstCard.querySelector('.tfaChainToggle');
    if (body) body.classList.add('open');
    if (toggle) toggle.classList.add('open');
  }
}

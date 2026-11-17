// Numbered upload slots can be added or removed without renumbering files.
const API_BASE = window.APP_CONFIG.apiBase.replace(/\/$/, '');
const form = document.getElementById('form');
const draft = document.getElementById('draft');
const msg = document.getElementById('message');
const button = document.getElementById('submit');
let current = '';
const stageNames = { upload: '正在提交材料', extract: '正在提取原文', prepare: '正在整理模型输入', model: '模型正在生成评述', verify: '正在核查引文与排版', done: '评述已完成' };
const stageOrder = Object.keys(stageNames);
let currentStage = 'upload';
function showProgress(event) {
  currentStage = event.stage;
  document.getElementById('progressTitle').textContent = stageNames[event.stage] || '正在处理';
  document.getElementById('progressDetail').textContent = event.detail;
  for (const item of document.getElementById('progressSteps').children) {
    const index = stageOrder.indexOf(item.dataset.stage);
    const active = stageOrder.indexOf(event.stage);
    item.className = index < active ? 'complete' : index === active ? 'active' : '';
    if (index === active) item.setAttribute('aria-current', 'step');
    else item.removeAttribute('aria-current');
  }
}
let comparisonCount = 1;
const addComparison = document.getElementById('addComparison');
const removeComparison = document.getElementById('removeComparison');
addComparison.onclick = () => {
  if (comparisonCount >= 10) return;
  const index = ++comparisonCount;
  const group = document.createElement('div');
  group.className = 'upload-group';
  // index 是受控整数，不包含用户内容。
  group.innerHTML = `<label for="comparison${index}"><span><b class="file-index">${String(index).padStart(2, '0')}</b>对比文件${index}</span><span class="badge">选填</span></label><input id="comparison${index}" name="comparison${index}" type="file" accept=".pdf,.docx,.txt,.md">`;
  document.getElementById('extraComparisons').append(group);
  removeComparison.hidden = false;
  addComparison.disabled = comparisonCount === 10;
};
removeComparison.onclick = () => {
  if (comparisonCount <= 1) return;
  document.getElementById('extraComparisons').lastElementChild.remove();
  comparisonCount--;
  addComparison.disabled = false;
  removeComparison.hidden = comparisonCount === 1;
};
// 原文仅在展开核对区时创建 DOM，避免长文档拖慢首屏和生成结果展示。
let sourceDocuments = [];
let sourcesRendered = false;
const sources = document.getElementById('sources');
const emptyState = document.getElementById('emptyState');
sources.addEventListener('toggle', () => {
  if (!sources.open || sourcesRendered) return;
  const fragment = document.createDocumentFragment();
  for (const doc of sourceDocuments) {
    const section = document.createElement('div');
    section.className = 'source';
    const title = document.createElement('strong');
    title.textContent = doc.label + ' · ' + doc.filename;
    const text = document.createElement('div');
    text.textContent = doc.text;
    section.append(title, text);
    fragment.append(section);
  }
  document.getElementById('sourceList').append(fragment);
  sourcesRendered = true;
});
fetch(API_BASE + '/api/status').then(r => r.json()).then(s => {
  document.getElementById('status').textContent = s.configured
    ? '本地反代已配置 · 模型：' + s.model
    : '尚未配置模型：请编辑 .env 中的 API_BASE_URL 和 MODEL';
}).catch(() => { document.getElementById('status').textContent = '无法读取模型配置'; });

form.addEventListener('submit', async e => {
  e.preventDefault();
  button.disabled = true;
  button.textContent = '正在生成评述…';
  document.getElementById('progressPanel').hidden = false;
  showProgress({ stage: 'upload', detail: '正在发送文件，后端接收完成后将更新处理阶段' });
  const started = performance.now();
  const updateElapsed = () => {
    const seconds = Math.floor((performance.now() - started) / 1000);
    document.getElementById('elapsedTime').textContent = '已等待 ' + (seconds < 60 ? seconds + ' 秒' : Math.floor(seconds / 60) + ' 分 ' + seconds % 60 + ' 秒');
  };
  updateElapsed();
  const elapsedTimer = setInterval(updateElapsed, 1000);
  msg.className = 'status';
  msg.textContent = '正在读取原文并生成：权利要求1三步法、从属权利要求简评。';
  draft.textContent = '';
  draft.hidden = true;
  emptyState.hidden = true;
  document.getElementById('wordCount').textContent = '正在生成';
  sources.open = false;
  sourceDocuments = [];
  sourcesRendered = false;
  document.getElementById('sourceList').replaceChildren();
  document.getElementById('controls').hidden = true;
  document.getElementById('sources').hidden = true;
  try {
    const body = new FormData(form);
    // 空白选填上传框不发送，防止被后端当作无效文件。
    for (const input of form.querySelectorAll('input[name^="comparison"]')) {
      if (!input.files.length) body.delete(input.name);
    }
    const res = await fetch(API_BASE + '/api/draft?stream=true', { method: 'POST', body });
    if (!res.ok) {
      const failure = await res.json();
      throw new Error(failure.error || '请检查必填文件是否已上传');
    }
    let data;
    await window.NoticeView.readEvents(res, (name, event) => {
      if (name === 'progress') showProgress(event);
      if (name === 'result') data = event;
      if (name === 'error') throw new Error(event.error);
    });
    if (!data) throw new Error('进度连接已中断，未收到完整结果，请检查后端日志后重试');
    current = data.draft;
    draft.hidden = false;
    emptyState.hidden = true;
    window.NoticeView.renderDraft(draft, current);
    showProgress({ stage: 'done', detail: '评述已生成，原文核查及段落排版已完成，可复制或下载正文' });
    document.getElementById('wordCount').textContent = current.replace(/\s/g, '').length.toLocaleString() + ' 字符';
    document.getElementById('controls').hidden = false;
    const warnings = data.warnings || [];
    msg.className = warnings.length ? 'status warn' : 'status';
    msg.style.whiteSpace = 'pre-wrap';
    msg.textContent = warnings.length
      ? '草稿已生成，原文核查发现以下事项：\n' + warnings.join('\n')
      : '草稿已生成，直接引文已通过文本匹配。请核对权利要求对应关系、文件编号及论证。';
    sourceDocuments = data.documents;
    document.getElementById('sources').hidden = false;
  } catch (err) {
    document.getElementById('progressTitle').textContent = '处理未完成';
    document.getElementById('progressDetail').textContent = (stageNames[currentStage] || '') + '时发生问题：' + err.message;
    msg.className = 'status error';
    msg.textContent = err.message;
    document.getElementById('wordCount').textContent = '生成未完成';
  } finally {
    clearInterval(elapsedTimer);
    updateElapsed();
    button.disabled = false;
    button.textContent = '生成权利要求评述 ↗';
  }
});
document.getElementById('download').onclick = () => {
  const url = URL.createObjectURL(new Blob([current], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = '专利审查意见通知书-草稿.txt';
  a.click();
  URL.revokeObjectURL(url);
};
document.getElementById('copy').onclick = async () => {
  try {
    await navigator.clipboard.writeText(current);
    document.getElementById('copy').textContent = '已复制';
    setTimeout(() => document.getElementById('copy').textContent = '复制全文', 1500);
  } catch {
    msg.className = 'status warn';
    msg.textContent = '浏览器未允许复制，请选中正文复制或下载文本。';
  }
};

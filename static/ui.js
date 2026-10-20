// 界面公共工具：安全文本展示、资料上传、运行记录与交互状态，不执行模型HTML。

// 准备$，保存id => document.getElementById(id)
const $ = id => document.getElementById(id);
// 准备show，保存value => typeof value === 'string' ? value : JSON.stringify(value, null, 2)
const show = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
// 准备noticeTimer：轻提示的延迟清除计时器；准备uiMode：页面当前演示或真实运行模式
let noticeTimer = null, uiMode = 'demo';
// 所有模型/文件内容先作为文本写入，避免把它们当成可信HTML执行。
function textNode(tag, text, cls) {
  // 准备node，保存document.createElement(tag)
  const node = document.createElement(tag); node.textContent = text;
  // 检查条件 cls；成立时执行紧随的分支
  if (cls) node.className = cls; return node;
}
// 引用本地SVG符号，图标不依赖外部资源或模型输出。
function icon(name, cls = '') {
  // 准备node，保存document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  // 设置DOM属性（node.setAttribute）
  node.setAttribute('class', 'icon ' + cls); node.setAttribute('aria-hidden', 'true');
  // 准备use，保存document.createElementNS('http://www.w3.org/2000/svg', 'use')
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  // 设置DOM属性（use.setAttribute）
  use.setAttribute('href', '/static/icons.svg#' + name); node.append(use); return node;
}
// 页面轻提示，超时后清空；原始执行证据仍保存在后端轨迹中。
function notice(text) {
  // 调用clearTimeout，执行此步处理（clearTimeout）
  clearTimeout(noticeTimer); $('notice').textContent = text;
  // 更新noticeTimer，供本次流程的后续步骤读取
  noticeTimer = setTimeout(() => {$('notice').textContent = '';}, 7000);
}
// 统一JSON接口错误；HTTP失败或非JSON都变成页面可处理的异常。
async function api(path, options = {}) {
  // 准备response：HTTP响应对象，之后还要检查状态和解析正文
  let response;
  // 进入可能失败的操作；异常交给catch，finally中的清理仍会执行（如有）
  try {response = await fetch(path, options);} catch (_) {throw new Error('连接失败，请确认本地项目服务正在运行。');}
  // 准备value：本步骤读取或计算的值
  let value;
  // 进入可能失败的操作；异常交给catch，finally中的清理仍会执行（如有）
  try {value = await response.json();} catch (_) {throw new Error('服务未返回有效结果，请稍后查看运行记录。');}
  // 检查条件 !response.ok；成立时执行紧随的分支
  if (!response.ok) {
    // 准备detail，保存value.error || value.detail
    let detail = value.error || value.detail;
    // 检查条件 Array.isArray(detail)；成立时执行紧随的分支
    if (Array.isArray(detail)) detail = detail.map(item => item.msg).join('；');
    // 抛出异常，由外层捕获并显示/记录失败，不继续当前正常流程
    throw new Error(typeof detail === 'string' ? detail : '本次操作未完成（HTTP ' + response.status + '）');
  }
  // 返回value，结束当前函数的这次调用
  return value;
}
// 准备post，保存(path, value, method = 'POST') => api(path, {method, headers:{'Content-Type':'application/
const post = (path, value, method = 'POST') => api(path, {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(value)});
// 浏览器允许时复制，否则提示手动选取；没有有效结果时不复制空内容。
async function copyText(value, success = '已复制') {
  // 检查条件 !value；成立时执行紧随的分支
  if (!value) return notice('当前没有可复制的内容。');
  // 进入可能失败的操作；异常交给catch，finally中的清理仍会执行（如有）
  try {await navigator.clipboard.writeText(value); notice(success);} catch (_) {notice('浏览器未允许复制，请手动选中文本复制。');}
}
// 替换按钮图标与文字，维持加载态和结束态的一致展示。
function setButtonLabel(button, name, label) {button.replaceChildren(icon(name, 'small'), document.createTextNode(label));}
// 只修饰生成中的展示副本，隐藏半截格式；不改变后端校验使用的完整答案。
function formattedDraft(text) {
  // 只修饰展示副本，完整回答仍由后端核对；代码块里的原文保持不变。
  // 准备fenced：当前行是否位于Markdown代码块内
  let fenced = false;
  // 返回String(text).split('\n').map(raw => { const trimmed = raw.trim(); if (trimmed.startsWith('，结束当前函数的这次调用
  return String(text).split('\n').map(raw => {
    // 准备trimmed，保存raw.trim()
    const trimmed = raw.trim();
    // 检查条件 trimmed.startsWith('```')；成立时执行紧随的分支
    if (trimmed.startsWith('```')) {fenced = !fenced; return raw;}
    // 检查条件 fenced；成立时执行紧随的分支
    if (fenced) return raw;
    // 检查条件 /^(?:#{1,6}|[-*]|\d+[.、]|`{1,2})$/.test(trimmed)；成立时执行紧随的分支
    if (/^(?:#{1,6}|[-*]|\d+[.、]|`{1,2})$/.test(trimmed)) return '';
    // 在引用完整到达前不显示半截ID；完整ID立即呈现为来源按钮。
    // 准备line，保存raw.replace(/\[\s*(?:id\s*:\s*)?([a-f0-9]{16})\s*\]/gi, (_, id) => '[' + id.toLowerCase() 
    let line = raw.replace(/\[\s*(?:id\s*:\s*)?([a-f0-9]{16})\s*\]/gi, (_, id) => '[' + id.toLowerCase() + ']');
    // 更新line，供本次流程的后续步骤读取
    line = line.replace(/\[\s*(?:i(?:d\s*:?\s*)?)?[a-f0-9]*$/i, '');
    // 准备codeParts，保存line.split(/(`[^`]*`)/g)
    const codeParts = line.split(/(`[^`]*`)/g);
    // 更新line，供本次流程的后续步骤读取
    line = codeParts.map(part => {
      // 检查条件 part.startsWith('`') && part.endsWith('`') && part.length > 1；成立时执行紧随的分支
      if (part.startsWith('`') && part.endsWith('`') && part.length > 1) return part;
      // 网络分包可能只送达加粗结束标记的一个星号。
      // 更新part，供本次流程的后续步骤读取
      part = part.replace(/(?<!\*)\*$/, '');
      // 检查条件 (part.match(/\*\*/g) || []).length % 2；成立时执行紧随的分支
      if ((part.match(/\*\*/g) || []).length % 2) {
        // 检查条件 part.endsWith('**')；成立时执行紧随的分支
        if (part.endsWith('**')) part = part.slice(0, -2);
        else part += '**';
      }
      // 返回part，结束当前函数的这次调用
      return part;
    }).join('');
    // 检查条件 (line.match(/`/g) || []).length % 2；成立时执行紧随的分支
    if ((line.match(/`/g) || []).length % 2) line += '`';
    // 返回line，结束当前函数的这次调用
    return line;
  }).join('\n');
}
// 有限的加粗/代码/引用解析，用DOM节点构造内容，不执行原始HTML。
function inlineText(container, text, onCitation) {
  // 准备pattern，保存/(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[a-f0-9]{16}\])/g
  const pattern = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[a-f0-9]{16}\])/g;
  // 准备last，保存0
  let last = 0;
  // 逐项遍历text.matchAll(pattern)，每次处理const match
  for (const match of text.matchAll(pattern)) {
    // 按顺序把节点或文本加入对应容器（container.append）
    container.append(document.createTextNode(text.slice(last, match.index)));
    // 准备token，保存match[0]
    const token = match[0];
    // 检查条件 token.startsWith('**')；成立时执行紧随的分支
    if (token.startsWith('**')) container.append(textNode('strong', token.slice(2, -2)));
    else if (token.startsWith('`')) container.append(textNode('code', token.slice(1, -1)));
    else {
      // 准备id，保存token.slice(1, -1)；准备button，保存textNode('button', id.slice(0, 4), 'citation')
      const id = token.slice(1, -1), button = textNode('button', id.slice(0, 4), 'citation');
      // 更新button.type，供本次流程的后续步骤读取
      button.type = 'button'; button.title = '查看原文片段 ' + id; button.setAttribute('aria-label', '查看引用片段 ' + id);
      // 更新button.onclick，供本次流程的后续步骤读取
      button.onclick = () => onCitation ? onCitation(id) : notice('可在本次执行记录中核对片段 ' + id);
      // 按顺序把节点或文本加入对应容器（container.append）
      container.append(button);
    }
    // 更新last，供本次流程的后续步骤读取
    last = match.index + token.length;
  }
  // 按顺序把节点或文本加入对应容器（container.append）
  container.append(document.createTextNode(text.slice(last)));
}
// 逐行渲染有限Markdown；不是全语法解析器，完整引用可回到对应来源。
function richText(container, text, onCitation) {
  // 替换容器现有内容，避免保留上次结果（container.replaceChildren）
  container.replaceChildren(); let list = null, code = null;
  // 逐项遍历String(text || '').split('\n')，每次处理const raw
  for (const raw of String(text || '').split('\n')) {
    // 准备line，保存raw.trim()
    const line = raw.trim();
    // 检查条件 line.startsWith('```')；成立时执行紧随的分支
    if (line.startsWith('```')) {
      // 检查条件 code；成立时执行紧随的分支
      if (code) code = null;
      else {const pre=textNode('pre','','code-block'); code=document.createElement('code'); pre.append(code);container.append(pre);}
      // 更新list，供本次流程的后续步骤读取
      list=null;continue;
    }
    // 检查条件 code；成立时执行紧随的分支
    if(code){code.textContent+=raw+'\n';continue;}
    // 检查条件 !line；成立时执行紧随的分支
    if (!line) {list = null; continue;}
    // 准备bullet，保存line.match(/^(?:[-*•]\s+|\d+[.、]\s*)(.*)$/)
    const bullet = line.match(/^(?:[-*•]\s+|\d+[.、]\s*)(.*)$/);
    // 检查条件 bullet；成立时执行紧随的分支
    if (bullet) {
      // 检查条件 !list；成立时执行紧随的分支
      if (!list) {list = document.createElement('ul'); container.append(list);}
      // 准备item，保存document.createElement('li')
      const item = document.createElement('li'); inlineText(item, bullet[1], onCitation); list.append(item);
    } else {
      // 更新list，供本次流程的后续步骤读取
      list = null; const heading = line.match(/^#{1,6}\s+(.*)$/);
      // 准备block，保存document.createElement(heading ? 'h3' : 'p')
      const block = document.createElement(heading ? 'h3' : 'p');
      // 调用inlineText，执行此步处理（inlineText）
      inlineText(block, heading ? heading[1] : line, onCitation); container.append(block);
    }
  }
}
// 真实异步操作进行时显示等待提示，不伪造模型生成文字。
function loading(container, label) {
  // 替换容器现有内容，避免保留上次结果（container.replaceChildren）
  container.replaceChildren(); const row = textNode('div', '', 'loading');
  // 按顺序把节点或文本加入对应容器（row.append）
  row.append(textNode('span', '', 'spinner'), document.createTextNode(label)); container.append(row);
}
// 错误展示与正文分开，避免把异常信息当作一段正常模型结论。
function errorBox(container, text) {
  // 替换容器现有内容，避免保留上次结果（container.replaceChildren）
  container.replaceChildren(); const row = textNode('div', '', 'status-box error');
  // 按顺序把节点或文本加入对应容器（row.append）
  row.append(icon('info'), textNode('span', text)); container.append(row);
}
// 以约定上海时区显示时间；数据库中仍保存时间戳。
function dateLabel(seconds, time = false) {
  // 检查条件 !Number.isFinite(seconds)；成立时执行紧随的分支
  if (!Number.isFinite(seconds)) return '—';
  // 返回new Date(seconds * 1000).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', month:'2-digit，结束当前函数的这次调用
  return new Date(seconds * 1000).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', month:'2-digit', day:'2-digit', ...(time ? {hour:'2-digit', minute:'2-digit'} : {})});
}
// 把毫秒转成可读单位，只格式化，不改变实际耗时数据。
function durationLabel(ms) {return typeof ms === 'number' ? (ms >= 1000 ? (ms / 1000).toFixed(2) + ' s' : Math.round(ms) + ' ms') : '—';}
// 读取实际文档/片段统计并提供删除入口，数字不使用静态占位值。
async function documents() {
  // 准备rows，保存await api('/api/rag/documents')
  const rows = await api('/api/rag/documents'); $('documents').replaceChildren();
  // 以纯文本更新页面，内容不作为HTML执行：$('document-count').textContent
  $('document-count').textContent = rows.length;
  // 以纯文本更新页面，内容不作为HTML执行：$('doc-total').textContent
  $('doc-total').textContent = rows.length;
  // 以纯文本更新页面，内容不作为HTML执行：$('chunk-total').textContent
  $('chunk-total').textContent = rows.reduce((sum, row) => sum + Number(row.chunks || 0), 0);
  // 检查条件 !rows.length；成立时执行紧随的分支
  if (!rows.length) $('documents').append(textNode('div', '还没有资料，添加第一份吧。', 'empty-small'));
  // 逐项遍历rows，每次处理const row
  for (const row of rows) {
    // 准备card，保存textNode('div', '', 'document-card')
    const card = textNode('div', '', 'document-card');
    // 准备extension，保存row.name.split('.').pop().toUpperCase()
    const extension = row.name.split('.').pop().toUpperCase();
    // 准备file，保存textNode('span', extension.slice(0, 3), 'file-icon')
    const file = textNode('span', extension.slice(0, 3), 'file-icon');
    // 准备content，保存textNode('div', '', 'document-content')
    const content = textNode('div', '', 'document-content');
    // 按顺序把节点或文本加入对应容器（content.append）
    content.append(textNode('div', row.name, 'document-name'), textNode('div', `v${row.version} · ${row.chunks} 个片段 · ${dateLabel(row.updated)}`, 'document-meta'));
    // 准备button，保存textNode('button', '', 'icon-button danger')
    const button = textNode('button', '', 'icon-button danger'); button.type = 'button';
    // 更新button.title，供本次流程的后续步骤读取
    button.title = '删除 ' + row.name; button.setAttribute('aria-label', '删除资料 ' + row.name); button.append(icon('trash'));
    // 更新button.onclick，供本次流程的后续步骤读取
    button.onclick = () => guard(button, async () => {
      // 检查条件 !confirm('删除“' + row.name + '”及其检索片段？')；成立时执行紧随的分支
      if (!confirm('删除“' + row.name + '”及其检索片段？')) return;
      // 等待调用api，执行此步处理（api）
      await api('/api/rag/documents/' + row.id, {method:'DELETE'}); await documents();
      // 调用notice，执行此步处理（notice）
      notice('资料及其索引已删除。'); await safeRefreshTraces();
    });
    // 按顺序把节点或文本加入对应容器（card.append）
    card.append(file, content, button); $('documents').append(card);
  }
}
// 限制格式和大小、处理拖入，再提交multipart文件；后端仍会再次校验。
function bindUpload() {
  // 准备input，保存$('file')；准备button，保存$('upload-submit')；准备drop，保存$('dropzone')
  const input = $('file'), button = $('upload-submit'), drop = $('dropzone');
  // 文件选择只更新页面状态，点击上传后才解析与向量化。
  function updateFile() {
    // 准备file，保存input.files[0]
    const file = input.files[0];
    // 检查条件 file && (file.size > 15 * 1024 * 1024 || !/\.(pdf|md|txt)$/i.test(file.name))；成立时执行紧随的分支
    if (file && (file.size > 15 * 1024 * 1024 || !/\.(pdf|md|txt)$/i.test(file.name))) {
      // 更新表单中的可编辑值：input.value
      input.value = ''; notice('请选择15 MB以内的PDF、Markdown或TXT文件。');
    }
    // 准备selected，保存input.files[0]
    const selected = input.files[0]; button.disabled = !selected;
    // 切换区域的显示或隐藏：$('selected-file').hidden
    $('selected-file').hidden = !selected;
    // 以纯文本更新页面，内容不作为HTML执行：$('selected-file').textContent
    $('selected-file').textContent = selected ? selected.name + ' · ' + (selected.size / 1024).toFixed(1) + ' KB' : '';
  }
  // 绑定事件处理函数，事件发生后才运行回调（input.addEventListener）
  input.addEventListener('change', updateFile);
  // 绑定事件处理函数，事件发生后才运行回调（drop.addEventListener）
  drop.addEventListener('dragover', event => {event.preventDefault(); drop.classList.add('dragging');});
  // 绑定事件处理函数，事件发生后才运行回调（drop.addEventListener）
  drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));
  // 绑定事件处理函数，事件发生后才运行回调（drop.addEventListener）
  drop.addEventListener('drop', event => {
    // 阻止表单默认跳转，由脚本处理提交（event.preventDefault）
    event.preventDefault(); drop.classList.remove('dragging');
    // 准备file，保存event.dataTransfer.files[0]
    const file = event.dataTransfer.files[0];
    // 检查条件 file；成立时执行紧随的分支
    if (file) {const transfer = new DataTransfer(); transfer.items.add(file); input.files = transfer.files; updateFile();}
  });
  // 更新$('upload').onsubmit，供本次流程的后续步骤读取
  $('upload').onsubmit = event => {
    // 阻止表单默认跳转，由脚本处理提交（event.preventDefault）
    event.preventDefault(); if (!input.files[0]) return;
    // 调用guard(button, async () => { setButtonLabel(button, 'refresh', '正在建立索引…'); try { const form，执行此步处理（guard(button, async () => { setButtonLabel(button, 'refresh', '正在建立索引…'); try { const form）
    guard(button, async () => {
      // 调用setButtonLabel，执行此步处理（setButtonLabel）
      setButtonLabel(button, 'refresh', '正在建立索引…');
      // 进入可能失败的操作；异常交给catch，finally中的清理仍会执行（如有）
      try {
        // 准备form，保存new FormData()
        const form = new FormData(); form.append('file', input.files[0]);
        // 准备result：接口或被测函数返回的结果
        const result = await api('/api/rag/documents', {method:'POST', body:form});
        // 准备info，保存result.unchanged ? '资料内容一致，无需重复处理。' : '资料已保存，当前版本 v' + result.version + '。'
        let info = result.unchanged ? '资料内容一致，无需重复处理。' : '资料已保存，当前版本 v' + result.version + '。';
        // 检查条件 result.empty_pages?.length；成立时执行紧随的分支
        if (result.empty_pages?.length) info += ' 第' + result.empty_pages.join('、') + '页未提取到文字。';
        // 更新表单中的可编辑值：input.value
        input.value = ''; updateFile(); await documents(); notice(info); await safeRefreshTraces();
      } finally {setButtonLabel(button, 'plus', '添加到知识库');}
    }).finally(() => {button.disabled = !input.files.length;});
  };
}
// 准备traceLabels，保存{'rag.ingest':'资料入库', 'rag.answer':'知识问答', 'agent.chat':'服务咨询', 'agent.draft':'整理草稿', 'age
const traceLabels = {'rag.ingest':'资料入库', 'rag.answer':'知识问答', 'agent.chat':'服务咨询', 'agent.draft':'整理草稿', 'agent.decide':'确认 / 取消任务', 'api.database':'数据库操作'};
// 显示最近执行摘要，点击后读取完整详情；原始payload只按文本呈现。
async function refreshTraces() {
  // 准备rows，保存await api('/api/traces')
  const rows = await api('/api/traces'); $('traces').replaceChildren();
  // 检查条件 !rows.length；成立时执行紧随的分支
  if (!rows.length) $('traces').append(textNode('div', '完成一次提问或资料操作后，记录会出现在这里。', 'empty-small'));
  // 逐项遍历rows，每次处理const row
  for (const row of rows) {
    // 准备button，保存textNode('button', '', 'trace-row')
    const button = textNode('button', '', 'trace-row'); button.type = 'button';
    // 准备title，保存textNode('span', traceLabels[row.project] || row.project)
    const title = textNode('span', traceLabels[row.project] || row.project);
    // 准备status，保存textNode('span', row.status === 'completed' ? '已完成' : '未完成', 'trace-status ' + row.status)
    const status = textNode('span', row.status === 'completed' ? '已完成' : '未完成', 'trace-status ' + row.status);
    // 按顺序把节点或文本加入对应容器（button.append）
    button.append(title, status, textNode('small', durationLabel(row.elapsed_ms) + ' · ' + dateLabel(row.created, true)));
    // 更新button.onclick，供本次流程的后续步骤读取
    button.onclick = () => guard(button, async () => {
      // 准备value：本步骤读取或计算的值
      const value = await api('/api/traces/' + row.id);
      // 以纯文本更新页面，内容不作为HTML执行：$('trace-detail').textContent
      $('trace-detail').textContent = show(value); $('trace-detail-wrap').hidden = false;
      // 更新$('trace-detail-wrap').open，供本次流程的后续步骤读取
      $('trace-detail-wrap').open = true; $('trace-detail-wrap').scrollIntoView({behavior:'smooth', block:'nearest'});
    });
    // 按顺序把节点或文本加入对应容器（$('traces').append）
    $('traces').append(button);
  }
}
// 刷新轨迹失败不推翻已完成的业务结果，提示用户稍后重试查看。
async function safeRefreshTraces() {try {await refreshTraces();} catch (_) {notice('操作已完成，但暂时无法刷新运行记录。');}}
// 维护字数和Ctrl/Command+Enter快捷键，受提交按钮忙碌状态限制。
function bindComposer(id, countId, formId) {
  // 准备input，保存$(id)
  const input = $(id);
  // 绑定事件处理函数，事件发生后才运行回调（input.addEventListener）
  input.addEventListener('input', () => {$(countId).textContent = input.value.length + ' / 4000';});
  // 绑定事件处理函数，事件发生后才运行回调（input.addEventListener）
  input.addEventListener('keydown', event => {if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {event.preventDefault(); if (!$(formId).querySelector('button[type=submit]').disabled) $(formId).requestSubmit();}});
}
// 页面内导航与刷新绑定，不发送任何实际云服务业务请求。
function bindNavigation() {
  // 逐项执行回调以更新对应元素（document.querySelectorAll('.nav-item').forEach）
  document.querySelectorAll('.nav-item').forEach(link => link.addEventListener('click', () => {
    // 逐项执行回调以更新对应元素（document.querySelectorAll('.nav-item').forEach）
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active')); link.classList.add('active');
    // 准备target，保存document.querySelector(link.getAttribute('href'))
    const target = document.querySelector(link.getAttribute('href')); if (target?.tagName === 'DETAILS') target.open = true;
  }));
  // 更新$('refresh-traces').onclick，供本次流程的后续步骤读取
  $('refresh-traces').onclick = () => guard($('refresh-traces'), refreshTraces);
}
// 页面初始化独立读取健康状态、资料与轨迹，单个面板失败不阻止其他面板显示。
async function commonInit() {
  // 调用bindNavigation，执行此步处理（bindNavigation）
  bindNavigation(); bindUpload();
  // 进入可能失败的操作；异常交给catch，finally中的清理仍会执行（如有）
  try {
    // 准备value：本步骤读取或计算的值
    const value = await api('/api/health'); uiMode = value.mode;
    // 以纯文本更新页面，内容不作为HTML执行：$('mode').textContent
    $('mode').textContent = value.mode === 'live' ? '真实模型模式' : '离线演示模式'; $('mode').dataset.state = value.mode;
    // 更新$('mode').title，供本次流程的后续步骤读取
    $('mode').title = value.mode === 'live' ? '本次使用真实模型接口' : '展示本地流程，不代表真实模型效果';
  } catch (error) {$('mode').textContent = '服务连接异常'; $('mode').dataset.state = 'error'; notice(error.message);}
  // 等待调用Promise.allSettled，执行此步处理（Promise.allSettled）
  await Promise.allSettled([
    documents().catch(error => {$('documents').replaceChildren(textNode('div', '资料暂时无法读取', 'empty-small'));notice(error.message);}),
    refreshTraces().catch(() => {$('traces').replaceChildren(textNode('div', '运行记录暂时无法读取，请点击刷新。', 'empty-small'));})
  ]);
}

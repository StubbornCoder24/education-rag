// 页面业务编排：响应用户操作、更新当前视图；数据库和最终校验以后端结果为准。

let lastTrace = null, lastAnswer = '';
// 统一处理按钮忙碌和异常；操作结束后恢复可用状态，Agent还需重新应用任务终态限制。
async function guard(button, action) {button.disabled = true; try {await action();} catch(error) {notice(error.message);} finally {button.disabled = false;}}
// 引用按钮只定位当前答案已展示的片段，不根据模型编号读取任意文件。
function locateSource(id) {
  const detail = document.getElementById('source-' + id);
  if (!detail) return notice('此片段不在当前回答的依据中。');
  detail.open = true; detail.classList.remove('flash');
  detail.scrollIntoView({behavior:'smooth', block:'center'}); detail.querySelector('summary').focus();
  requestAnimationFrame(() => detail.classList.add('flash'));
}
// 保留文件名/页码/版本及原文，方便人工检查“有引用”是否真的“有依据”。
function renderSources(rows) {
  // 替换容器现有内容，避免保留上次结果（$('sources').replaceChildren）
  $('sources').replaceChildren(); $('source-count').textContent = rows.length;
  if (!rows.length) {const empty = textNode('div', '', 'source-empty'); empty.append(icon('file'), textNode('p', '这次没有找到可用的资料依据。\n可以补充资料，或调整问题。')); $('sources').append(empty);}
  rows.forEach((row, index) => {
    const detail = document.createElement('details'); detail.className = 'source-card'; detail.id = 'source-' + row.id;
    const summary = document.createElement('summary'), heading = document.createElement('span');
    const location = row.page ? '第 ' + row.page + ' 页' : row.section || '正文';
    heading.append(textNode('span', row.name, 'source-name'), textNode('span', location + ' · v' + row.version, 'source-location'));
    summary.append(textNode('span', String(index + 1).padStart(2, '0'), 'source-number'), heading, icon('chevron'));
    detail.append(summary, textNode('div', row.text, 'source-text'), textNode('div', '片段 ' + row.id, 'source-id'));
    $('sources').append(detail);
  });
}
// 提交一次问答：先展示待核对草稿，只有后端done且引用校验完成才允许复制/反馈。
$('rag-form').onsubmit = event => {
  // 阻止表单默认跳转，由脚本处理提交（event.preventDefault）
  event.preventDefault(); const question = $('rag-question').value.trim(); if (!question) return notice('先写下你的问题吧。');
  guard($('ask-submit'), async () => {
    lastTrace = null; lastAnswer = ''; $('rag-welcome').hidden = true; $('answer-section').hidden = false;
    // 切换区域的显示或隐藏：$('feedback').hidden
    $('feedback').hidden = true; $('answer-status').textContent = '正在查找依据';
    loading($('rag-answer'), '正在检索资料并组织回答…');
    // 替换容器现有内容，避免保留上次结果（$('sources').replaceChildren）
    $('sources').replaceChildren(textNode('div', '正在查找相关片段…', 'empty-small')); $('source-count').textContent = '—';
    setButtonLabel($('ask-submit'), 'refresh', '正在回答…');
    let renderTimer = null;
    try {
      let result = null, draft = '';
      await readAnswerStream({question, strategy:$('strategy').value}, event => {
        if (event.type === 'status') $('answer-status').textContent = event.message;
        else if (event.type === 'sources') renderSources(event.sources || []);
        else if (event.type === 'delta') {
          draft += event.text;
          // 合并短时间内的增量，边生成边排版，避免每个token都重建DOM。
          if (renderTimer === null) renderTimer = setTimeout(() => {
            renderTimer = null;
            richText($('rag-answer'), formattedDraft(draft), locateSource);
          }, 70);
        } else if (event.type === 'done') result = event.result;
      });
      clearTimeout(renderTimer); renderTimer = null;
      if (!result) throw new Error('未收到完整回答，请重新提问。');
      renderSources(result.sources || []); richText($('rag-answer'), result.answer, locateSource);
      $('answer-status').textContent = result.abstained ? '资料不足' : result.mode === 'demo' ? '离线资料摘录' : '已生成 · 请核对引用';
      lastTrace = result.trace_id; lastAnswer = result.answer;
      // 切换区域的显示或隐藏：$('feedback').hidden
      $('feedback').hidden = false;
      for (const id of ['useful','not-useful']) {$(id).disabled=false; $(id).setAttribute('aria-pressed','false');}
      await safeRefreshTraces();
    } catch (error) {
      clearTimeout(renderTimer); renderTimer = null;
      $('answer-status').textContent = '本次未完成'; errorBox($('rag-answer'), error.message);
      // 替换容器现有内容，避免保留上次结果（$('sources').replaceChildren）
      $('sources').replaceChildren(textNode('div', '本次未取得可展示的依据。', 'empty-small')); $('source-count').textContent = '0';
      await safeRefreshTraces();
    } finally {clearTimeout(renderTimer); setButtonLabel($('ask-submit'), 'arrow', '开始提问');}
  });
};
for (const [id, rating] of [['useful',1],['not-useful',0]]) $(id).onclick = () => guard($(id), async () => {
  if (!lastTrace) return;
  await post('/api/feedback', {trace_id:lastTrace, rating, comment:''});
  // 设置DOM属性（$(id).setAttribute）
  $(id).setAttribute('aria-pressed','true'); notice('谢谢，反馈已保存。');
});
$('copy-answer').onclick = () => copyText(lastAnswer, '回答已复制。');
document.querySelectorAll('[data-prompt]').forEach(button => {button.onclick = () => {
  $('rag-question').value = button.dataset.prompt; $('rag-question').dispatchEvent(new Event('input')); $('rag-question').focus();
};});
bindComposer('rag-question','question-count','rag-form');
commonInit().catch(error => notice(error.message));

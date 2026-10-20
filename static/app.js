// 页面业务编排：响应用户操作、更新当前视图；数据库和最终校验以后端结果为准。

// 准备lastTrace，保存null；准备lastAnswer，保存''
let lastTrace = null, lastAnswer = '';
// 统一处理按钮忙碌和异常；操作结束后恢复可用状态，Agent还需重新应用任务终态限制。
async function guard(button, action) {button.disabled = true; try {await action();} catch(error) {notice(error.message);} finally {button.disabled = false;}}
// 引用按钮只定位当前答案已展示的片段，不根据模型编号读取任意文件。
function locateSource(id) {
  // 准备detail，保存document.getElementById('source-' + id)
  const detail = document.getElementById('source-' + id);
  // 检查条件 !detail；成立时执行紧随的分支
  if (!detail) return notice('此片段不在当前回答的依据中。');
  // 更新detail.open，供本次流程的后续步骤读取
  detail.open = true; detail.classList.remove('flash');
  // 将指定来源/消息滚动到可见位置（detail.scrollIntoView）
  detail.scrollIntoView({behavior:'smooth', block:'center'}); detail.querySelector('summary').focus();
  // 调用requestAnimationFrame，执行此步处理（requestAnimationFrame）
  requestAnimationFrame(() => detail.classList.add('flash'));
}
// 保留文件名/页码/版本及原文，方便人工检查“有引用”是否真的“有依据”。
function renderSources(rows) {
  // 替换容器现有内容，避免保留上次结果（$('sources').replaceChildren）
  $('sources').replaceChildren(); $('source-count').textContent = rows.length;
  // 检查条件 !rows.length；成立时执行紧随的分支
  if (!rows.length) {const empty = textNode('div', '', 'source-empty'); empty.append(icon('file'), textNode('p', '这次没有找到可用的资料依据。\n可以补充资料，或调整问题。')); $('sources').append(empty);}
  // 逐项执行回调以更新对应元素（rows.forEach）
  rows.forEach((row, index) => {
    // 准备detail，保存document.createElement('details')
    const detail = document.createElement('details'); detail.className = 'source-card'; detail.id = 'source-' + row.id;
    // 准备summary，保存document.createElement('summary')；准备heading，保存document.createElement('span')
    const summary = document.createElement('summary'), heading = document.createElement('span');
    // 准备location，保存row.page ? '第 ' + row.page + ' 页' : row.section || '正文'
    const location = row.page ? '第 ' + row.page + ' 页' : row.section || '正文';
    // 按顺序把节点或文本加入对应容器（heading.append）
    heading.append(textNode('span', row.name, 'source-name'), textNode('span', location + ' · v' + row.version, 'source-location'));
    // 按顺序把节点或文本加入对应容器（summary.append）
    summary.append(textNode('span', String(index + 1).padStart(2, '0'), 'source-number'), heading, icon('chevron'));
    // 按顺序把节点或文本加入对应容器（detail.append）
    detail.append(summary, textNode('div', row.text, 'source-text'), textNode('div', '片段 ' + row.id, 'source-id'));
    // 按顺序把节点或文本加入对应容器（$('sources').append）
    $('sources').append(detail);
  });
}
// 提交一次问答：先展示待核对草稿，只有后端done且引用校验完成才允许复制/反馈。
// 更新$('rag-form').onsubmit，供本次流程的后续步骤读取
$('rag-form').onsubmit = event => {
  // 阻止表单默认跳转，由脚本处理提交（event.preventDefault）
  event.preventDefault(); const question = $('rag-question').value.trim(); if (!question) return notice('先写下你的问题吧。');
  // 调用guard，执行此步处理（guard）
  guard($('ask-submit'), async () => {
    // 更新lastTrace，供本次流程的后续步骤读取
    lastTrace = null; lastAnswer = ''; $('rag-welcome').hidden = true; $('answer-section').hidden = false;
    // 切换区域的显示或隐藏：$('feedback').hidden
    $('feedback').hidden = true; $('answer-status').textContent = '正在查找依据';
    // 调用loading，执行此步处理（loading）
    loading($('rag-answer'), '正在检索资料并组织回答…');
    // 替换容器现有内容，避免保留上次结果（$('sources').replaceChildren）
    $('sources').replaceChildren(textNode('div', '正在查找相关片段…', 'empty-small')); $('source-count').textContent = '—';
    // 调用setButtonLabel，执行此步处理（setButtonLabel）
    setButtonLabel($('ask-submit'), 'refresh', '正在回答…');
    // 准备renderTimer：合并短时间内多次内容更新的排版计时器
    let renderTimer = null;
    // 进入可能失败的操作；异常交给catch，finally中的清理仍会执行（如有）
    try {
      // 准备result：接口或被测函数返回的结果；准备draft：生成过程中暂存的回答文本
      let result = null, draft = '';
      // 等待调用readAnswerStream，执行此步处理（readAnswerStream）
      await readAnswerStream({question, strategy:$('strategy').value}, event => {
        // 检查条件 event.type === 'status'；成立时执行紧随的分支
        if (event.type === 'status') $('answer-status').textContent = event.message;
        else if (event.type === 'sources') renderSources(event.sources || []);
        else if (event.type === 'delta') {
          // 更新draft，供本次流程的后续步骤读取
          draft += event.text;
          // 合并短时间内的增量，边生成边排版，避免每个token都重建DOM。
          // 检查条件 renderTimer === null；成立时执行紧随的分支
          if (renderTimer === null) renderTimer = setTimeout(() => {
            // 更新renderTimer，供本次流程的后续步骤读取
            renderTimer = null;
            // 调用richText，执行此步处理（richText）
            richText($('rag-answer'), formattedDraft(draft), locateSource);
          }, 70);
        } else if (event.type === 'done') result = event.result;
      });
      // 调用clearTimeout，执行此步处理（clearTimeout）
      clearTimeout(renderTimer); renderTimer = null;
      // 检查条件 !result；成立时执行紧随的分支
      if (!result) throw new Error('未收到完整回答，请重新提问。');
      // 调用renderSources，执行此步处理（renderSources）
      renderSources(result.sources || []); richText($('rag-answer'), result.answer, locateSource);
      // 以纯文本更新页面，内容不作为HTML执行：$('answer-status').textContent
      $('answer-status').textContent = result.abstained ? '资料不足' : result.mode === 'demo' ? '离线资料摘录' : '已生成 · 请核对引用';
      // 更新lastTrace，供本次流程的后续步骤读取
      lastTrace = result.trace_id; lastAnswer = result.answer;
      // 切换区域的显示或隐藏：$('feedback').hidden
      $('feedback').hidden = false;
      // 逐项遍历['useful','not-useful']，每次处理const id
      for (const id of ['useful','not-useful']) {$(id).disabled=false; $(id).setAttribute('aria-pressed','false');}
      // 等待调用safeRefreshTraces，执行此步处理（safeRefreshTraces）
      await safeRefreshTraces();
    } catch (error) {
      // 调用clearTimeout，执行此步处理（clearTimeout）
      clearTimeout(renderTimer); renderTimer = null;
      // 以纯文本更新页面，内容不作为HTML执行：$('answer-status').textContent
      $('answer-status').textContent = '本次未完成'; errorBox($('rag-answer'), error.message);
      // 替换容器现有内容，避免保留上次结果（$('sources').replaceChildren）
      $('sources').replaceChildren(textNode('div', '本次未取得可展示的依据。', 'empty-small')); $('source-count').textContent = '0';
      // 等待调用safeRefreshTraces，执行此步处理（safeRefreshTraces）
      await safeRefreshTraces();
    } finally {clearTimeout(renderTimer); setButtonLabel($('ask-submit'), 'arrow', '开始提问');}
  });
};
// 逐项遍历[['useful',1],['not-useful',0]]，每次处理const [id, rating]
for (const [id, rating] of [['useful',1],['not-useful',0]]) $(id).onclick = () => guard($(id), async () => {
  // 检查条件 !lastTrace；成立时执行紧随的分支
  if (!lastTrace) return;
  // 等待调用post，执行此步处理（post）
  await post('/api/feedback', {trace_id:lastTrace, rating, comment:''});
  // 设置DOM属性（$(id).setAttribute）
  $(id).setAttribute('aria-pressed','true'); notice('谢谢，反馈已保存。');
});
// 更新$('copy-answer').onclick，供本次流程的后续步骤读取
$('copy-answer').onclick = () => copyText(lastAnswer, '回答已复制。');
// 逐项执行回调以更新对应元素（document.querySelectorAll('[data-prompt]').forEach）
document.querySelectorAll('[data-prompt]').forEach(button => {button.onclick = () => {
  // 更新表单中的可编辑值：$('rag-question').value
  $('rag-question').value = button.dataset.prompt; $('rag-question').dispatchEvent(new Event('input')); $('rag-question').focus();
};});
// 调用bindComposer，执行此步处理（bindComposer）
bindComposer('rag-question','question-count','rag-form');
// 调用commonInit().catch，执行此步处理（commonInit().catch）
commonInit().catch(error => notice(error.message));

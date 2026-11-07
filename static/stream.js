// 流式传输客户端：区分网络字节分包、SSE事件和最终完成，HTTP200不等于业务成功。

// fetch流支持POST；按SSE帧缓冲，处理任意网络分包和跨包UTF-8。
// POST建立SSE响应；跨网络分包累计UTF-8与事件帧，只有done才算业务完成。
async function readAnswerStream(payload, onEvent) {
  // 浏览器侧维护一个会话号，服务端用它取最近几轮问答做上下文
  let sessionId = localStorage.getItem('rag-session');
  if (!sessionId) {
    sessionId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)).replace(/-/g, '');
    localStorage.setItem('rag-session', sessionId);
  }
  const body = Object.assign({}, payload, {session_id: sessionId});
  const response = await fetch('/api/rag/ask/stream', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
  });
  if (!response.ok) {
    const value = await response.json().catch(() => ({}));
    // 抛出异常，由外层捕获并显示/记录失败，不继续当前正常流程
    throw new Error(value.error || '请求未完成（HTTP ' + response.status + '）');
  }
  if (!response.body) throw new Error('浏览器未提供流读取能力，请更新浏览器。');
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '', completed = false;
  // 只有遇到完整SSE帧边界才解析JSON；错误与完成事件决定本次流的终态。
  function consume() {
    let boundary;
    // 只要(boundary = buffer.indexOf('\n\n')) !== -1成立，就继续这一轮读取或解析
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
      const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
      if (!data) continue;
      const event = JSON.parse(data);
      if (event.type === 'error') throw new Error(event.message || '本次生成未完成');
      onEvent(event);
      if (event.type === 'done') {completed = true; return;}
    }
  }
  try {
    // 只要!completed成立，就继续这一轮读取或解析
    while (!completed) {
      const {value, done} = await reader.read();
      buffer += decoder.decode(value, {stream:!done});
      consume();
      if (done) break;
    }
    if (!completed) throw new Error('连接中断，回答未完成，请重新提问。');
  } finally {
    await reader.cancel().catch(() => {}); reader.releaseLock();
  }
}

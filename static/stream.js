// 流式传输客户端：区分网络字节分包、SSE事件和最终完成，HTTP200不等于业务成功。

// fetch流支持POST；按SSE帧缓冲，处理任意网络分包和跨包UTF-8。
// POST建立SSE响应；跨网络分包累计UTF-8与事件帧，只有done才算业务完成。
async function readAnswerStream(payload, onEvent) {
  // 准备response：HTTP响应对象，之后还要检查状态和解析正文
  const response = await fetch('/api/rag/ask/stream', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
  });
  // 检查条件 !response.ok；成立时执行紧随的分支
  if (!response.ok) {
    // 准备value：本步骤读取或计算的值
    const value = await response.json().catch(() => ({}));
    // 抛出异常，由外层捕获并显示/记录失败，不继续当前正常流程
    throw new Error(value.error || '请求未完成（HTTP ' + response.status + '）');
  }
  // 检查条件 !response.body；成立时执行紧随的分支
  if (!response.body) throw new Error('浏览器未提供流读取能力，请更新浏览器。');
  // 准备reader：响应体读取器，用于逐批接收网络字节；准备decoder：UTF-8解码器，保留跨网络包的未完成字符
  const reader = response.body.getReader(), decoder = new TextDecoder();
  // 准备buffer：尚未解析完的SSE文本缓冲区；准备completed：是否已收到业务done事件
  let buffer = '', completed = false;
  // 只有遇到完整SSE帧边界才解析JSON；错误与完成事件决定本次流的终态。
  function consume() {
    // 准备boundary：完整SSE帧结束分隔符的位置
    let boundary;
    // 只要(boundary = buffer.indexOf('\n\n')) !== -1成立，就继续这一轮读取或解析
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      // 准备frame：从缓冲区取出的一帧SSE文本
      const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
      // 准备data：解析前的数据行或工具返回内容
      const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
      // 检查条件 !data；成立时执行紧随的分支
      if (!data) continue;
      // 准备event：从JSON解析得到的业务事件
      const event = JSON.parse(data);
      // 检查条件 event.type === 'error'；成立时执行紧随的分支
      if (event.type === 'error') throw new Error(event.message || '本次生成未完成');
      // 调用onEvent，执行此步处理（onEvent）
      onEvent(event);
      // 检查条件 event.type === 'done'；成立时执行紧随的分支
      if (event.type === 'done') {completed = true; return;}
    }
  }
  // 进入可能失败的操作；异常交给catch，finally中的清理仍会执行（如有）
  try {
    // 只要!completed成立，就继续这一轮读取或解析
    while (!completed) {
      // 准备{value, done}，保存await reader.read()
      const {value, done} = await reader.read();
      // 更新buffer，供本次流程的后续步骤读取
      buffer += decoder.decode(value, {stream:!done});
      // 调用consume，执行此步处理（consume）
      consume();
      // 检查条件 done；成立时执行紧随的分支
      if (done) break;
    }
    // 检查条件 !completed；成立时执行紧随的分支
    if (!completed) throw new Error('连接中断，回答未完成，请重新提问。');
  } finally {
    // 等待调用reader.cancel().catch，执行此步处理（reader.cancel().catch）
    await reader.cancel().catch(() => {}); reader.releaseLock();
  }
}

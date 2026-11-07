// 前端单元检查：模拟必要对象验证客户端行为，不启动服务或调用真实模型。

const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('static/stream.js','utf8');
async function run(text, expectedError=false) {
  const bytes = new TextEncoder().encode(text);
  // 真实页面用 localStorage 保存会话号；这里给最小替身，避免测试因宿主对象缺失而失败。
  const storage = new Map();
  const context = vm.createContext({
    TextDecoder,
    crypto: {randomUUID: () => 'test-session-id'},
    localStorage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value)},
    fetch: async () => new Response(new ReadableStream({
    start(controller) {for (const byte of bytes) controller.enqueue(Uint8Array.of(byte)); controller.close();}
  }))});
  vm.runInContext(source, context);
  const events = [];
  if (expectedError) await assert.rejects(() => context.readAnswerStream({}, e => events.push(e)));
  else await context.readAnswerStream({}, e => events.push(e));
  return events;
}
(async () => {
  const events = await run('data: {"type":"delta","text":"中文"}\n\ndata: {"type":"done","result":{}}\n\n');
  // 断言本测试的预期行为：assert.equal(events[0].text,'中文')
  assert.equal(events[0].text,'中文'); assert.equal(events[1].type,'done');
  await run('data: {"type":"delta","text":"未完成"}\n\n', true);
  await run('data: {"type":"error","message":"引用错误"}\n\n', true);
  console.log('流客户端：逐字节UTF-8分包、完成、中断和错误事件通过');
})().catch(error => {console.error(error); process.exitCode=1;});

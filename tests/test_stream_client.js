// 前端单元检查：模拟必要对象验证客户端行为，不启动服务或调用真实模型。

// 准备fs，保存require('fs')；准备vm，保存require('vm')；准备assert，保存require('assert')
const fs = require('fs'), vm = require('vm'), assert = require('assert');
// 准备source，保存fs.readFileSync('static/stream.js','utf8')
const source = fs.readFileSync('static/stream.js','utf8');
async function run(text, expectedError=false) {
  // 准备bytes，保存new TextEncoder().encode(text)
  const bytes = new TextEncoder().encode(text);
  // 准备context，保存vm.createContext({TextDecoder, fetch: async () => new Response(new ReadableStream({ start(
  const context = vm.createContext({TextDecoder, fetch: async () => new Response(new ReadableStream({
    start(controller) {for (const byte of bytes) controller.enqueue(Uint8Array.of(byte)); controller.close();}
  }))});
  // 调用vm.runInContext，执行此步处理（vm.runInContext）
  vm.runInContext(source, context);
  // 准备events，保存[]
  const events = [];
  // 检查条件 expectedError；成立时执行紧随的分支
  if (expectedError) await assert.rejects(() => context.readAnswerStream({}, e => events.push(e)));
  else await context.readAnswerStream({}, e => events.push(e));
  // 返回events，结束当前函数的这次调用
  return events;
}
// 调用(async () => { const events = await run('data: {"type":"delta","text":"中文"}\n\ndata: {"typ，执行此步处理（(async () => { const events = await run('data: {"type":"delta","text":"中文"}\n\ndata: {"typ）
(async () => {
  // 准备events，保存await run('data: {"type":"delta","text":"中文"}\n\ndata: {"type":"done","result":{}}\n\n')
  const events = await run('data: {"type":"delta","text":"中文"}\n\ndata: {"type":"done","result":{}}\n\n');
  // 断言本测试的预期行为：assert.equal(events[0].text,'中文')
  assert.equal(events[0].text,'中文'); assert.equal(events[1].type,'done');
  // 等待调用run，执行此步处理（run）
  await run('data: {"type":"delta","text":"未完成"}\n\n', true);
  // 等待调用run，执行此步处理（run）
  await run('data: {"type":"error","message":"引用错误"}\n\n', true);
  // 调用console.log，执行此步处理（console.log）
  console.log('流客户端：逐字节UTF-8分包、完成、中断和错误事件通过');
})().catch(error => {console.error(error); process.exitCode=1;});

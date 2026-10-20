// 前端单元检查：模拟必要对象验证客户端行为，不启动服务或调用真实模型。

// 准备fs，保存require('fs')；准备vm，保存require('vm')；准备assert，保存require('assert')
const fs = require('fs'), vm = require('vm'), assert = require('assert');
// 准备source，保存fs.readFileSync('static/ui.js','utf8')
const source = fs.readFileSync('static/ui.js','utf8');
// 最小DOM验证真实展示器的元素类型与文本安全，不运行页面初始化或网络。
class Element {
  constructor(tag, text='') {this.tag=tag;this.children=[];this._text=text;this.attrs={};}
  append(...children) {this.children.push(...children);}
  replaceChildren(...children) {this.children=children;this._text='';}
  setAttribute(k,v) {this.attrs[k]=v;}
  set textContent(v) {this._text=v;this.children=[];}
  get textContent() {return this._text + this.children.map(c=>c.textContent).join('');}
}
// 准备document，保存{createElement: tag=>new Element(tag),createTextNode:text=>new Element('#text',text)}
const document = {createElement: tag=>new Element(tag),createTextNode:text=>new Element('#text',text)};
// 准备context，保存vm.createContext({document})
const context = vm.createContext({document}); vm.runInContext(source,context);
// 准备draft：生成过程中暂存的回答文本
const draft = text=>context.formattedDraft(text);
// 断言本测试的预期行为：assert.equal(draft('**重点'),'**重点**')
assert.equal(draft('**重点'),'**重点**');
// 断言本测试的预期行为：assert.equal(draft('**'),'')
assert.equal(draft('**'),'');
// 断言本测试的预期行为：assert.equal(draft('开头 **'),'开头 ')
assert.equal(draft('开头 **'),'开头 ');
// 断言本测试的预期行为：assert.equal(draft('**重点*'),'**重点**')
assert.equal(draft('**重点*'),'**重点**');
// 断言本测试的预期行为：assert.equal(draft('依据[id: abc123'),'依据')
assert.equal(draft('依据[id: abc123'),'依据');
// 断言本测试的预期行为：assert.equal(draft('依据[i'),'依据')
assert.equal(draft('依据[i'),'依据');
// 断言本测试的预期行为：assert.equal(draft('依据[ abcdef0123456789 ]'),'依据[abcdef0123456789]')
assert.equal(draft('依据[ abcdef0123456789 ]'),'依据[abcdef0123456789]');
// 断言本测试的预期行为：assert.equal(draft('变量 `value'),'变量 `value`')
assert.equal(draft('变量 `value'),'变量 `value`');
// 断言本测试的预期行为：assert.equal(draft('```python\na[0] **原文\n```'),'```python\na[0] **原文\n```')
assert.equal(draft('```python\na[0] **原文\n```'),'```python\na[0] **原文\n```');
function descendants(node) {return [node,...node.children.flatMap(descendants)];}
// 准备target，保存new Element('div')
const target = new Element('div');
// 调用context.richText，执行此步处理（context.richText）
context.richText(target,draft('## 标题\n- **正在输出的重点'),'');
// 断言本测试的预期行为：assert(descendants(target).some(n=>n.tag==='h3' && n.textContent==='标题'))
assert(descendants(target).some(n=>n.tag==='h3' && n.textContent==='标题'));
// 断言本测试的预期行为：assert(descendants(target).some(n=>n.tag==='li'))
assert(descendants(target).some(n=>n.tag==='li'));
// 断言本测试的预期行为：assert(descendants(target).some(n=>n.tag==='strong' && n.textContent==='正在输出的重点'))
assert(descendants(target).some(n=>n.tag==='strong' && n.textContent==='正在输出的重点'));
// 断言本测试的预期行为：assert(!target.textContent.includes('**'))
assert(!target.textContent.includes('**'));
// 调用context.richText，执行此步处理（context.richText）
context.richText(target,draft('<img src=x onerror=alert(1)>'),null);
// 断言本测试的预期行为：assert(!descendants(target).some(n=>n.tag==='img'))
assert(!descendants(target).some(n=>n.tag==='img'));
// 调用console.log，执行此步处理（console.log）
console.log('流式排版：分包加粗/行内代码/引用、代码块保真、标题列表和HTML安全通过');

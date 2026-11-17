// 无浏览器依赖的安全渲染及流式分包测试：node --test test_frontend.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function node(tag = '') {
  return { tag, children: [], textContent: '',
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; }
  };
}
const context = { window: {}, TextDecoder, document: {
  createDocumentFragment: () => node(), createElement: tag => node(tag),
  createTextNode: text => ({ textContent: text, children: [] })
} };
vm.runInNewContext(fs.readFileSync('frontend/notice-view.js', 'utf8'), context);
const view = context.window.NoticeView;
const text = item => item.textContent + item.children.map(text).join('');
test('only feature text is bold, nested brackets and unsafe HTML stay intact', () => {
  const output = node();
  const source = '公开原文（相当于获取图像（含彩色）并保存），其余（说明）。（相当于<img onerror=alert(1)>）';
  view.renderDraft(output, source);
  assert.equal(text(output), source);
  const bold = output.children[0].children.filter(item => item.tag === 'strong');
  assert.equal(bold.length, 2);
  assert.equal(bold[0].textContent, '获取图像（含彩色）并保存');
  assert.equal(bold[1].textContent, '<img onerror=alert(1)>');
  view.renderDraft(output, '正文（相当于未闭合');
  assert.equal(text(output), '正文（相当于未闭合');
});
test('SSE handles arbitrary UTF-8 chunk boundaries and heartbeat frames', async () => {
  const raw = ': heartbeat\n\nevent: progress\r\ndata: {"detail":"正在生成"}\r\n\r\nevent: result\ndata: {"draft":"正文"}\n\n';
  const bytes = new TextEncoder().encode(raw);
  const stream = new ReadableStream({ start(controller) {
    for (let i = 0; i < bytes.length; i += 3) controller.enqueue(bytes.slice(i, i + 3));
    controller.close();
  } });
  const events = [];
  await view.readEvents(new Response(stream), (name, data) => events.push([name, data]));
  assert.equal(events.length, 2);
  assert.equal(events[0][1].detail, '正在生成');
  assert.equal(events[1][1].draft, '正文');
});

// 小型原生渲染工具：不解析 Markdown，不把模型输出当作 HTML 执行。
window.NoticeView = {
  renderDraft(element, text) {
    const fragment = document.createDocumentFragment();
    let cursor = 0;
    const pattern = /（\s*相当于\s*/g;
    let match;
    while ((match = pattern.exec(text))) {
      let depth = 1;
      let end = pattern.lastIndex;
      for (; end < text.length; end++) {
        if (text[end] === '（') depth++;
        if (text[end] === '）' && --depth === 0) break;
      }
      if (depth !== 0) break;
      fragment.append(document.createTextNode(text.slice(cursor, pattern.lastIndex)));
      const strong = document.createElement('strong');
      strong.textContent = text.slice(pattern.lastIndex, end);
      fragment.append(strong);
      cursor = end;
      pattern.lastIndex = end + 1;
    }
    fragment.append(document.createTextNode(text.slice(cursor)));
    element.replaceChildren(fragment);
  },

  async readEvents(response, onEvent) {
    if (!response.body) throw new Error('浏览器不支持进度接收，请使用新版浏览器');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    function consume() {
      let separator;
      while ((separator = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, separator.index);
        buffer = buffer.slice(separator.index + separator[0].length);
        let name = 'message';
        const lines = [];
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith('event:')) name = line.slice(6).trim();
          if (line.startsWith('data:')) lines.push(line.slice(5).trimStart());
        }
        if (lines.length) onEvent(name, JSON.parse(lines.join('\n')));
      }
    }
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        consume();
      }
      buffer += decoder.decode();
      if (buffer.trim()) { buffer += '\n\n'; consume(); }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }
};

"""统一封装反代请求和响应解析，供 API 与连通性测试复用。"""
import json
import os
import re
import urllib.error
import urllib.request
import time
from collections.abc import Callable


def call_model(messages: list[dict[str, str]], on_progress: Callable[[int], None] | None = None) -> str:
    # 兼容 CLIProxyAPI 的 OpenAI Chat Completions 接口。
    base = os.getenv("API_BASE_URL", "").rstrip("/")
    model = os.getenv("MODEL", "")
    if not base or not model or model == "your-model-id":
        raise ValueError("请先在 .env 中配置 API_BASE_URL 和 MODEL")
    if not re.fullmatch(r"https?://[^\s]+", base):
        raise ValueError("API_BASE_URL 必须是 http:// 或 https:// 地址")
    url = base + ("/chat/completions" if not base.endswith("/chat/completions") else "")
    payload = json.dumps({"model": model, "messages": messages, "temperature": 0.2, "stream": on_progress is not None}, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if os.getenv("API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["API_KEY"]
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=int(os.getenv("API_TIMEOUT", "180"))) as res:
            if on_progress is not None and 'text/event-stream' in res.headers.get('Content-Type', ''):
                return read_model_stream(res, on_progress)
            body = json.load(res)
    except urllib.error.HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", "replace")
        key = os.getenv("API_KEY", "")
        if key:
            detail = detail.replace(key, "[REDACTED]")
        raise ValueError(f"模型接口返回 HTTP {exc.code}：{detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError(f"无法连接模型接口：{exc}") from exc
    try:
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            raise KeyError("content")
        if on_progress:
            on_progress(len(content))
        return content.strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("模型接口响应缺少 choices[0].message.content") from exc


def read_model_stream(response, on_progress: Callable[[int], None]) -> str:
    """读取上游 SSE，只报告正文字符数，不暴露内部推理或原文片段。"""
    chunks = []
    count = 0
    reported = 0.0
    finished = False
    for line in response:
        line = line.decode('utf-8').strip()
        if not line.startswith('data:'):
            continue
        data = line[5:].strip()
        if data == '[DONE]':
            finished = True
            break
        if not data:
            continue
        event = json.loads(data)
        if event.get('error'):
            raise ValueError('模型流返回错误，请检查反代服务日志')
        choices = event.get('choices') or []
        if not choices:
            continue
        choice = choices[0]
        part = choice.get('delta', {}).get('content') or ''
        if isinstance(part, str) and part:
            chunks.append(part)
            count += len(part)
            # 限流进度回调，不为每个 token 触发网络及浏览器更新。
            if time.monotonic() - reported >= 0.5:
                on_progress(count)
                reported = time.monotonic()
        reason = choice.get('finish_reason')
        if reason in ('length', 'content_filter'):
            raise ValueError('模型输出被截断或过滤，未得到完整评述，请缩小评述范围后重试')
        if reason is not None:
            finished = True
    if not finished:
        raise ValueError('模型连接提前中断，未得到完整评述，请重试')
    result = ''.join(chunks).strip()
    if not result:
        raise ValueError('模型未返回正文')
    on_progress(count)
    return result



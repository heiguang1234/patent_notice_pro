"""将同步生成服务的真实阶段通过 SSE 推送给浏览器。"""
import asyncio
import json
import logging
import os

from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from backend.services.drafting import generate_draft


def progress_response(files: list, scope: str) -> StreamingResponse:
    async def events():
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def report(data):
            loop.call_soon_threadsafe(queue.put_nowait, ('progress', data))

        async def work():
            try:
                result = await run_in_threadpool(generate_draft, files, scope, report)
                await queue.put(('result', result))
            except Exception as exc:
                logging.exception('流式通知书生成失败')
                detail = str(exc) if isinstance(exc, ValueError) else '生成失败，请检查后端日志'
                key = os.getenv('API_KEY', '')
                if key:
                    detail = detail.replace(key, '[REDACTED]')
                await queue.put(('error', {'error': detail}))

        task = asyncio.create_task(work())
        try:
            yield encode('progress', {'stage': 'upload', 'detail': f'后端已收到{len(files)}份文件'})
            while True:
                try:
                    name, data = await asyncio.wait_for(queue.get(), timeout=10)
                except asyncio.TimeoutError:
                    # 心跳仅维持连接，不表示模型完成了新步骤。
                    yield ': heartbeat\n\n'
                    continue
                yield encode(name, data)
                if name in ('result', 'error'):
                    break
        finally:
            # 关闭浏览器连接时停止推送；底层同步 HTTP 请求依其超时结束。
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(events(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


def encode(name: str, data: dict) -> str:
    return f'event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'

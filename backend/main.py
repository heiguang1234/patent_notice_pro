"""后端 API 入口：处理上传和跨域请求，业务逻辑位于 services。"""
import logging
import os
import re
from fastapi import FastAPI, File, Form, UploadFile, Request
from starlette.datastructures import UploadFile as FormUploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from backend.config import MAX_FILE, load_env
from backend.services.drafting import generate_draft
from backend.progress import progress_response

load_env()
app = FastAPI(title="专利审查意见通知书 API", version="1.0.0")
# 前端使用独立端口，只允许明确列出的本地前端来源。
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("FRONTEND_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(","),
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)


@app.get("/api/status")
def status() -> dict:
    """仅返回配置状态和模型名，密钥不发送到浏览器。"""
    model = os.getenv("MODEL", "")
    return {"configured": bool(os.getenv("API_BASE_URL") and model and model != "your-model-id"), "model": model}


@app.post("/api/draft")
async def draft(request: Request, application: UploadFile = File(...), comparison1: UploadFile = File(...),
                comparison2: UploadFile | None = File(None), comparison3: UploadFile | None = File(None),
                scope: str = Form("")):
    """限制上传大小；在线程池执行耗时的解析和同步模型请求。"""
    # 编号来自输入框字段名；缺少对比文件2时，对比文件3仍保持编号3。
    slots = [("申请文件", application), ("对比文件1", comparison1),
             ("对比文件2", comparison2), ("对比文件3", comparison3)]
    uploads = [upload for _, upload in slots if upload is not None]
    try:
        # 兼容固定编号1—3，并接收动态添加的4—10号上传框。
        form = await request.form()
        extra_slots = []
        for name in form:
            if not name.startswith("comparison"):
                continue
            match = re.fullmatch(r"comparison([1-9]|10)", name)
            if not match:
                raise ValueError("对比文件编号须为1至10")
            if len(form.getlist(name)) != 1:
                raise ValueError("每个对比文件编号仅能上传一份文件")
            index = int(match.group(1))
            if index > 3:
                upload = form[name]
                if not isinstance(upload, FormUploadFile):
                    raise ValueError(f"对比文件{index}必须为文件")
                extra_slots.append((index, upload))
                uploads.append(upload)
        slots.extend((f"对比文件{index}", upload) for index, upload in sorted(extra_slots))
        files = []
        for label, upload in slots:
            if upload is None:
                continue
            if not upload.filename:
                raise ValueError("上传文件缺少文件名")
            data = await upload.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                return JSONResponse(status_code=413, content={"error": f"{upload.filename} 超过 20 MB"})
            files.append((label, upload.filename, data))
        if request.query_params.get('stream') == 'true':
            return progress_response(files, scope)
        return await run_in_threadpool(generate_draft, files, scope)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception:
        logging.exception("通知书生成失败")
        return JSONResponse(status_code=500, content={"error": "服务器处理失败，请查看后端日志"})
    finally:
        # 大文件可能由框架暂存至临时目录，请求结束立即关闭清理。
        for upload in uploads:
            await upload.close()

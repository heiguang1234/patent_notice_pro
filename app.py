"""兼容原启动命令；后端实现位于 backend/。"""
import os
import uvicorn
from backend.config import load_env

if __name__ == "__main__":
    load_env()
    uvicorn.run("backend.main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8765")))

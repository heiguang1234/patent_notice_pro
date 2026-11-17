"""配置加载：密钥只在后端读取。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_FILE = 20 * 1024 * 1024
MAX_TEXT = 60_000
MAX_TOTAL_TEXT = 120_000


def load_env() -> None:
    # 从项目根目录加载配置；已有系统环境变量优先。
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))



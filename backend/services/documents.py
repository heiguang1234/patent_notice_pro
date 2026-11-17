"""从上传内容提取文本，并生成可追溯的引用编号。"""
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from backend.config import MAX_TEXT


def extract_text(filename: str, data: bytes) -> str:
    # 按扩展名选择解析器；扫描 PDF 需先进行 OCR。
    suffix = Path(filename).suffix.lower()
    if suffix in (".txt", ".md"):
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                pass
        raise ValueError(f"{filename}：无法识别文本编码")
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                root = ET.fromstring(zf.read("word/document.xml"))
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paragraphs = []
            for p in root.iter(ns + "p"):
                value = "".join(t.text or "" for t in p.iter(ns + "t"))
                if value.strip():
                    paragraphs.append(value)
            return "\n".join(paragraphs)
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            raise ValueError(f"{filename}：DOCX 文件无效") from exc
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF 提取需要安装依赖：python -m pip install -r requirements.txt") from exc
        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(f"[第 {i} 页]\n{page.extract_text() or ''}" for i, page in enumerate(reader.pages, 1))
        except Exception as exc:
            raise ValueError(f"{filename}：PDF 无法读取") from exc
    raise ValueError(f"{filename}：仅支持 PDF、DOCX、TXT、MD")


def numbered_text(text: str, label: str, limit: int = MAX_TEXT) -> tuple[str, bool]:
    # 保留稳定的原文段落编号，截断后仍能定位引用。
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 不合并正文内部空白或改写原文，仅添加段落定位标记。
    blocks = [x.strip() for x in re.split(r"\n\s*\n|(?<=。)\s*\n", text)]
    blocks = [x for x in blocks if x]
    if not blocks:
        raise ValueError(f"{label}：没有提取到文字；扫描版 PDF 请先 OCR")
    lines = [f"[{label} §{i}] {block}" for i, block in enumerate(blocks, 1)]
    result = "\n".join(lines)
    if len(result) <= limit:
        return result, False
    # 保留首尾完整段落，避免截断一个段落造成引用失真。
    half = limit // 2
    head = []
    tail = []
    size = 0
    for line in lines:
        if size + len(line) > half:
            break
        head.append(line)
        size += len(line) + 1
    size = 0
    for line in reversed(lines):
        if size + len(line) > half:
            break
        tail.append(line)
        size += len(line) + 1
    return "\n".join(head + ["[中间内容因长度限制省略]"] + list(reversed(tail))), True



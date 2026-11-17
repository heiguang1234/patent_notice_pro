"""编排文件解析、引用编号和模型生成，不依赖 Web 框架。"""
from pathlib import Path
from collections.abc import Callable
from backend.config import MAX_FILE, MAX_TEXT, MAX_TOTAL_TEXT
from backend.services.documents import extract_text, numbered_text
from backend.services.model_client import call_model
from backend.services.prompts import SYSTEM
from backend.services.validation import check_quotes
from backend.services.formatting import format_notice


def generate_draft(files: list[tuple[str, str, bytes]], scope: str,
                   progress: Callable[[dict], None] | None = None) -> dict:
    """使用上传框明确指定的编号，不让模型猜测文件身份。"""
    if not 2 <= len(files) <= 11:
        raise ValueError("需上传申请文件和1至10份对比文件")
    documents, truncated = [], []
    # 原文完整送入模型。超过上下文预算时停止，绝不静默截掉证据。
    total = 0
    def report(stage: str, detail: str, **extra):
        if progress:
            progress({"stage": stage, "detail": detail, **extra})

    for index, (label, filename, data) in enumerate(files, 1):
        report('extract', f'正在提取{label}：{filename}', current=index, total=len(files))
        if len(data) > MAX_FILE:
            raise ValueError(f"{filename} 超过 20 MB")
        source, shortened = numbered_text(extract_text(filename, data), label, MAX_TEXT)
        if shortened:
            raise ValueError(f"{label} 超过 {MAX_TEXT} 字符预算，无法完整提交原文，请拆分材料后重试")
        total += len(source)
        if total > MAX_TOTAL_TEXT:
            raise ValueError("全部文件超过 120000 字符预算，无法完整提交原文，请拆分材料后重试")
        documents.append({"label": label, "filename": Path(filename).name, "text": source})
        if shortened:
            truncated.append(label)
    labels = "、".join(doc["label"] for doc in documents if doc["label"] != "申请文件")
    content = f"本次实际上传的对比文件为：{labels}。只使用这些文件，按实际数量选择论证组合，不套用未上传文件。\n"
    content += "审查范围及适用规则：\n" + (scope.strip()[:4000] or "未提供。不得臆测法域、审查阶段及具体法条。")
    for doc in documents:
        content += f"\n\n=== {doc['label']}：{doc['filename']} ===\n{doc['text']}"
    report('prepare', f'已提取{len(files)}份文件，共{total}个字符，正在整理模型输入')
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]
    report('model', '已提交模型，等待生成正文；此阶段耗时取决于材料长度与上游负载')
    if progress:
        draft = call_model(messages, on_progress=lambda count: report('model', f'已接收{count}个正文字符，模型仍在生成', characters=count))
    else:
        draft = call_model(messages)
    # 先检查未改写的直接引文，再去掉内部标记并整理中文纯文本。
    report('verify', '模型已返回，正在逐字核查引文并整理中文段落格式')
    warnings = check_quotes(draft, documents)
    return {"draft": format_notice(draft), "documents": documents, "truncated": truncated,
            "warnings": warnings}

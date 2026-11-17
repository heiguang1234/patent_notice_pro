"""直接引用核查：仅忽略排版空白，不忽略文字差异。"""
import re


def check_quotes(draft: str, documents: list[dict]) -> list[str]:
    """检查模型用约定引号标记的原文；语义对应及论证仍需人工复核。"""
    normalize = lambda value: re.sub(r"\s+", "", value)
    # 跨相邻段落引用时，去掉程序插入的定位标记再匹配，避免误报。
    # 不移除原文真实段号，仍要求所引文字连续出现，不允许拼接不连续内容。
    def source_text(document: dict) -> str:
        text = re.sub(r"(?m)^\[(?:申请文件|对比文件\d+) §\d+\] ", "", document["text"])
        return normalize(text)

    application = [source_text(d) for d in documents if d["label"] == "申请文件"]
    comparisons = [source_text(d) for d in documents if d["label"] != "申请文件"]
    warnings = []
    for opening, closing, sources, kind in [("「", "」", comparisons, "对比文件"), ("『", "』", application, "申请文件")]:
        quotes = re.findall(re.escape(opening) + r"(.*?)" + re.escape(closing), draft, re.S)
        if not quotes:
            warnings.append(f"未检测到{kind}的直接引用标记，无法自动核查原文，请人工复核。")
        for quote in quotes:
            if not normalize(quote) or not any(normalize(quote) in text for text in sources):
                warnings.append(f"以下{kind}引文未在上传原文中逐字找到：{quote[:100]}")
    return warnings

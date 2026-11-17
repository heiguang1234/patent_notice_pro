"""将模型内部带核查标记的草稿转换为可直接使用的中文纯文本。"""
import re


def format_notice(text: str) -> str:
    """去除排版标记，规范中文标点，保留数字小数点及技术标识。"""
    text = re.sub(r"^\s*```[^\n]*\n?|^\s*```\s*$", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"\[([^\]\n]+)\]\([^\n)]*\)", r"\1", text)
    for marker in ("**", "__", "`", "「", "」", "『", "』"):
        text = text.replace(marker, "")
    # 内部引用定位仅供核查，通知书正文使用“参见说明书第……段”等句式。
    text = re.sub(r"\[(?:申请文件|对比文件\d+)\s*§\d+\]", "", text)
    text = text.translate(str.maketrans({"(": "（", ")": "）", ",": "，", ";": "；", ":": "：", "?": "？", "!": "！", '"': '', '“': '', '”': ''}))
    # 只规范已有数字段号，不把提取文本编号冒充原件说明书段号。
    text = re.sub(r"参见(?:【)?说明书第\s*[【\[]\s*([\d\s、，,至到—–\-]+)\s*[】\]]\s*段(?:】)?", r"参见说明书第【\1】段", text)
    text = re.sub(r"参见说明书第\s*(\d+(?:(?:至|到|—|–|-|、|，)\d+)*)\s*段", r"参见说明书第【\1】段", text)
    # 保护 0.5、S2.1、Mask_Rcnn 等技术标识中的句点。
    text = re.sub(r"(?<![A-Za-z0-9])\.|\.(?![A-Za-z0-9])", "。", text)
    # 删除“（相当于”前的句号、逗号、分号等，直接接原文。
    text = re.sub(r"[，。；：、！？,. ;:!?\s]+(?=（\s*相当于)", "", text)
    # 若模型仍添加开场说明，只保留从权利要求1正式评述起的内容。
    start = re.search(r"(?m)^\s*(?:\d+、\s*)?权利要求\s*1\s*要求保护", text)
    if start:
        text = text[start.start():].lstrip()
    # 清理句末标点紧接下一分句时产生的“。，”等排版错误。
    text = re.sub(r"[。；]\s*，", "，", text)
    # 仅整理权利要求1的区别特征及后续论述，不展开从属项简评。
    dependent = re.search(r"(?m)^\s*\d+、\s*(?:从属)?权利要求(?!\s*1\s*要求保护)", text)
    end = dependent.start() if dependent else len(text)
    first, rest = text[:end], text[end:]
    difference = re.search(r"(?:该权利要求|权利要求1)与对比文件1相比，区别技术特征在于：", first)
    if difference:
        prefix = first[:difference.start()].rstrip()
        reasoning = first[difference.end():]
        problem = re.search(r"基于上述区别技术特征", reasoning)
        if problem:
            features = reasoning[:problem.start()]
            features = re.sub(r"\s*（(\d+)）", r"\n\n（\1）", features).strip()
            reasoning = features + "\n\n" + reasoning[problem.start():].strip()
        reasoning = re.sub(r"(?<=[。；])\s*(?=(?:对于|至于)区别技术特征)", "\n\n", reasoning)
        first = prefix + "\n\n该权利要求与对比文件1相比，区别技术特征在于：\n\n" + reasoning.strip() + "\n\n"
        text = first + rest.lstrip()
    return text.strip()

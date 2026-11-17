"""手动测试写作格式：使用虚构材料调用真实模型，不用于实际审查。"""
from backend.config import load_env
from backend.services.drafting import generate_draft


if __name__ == "__main__":
    load_env()
    files = [
        ("申请文件", "application.txt", "权利要求书\n\n1.一种图像采集方法，其特征在于，包括：利用摄像头获取图像；将所述图像存入存储器。\n\n2.根据权利要求1所述的方法，其特征在于，所述存储器为非易失性存储器。".encode()),
        ("对比文件1", "d1.txt", "一种影像获取方法。测试文献，公开号待核实。\n\n[0001] 该方法通过相机拍摄获得影像数据。".encode()),
        ("对比文件2", "d2.txt", "一种影像存储方法。测试文献，公开号待核实。\n\n[0002] 将拍摄所得影像保存在非易失性存储设备中，使得断电后仍可读取影像。".encode()),
    ]
    result = generate_draft(files, "这是虚构的格式测试材料，仅评述权利要求1、2。")
    print(result["draft"])
    assert result["draft"].startswith("1、权利要求1要求保护")
    assert "其特征在于" not in result["draft"].split("对比文件1", 1)[0]
    assert "**" not in result["draft"]
    assert "相当于利用摄像头获取图像" in result["draft"]
    assert '公开了一种影像获取方法（相当于一种图像采集方法）' in result['draft']
    assert '参见说明书第【' in result['draft']
    assert not result["warnings"], result["warnings"]
    print("\nPASS: 主题名称、技术含义对应、纯文本及引文检查通过。")

import sys
import pytest
from pathlib import Path

# 设置 UTF-8 输出
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 添加工程根目录到 sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from writers.script_generator import ScriptGenerator

@pytest.mark.integration
def test_script_generation():
    print("▶ 测试 1: 验证爆款分镜脚本生成...")
    generator = ScriptGenerator()
    
    script = generator.generate_script(
        topic_or_content="为什么自律的人都起不来床？",
        style="干货科普"
    )
    
    print(f"✅ 生成标题: 《{script.title}》")
    print(f"✅ 风格定位: {script.tone_style}, 推荐BGM: {script.bgm_type}")
    print(f"✅ 标签: {script.tags}")
    print(f"✅ 分镜数量: {len(script.scenes)}")
    
    for sc in script.scenes:
        print(f"  [分镜 {sc.scene_index}] 转场: {sc.transition}")
        print(f"    口播: {sc.voiceover_text}")
        print(f"    视觉搜索词: {sc.visual_keywords}")
        print(f"    高亮词: {sc.caption_highlight}")
        
    assert len(script.scenes) >= 3, "分镜数量应不少于3个"
    assert script.title, "标题不能为空"
    print("\n🎉 脚本生成模块验证通过！")

if __name__ == "__main__":
    test_script_generation()

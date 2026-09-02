"""
AI Traffic Pipeline - 全自动爆款内容挖掘与短视频生成系统 CLI & Web Studio 统一入口
"""
import sys
import os
import argparse
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from core.orchestrator import VideoPipelineRunner
from crawlers.hot_topics import HotTopicCrawler, CATEGORY_NAMES
from config.settings import VOICE_PRESETS
from core.logging_config import configure_logging

console = Console(legacy_windows=False, force_terminal=True)

def show_banner():
    banner = """
    ==================================================================
      >>> AI Traffic Pipeline Studio - 工业级爆款短视频创作中心 <<<
      垂直领域细分 | 多平台共振登顶 | LLM 分镜 | 9:16 工业级渲染
    ==================================================================
    """
    console.print(f"[bold cyan]{banner}[/bold cyan]")

def handle_list_trends(category: str = "all"):
    cat_title = CATEGORY_NAMES.get(category, "全网综合")
    console.print(f"\n[bold yellow][*] 正在抓取并计算【{cat_title}】过去 24 小时高热爆款...[/bold yellow]\n")
    trends = HotTopicCrawler.get_categorized_trends(category=category, limit=12)
    
    table = Table(title=f"🏆 实时热榜 - {cat_title} (多平台交叉共振)", show_header=True, header_style="bold magenta")
    table.add_column("排名", style="dim", width=6)
    table.add_column("领域分类", width=12)
    table.add_column("数据来源 / 共振平台", width=22)
    table.add_column("爆款标题 / 话题", style="bold white")
    table.add_column("爆发指数", justify="right", style="green")
    
    for i, t in enumerate(trends, 1):
        if t.is_resonance:
            plat_str = f"[bold yellow]🔥共振[{'+'.join(t.resonating_platforms)}][/bold yellow]"
            rank_str = f"[bold red]★ {i}[/bold red]"
        else:
            plat_str = f"[dim]{t.source_platform}[/dim]"
            rank_str = str(i)
            
        cat_badge = f"[cyan]{t.category_name}[/cyan]"
        table.add_row(rank_str, cat_badge, plat_str, t.title, f"[bold]{t.hot_score:.1f}[/bold]")
        
    console.print(table)
    console.print("\n[dim]💡 提示：可使用 --category [tech|finance|social|entertainment|growth|resonance] 切换细分领域[/dim]\n")

def start_web_studio(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    console.print(Panel(
        f"[bold green]🚀 Web Studio 已启动！[/bold green]\n\n"
        f"👉 本地访问地址: [bold underline cyan]http://{host}:{port}[/bold underline cyan]\n\n"
        f"[dim]包含：多领域热点雷达、多平台共振登顶看板、分镜卡片工作台与 9:16 实时播放器[/dim]",
        title="[STUDIO] 创作工作台服务运行中",
        border_style="cyan"
    ))
    uvicorn.run("web_studio.server:app", host=host, port=port, reload=True, reload_dirs=[str(BASE_DIR)])

def main():
    configure_logging()
    show_banner()
    
    parser = argparse.ArgumentParser(description="AI 爆款短视频自动化生产流水线")
    parser.add_argument("--web", action="store_true", help="启动现代深色玻璃拟态 Web Studio 可视化创作工作台")
    parser.add_argument("--port", type=int, default=8000, help="Web Studio 运行端口 (默认 8000)")
    parser.add_argument("--category", type=str, default="all", choices=list(CATEGORY_NAMES.keys()), help="选择细分领域榜单")
    parser.add_argument("--topic", type=str, default="", help="指定视频创作主题（如：'为什么越自律的人越自由'）")
    parser.add_argument("--auto-trend", action="store_true", help="全自动模式：抓取当前分类 Top 1 爆款热点并一键出片")
    parser.add_argument("--list-trends", action="store_true", help="查看实时爆款热榜")
    parser.add_argument("--voice", type=str, default="yunxi", choices=list(VOICE_PRESETS.keys()), help="选择解说音色预设")
    
    args = parser.parse_args()
    
    if args.web:
        start_web_studio(port=args.port)
        return
        
    if args.list_trends:
        handle_list_trends(category=args.category)
        return
        
    topic = args.topic
    if not topic and not args.auto_trend:
        console.print("[bold green]请选择操作[/bold green]:\n  1. 输入 [bold cyan]web[/bold cyan] 启动可视化工作台\n  2. 直接输入 [bold yellow]创作主题[/bold yellow] 出片\n  3. 直接 [bold white]回车[/bold white] 抓取全网共振 Top 1 爆款自动出片\n👉 ", end="")
        user_input = input().strip()
        if user_input.lower() == "web":
            start_web_studio(port=args.port)
            return
        elif user_input:
            topic = user_input
            
    console.print(Panel(f"[bold cyan]正在启动自动化生产流水线...[/bold cyan]\n目标选题: [bold yellow]{topic if topic else '全网共振 Top 1 爆款'}[/bold yellow]\n解说音色: [bold magenta]{VOICE_PRESETS.get(args.voice, args.voice)}[/bold magenta]", title="[INIT] 任务初始化"))
    
    try:
        result = VideoPipelineRunner.run(
            topic=topic,
            voice=VOICE_PRESETS.get(args.voice, args.voice),
        )
        
        console.print("\n" + "="*60 + "\n")
        console.print("[bold green][DONE] 全流程执行完毕！产出清单：[/bold green]")
        for log in result.get("logs", []):
            console.print(f"  {log}")
            
        final_video = result.get("final_video_path")
        draft_dir = result.get("jianying_draft_path")
        
        summary_text = f"""
[bold green][1] 工业级 1080x1920 MP4 成品 (含转场音效与大标题):[/bold green]
   -> [bold underline]{final_video}[/bold underline]

[bold yellow][2] 剪映草稿工程 (可导入剪映精修):[/bold yellow]
   -> [bold underline]{draft_dir}[/bold underline]
        """
        console.print(Panel(summary_text, title="[FINISH] 成品交付", border_style="green"))
        
    except Exception as e:
        console.print(f"\n[bold red][ERROR] 流水线运行异常:[/bold red] {e}", style="red")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

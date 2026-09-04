"""
高级实景视觉素材检索与 1080x1920 高清摄影/视频多引擎分发器
特性：
1. 真实商用画质直连：内置海量 1080x1920 顶级免版权摄影大片（体育、芯片、手机、摩天大厦、书桌、日出跑道、会议室等）
2. 真实双视频引擎：集成 Pexels + Pixabay 官方 API，优先下发真实 9:16 免版权 4K/1080P 实拍短视频
3. 真实百科纪实图源：集成 Wikimedia Commons 开放媒体库，避免人物假脸
4. 商业关键词智能语义映射：中文/抽象分镜自动转为高命中率纯英文商业摄影检索词
5. 彻底去除“AI 塑料感”：优先实拍视频 > 真实单反摄影 > 纪实原片 > 仅在显式指定时走 AI 生图
"""
from __future__ import annotations

import hashlib
import logging
import os
import random
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from PIL import Image, ImageDraw, ImageFilter

from config.settings import (
    ASSETS_OUTPUT_DIR,
    MEDIA_FETCH_CONCURRENCY,
    PEXELS_API_KEY,
    PIXABAY_API_KEY,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from media.pixabay_client import PixabayMediaClient

logger = logging.getLogger(__name__)

# 常用中文意象与专业商业实拍英文词语义映射表 (大幅提升 Pexels / Pixabay 检索命中率)
COMMERCIAL_QUERY_MAP = [
    # 三体 / 科幻 / 深空 / 宇宙 / 黑暗森林 / 执剑人
    (r"三体|水滴|智子|面壁|执剑|红岸|歌者|降维|二向箔|罗辑|程心|庄颜|大刘", "deep space universe galaxy stars cinematic"),
    (r"宇宙|星空|太空|银河|深空|天体|黑洞|星球|星系|光年", "universe galaxy space starry night milky way"),
    (r"末日|灾难|毁灭|降临|浩劫|绝望|风暴|废墟", "dramatic stormy clouds epic landscape darkness"),
    (r"博弈|抉择|决定|生死|存亡|危机|对抗|算计|谋略", "chess game strategy intense focus dramatic light"),
    (r"按纽|按钮|开关|发射|按下|控制台|核按钮|警报", "pressing button finger control room switch"),
    (r"人性|思考|哲思|命运|沉思|孤独|悲悯|众生", "man thinking portrait serious looking away solitude"),
    (r"科技|未来|赛博|文明|纪元|探索", "futuristic tech cyberpunk neon modern digital"),

    # 体育 / 竞技
    (r"女篮|女足|女性运动|女运动员", "women basketball match court action athlete"),
    (r"男篮|篮球|灌篮|三分球|球场", "basketball game match professional action court"),
    (r"足球|世界杯|球赛|点球|绿茵", "soccer football match tournament athlete stadium"),
    (r"运动|体育|赛事|锦标赛|夺冠|金牌|奖杯", "sports championship athlete victory trophy stadium"),
    (r"跑步|晨跑|马拉松|冲刺|田径", "running marathon athlete track morning finish line"),
    (r"健身|力量|哑铃|硬拉|撸铁|减脂", "gym workout fitness training strength athlete"),
    (r"自律|晨起|冥想|习惯|读书|阅读", "morning routine athlete workout focus meditation book"),

    # 科技 / 芯片 / 算力
    (r"芯片|半导体|光刻|主板|硬件|显卡", "semiconductor microchip motherboard macro technology"),
    (r"算力|服务器|机房|云计算|数据中心", "datacenter server racks modern computing technology"),
    (r"ai|人工智能|算法|深度学习|大模型", "artificial intelligence network modern technology computer"),
    (r"代码|编程|程序员|黑客|软件", "software code computer screen programming developer"),

    # 财经 / 商业 / 职场
    (r"黄金|金条|金价|财富|贵金属", "gold bars bullion treasure luxury finance wealth"),
    (r"股票|股市|k线|交易|基金|行情", "stock market trading chart screen finance bull"),
    (r"搞钱|搞投资|理财|资产|商业模式", "finance modern office investment wealth growth money"),
    (r"经济|通胀|汇率|货币|美元|银行", "global trade skyscraper economy finance banking bank"),
    (r"职场|工位|开会|加班|汇报|ppt", "modern corporate office teamwork discussion business"),
    (r"老板|领导|高管|战略|ceo", "business executive leadership meeting office boardroom"),
    (r"打工|跳槽|简历|求职|HR", "workspace employee laptop coffee focused work career"),

    # 社会 / 情感 / 悬疑
    (r"医院|医生|医疗|手术|健康", "doctor hospital medical healthcare clinic surgeon"),
    (r"城市|街头|车流|夜市|繁华|天际线", "city skyline night traffic crowd street metropolitan"),
    (r"情感|治愈|拥抱|落泪|心碎|晚霞", "heartfelt sunset warm hug emotion calm coffee"),
    # 法律 / 犯罪 / 审判 / 正义 / 纪实
    (r"认罪|庭审|法庭|法官|审判|判决|律师|辩护|被告|原告|法槌|手铐|监狱|罪犯|犯罪|乱港|涉案|公诉|司法|法治", "courtroom trial judge gavel legal justice law"),
    (r"真相|调查|内幕|揭露|黑幕|证据|卷宗|档案|线索", "investigation documents evidence magnifying glass mystery archive"),
    (r"历史|过去|风云|时代|沧桑|岁月|变迁|复盘", "vintage archive newspaper history retro documentary clock"),
]

# 全局项目素材跨实例去重集合 (彻底根除多实例并发时的图库重复下发)
_GLOBAL_PROJECT_USED_ASSETS: Dict[str, set] = {}

# 垂直领域 1080x1920 超清实拍商用大片库 (涵盖 20+ 细分赛道，真实超清竖屏摄影镜头)
CURATED_PHOTO_COLLECTION = {
    "justice": [
        "photo-1589829545856-d10d557cf95f",  # 严肃法庭法槌与法律案卷
        "photo-1453733190028-5615fddf2945",  # 庄严正义法院大楼罗马立柱
        "photo-1505664194779-8beaceb93744",  # 厚重司法典籍与判例
        "photo-1589994965851-a8f479c573a9",  # 正义女神天平与象征
        "photo-1575505586569-646b2ca898fc",  # 签字画押与严谨法律文书
        "photo-1486406146926-c627a92ad1ab",  # 现代化法务摩天大楼
    ],
    "documentary": [
        "photo-1585829365295-ab7cd400c167",  # 复古报纸头条与旧新闻
        "photo-1524995997946-a1c2e315a42f",  # 浩瀚图书馆档案与绝密宗卷
        "photo-1518709268805-4e9042af9f23",  # 昏暗案情分析室与泛黄线索
        "photo-1461360370896-922624d12aa1",  # 老怀表与流逝历史岁月
    ],
    "scifi": [
        "photo-1506703719100-a0f3a48c0f86",  # 壮丽深空星云与星尘
        "photo-1451187580459-43490279c0fa",  # 地球外太空发光视界
        "photo-1446776811953-b23d57bd21aa",  # 太空轨道与深邃宇宙
        "photo-1516339901601-2e1b62dc0c45",  # 银河与深邃星空
        "photo-1462331940025-496dfbfc7564",  # 浩瀚星云与宇宙射电
        "photo-1447433589675-4aaa569f3e05",  # 极夜极光与璀璨星河
        "photo-1502134249126-9f3755a50d78",  # 幽蓝星空与山脉
        "photo-1419242902214-272b3f66ee7a",  # 宇宙星系微光
        "photo-1506443432602-ac2fcd6f54e0",  # 深空神秘星尘
        "photo-1538370965046-79c0d6907d47",  # 璀璨星空与孤独探索
    ],
    "strategy": [
        "photo-1529699211952-734e80c4d42b",  # 国际象棋王见王终局博弈
        "photo-1580541832626-2a7131ee809f",  # 经典黑白棋局深谋远虑
        "photo-1586165368502-1bad197a6461",  # 国际象棋对弈指尖特写
        "photo-1560250097-0b93528c311a",  # 严峻沉思的高管与决策者
        "photo-1507003211169-0a1dd7228f2d",  # 坚毅目光与深沉对峙
        "photo-1534528741775-53994a69daeb",  # 聚光灯下的深沉神情
        "photo-1551836022-d5d88e9218df",  # 决断时刻的手势与眼神
        "photo-1517841905240-472988babdf9",  # 复杂心绪下的沉着特写
    ],
    "sports": [
        "photo-1546519638-68e109498ffc",  # 篮球场专注投篮特写
        "photo-1519766304817-4f37bda74a29",  # 运动员激烈对抗与球场
        "photo-1574629810360-7efbbe195018",  # 足球场激情比赛
        "photo-1517838277536-f5f99be501cd",  # 专注力量举重训练
        "photo-1461896836934-ffe607ba8211",  # 冲刺跑道终点线
        "photo-1534438327276-14e5300c3a48",  # 健身房专注挥汗特写
        "photo-1517649763962-0c623266ddc0",  # 体育馆木地板与球鞋
        "photo-1526676037777-05a232554f77",  # 运动团队击掌与胜利欢呼
    ],
    "tech": [
        "photo-1518770660439-4636190af475",  # 芯片主板特写
        "photo-1519389950473-47ba0277781c",  # 极客笔记本与团队
        "photo-1550751827-4bd374c3f58b",  # 赛博安全与科技蓝光
        "photo-1526374965328-7f61d4dc18c5",  # 矩阵代码与数据流
        "photo-1531297484001-80022131f5a1",  # 现代极简笔记本
        "photo-1451187580459-43490279c0fa",  # 数字地球与全球算力
        "photo-1592478411213-6153e4ebc07d",  # 自动驾驶与未来座舱
        "photo-1581091226825-a6a2a5aee158",  # 机器人与未来工业
        "photo-1618005182384-a83a8bd57fbe",  # 抽象流动算力色彩
        "photo-1620712943543-bcc4688e7485",  # AI 人脑神经网络
        "photo-1634017839464-5c339ebe3cb4",  # 3D 悬浮几何数据球
        "photo-1504639725590-34d0984388bd",  # 程序员深夜代码特写
    ],
    "finance": [
        "photo-1486406146926-c627a92ad1ab",  # 现代化金融大厦仰拍
        "photo-1611974789855-9c2a0a7236a3",  # 股票走势与交易K线
        "photo-1590283603385-17ffb3a7f29f",  # 华尔街与商业中心
        "photo-1450133064473-71024230f91b",  # 商业会议与合作签约
        "photo-1579532537598-459ecdaf39cc",  # 黄金与财富金融
        "photo-1559526324-4b87b5e36e44",  # 现代写字楼全景
        "photo-1565372195458-9de0b320ef04",  # 商业谈判握手
        "photo-1526304640581-d334cdbbf45e",  # 纸币与美元货币流动
        "photo-1642543492481-44e81e3914a7",  # 算账计算器与账本
    ],
    "entertainment": [
        "photo-1470225620780-dba8ba36b745",  # 音乐节舞台灯光与观众
        "photo-1511671782779-c97d3d27a1d4",  # 专业录音棚与麦克风
        "photo-1518709268805-4e9042af9f23",  # 游戏电竞机械键盘
        "photo-1489599849927-2ee91cede3ba",  # 电影院银幕与放映机
        "photo-1514525253161-7a46d19cd819",  # 狂欢派对灯光秀
        "photo-1598488035139-bdbb2231ce04",  # 录影棚摄像机机位
        "photo-1492684223066-81342ee5ff30",  # 聚光灯与红毯现场
        "photo-1501386761578-eac5c94b800a",  # 演唱会万人挥手
    ],
    "celebrity": [
        "photo-1534528741775-53994a69daeb",  # 时尚名媛时尚肖像
        "photo-1507003211169-0a1dd7228f2d",  # 自信青年特写
        "photo-1517841905240-472988babdf9",  # 年轻女性阳光微笑
        "photo-1539571696357-5a69c17a67c6",  # 街头时尚抓拍
        "photo-1524504388940-b1c1722653e1",  # 墨镜潮人侧影
        "photo-1500648767791-00dcc994a43e",  # 成熟商业人士目光
    ],
    "workplace": [
        "photo-1497215728101-856f4ea42174",  # 极简明亮开放式工位
        "photo-1522071820081-009f0129c71c",  # 团队头脑风暴讨论
        "photo-1542744173-8e7e53415bb0",  # 白板战略图解
        "photo-1573496359142-b8d87734a5a2",  # 职场女性专注办公
        "photo-1551836022-d5d88e9218df",  # 咖啡馆移动办公
        "photo-1507679799987-c73779587ccf",  # 西装革履领带整理
    ],
    "drama": [
        "photo-1509281373149-e957c6296406",  # 聚光灯下的戏剧面具
        "photo-1485846234645-a62644f84728",  # 电影打板器特写
        "photo-1536440136628-849c177e76a1",  # 昏暗电影院红色座椅
        "photo-1578836537282-3171d77f8632",  # 舞台帷幕拉开瞬间
        "photo-1478720568477-152d9b164e26",  # 电影放映机光束
    ],
    "mystery": [
        "photo-1509198397868-475647b2a1e5",  # 迷雾森林神秘光线
        "photo-1518709268805-4e9042af9f23",  # 昏暗侦探书房与档案
        "photo-1508700115892-45ecd05ae2ad",  # 赛博朋克雨夜街道
        "photo-1516339901601-2e1b62dc0c45",  # 深邃星空与银河
        "photo-1534447677768-be436bb09401",  # 废弃老建筑光影
    ],
    "growth": [
        "photo-1506126613408-eca07ce68773",  # 清晨日出冥想与自律
        "photo-1499750310107-5fef28a66643",  # 极简木质书桌与暖光
        "photo-1434494878577-86c23bcb06b9",  # 跑步运动与晨光跑道
        "photo-1507842229451-2d79f04eeaa2",  # 温暖图书馆与专注阅读
        "photo-1529699211952-734e80c4d42b",  # 国际象棋战略布局
        "photo-1464822759023-fed622ff2c3b",  # 站在雪山之巅远眺
        "photo-1476480862126-209bfaa8edc8",  # 登高远足步道
        "photo-1517838277536-f5f99be501cd",  # 健身房专注力量训练
    ],
    "social": [
        "photo-1477959858617-67f30bc75b82",  # 繁华都市夜景车流
        "photo-1519494026892-80bbd2d6fd0d",  # 现代医院与专业医疗
        "photo-1497633762265-9d179a990aa6",  # 现代大学校园与书籍
        "photo-1514565131-fce0801e5785",  # 城市暴雨与天气实景
        "photo-1449824913935-59a10b8d2000",  # 城市天际线与桥梁
        "photo-1488521787991-ed7bbaae773c",  # 温暖公益与关怀握手
        "photo-1577495508048-b635879837f1",  # 街头讨论人群
    ],
    "emotions": [
        "photo-1516589178581-6cd7833ae3b2",  # 浪漫晚霞与心动剪影
        "photo-1534447677768-be436bb09401",  # 独自看雨窗台倒影
        "photo-1518495973542-4542c06a5843",  # 阳光穿过树叶微光
        "photo-1499209974431-9dddcece7f88",  # 晨雾中的温暖咖啡
        "photo-1474552226712-ac0f0961a954",  # 温暖拥抱与治愈
    ],
}


class PexelsMediaClient:
    """视觉素材客户端与 1080x1920 真实商用大片分发器 (集成 Pexels + Pixabay + Wikimedia 双引擎)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        pixabay_client: Optional[PixabayMediaClient] = None,
    ):
        self.api_key = api_key or PEXELS_API_KEY
        self.headers = {"Authorization": self.api_key} if self.api_key else {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        self.pixabay_client = pixabay_client or PixabayMediaClient(api_key=PIXABAY_API_KEY)
        self._used_assets_by_project: Dict[str, set] = {}

    def _extract_core_video_query(self, query: str) -> str:
        """
        将长句/复合句提炼为 1~2 个最强实拍高频动名词，极大提升 Pexels / Pixabay 竖屏视频命中率
        """
        q = (query or "").lower()
        if any(w in q for w in ["space", "galaxy", "universe", "stars", "planet", "cosmic"]):
            return "universe"
        if any(w in q for w in ["basketball", "hoop"]):
            return "basketball"
        if any(w in q for w in ["soccer", "football", "stadium"]):
            return "soccer"
        if any(w in q for w in ["running", "marathon", "sprint"]):
            return "running"
        if any(w in q for w in ["gym", "workout", "fitness", "training"]):
            return "gym workout"
        if any(w in q for w in ["chess", "strategy"]):
            return "chess"
        if any(w in q for w in ["button", "switch", "finger"]):
            return "pressing button"
        if any(w in q for w in ["chip", "semiconductor", "microchip"]):
            return "technology"
        if any(w in q for w in ["code", "programming", "software"]):
            return "coding"
        if any(w in q for w in ["stock", "trading", "finance", "gold"]):
            return "stock market"
        if any(w in q for w in ["office", "meeting", "boardroom", "workplace"]):
            return "office meeting"
        if any(w in q for w in ["city", "skyline", "traffic"]):
            return "city night"
        if any(w in q for w in ["hospital", "doctor", "medical"]):
            return "hospital"
        if any(w in q for w in ["thinking", "portrait", "serious", "man"]):
            return "man thinking"
        if any(w in q for w in ["storm", "clouds", "darkness"]):
            return "storm clouds"

        words = [w for w in re.findall(r"[a-zA-Z]{3,}", q) if w not in {"the", "and", "with", "for", "modern", "cinematic"}]
        return " ".join(words[:2]) if words else "commercial lifestyle"

    def _normalize_commercial_query(
        self,
        keywords: List[str],
        image_prompt: Optional[str] = None,
        voiceover_text: str = "",
    ) -> str:
        """
        把中文、抽象词或杂乱短语提炼并翻译为商业摄影实拍高命中率英文检索词。
        """
        combined = f"{' '.join(str(k) for k in keywords)} {image_prompt or ''} {voiceover_text}".lower()

        # 1. 优先匹配商业实拍专业映射表
        for pattern, english_kw in COMMERCIAL_QUERY_MAP:
            if re.search(pattern, combined):
                return english_kw

        # 2. 从已有 image_prompt 中提取纯英文核心实体词
        if image_prompt:
            en_words = re.findall(r"[a-zA-Z]{3,}", image_prompt)
            stop_words = {"the", "and", "with", "for", "vertical", "cinematic", "photorealistic", "ultra", "detailed", "lighting"}
            clean_words = [w for w in en_words if w.lower() not in stop_words]
            if len(clean_words) >= 2:
                return " ".join(clean_words[:4])

        # 3. 兜底提取 keywords 中的英文字符串
        en_candidates = [str(k).strip() for k in keywords if re.match(r"^[a-zA-Z0-9\s\-]+$", str(k).strip())]
        if en_candidates:
            return " ".join(en_candidates[:3])

        return "commercial lifestyle focus"

    def _search_wikimedia_real_photo(
        self,
        query: str,
        voiceover_text: str,
        scene_idx: int,
        project_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        检索 Wikimedia Commons 维基共享媒体库中的真实新闻/百科照片。
        特别适合特定历史事件、体育名人、地理标志，彻底避免 AI 假脸。
        """
        target_name = ""
        combined = f"{query} {voiceover_text}"
        name_match = re.search(r"(姚明|易建联|李金铭|韩旭|李梦|王思雨|郑薇|库里|詹姆斯|科比|乔丹|莫言|马斯克|雷军|周鸿祎|罗辑|刘慈欣)", combined)
        if name_match:
            target_name = name_match.group(1)

        if not target_name:
            return None

        try:
            logger.info("检测到真实人物/专有实体 [%s]，正在检索维基媒体公有领域真实照片...", target_name)
            wiki_api = "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": f"{target_name} portrait filetype:bitmap",
                "gsrlimit": 3,
                "prop": "imageinfo",
                "iiprop": "url|size",
                "format": "json",
            }
            resp = self.session.get(wiki_api, params=params, timeout=6)
            if resp.status_code == 200:
                pages = resp.json().get("query", {}).get("pages", {})
                for _, page in pages.items():
                    info = (page.get("imageinfo") or [{}])[0]
                    img_url = info.get("url")
                    if img_url and (img_url.endswith(".jpg") or img_url.endswith(".png") or img_url.endswith(".jpeg")):
                        save_path = ASSETS_OUTPUT_DIR / f"{project_id}_asset_scene_{scene_idx}.jpg"
                        dl = self.session.get(img_url, timeout=12)
                        if dl.status_code == 200 and len(dl.content) > 10_000:
                            with open(save_path, "wb") as f:
                                f.write(dl.content)
                            logger.info("成功获取 Wikimedia 真实百科实拍原图: %s", target_name)
                            return {
                                "asset_file": str(save_path),
                                "asset_type": "image",
                                "source": "wikimedia_commons_real",
                                "keyword": target_name,
                            }
        except Exception as e:
            logger.warning("Wikimedia 真实素材检索异常: %s", e)

        return None

    def fetch_scene_asset(
        self,
        keywords: List[str],
        scene_idx: int,
        project_id: str,
        duration: float = 4.0,
        prefer_video: bool = True,
        image_prompt: Optional[str] = None,
        explicit_url: Optional[str] = None,
        voiceover_text: str = "",
        scene_type: str = "",
    ) -> Dict[str, Any]:
        """
        获取分镜素材（遵循“去 AI 味、告别静态重复、释放真实视频”的高质感实拍管线）：
        1. 商业实拍检索词智能标准化与核心动词提取
        2. 【第一首选】Pexels / Pixabay 真实 9:16 短视频双引擎
        3. 若明确指定了专属定制图片或真实视频未命中，则使用显式素材
        4. 【第二首选】Wikimedia Commons 真实新闻纪实与人物原图
        5. 【第三首选】Pixabay / Pexels 真实 1080x1920 竖屏摄影大片
        6. 【第四首选】精选 19 大垂直赛道超清单反摄影大片池 (严格按项目去重)
        7. 【保底兜底】若所有真实素材库皆无法匹配，再进入 AI 生图 (Flux/SDXL)
        8. 【终极离线】本地高质感弥散流光
        """
        save_path = ASSETS_OUTPUT_DIR / f"{project_id}_asset_scene_{scene_idx}.jpg"

        # 商业实拍检索词智能标准化
        commercial_query = self._normalize_commercial_query(keywords, image_prompt, voiceover_text)
        logger.info("分镜 #%d 智能提取商业实拍检索词: [%s]", scene_idx, commercial_query)

        # 1. 真实 9:16 动态短视频双引擎 (Pexels -> Pixabay)
        # 注意：即使前端传了默认占位图片 URL，当 prefer_video=True 时，也优先升级为震撼的真实实拍视频！
        if prefer_video and commercial_query:
            # 1.1 Pexels 官方真实视频
            if self.api_key:
                try:
                    res_pexels_v = self._search_pexels(commercial_query, scene_idx, project_id)
                    if res_pexels_v and res_pexels_v.get("asset_type") == "video":
                        logger.info("分镜 #%d 成功命中 Pexels 真实视频", scene_idx)
                        return res_pexels_v
                except Exception as e:
                    logger.warning("Pexels 视频检索失败: %s", e)

            # 1.2 Pixabay 官方真实实拍视频
            if self.pixabay_client and self.pixabay_client.is_configured:
                res_pixabay_v = self.pixabay_client.search_video(commercial_query, scene_idx, project_id)
                if res_pixabay_v:
                    logger.info("分镜 #%d 成功命中 Pixabay 真实视频", scene_idx)
                    return res_pixabay_v

        # 2. 若视频未命中，且前端传入了有效的显式指定素材 (非普通占位图或用户特定上传)
        if explicit_url and explicit_url.startswith("http"):
            try:
                logger.info("分镜 #%d 视频未覆盖，下载显式指定画面: %s", scene_idx, explicit_url[:60])
                resp = self.session.get(explicit_url, timeout=20)
                if resp.status_code == 200 and len(resp.content) > 5000:
                    with open(save_path, "wb") as f:
                        f.write(resp.content)
                    return {
                        "asset_file": str(save_path),
                        "asset_type": "image",
                        "source": "dynamic_ai_web_image",
                        "keyword": image_prompt or "",
                    }
            except Exception as e:
                logger.warning("下载指定画面失败 (%s)，进入实拍大片匹配管线", e)

        # 3. 真实人物/事件纪实照片 (Wikimedia Commons)
        real_wiki = self._search_wikimedia_real_photo(commercial_query, voiceover_text, scene_idx, project_id)
        if real_wiki:
            return real_wiki

        # 4. 真实 1080x1920 竖屏摄影大片双引擎 (Pixabay Photo -> Pexels Photo)
        if self.pixabay_client and self.pixabay_client.is_configured and commercial_query:
            res_pixabay_p = self.pixabay_client.search_photo(commercial_query, scene_idx, project_id)
            if res_pixabay_p:
                logger.info("分镜 #%d 成功命中 Pixabay 真实竖屏摄影", scene_idx)
                return res_pixabay_p

        if self.api_key and commercial_query:
            try:
                res_pexels_p = self._search_pexels(commercial_query, scene_idx, project_id)
                if res_pexels_p:
                    return res_pexels_p
            except Exception as e:
                logger.warning("Pexels 摄影检索失败: %s", e)

        # 5. 精选 19 大细分赛道真实单反摄影大片池 (Unsplash 真实原片 CDN，严格同项目去重)
        try:
            res_curated = self._match_and_download_curated_photo(commercial_query, scene_idx, project_id)
            if res_curated:
                logger.info("分镜 #%d 成功命中 19 大赛道精选商业摄影原片 (独家无重复)", scene_idx)
                return res_curated
        except Exception as e:
            logger.warning("精选实景图片匹配失败: %s", e)

        # 6. 仅在真实素材均未覆盖时，才调用动态 AI 生图兜底
        prompt = self._build_scene_prompt(image_prompt, keywords, voiceover_text, scene_type)
        if prompt:
            try:
                from media.ai_image_gen import AIImageGenerator
                ai_img = ai_gen.generate_image(
                    prompt=prompt,
                    project_id=project_id,
                    scene_index=scene_idx,
                    voiceover_text=voiceover_text,
                    scene_type=scene_type,
                )
                if ai_img and os.path.exists(ai_img):
                    logger.info("分镜 #%d 启用 AI 视觉增强生成: %s", scene_idx, ai_img)
                    return {
                        "asset_file": ai_img,
                        "asset_type": "image",
                        "source": "dynamic_ai_flux",
                        "keyword": prompt,
                    }
            except Exception as e:
                logger.warning("分镜 #%d 动态 AI 生图异常: %s", scene_idx, e)

        # 7. 本地纯净深色弥散流光保底
        return self._generate_pure_mesh_gradient(scene_idx, project_id)

    @staticmethod
    def _build_scene_prompt(
        image_prompt: Optional[str], keywords: List[str], voiceover_text: str, scene_type: str
    ) -> str:
        """把抽象分镜约束为可见的主体、动作和环境，降低万能图与跑题图概率。"""
        base = (image_prompt or "").strip()
        searchable = ", ".join(str(k) for k in keywords if str(k).strip())
        spoken_anchor = re.sub(r"\s+", " ", voiceover_text).strip()[:90]
        role_shots = {
            "hook": "tight documentary close-up, immediate action, strong foreground",
            "context": "handheld medium shot, environmental context, candid people",
            "evidence": "overhead detail shot, physical evidence and readable objects",
            "action": "close-up of hands performing a concrete action",
            "turn": "wide observational shot with visual contrast and negative space",
            "outro": "candid reaction shot, human eye contact, open composition",
        }
        shot = role_shots.get(scene_type, "natural documentary medium shot")
        parts = [base, searchable, f"spoken scene meaning: {spoken_anchor}" if spoken_anchor else "", shot]
        return ", ".join(p for p in parts if p) + ", one clear subject, authentic location, natural light, no text, no collage"

    def _match_and_download_curated_photo(
        self,
        keyword_str: str,
        scene_idx: int,
        project_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        根据分镜关键词精准选择领域摄影大片并下载 1080x1920 竖屏版 (含同项目全局去重)
        """
        save_path = ASSETS_OUTPUT_DIR / f"{project_id}_asset_scene_{scene_idx}.jpg"
        kw_lower = keyword_str.lower()

        # 细粒度判定关键词所属领域 (优先匹配精准垂直领域)
        cat = None
        if any(w in kw_lower for w in ["court", "trial", "judge", "gavel", "justice", "law", "prison", "handcuff", "guilty", "plea", "lawyer", "legal", "crime", "verdict", "police"]):
            cat = "justice"
        elif any(w in kw_lower for w in ["history", "archive", "newspaper", "document", "vintage", "retro", "record", "headline"]):
            cat = "documentary"
        elif any(w in kw_lower for w in ["space", "galaxy", "universe", "stars", "planet", "cosmic", "scifi", "alien", "astronomy"]):
            cat = "scifi"
        elif any(w in kw_lower for w in ["chess", "strategy", "game", "button", "switch", "decision", "crisis", "intense", "thinking", "solitude"]):
            cat = "strategy"
        elif any(w in kw_lower for w in ["basketball", "sports", "athlete", "soccer", "football", "workout", "tournament", "stadium"]):
            cat = "sports"
        elif any(w in kw_lower for w in ["chip", "tech", "computer", "phone", "code", "ai", "robot", "server", "algorithm", "digital", "future"]):
            cat = "tech"
        elif any(w in kw_lower for w in ["market", "stock", "money", "chart", "building", "finance", "business", "bank", "invest", "economy", "trade", "gold"]):
            cat = "finance"
        elif any(w in kw_lower for w in ["office", "desk", "meeting", "work", "boss", "job", "career", "worker", "colleague"]):
            cat = "workplace"
        elif any(w in kw_lower for w in ["music", "concert", "movie", "film", "stage", "camera", "show", "tv", "entertainment", "variety"]):
            cat = "entertainment"
        elif any(w in kw_lower for w in ["star", "actor", "actress", "celebrity", "model", "fashion", "portrait", "woman", "man", "person"]):
            cat = "celebrity"
        elif any(w in kw_lower for w in ["drama", "conflict", "mask", "theatre", "curtain", "fight", "tension"]):
            cat = "drama"
        elif any(w in kw_lower for w in ["mystery", "dark", "night", "detective", "shadow", "fog", "rain", "cyberpunk", "secret"]):
            cat = "mystery"
        elif any(w in kw_lower for w in ["city", "hospital", "doctor", "street", "car", "social", "traffic", "crowd", "people", "news"]):
            cat = "social"
        elif any(w in kw_lower for w in ["love", "heart", "sunset", "coffee", "hug", "warm", "emotion", "tear", "alone", "sad"]):
            cat = "emotions"
        elif any(w in kw_lower for w in ["habit", "routine", "meditation", "exercise", "morning", "growth"]):
            cat = "growth"

        # 若未命中特定赛道，按分镜轮询多样化垂直图库，绝不让所有镜头回退到同一种图！
        if not cat:
            diverse_pools = ["documentary", "strategy", "social", "workplace", "finance", "mystery"]
            cat = diverse_pools[(scene_idx - 1) % len(diverse_pools)]

        photo_pool = CURATED_PHOTO_COLLECTION.get(cat) or CURATED_PHOTO_COLLECTION["documentary"]
        used_set = _GLOBAL_PROJECT_USED_ASSETS.setdefault(project_id, set())
        self._used_assets_by_project.setdefault(project_id, set()).update(used_set)

        # 智能探查未使用的照片 ID，彻底消除同项目多镜头重复
        seed_hash = int(hashlib.md5(f"{kw_lower}:{project_id}".encode("utf-8")).hexdigest()[:6], 16)
        base_idx = (seed_hash + (scene_idx - 1) * 2) % len(photo_pool)
        photo_id = None

        # 优先在当前类别中找未用过的
        for offset in range(len(photo_pool)):
            cand_id = photo_pool[(base_idx + offset) % len(photo_pool)]
            if cand_id not in used_set:
                photo_id = cand_id
                break

        # 若当前类别已被当前项目用尽，向其他高质感备选池借图，绝不复用
        if not photo_id:
            for fallback_cat in ["justice", "documentary", "strategy", "social", "workplace"]:
                f_pool = CURATED_PHOTO_COLLECTION.get(fallback_cat, [])
                for cand_id in f_pool:
                    if cand_id not in used_set:
                        photo_id = cand_id
                        cat = fallback_cat
                        break
                if photo_id:
                    break

        if not photo_id:
            photo_id = photo_pool[base_idx % len(photo_pool)]

        used_set.add(photo_id)
        self._used_assets_by_project[project_id].add(photo_id)

        url = f"https://images.unsplash.com/{photo_id}?w=1080&h=1920&fit=crop&q=82"
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 10000:
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                return {
                    "asset_file": str(save_path),
                    "asset_type": "image",
                    "source": f"curated_{cat}_photo",
                    "keyword": keyword_str,
                }
        except Exception as e:
            logger.warning("下载精选竖屏大片超时 (%s)，切换备选", e)

        return None

    def _generate_pure_mesh_gradient(
        self,
        scene_idx: int,
        project_id: str,
    ) -> Dict[str, Any]:
        """
        生成苹果发布会级【纯净深色弥散流光 (Smooth Mesh Gradient)】
        ★ 彻底去除所有廉价白点与杂乱散点，仅保留丝滑多色温有机光晕
        """
        save_path = ASSETS_OUTPUT_DIR / f"{project_id}_asset_scene_{scene_idx}_ambient.png"

        color_themes = [
            [(10, 14, 26), (18, 30, 56), (0, 190, 255)],    # 科技深蓝霓虹
            [(16, 10, 24), (40, 18, 58), (180, 60, 240)],   # 赛博幻紫
            [(10, 20, 16), (22, 50, 38), (35, 210, 125)],   # 极客暗翡
            [(22, 16, 10), (56, 32, 16), (250, 160, 30)],   # 奢华深金
            [(22, 10, 16), (56, 16, 30), (250, 50, 90)],    # 炽热绯红
        ]
        theme = color_themes[(scene_idx - 1) % len(color_themes)]
        c_dark, c_mid, c_accent = theme

        img = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (c_dark[0], c_dark[1], c_dark[2], 255))
        draw = ImageDraw.Draw(img)

        for y in range(0, VIDEO_HEIGHT, 4):
            ratio = y / VIDEO_HEIGHT
            r = int(c_dark[0] * (1 - ratio) + c_mid[0] * ratio)
            g = int(c_dark[1] * (1 - ratio) + c_mid[1] * ratio)
            b = int(c_dark[2] * (1 - ratio) + c_mid[2] * ratio)
            draw.rectangle([0, y, VIDEO_WIDTH, y + 4], fill=(r, g, b, 255))

        glow_layer = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(glow_layer)

        cx1 = int(VIDEO_WIDTH * (0.35 + (scene_idx * 0.15) % 0.35))
        cy1 = int(VIDEO_HEIGHT * (0.42 + (scene_idx * 0.1) % 0.25))
        r1 = 520
        g_draw.ellipse([cx1 - r1, cy1 - r1, cx1 + r1, cy1 + r1], fill=(c_accent[0], c_accent[1], c_accent[2], 60))

        cx2 = int(VIDEO_WIDTH * (0.68 - (scene_idx * 0.12) % 0.3))
        cy2 = int(VIDEO_HEIGHT * (0.62 - (scene_idx * 0.08) % 0.2))
        r2 = 440
        g_draw.ellipse([cx2 - r2, cy2 - r2, cx2 + r2, cy2 + r2], fill=(c_mid[0], c_mid[1], c_mid[2], 75))

        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=100))
        final_img = Image.alpha_composite(img, glow_layer)
        final_img.convert("RGB").save(str(save_path), quality=95)

        return {
            "asset_file": str(save_path),
            "asset_type": "image",
            "source": "pure_mesh_gradient",
            "keyword": "pure mesh gradient",
        }

    def _search_pexels(self, query: str, scene_idx: int, project_id: str) -> Optional[Dict[str, Any]]:
        """优先使用极简核心词搜索 Pexels 竖屏视频，无合适视频时搜索竖屏图片。"""
        used_set = self._used_assets_by_project.setdefault(project_id, set())
        video_q = query if len(query.strip().split()) <= 2 else self._extract_core_video_query(query)

        # 1. 检索竖屏真实视频
        try:
            params = {"query": video_q, "orientation": "portrait", "per_page": 5}
            resp = self.session.get("https://api.pexels.com/videos/search", headers=self.headers, params=params, timeout=8)
            if resp.status_code == 200:
                videos = resp.json().get("videos", [])
                for chosen in videos:
                    vid_id = f"pexels_v_{chosen.get('id')}"
                    if vid_id in used_set:
                        continue
                    files = sorted(chosen.get("video_files", []), key=lambda item: item.get("height", 0), reverse=True)
                    for vf in files:
                        if vf.get("width", 0) <= vf.get("height", 1) and vf.get("link"):
                            save_path = ASSETS_OUTPUT_DIR / f"{project_id}_asset_scene_{scene_idx}.mp4"
                            download = self.session.get(vf["link"], timeout=30)
                            if download.status_code == 200 and len(download.content) >= 100_000:
                                with open(save_path, "wb") as f:
                                    f.write(download.content)
                                used_set.add(vid_id)
                                return {
                                    "asset_file": str(save_path),
                                    "asset_type": "video",
                                    "source": "pexels",
                                    "keyword": video_q,
                                    "duration": chosen.get("duration", 5.0),
                                }
        except Exception as e:
            logger.debug("Pexels 竖屏视频检索尝试 [%s] 失败: %s", video_q, e)

        # 2. 视频未命中，搜索竖屏单反摄影
        try:
            params = {"query": video_q, "orientation": "portrait", "per_page": 5}
            photo_resp = self.session.get("https://api.pexels.com/v1/search", headers=self.headers, params=params, timeout=8)
            if photo_resp.status_code == 200:
                photos = photo_resp.json().get("photos", [])
                for chosen_photo in photos:
                    pid = f"pexels_p_{chosen_photo.get('id')}"
                    if pid in used_set:
                        continue
                    photo_url = chosen_photo.get("src", {}).get("portrait") or chosen_photo.get("src", {}).get("large2x")
                    if photo_url:
                        download = self.session.get(photo_url, timeout=20)
                        if download.status_code == 200 and len(download.content) > 20_000:
                            save_path = ASSETS_OUTPUT_DIR / f"{project_id}_asset_scene_{scene_idx}.jpg"
                            with open(save_path, "wb") as f:
                                f.write(download.content)
                            used_set.add(pid)
                            return {
                                "asset_file": str(save_path),
                                "asset_type": "image",
                                "source": "pexels_photo",
                                "keyword": video_q,
                                "photographer": chosen_photo.get("photographer", "Pexels"),
                            }
        except Exception as e:
            logger.debug("Pexels 摄影检索失败: %s", e)

        return None

    def fetch_scene_assets(self, scenes: List[Dict[str, Any]], project_id: str) -> List[Dict[str, Any]]:
        """批量获取/生成所有分镜真实素材"""
        def fetch(s: Dict[str, Any]) -> Dict[str, Any]:
            s_idx = s.get("scene_index", 1)
            kws = s.get("visual_keywords", ["cinematic", "focus"])
            dur = float(s.get("duration", 4.0))
            img_prompt = s.get("image_prompt")
            explicit_url = s.get("img") or s.get("img_url")
            existing_file = s.get("asset_file")

            if existing_file and os.path.exists(existing_file):
                s_copy = dict(s)
                s_copy["asset_source"] = "user_selected_local"
                return s_copy

            res = self.fetch_scene_asset(
                kws, s_idx, project_id, duration=dur,
                image_prompt=img_prompt, explicit_url=explicit_url,
                voiceover_text=s.get("voiceover_text", ""), scene_type=s.get("scene_type", ""),
            )
            s_copy = dict(s)
            s_copy["asset_file"] = res.get("asset_file")
            s_copy["asset_type"] = res.get("asset_type")
            s_copy["asset_source"] = res.get("source", "unknown")
            s_copy["asset_keyword"] = res.get("keyword", "")
            return s_copy

        with ThreadPoolExecutor(max_workers=MEDIA_FETCH_CONCURRENCY, thread_name_prefix="media-fetch") as pool:
            return list(pool.map(fetch, scenes))


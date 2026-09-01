"""
全网多垂直领域爆款热点与【多平台共振登顶】挖掘引擎 (工业级高精度分类)
分类领域支持：
1. 🔥 全网共振 (多端如抖音+微博+B站重合爆款，加权绝对登顶)
2. 💻 科技数码 (AI、半导体、硬件、自动驾驶、大模型、数码极客)
3. 📈 商业财经 (股市、经济、涨价、创投、黄金消费、企业财报)
4. 🌐 社会民生 (时政、民生、教育、天气灾害、社会救灾、辟谣)
5. 🎭 娱乐文娱 (影视剪辑、综艺、明星、八卦、鬼畜动漫、体育电竞)
6. 🧠 认知职场 (自律、底层逻辑、思维模型、职场逆袭、心理学)
"""
import sys
import time
import re
import logging
import math
import requests
from typing import List, Dict, Any, Optional, Set
from core.state import RawTopicItem

logger = logging.getLogger(__name__)

CATEGORY_NAMES = {
    "resonance": "🔥 全网共振",
    "tech": "💻 科技数码",
    "finance": "📈 商业财经",
    "social": "🌐 社会民生",
    "entertainment": "🎭 娱乐文娱",
    "growth": "🧠 认知职场",
    "all": "⚡ 全网综合"
}

class HotTopicCrawler:
    """多垂直领域与跨平台共振爆款热榜抓取器 (高精度多源分类器)"""
    
    @staticmethod
    def _create_session() -> requests.Session:
        s = requests.Session()
        s.trust_env = False
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*"
        })
        return s

    @classmethod
    def _classify_topic(cls, title: str, tname: Optional[str] = None) -> str:
        """
        双层高精度分类架构：
        1. 平台原生官方分区标签映射 (如 B站官方 tname: 影视剪辑 / 极客DIY / 游戏 / 搞笑)
        2. 正则表达式精确边界与否定词过滤（避免 2 字符英文误伤如 'ai', 'rap'）
        """
        # 1. 优先使用官方原生分区
        if tname:
            tn = tname.strip()
            if any(x in tn for x in ['游戏', '影视', '综艺', '搞笑', '动画', '鬼畜', '音乐', '舞蹈', '娱乐', '生活', '美食', '电竞']):
                return 'entertainment'
            if any(x in tn for x in ['数码', '极客', '软件', '科技', '电脑', '手机']):
                return 'tech'
            if any(x in tn for x in ['财经', '商业', '经济', '金融', '投资']):
                return 'finance'
            if any(x in tn for x in ['社科', '法律', '时事', '资讯', '热点']):
                return 'social'

        title_lower = title.lower()

        # 2. 娱乐文娱优先排查（影视/短剧/动漫/游戏/鬼畜/体育）
        ent_patterns = [
            r'第\d+集', r'短剧', r'影视', r'综艺', r'明星', r'八卦', r'rap', r'唱跳', r'演唱会',
            r'游戏', r'原神', r'明日方舟', r'英雄联盟', r'王者荣耀', r'世一上', r'绝杀', r'大师赛',
            r'羽毛球', r'德约科维奇', r'中网', r'mv', r'鬼畜', r'动漫', r'二次元', r'歌手', r'演员'
        ]
        if any(re.search(p, title_lower) for p in ent_patterns):
            return 'entertainment'

        # 3. 科技数码（使用词边界与精准专业词）
        tech_patterns = [
            r'\bai\b', r'\baigc\b', r'\bdeepseek\b', r'\bopenai\b', r'\bmacbook\b', r'\biphone\b', r'\bipad\b',
            r'芯片', r'半导体', r'手机', r'华为', r'小米', r'苹果', r'显卡', r'英伟达', r'自动驾驶',
            r'新能源车', r'极客', r'耳机', r'蓝牙', r'鸿蒙', r'大模型', r'算法', r'操作系统', r'硬件', r'软件应用'
        ]
        if any(re.search(p, title_lower) for p in tech_patterns):
            return 'tech'

        # 4. 商业财经
        fin_patterns = [
            r'股市', r'a股', r'港股', r'美股', r'基金', r'理财', r'房价', r'房产', r'涨价',
            r'降价', r'降息', r'加息', r'gdp', r'以旧换新', r'黄金', r'外汇', r'财报', r'资产', r'存钱'
        ]
        if any(re.search(p, title_lower) for p in fin_patterns):
            return 'finance'

        # 5. 认知与职场
        growth_patterns = [
            r'自律', r'思维', r'认知', r'习惯', r'底层逻辑', r'闭环', r'复利', r'逆袭', r'拖延', r'微习惯', r'情商'
        ]
        if any(re.search(p, title_lower) for p in growth_patterns):
            return 'growth'

        # 6. 默认归入社会民生
        return 'social'

    @staticmethod
    def _extract_tokens(text: str) -> Set[str]:
        """提取用于多平台跨端共振匹配的核心特征词"""
        clean = re.sub(r'[^\w\u4e00-\u9fa5]', ' ', text.lower())
        tokens = set()
        stopwords = {'推荐', '视频', '第一', '中国', '一个', '今天', '如何', '为什么', '什么', '我们', '大家', '正式', '回应', '指南'}
        
        for w in clean.split():
            if len(w) >= 2 and w not in stopwords:
                tokens.add(w)
                for i in range(len(w) - 1):
                    sub = w[i:i+2]
                    if sub not in stopwords:
                        tokens.add(sub)
        return tokens

    @staticmethod
    def _score_editorial_value(item: RawTopicItem) -> tuple[float, str]:
        """Separate raw popularity from usefulness as a video topic."""
        title = item.title.strip()
        specificity = min(18.0, len(set(title)) * 0.9)
        engagement = min(12.0, math.log10(max(1, item.like_count + item.comment_count * 3 + item.share_count * 5)) * 3)
        resonance = 14.0 if item.is_resonance else 0.0
        question_value = 6.0 if any(mark in title for mark in ("为什么", "如何", "？", "?")) else 2.0
        score = min(100.0, item.hot_score * 0.5 + specificity + engagement + resonance + question_value)
        reasons = []
        if item.is_resonance:
            reasons.append(f"{len(item.resonating_platforms)} 平台共振")
        if engagement >= 8:
            reasons.append("互动强")
        reasons.append("信息具体" if specificity >= 12 else "需补充切口")
        return round(score, 1), " · ".join(reasons)

    @classmethod
    def fetch_douyin_hot(cls) -> List[RawTopicItem]:
        """抓取抖音官方实时热搜榜"""
        items = []
        try:
            session = cls._create_session()
            session.headers.update({"Referer": "https://www.douyin.com/"})
            url = "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/"
            resp = session.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("word_list", [])
                for i, item in enumerate(data[:35]):
                    word = item.get("word", "")
                    hot_value = item.get("hot_value", 0)
                    score = max(80.0, 99.0 - (i * 0.5))
                    if word:
                        cat = cls._classify_topic(word)
                        items.append(RawTopicItem(
                            id=f"douyin_{i+1}",
                            source_platform="douyin",
                            title=word,
                            raw_content=f"抖音实时热点：#{word}#",
                            category=cat,
                            category_name=CATEGORY_NAMES.get(cat, "社会民生"),
                            like_count=int(hot_value) if hot_value else 0,
                            hot_score=round(score, 1),
                            captured_at=time.strftime("%Y-%m-%d %H:%M:%S")
                        ))
        except Exception as e:
            logger.warning("抖音热搜抓取失败: %s", e)
        return items

    @classmethod
    def fetch_bilibili_hot(cls) -> List[RawTopicItem]:
        """抓取B站综合热门视频与爆款榜 (带有官方 tname 精确分区)"""
        items = []
        try:
            session = cls._create_session()
            url = "https://api.bilibili.com/x/web-interface/popular?ps=35&pn=1"
            session.headers.update({"Referer": "https://www.bilibili.com/"})
            resp = session.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("list", [])
                for i, entry in enumerate(data[:35]):
                    title = entry.get("title", "")
                    desc = entry.get("desc", "")
                    tname = entry.get("tname", "")
                    stat = entry.get("stat", {})
                    likes = stat.get("like", 0)
                    score = max(80.0, 98.8 - (i * 0.5))
                    if title:
                        cat = cls._classify_topic(title, tname=tname)
                        items.append(RawTopicItem(
                            id=f"bili_{entry.get('bvid', i)}",
                            source_platform="bilibili",
                            title=title,
                            raw_content=desc or title,
                            category=cat,
                            category_name=CATEGORY_NAMES.get(cat, "社会民生"),
                            like_count=likes,
                            hot_score=round(score, 1),
                            captured_at=time.strftime("%Y-%m-%d %H:%M:%S")
                        ))
        except Exception as e:
            logger.warning("B站热门抓取失败: %s", e)
        return items

    @classmethod
    def fetch_weibo_hot(cls) -> List[RawTopicItem]:
        """抓取微博实时热搜榜"""
        items = []
        try:
            session = cls._create_session()
            url = "https://weibo.com/ajax/side/hotSearch"
            session.headers.update({"Referer": "https://weibo.com/"})
            resp = session.get(url, timeout=5)
            if resp.status_code == 200:
                realtime = resp.json().get("data", {}).get("realtime", [])
                for i, item in enumerate(realtime[:40]):
                    word = item.get("word", "")
                    raw_hot = item.get("num", 0)
                    score = max(80.0, 98.5 - (i * 0.5))
                    if word:
                        cat = cls._classify_topic(word)
                        items.append(RawTopicItem(
                            id=f"weibo_{i+1}",
                            source_platform="weibo",
                            title=word,
                            raw_content=f"微博热门讨论话题：#{word}#",
                            category=cat,
                            category_name=CATEGORY_NAMES.get(cat, "社会民生"),
                            hot_score=round(score, 1),
                            captured_at=time.strftime("%Y-%m-%d %H:%M:%S")
                        ))
        except Exception as e:
            logger.warning("微博热搜抓取失败: %s", e)
        return items

    @classmethod
    def get_preset_growth_topics(cls) -> List[RawTopicItem]:
        """认知/职场/商业底层常青高赞选题库"""
        presets = [
            ("为什么越厉害的人，越把时间花在无人问津的苦功夫上？", "揭秘成功人士的底层复利思维与沉潜法则", "growth", "认知职场"),
            ("为什么你每天很忙却存不下钱？核心问题在这 3 个隐形陷阱", "普通人摆脱财务内耗的思维转变", "finance", "商业财经"),
            ("戒掉即时满足：教你用微习惯骗过大脑，实现自律自由", "心理学微习惯养成体系", "growth", "认知职场"),
            ("真正拉开人与人差距的，从不是智商，而是闭环思维", "职场与人生高手的做事逻辑", "growth", "认知职场"),
            ("深度解读【具身认知】：为什么你的身体姿势决定了你的思维状态？", "前沿心理学科普与实操建议", "growth", "认知职场")
        ]
        return [
            RawTopicItem(
                id=f"preset_{i+1}",
                source_platform="curated_viral",
                title=p[0],
                raw_content=p[1],
                category=p[2],
                category_name=p[3],
                hot_score=94.0 - i,
                captured_at=time.strftime("%Y-%m-%d %H:%M:%S")
            )
            for i, p in enumerate(presets)
        ]

    @classmethod
    def get_categorized_trends(
        cls,
        category: str = "all",
        limit: int = 12
    ) -> List[RawTopicItem]:
        """
        核心分类与共振聚合逻辑：
        1. 抓取各平台全量实时池
        2. 精确跨端共振匹配
        3. 细分领域过滤与共振登顶
        """
        all_raw_pool: List[RawTopicItem] = []
        all_raw_pool.extend(cls.fetch_douyin_hot())
        all_raw_pool.extend(cls.fetch_bilibili_hot())
        all_raw_pool.extend(cls.fetch_weibo_hot())
        all_raw_pool.extend(cls.get_preset_growth_topics())

        # 1. 跨平台共振匹配检测
        token_map = {}
        for item in all_raw_pool:
            token_map[item.id] = cls._extract_tokens(item.title)

        for i, item1 in enumerate(all_raw_pool):
            tokens1 = token_map.get(item1.id, set())
            if not tokens1:
                continue
            matched_platforms = {item1.source_platform}
            
            for j, item2 in enumerate(all_raw_pool):
                if i != j and item1.source_platform != item2.source_platform:
                    tokens2 = token_map.get(item2.id, set())
                    overlap = tokens1 & tokens2
                    if len(overlap) >= 2 or any(len(t) >= 3 for t in overlap):
                        matched_platforms.add(item2.source_platform)
                        
            if len(matched_platforms) >= 2:
                item1.is_resonance = True
                item1.resonating_platforms = sorted(list(matched_platforms))
                item1.hot_score = round(min(100.0, 98.0 + len(matched_platforms) * 0.8), 1)

        for item in all_raw_pool:
            item.editorial_score, item.trend_reason = cls._score_editorial_value(item)

        # 2. 领域过滤
        if category == "resonance":
            filtered = [item for item in all_raw_pool if item.is_resonance]
        elif category in ("tech", "finance", "social", "entertainment", "growth"):
            # 在垂直分类中，只展示属于该分类的话题（如果是共振爆款，也必须符合该分类才展示在当前分类中）
            filtered = [item for item in all_raw_pool if item.category == category]
        else:
            filtered = all_raw_pool

        # 3. 排序策略：同分类内共振爆款优先置顶，其次按热度排序
        filtered.sort(key=lambda x: (x.is_resonance, x.editorial_score, x.hot_score), reverse=True)

        # 4. 去重
        seen_titles = set()
        final_list = []
        for t in filtered:
            simple_key = re.sub(r'[^\w\u4e00-\u9fa5]', '', t.title)[:10]
            if simple_key not in seen_titles:
                seen_titles.add(simple_key)
                final_list.append(t)
                if len(final_list) >= limit:
                    break

        return final_list

    @classmethod
    def get_top_trending(cls, limit: int = 10) -> List[RawTopicItem]:
        """兼容旧接口"""
        return cls.get_categorized_trends(category="all", limit=limit)

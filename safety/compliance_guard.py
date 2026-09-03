"""
文案合规风控审查与敏感词语义平替引擎 (Compliance Guard)
严格对齐中国广告法极限词规则与抖音、B站、小红书自媒体内容安全红线。
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 1. 广告法极限用语词典与合规平替映射
AD_LAW_DICT: Dict[str, str] = {
    "全网最好": "很受欢迎",
    "全网第一": "广受关注",
    "全国第一": "行业前列",
    "天下第一": "赫赫有名",
    "天下无敌": "实力出众",
    "万能神药": "针对性方案",
    "万能解法": "实用解法",
    "绝对有效": "普遍有效",
    "百分之百": "极大可能",
    "100%": "大概率",
    "无可替代": "非常关键",
    "顶级天花板": "标杆水准",
    "天花板": "标杆水准",
    "最牛": "很厉害",
    "最强": "实力过硬",
    "最好": "很不错",
    "最佳": "更优",
    "首选": "优质选择",
    "独一无二": "别具特色",
    "唯一": "关键",
    "绝对": "通常",
    "极致": "极高水准",
}

# 2. 平台夸大引流与诱导高危词汇
PLATFORM_SENSITIVE_DICT: Dict[str, str] = {
    "一夜暴富": "快速积累",
    "必赚不赔": "有可观潜力",
    "稳赚不赔": "有较高胜率",
    "躺赚": "建立被动收入",
    "无脑入": "值得参考",
    "闭眼入": "值得关注",
    "保本保收益": "注重风险控制",
    "内部绝密": "核心认知",
    "内部黑幕": "行业底层机制",
    "零风险": "低试错成本",
    "封神": "非常出彩",
    "必死无疑": "面临严重瓶颈",
    "彻底完蛋": "陷入严重被动",
}

# 3. 恐慌焦虑制造词汇
ANXIETY_MISLEADING_DICT: Dict[str, str] = {
    "大祸临头": "面临重大挑战",
    "灾难降临": "突发情况发生",
    "彻底死定": "陷入死局",
    "倾家荡产": "承受巨大损失",
}


class ComplianceMatch(BaseModel):
    word: str
    category: str  # ad_law | platform_sensitive | anxiety_misleading
    level: str  # high | medium
    start_index: int
    end_index: int
    replacement: str


class ComplianceScanResult(BaseModel):
    is_compliant: bool
    risk_level: str  # clean | medium | high
    total_issues: int
    matches: List[ComplianceMatch] = Field(default_factory=list)
    sanitized_text: str


class ComplianceGuard:
    """文案合规风控扫描与自动平替器"""

    def __init__(self):
        # 预编译各品类高危词正则，优先按长度逆序匹配以防短词吃掉长词
        all_entries: List[Tuple[str, str, str, str]] = []
        for w, rep in AD_LAW_DICT.items():
            all_entries.append((w, rep, "ad_law", "high"))
        for w, rep in PLATFORM_SENSITIVE_DICT.items():
            all_entries.append((w, rep, "platform_sensitive", "high"))
        for w, rep in ANXIETY_MISLEADING_DICT.items():
            all_entries.append((w, rep, "anxiety_misleading", "medium"))

        # 按词长从大到小排序
        all_entries.sort(key=lambda x: len(x[0]), reverse=True)
        self._entries = all_entries

    def scan(self, text: str) -> ComplianceScanResult:
        """扫描文本中的合规风险词并返回定位与平替建议"""
        if not text:
            return ComplianceScanResult(
                is_compliant=True,
                risk_level="clean",
                total_issues=0,
                matches=[],
                sanitized_text="",
            )

        matches: List[ComplianceMatch] = []
        occupied_spans = set()

        for word, rep, cat, lvl in self._entries:
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            for m in pattern.finditer(text):
                start, end = m.span()
                # 检查该位置是否已被更长的复合词占用
                if any(start < o_end and end > o_start for o_start, o_end in occupied_spans):
                    continue

                occupied_spans.add((start, end))
                matches.append(
                    ComplianceMatch(
                        word=m.group(0),
                        category=cat,
                        level=lvl,
                        start_index=start,
                        end_index=end,
                        replacement=rep,
                    )
                )

        # 按在文本中的出现顺序排序
        matches.sort(key=lambda x: x.start_index)

        # 构建平替后的文本
        sanitized_chars = []
        last_idx = 0
        for m in matches:
            sanitized_chars.append(text[last_idx:m.start_index])
            sanitized_chars.append(m.replacement)
            last_idx = m.end_index
        sanitized_chars.append(text[last_idx:])
        sanitized_text = "".join(sanitized_chars)

        has_high = any(m.level == "high" for m in matches)
        risk_level = "clean"
        if has_high:
            risk_level = "high"
        elif matches:
            risk_level = "medium"

        return ComplianceScanResult(
            is_compliant=len(matches) == 0,
            risk_level=risk_level,
            total_issues=len(matches),
            matches=matches,
            sanitized_text=sanitized_text,
        )

    def auto_sanitize(self, text: str) -> str:
        """一键平替全部风险词，返回安全合规的文案"""
        res = self.scan(text)
        return res.sanitized_text


compliance_guard = ComplianceGuard()

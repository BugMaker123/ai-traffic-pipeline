"""
LLM 深度爆款脚本与多档位分镜生成引擎 (DeepSeek / OpenAI 兼容)
"""
import os
import json
import logging
import re
import uuid
import hashlib
from datetime import date
from typing import Dict, Any, Optional
import requests
from config.settings import OPENAI_API_KEY, OPENAI_BASE_URL, LLM_MODEL
from core.state import VideoProjectScript, SceneItem
from writers.prompts import SCRIPT_SYSTEM_PROMPT, SCRIPT_USER_TEMPLATE

logger = logging.getLogger(__name__)

DURATION_PRESETS = {
    "quick_30s": "短小精悍型 (30~45秒，4~5个紧凑分镜，约180字)",
    "deep_60s": "深度干货/故事型 (60~90秒，6~8个饱满分镜，约350~450字，推荐)",
    "long_120s": "长视频精解型 (2~3分钟，9~12个深度分镜，约600~800字)"
}

STYLE_PRESETS = {
    "干货科普": "严谨硬核科普，数据与运行机制拆解，逻辑严密清晰",
    "商业认知": "商业模式、信息差、财富积累逻辑与产业资本透视",
    "幽默反转": "网梗金句频出，意料之外的戏剧性反转，轻松幽默搞怪",
    "情感共鸣": "深度治愈、戳中社会群体软肋的高密度情绪共情",
    "犀利吐槽": "嘴替视角，一针见血、辛辣讽刺乱象与荒谬现象",
    "悬疑探秘": "电影级悬疑感，层层抽丝剥茧、充满悬念与未解之谜",
    "燃系励志": "高能量热血、打破内耗、激情澎湃的坚定行动号召",
    "避坑实操": "保姆级避坑指南，步骤清晰落地，强调防套路实操",
    "历史故事": "史诗感叙事，厚重历史事件拉片与现实深度映射",
    "思维模型": "高阶认知模型拆解，第一性原理与决策框架升级",
    "深度拉片": "慢节奏电影级叙事，注重画面细节、意象留白与视听隐喻",
    "客观评述": "中立客观、多视角平衡的事实核查与深度舆论复盘"
}

class ScriptGenerator:
    """大模型高信息密度分镜剧本生成器"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or OPENAI_API_KEY
        self.base_url = base_url or OPENAI_BASE_URL
        self.model = model or LLM_MODEL

    def generate_script(
        self,
        topic_or_content: str,
        style: str = "干货科普",
        duration_tier: str = "deep_60s",
        project_id: Optional[str] = None,
        source_content: str = "",
        source_platform: str = "",
        captured_at: str = "",
        chosen_angle: str = "",
    ) -> VideoProjectScript:
        """
        根据输入主题与时长档位，生成深度饱满的结构化分镜剧本（可指定选定切口）
        """
        proj_id = project_id or f"proj_{uuid.uuid4().hex[:8]}"
        duration_desc = DURATION_PRESETS.get(duration_tier, DURATION_PRESETS["deep_60s"])
        
        effective_source = source_content
        if chosen_angle:
            effective_source = f"[用户已选定切口视角]\n{chosen_angle}\n\n[背景材料]\n{source_content}"

        # 1. 尝试调用大模型 API
        if self.api_key:
            try:
                script_dict = self._call_llm(
                    topic_or_content, style, duration_desc, proj_id,
                    effective_source, source_platform, captured_at,
                    chosen_angle=chosen_angle,
                )
                if script_dict and "scenes" in script_dict and len(script_dict["scenes"]) > 0:
                    unsupported = self._unsupported_temporal_claims(script_dict, f"{topic_or_content} {source_content}")
                    if unsupported:
                        logger.warning("检测到无来源时效断言，要求重写: %s", ", ".join(unsupported))
                        correction = (
                            f"{source_content}\n\n[强制纠错] 上一稿出现材料不支持的内容：{', '.join(unsupported)}。"
                            "重写时全部删除，不得替换成其他具体型号、年份或价格。"
                        )
                        script_dict = self._call_llm(
                            topic_or_content, style, duration_desc, proj_id,
                            correction, source_platform, captured_at,
                            chosen_angle=chosen_angle,
                        )
                        if not script_dict or self._unsupported_temporal_claims(
                            script_dict, f"{topic_or_content} {source_content}"
                        ):
                            raise ValueError("生成稿包含来源未支持的时效性事实")
                    script_dict["grounding_status"] = "source_grounded" if source_content else "topic_only"
                    script_dict["freshness_note"] = (
                        f"依据 {source_platform or '热点来源'} 于 {captured_at or '当前'} 提供的材料生成"
                        if source_content else "未提供事实来源，已限制具体时效性断言"
                    )
                    return VideoProjectScript(**script_dict)
            except Exception as e:
                logger.warning("LLM API 调用失败，切换至模板引擎: %s", e)

        # 2. 深度多幕剧本兜底生成
        return self._generate_deep_fallback_script(topic_or_content, style, proj_id)

    def generate_script_from_reference(
        self,
        ref_title: str,
        ref_transcript: str,
        style: str = "干货科普",
        duration_tier: str = "deep_60s",
        project_id: Optional[str] = None,
        source_platform: str = "短视频提取",
    ) -> VideoProjectScript:
        """
        基于原视频转写文案或参考材料进行爆款重构仿写：
        分析其 Hook 破题法、论点层层递进与互动转折，去粗取精输出高质量原创分镜。
        """
        prompt_topic = f"【爆款重构】原视频主题：《{ref_title}》"
        prompt_source = (
            f"以下为原视频/文章的参考提取文案（提取自 {source_platform}）：\n\n"
            f"--- 原文开始 ---\n{ref_transcript[:3000]}\n--- 原文结束 ---\n\n"
            "请深入解构该内容的爆款内核与认知痛点，重新组织表达，去除口水话与赘述，"
            "使用全新的抓人开头（黄金3秒Hook）与更清晰有力的层次结构，重构出适合短视频口播的全新原创分镜脚本。"
        )
        return self.generate_script(
            topic_or_content=prompt_topic,
            style=style,
            duration_tier=duration_tier,
            project_id=project_id,
            source_content=prompt_source,
            source_platform=source_platform,
            captured_at=str(date.today()),
        )

    @staticmethod
    def _unsupported_temporal_claims(script: Dict[str, Any], allowed_text: str) -> list[str]:
        """拦截来源材料中不存在的高时效年份、型号与价格断言。"""
        text = " ".join(
            [str(script.get("title", "")), str(script.get("topic_summary", ""))]
            + [str(scene.get("voiceover_text", "")) for scene in script.get("scenes", [])]
        )
        patterns = (
            r"20\d{2}年?",
            r"iPhone\s*\d+(?:\s*(?:Pro|Plus|mini|Max))*",
            r"Apple\s*Watch\s*Series\s*\d+",
            r"(?:售价|价格|降价|补贴)[^，。；]{0,12}\d+(?:\.\d+)?(?:元|美元|万元)",
        )
        normalized_allowed = allowed_text.lower().replace(" ", "")
        claims: list[str] = []
        for pattern in patterns:
            for claim in re.findall(pattern, text, flags=re.IGNORECASE):
                if claim.lower().replace(" ", "") not in normalized_allowed:
                    claims.append(claim)
        return list(dict.fromkeys(claims))

    def _call_llm(
        self,
        topic: str,
        style: str,
        duration_desc: str,
        proj_id: str,
        source_content: str = "",
        source_platform: str = "",
        captured_at: str = "",
        chosen_angle: str = "",
    ) -> Optional[Dict[str, Any]]:
        """调用 DeepSeek / OpenAI 接口生成高信息量剧本"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        user_prompt = SCRIPT_USER_TEMPLATE.format(
            topic_or_content=topic,
            chosen_angle=chosen_angle or "（未指定特定切口，请按选定风格最炸裂的网感视角自由展开）",
            style=style,
            duration_spec=duration_desc,
            source_content=source_content or "（无额外背景材料）",
        )
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SCRIPT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.92,
            "response_format": {"type": "json_object"} if "deepseek" in self.model.lower() or "gpt" in self.model.lower() else None
        }
        
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        
        if resp.status_code != 200:
            raise RuntimeError(f"API 返回错误: {resp.status_code} - {resp.text}")
            
        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"].strip()
        
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if json_match:
            script_data = json.loads(json_match.group(0))
            script_data["project_id"] = proj_id
            return script_data
            
        return None

    def _generate_deep_fallback_script(self, topic: str, style: str, proj_id: str) -> VideoProjectScript:
        """生成 6 幕高信息密度、逻辑严密的完整爆款剧本（保底生成）"""
        clean_topic = topic.strip()
        variant = int(hashlib.sha256(f"{clean_topic}:{style}".encode("utf-8")).hexdigest()[:8], 16) % 3
        openings = [
            f"先别急着给【{clean_topic}】下结论。把镜头拉近，真正影响结果的，往往是被讨论声量盖住的那个细节。",
            f"如果把【{clean_topic}】当成一笔账来算，最贵的通常不在明面上，而在被忽略的时间、选择和机会成本里。",
            f"关于【{clean_topic}】，有两种说法听起来都对，却会把人带向相反的行动。分歧究竟藏在哪里？",
        ]
        
        scenes_data = [
            {
                "scene_index": 1,
                "voiceover_text": openings[variant],
                "visual_keywords": ["documentary close up", "street observation", "notebook detail"],
                "image_prompt": "cinematic dark portrait of a focused person with intense eye contact and neon edge light",
                "caption_highlight": [clean_topic[:12], "被忽略的细节"],
                "transition": "zoom_in"
            },
            {
                "scene_index": 2,
                "voiceover_text": f"先拆掉一个常见混淆：讨论【{clean_topic}】时，人们经常把现象、原因和结果揉成一句话。信息越热闹，因果关系反而越容易被省略。",
                "visual_keywords": ["news wall investigation", "cause effect diagram", "crowded discussion"],
                "image_prompt": "abstract futuristic neural network with glowing synapses and gears",
                "caption_highlight": ["表象当本质", "对抗本能", "报复性摆烂"],
                "transition": "fade"
            },
            {
                "scene_index": 3,
                "voiceover_text": "判断它，不妨连续问三次：谁在做选择，谁承担代价，谁从这个叙事中获益。三个答案如果不是同一群人，关键通常就在这里。",
                "visual_keywords": ["three people negotiation", "receipt cost closeup", "decision making office"],
                "image_prompt": "glowing golden geometric loops and upward momentum in modern studio",
                "caption_highlight": ["正向反馈闭环", "环境推着往前走", "骗过大脑"],
                "transition": "slide_left"
            },
            {
                "scene_index": 4,
                "voiceover_text": f"把方法落到【{clean_topic}】：先记录一个可观察事实，再找一个反例，最后写下结论成立的边界。少一个步骤，都可能只是立场，不是判断。",
                "visual_keywords": ["field notes writing", "fact checking documents", "counterexample cards"],
                "image_prompt": "determined athlete at starting line bathed in golden morning sun",
                "caption_highlight": ["戒掉完美主义", "微小动作", "惯性接管执行力"],
                "transition": "fade"
            },
            {
                "scene_index": 5,
                "voiceover_text": "更稳妥的答案往往没那么痛快：它允许例外，也承认信息不足。但正是这些边界，让观点能经得住下一条新闻和下一次现实检验。",
                "visual_keywords": ["quiet newsroom desk", "boundary line map", "editor reviewing notes"],
                "image_prompt": "inspirational panoramic mountain peak view with cinematic soft rays",
                "caption_highlight": ["最大差距", "底层认知", "思维一变"],
                "transition": "zoom_in"
            },
            {
                "scene_index": 6,
                "voiceover_text": f"所以把问题留给你：在【{clean_topic}】里，你亲眼见过的事实，和最流行的说法一致吗？说一个具体经历，比站队更有价值。",
                "visual_keywords": ["street interview microphone", "real people conversation", "community testimony"],
                "image_prompt": "confident person smiling in golden hour with warm welcoming lighting",
                "caption_highlight": ["双击收藏", "第一步微行动", "见证蜕变"],
                "transition": "fade"
            }
        ]
        
        return VideoProjectScript(
            project_id=proj_id,
            title=f"把【{clean_topic}】放回真实现场",
            topic_summary=f"从可观察事实、因果关系与适用边界三个层次重新审视{clean_topic}",
            tone_style=style,
            bgm_type="energetic",
            scenes=scenes_data,
            tags=[clean_topic, "现场观察", "因果拆解", "观点边界"],
            grounding_status="topic_only",
            freshness_note="LLM 不可用且无事实核验材料，兜底稿不包含具体时效性断言",
        )

    def generate_angles(
        self,
        topic: str,
        raw_content: str = "",
        category: str = "",
    ) -> list[dict[str, Any]]:
        """
        根据原始热搜/选题，调用大模型生成 3~4 个差异化的短视频爆款切口（Angle）供用户选择
        """
        clean_topic = topic.strip()
        if self.api_key:
            try:
                system_prompt = (
                    "你是一位顶级短视频内容总监与爆款操盘手。你的任务是将用户提供的原始热点话题或新闻，"
                    "解构成 3~4 个差异化明显、极具完播率和讨论度的短视频【核心切入口（Angle / Hook 视角）】。\n"
                    "请以 JSON 格式输出，根节点为 'angles' 数组，每个切口包含以下字段：\n"
                    "- id: 切口唯一标识（如 'angle_1', 'angle_2'）\n"
                    "- tag: 切口类型标签（如：'🔥 颠覆反常识' / '💡 深度底层逻辑' / '🎭 情绪共鸣吐槽' / '⚡ 实操避坑指南' / '⚖️ 深度利弊权衡'）\n"
                    "- title: 经过切口重塑后的爆款短视频标题（必须极具点击欲与吸引力）\n"
                    "- hook: 黄金前 3 秒抓人开篇台词示例（20~35字，必须极有悬念感）\n"
                    "- core_conflict: 该切口的核心戏剧冲突或思考维度（15~30字）\n"
                    "- target_audience: 适合触达的受众群体（如：青年职场人、大众泛用户、数码科技迷）\n"
                )
                user_prompt = (
                    f"原始热点话题：《{clean_topic}》\n"
                    f"背景信息/来源详情：{raw_content or '（无额外背景）'}\n"
                    f"所属赛道：{category or '全网热点'}\n"
                    "请输出 3~4 个高质感、高完播率的切口 JSON："
                )
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.88,
                    "response_format": {"type": "json_object"} if "deepseek" in self.model.lower() or "gpt" in self.model.lower() else None
                }
                url = f"{self.base_url.rstrip('/')}/chat/completions"
                resp = requests.post(url, headers=headers, json=payload, timeout=35)
                if resp.status_code == 200:
                    raw_text = resp.json()["choices"][0]["message"]["content"].strip()
                    json_match = re.search(r'\[.*\]|\{.*\}', raw_text, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group(0))
                        angles = []
                        if isinstance(parsed, list):
                            angles = parsed
                        elif isinstance(parsed, dict):
                            angles = parsed.get("angles") or parsed.get("items") or parsed.get("list") or parsed.get("data") or []
                            if not angles:
                                for v in parsed.values():
                                    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                                        angles = v
                                        break
                        if angles and len(angles) > 0:
                            for idx, a in enumerate(angles):
                                a["id"] = f"angle_{idx + 1}"
                                if not a.get("title"):
                                    a["title"] = f"关于【{clean_topic}】的深度思考"
                                if not a.get("hook"):
                                    a["hook"] = f"很多人看【{clean_topic}】只看了表面，但真正关键的细节藏在这里。"
                                if not a.get("tag"):
                                    a["tag"] = "💡 深度切口"
                            return angles
            except Exception as e:
                logger.warning("LLM 生成切口失败，降级至规则切口生成: %s", e)

        # 规则保底切口生成
        return self._generate_fallback_angles(clean_topic, category)

    def _generate_fallback_angles(self, topic: str, category: str = "") -> list[dict[str, Any]]:
        """保底生成 4 个不同维度的爆款创作切口"""
        return [
            {
                "id": "angle_1",
                "tag": "🔥 颠覆反常识",
                "title": f"为什么所有人都看好【{topic}】，我却劝你三思？",
                "hook": f"90%的人看到【{topic}】都在跟风凑热闹，但如果把底层逻辑拆开看，真正的陷阱才刚刚浮出水面。",
                "core_conflict": "打破大众直觉惯性，揭示被忽略的成本与潜在盲区",
                "target_audience": "追求独立思考、渴望避坑的理性观众"
            },
            {
                "id": "angle_2",
                "tag": "💡 深度底层逻辑",
                "title": f"读懂【{topic}】背后这笔账，你就看透了游戏规则",
                "hook": f"表面上看这只是一条热搜，但往深挖一层，本质上是一场关于利益、资源与注意力的重新分配。",
                "core_conflict": "从商业资本/系统机制维度透视事件驱动力",
                "target_audience": "关注商业模式、行业趋势与成长认知的群体"
            },
            {
                "id": "angle_3",
                "tag": "🎭 强烈情绪共鸣",
                "title": f"关于【{topic}】，说出了多少普通人不敢提的真实心声？",
                "hook": f"今天刷到【{topic}】，底下有一条评论瞬间戳中了无数人：我们真正焦虑的从来不是事件本身，而是身处其中的无力感。",
                "core_conflict": "精准捕捉社会群体心理投射，拉满情绪共鸣与转评欲",
                "target_audience": "大众泛用户、渴望情感宣泄与同频认同的受众"
            },
            {
                "id": "angle_4",
                "tag": "⚡ 普通人破局行动",
                "title": f"【{topic}】发生后，普通人如何抓住第一波红利？",
                "hook": f"每次出现【{topic}】这样的风口，有人在围观，有人已经在悄悄执行这3步破局法了。",
                "core_conflict": "将宏大热点落脚到普通个体的微观实操行动",
                "target_audience": "注重效率落地、搞钱实战与个人增值的创作者"
            }
        ]

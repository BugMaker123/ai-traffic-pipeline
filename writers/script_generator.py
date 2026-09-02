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
    ) -> VideoProjectScript:
        """
        根据输入主题与时长档位，生成深度饱满的结构化分镜剧本
        """
        proj_id = project_id or f"proj_{uuid.uuid4().hex[:8]}"
        duration_desc = DURATION_PRESETS.get(duration_tier, DURATION_PRESETS["deep_60s"])
        
        # 1. 尝试调用大模型 API
        if self.api_key:
            try:
                script_dict = self._call_llm(
                    topic_or_content, style, duration_desc, proj_id,
                    source_content, source_platform, captured_at,
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
        self, topic: str, style: str, duration_desc: str, proj_id: str,
        source_content: str = "", source_platform: str = "", captured_at: str = "",
    ) -> Optional[Dict[str, Any]]:
        """调用 DeepSeek / OpenAI 接口生成高信息量剧本"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        user_prompt = SCRIPT_USER_TEMPLATE.format(
            topic_or_content=topic,
            style=style,
            duration_spec=duration_desc,
            current_date=date.today().isoformat(),
            source_platform=source_platform or "未提供",
            captured_at=captured_at or "未提供",
            source_content=source_content or "（无事实材料）",
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

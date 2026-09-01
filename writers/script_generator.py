"""
LLM 深度爆款脚本与多档位分镜生成引擎 (DeepSeek / OpenAI 兼容)
"""
import os
import json
import logging
import re
import uuid
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
        project_id: Optional[str] = None
    ) -> VideoProjectScript:
        """
        根据输入主题与时长档位，生成深度饱满的结构化分镜剧本
        """
        proj_id = project_id or f"proj_{uuid.uuid4().hex[:8]}"
        duration_desc = DURATION_PRESETS.get(duration_tier, DURATION_PRESETS["deep_60s"])
        
        # 1. 尝试调用大模型 API
        if self.api_key:
            try:
                script_dict = self._call_llm(topic_or_content, style, duration_desc, proj_id)
                if script_dict and "scenes" in script_dict and len(script_dict["scenes"]) > 0:
                    return VideoProjectScript(**script_dict)
            except Exception as e:
                logger.warning("LLM API 调用失败，切换至模板引擎: %s", e)

        # 2. 深度多幕剧本兜底生成
        return self._generate_deep_fallback_script(topic_or_content, style, proj_id)

    def _call_llm(self, topic: str, style: str, duration_desc: str, proj_id: str) -> Optional[Dict[str, Any]]:
        """调用 DeepSeek / OpenAI 接口生成高信息量剧本"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        user_prompt = SCRIPT_USER_TEMPLATE.format(
            topic_or_content=topic,
            style=style,
            duration_spec=duration_desc
        )
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SCRIPT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.75,
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
        
        scenes_data = [
            {
                "scene_index": 1,
                "voiceover_text": f"为什么关于【{clean_topic}】，90% 的普通人每天都在做无效努力，而极少数真正的高手却能轻松破局？真相可能会彻底颠覆你的认知！",
                "visual_keywords": ["shocked person", "thinking deeply", "dark neon light"],
                "image_prompt": "cinematic dark portrait of a focused person with intense eye contact and neon edge light",
                "caption_highlight": ["90%普通人", "无效努力", "轻松破局"],
                "transition": "zoom_in"
            },
            {
                "scene_index": 2,
                "voiceover_text": "很多人最大的误区，就是把表象当本质，以为只要咬牙硬撑就能拿到结果。但心理学与行为科学研究证实：对抗本能的努力，只会带来报复性的摆烂与内耗。",
                "visual_keywords": ["human brain glowing", "clock mechanism", "chess game strategy"],
                "image_prompt": "abstract futuristic neural network with glowing synapses and gears",
                "caption_highlight": ["表象当本质", "对抗本能", "报复性摆烂"],
                "transition": "fade"
            },
            {
                "scene_index": 3,
                "voiceover_text": "顶尖高手的核心秘诀，从来不是意志力有多强，而是懂得设计‘正向反馈闭环’，让系统和环境推着自己往前走，从而用极低的阻力骗过大脑。",
                "visual_keywords": ["growth chart upward", "domino effect", "sunrise landscape"],
                "image_prompt": "glowing golden geometric loops and upward momentum in modern studio",
                "caption_highlight": ["正向反馈闭环", "环境推着往前走", "骗过大脑"],
                "transition": "slide_left"
            },
            {
                "scene_index": 4,
                "voiceover_text": "想要彻底破局，第一步就是戒掉‘完美主义’。把宏大的目标切碎成两分钟内就能完成的微小动作，先启动，让惯性接管你的执行力。",
                "visual_keywords": ["runner starting line", "focus concentration", "morning sun"],
                "image_prompt": "determined athlete at starting line bathed in golden morning sun",
                "caption_highlight": ["戒掉完美主义", "微小动作", "惯性接管执行力"],
                "transition": "fade"
            },
            {
                "scene_index": 5,
                "voiceover_text": "记住：人与人之间最大的差距，不在于起跑线，而在于是否具备对事物本质规律的底层认知。思维一变，你的整个世界都会跟着改变。",
                "visual_keywords": ["golden horizon light", "achievement success", "mountain peak"],
                "image_prompt": "inspirational panoramic mountain peak view with cinematic soft rays",
                "caption_highlight": ["最大差距", "底层认知", "思维一变"],
                "transition": "zoom_in"
            },
            {
                "scene_index": 6,
                "voiceover_text": "双击点赞收藏这条视频，提醒自己在迷茫时随时重温。在评论区写下你今天的第一步微行动，我们一起见证蜕变！",
                "visual_keywords": ["thumbs up motivation", "community connection", "focus"],
                "image_prompt": "confident person smiling in golden hour with warm welcoming lighting",
                "caption_highlight": ["双击收藏", "第一步微行动", "见证蜕变"],
                "transition": "fade"
            }
        ]
        
        return VideoProjectScript(
            project_id=proj_id,
            title=f"90%的人都不知道的【{clean_topic}】破局真相",
            topic_summary=f"深度拆解{clean_topic}的底层机制与步骤化落地破局方案",
            tone_style=style,
            bgm_type="energetic",
            scenes=scenes_data,
            tags=[clean_topic, "深度认知", "底层逻辑", "个人成长", "自律逆袭"]
        )

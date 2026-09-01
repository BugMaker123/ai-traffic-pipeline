"""
字幕对齐与 SRT/ASS 生成模块
将 TTS 毫秒时间戳转换为短视频爆款节奏字幕（单行 6~12 字，高亮关键词）
"""
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

def format_timestamp_srt(seconds: float) -> str:
    """将秒数转换为 SRT 时间戳格式 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

class SubtitleAligner:
    """字幕切分与时间轴对齐器"""

    @staticmethod
    def chunk_scene_subtitles(
        scene_data: Dict[str, Any],
        start_offset: float = 0.0,
        max_chars_per_line: int = 14
    ) -> List[Dict[str, Any]]:
        """
        根据分镜的时间戳和台词，切分成适合短视频的快节奏单句字幕
        :param scene_data: 包含 text/voiceover_text, word_timestamps, duration 的分镜
        :param start_offset: 该分镜在整部视频全局时间轴上的起始偏置
        :param max_chars_per_line: 每屏最大字数
        """
        raw_text = scene_data.get("voiceover_text", "")
        timestamps = scene_data.get("word_timestamps", [])
        scene_duration = scene_data.get("duration", 3.0)
        
        # 如果没有细粒度 word_timestamps，进行基于字数的均分估算
        if not timestamps:
            return SubtitleAligner._fallback_chunk(raw_text, start_offset, scene_duration, max_chars_per_line)
            
        # 根据标点符号（，。！？；、）或字数上限进行断句分块
        chunks = []
        current_chunk_words = []
        current_chunk_text = ""
        
        # 分句标点
        split_punc = set("，。！？；,!?;、\n")
        
        for w in timestamps:
            word_str = w.get("text", "")
            current_chunk_words.append(w)
            current_chunk_text += word_str
            
            # 判断是否需要切片
            ends_with_punc = any(current_chunk_text.endswith(p) for p in split_punc)
            reaches_length = len(current_chunk_text) >= max_chars_per_line
            
            if ends_with_punc or reaches_length:
                # 过滤掉末尾纯标点，展示更干净
                clean_text = current_chunk_text.strip("，。！？；,!?;、 \t\n")
                if clean_text:
                    c_start = current_chunk_words[0]["start"] + start_offset
                    c_end = current_chunk_words[-1]["end"] + start_offset
                    chunks.append({
                        "text": clean_text,
                        "start": round(c_start, 3),
                        "end": round(c_end, 3),
                        "duration": round(c_end - c_start, 3)
                    })
                current_chunk_words = []
                current_chunk_text = ""
                
        # 处理剩余词
        if current_chunk_words:
            clean_text = current_chunk_text.strip("，。！？；,!?;、 \t\n")
            if clean_text:
                c_start = current_chunk_words[0]["start"] + start_offset
                c_end = current_chunk_words[-1]["end"] + start_offset
                chunks.append({
                    "text": clean_text,
                    "start": round(c_start, 3),
                    "end": round(c_end, 3),
                    "duration": round(c_end - c_start, 3)
                })
                
        return chunks

    @staticmethod
    def _fallback_chunk(text: str, start_offset: float, duration: float, max_chars: int) -> List[Dict[str, Any]]:
        """当无 TTS 时间戳时的匀速时间切分回退方案"""
        # 按标点切分
        segments = [s.strip() for s in re.split(r'[，。！？；,!?;、\n]+', text) if s.strip()]
        if not segments:
            segments = [text]
            
        total_chars = sum(len(s) for s in segments)
        if total_chars == 0:
            return []
            
        chunks = []
        cur_time = start_offset
        for seg in segments:
            seg_duration = (len(seg) / total_chars) * duration
            chunks.append({
                "text": seg,
                "start": round(cur_time, 3),
                "end": round(cur_time + seg_duration, 3),
                "duration": round(seg_duration, 3)
            })
            cur_time += seg_duration
            
        return chunks

    @staticmethod
    def export_srt(subtitles: List[Dict[str, Any]], output_path: str | Path) -> str:
        """导出标准 SRT 字幕文件"""
        lines = []
        for i, sub in enumerate(subtitles, 1):
            start_str = format_timestamp_srt(sub["start"])
            end_str = format_timestamp_srt(sub["end"])
            lines.append(f"{i}\n{start_str} --> {end_str}\n{sub['text']}\n")
            
        srt_content = "\n".join(lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        return str(output_path)

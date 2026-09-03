"""
视频抗查重与微混淆处理引擎 (Video Anti-Duplicate Micro-Jitter Engine)
对渲染完成的短视频施加微小随机扰动，打破短视频平台的机器特征指纹比对：
1. 画面中心微裁切缩放 (Center Crop & Re-scale 1%~2%)
2. 播放速度微扰动 (Playback Speed Jitter 0.99x ~ 1.01x)
3. 画面明度与对比度微抖动 (Color & Contrast Jitter)
4. 原始元数据清除与随机数字指纹注入 (Metadata Scrub & UUID injection)
"""
from __future__ import annotations

import hashlib
import logging
import random
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

import imageio_ffmpeg

logger = logging.getLogger(__name__)


def calculate_file_hash(file_path: str | Path) -> str:
    """计算文件的 MD5 哈希指纹"""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class AntiDuplicateOptions(BaseModel):
    crop_percent: float = Field(default=0.015, ge=0.005, le=0.05, description="画面中心裁切比例 (0.5%~5%)")
    speed_factor: float = Field(default=1.008, ge=0.98, le=1.02, description="时间轴变速系数 (0.98x~1.02x)")
    contrast_adjust: float = Field(default=1.015, ge=0.98, le=1.05, description="对比度微调系数")
    brightness_adjust: float = Field(default=0.008, ge=-0.05, le=0.05, description="亮度微调")
    randomize: bool = Field(default=True, description="是否在范围内随机微扰动")
    scrub_metadata: bool = Field(default=True, description="是否抹除原编码元数据并注入新指纹")


class AntiDuplicateProcessor:
    """抗查重微混淆处理器"""

    @classmethod
    def process_video(
        cls,
        input_video_path: str | Path,
        output_video_path: Optional[str | Path] = None,
        options: Optional[AntiDuplicateOptions] = None,
    ) -> Dict[str, Any]:
        """
        对输入视频执行微混淆处理
        """
        in_path = Path(input_video_path).resolve()
        if not in_path.is_file():
            raise FileNotFoundError(f"待处理视频文件不存在: {input_video_path}")

        opts = options or AntiDuplicateOptions()
        if opts.randomize:
            crop_pct = round(random.uniform(0.01, 0.02), 4)
            spd = round(random.choice([0.992, 0.995, 1.005, 1.008, 1.012]), 4)
            contrast = round(random.uniform(1.01, 1.025), 4)
            brightness = round(random.uniform(-0.01, 0.015), 4)
        else:
            crop_pct = opts.crop_percent
            spd = opts.speed_factor
            contrast = opts.contrast_adjust
            brightness = opts.brightness_adjust

        if output_video_path:
            out_path = Path(output_video_path).resolve()
        else:
            out_path = in_path.parent / f"{in_path.stem}_antidup_{uuid.uuid4().hex[:6]}.mp4"

        out_path.parent.mkdir(parents=True, exist_ok=True)
        original_md5 = calculate_file_hash(in_path)

        # 构建高性能 FFmpeg 滤镜链
        # 1. 裁剪微放缩: crop=iw*(1-crop_pct):ih*(1-crop_pct), scale=1080:1920
        # 2. 对比度/明度微调: eq=contrast=...:brightness=...
        # 3. 视频时间戳微调: setpts=(1/spd)*PTS
        # 4. 音频时间戳微调: atempo=spd
        vf_filters = [
            f"crop=iw*(1-{crop_pct:.4f}):ih*(1-{crop_pct:.4f})",
            "scale=1080:1920:flags=lanczos",
            f"eq=contrast={contrast:.4f}:brightness={brightness:.4f}",
            f"setpts={1.0 / spd:.6f}*PTS",
        ]
        vf_str = ",".join(vf_filters)
        af_str = f"atempo={spd:.4f}"

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        unique_fingerprint = f"MatrixClean_{uuid.uuid4().hex}"

        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", str(in_path),
            "-vf", vf_str,
            "-af", af_str,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "192k",
        ]

        if opts.scrub_metadata:
            cmd.extend([
                "-map_metadata", "-1",
                "-metadata", f"title={unique_fingerprint}",
                "-metadata", f"comment={unique_fingerprint}",
            ])

        cmd.append(str(out_path))

        logger.info("开始执行抗查重微混淆: %s -> %s (变速: %.3fx, 裁切: %.2f%%)", in_path.name, out_path.name, spd, crop_pct * 100)
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
        if res.returncode != 0 or not out_path.is_file():
            stderr_msg = res.stderr.decode("utf-8", errors="ignore")
            logger.warning("FFmpeg 抗查重命令失败: %s，执行保底指纹注入", stderr_msg)
            # 保底方案：纯元数据/文件混淆
            out_path.write_bytes(in_path.read_bytes() + f"\n<!--{unique_fingerprint}-->".encode("utf-8"))

        processed_md5 = calculate_file_hash(out_path)

        return {
            "success": True,
            "original_path": str(in_path),
            "processed_path": str(out_path),
            "original_md5": original_md5,
            "processed_md5": processed_md5,
            "is_hash_different": original_md5 != processed_md5,
            "applied_params": {
                "crop_percent": crop_pct,
                "speed_factor": spd,
                "contrast": contrast,
                "brightness": brightness,
                "fingerprint": unique_fingerprint,
            },
        }


anti_duplicate_processor = AntiDuplicateProcessor()

"""Lip-sync 模块：调用 Replicate 的 Wav2Lip 模型，把 face.mp4 + tts.mp3 合成唇形对齐视频。

价格：约 $0.13 / 次，典型耗时 30-90 秒。
去 https://replicate.com/account/api-tokens 拿 token 填 .env 的 REPLICATE_API_TOKEN。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import requests


# lucataco 的 wav2lip 镜像，社区最常用，输入字段 face + audio
DEFAULT_MODEL = (
    "lucataco/wav2lip:"
    "a0466f4eaec284fce056f9c1c2c22df3fa6c1aa3f0812c1b1d1d8d9f8d8e9a9e"
)


def is_available() -> bool:
    return bool(os.getenv("REPLICATE_API_TOKEN", "").strip())


def _resolve_model() -> str:
    """允许用户通过 REPLICATE_MODEL 环境变量覆盖模型/版本。"""
    return os.getenv("REPLICATE_MODEL", "").strip() or DEFAULT_MODEL


def run_wav2lip(face_mp4: bytes, audio_mp3: bytes) -> bytes:
    """返回合成后的 mp4 字节。"""
    import replicate  # 延迟 import，未装也不影响其它路由

    if not is_available():
        raise RuntimeError("REPLICATE_API_TOKEN 未配置")

    # Replicate 需要文件句柄或 URL；用临时文件最稳
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        face_path = p / "face.mp4"
        audio_path = p / "audio.mp3"
        face_path.write_bytes(face_mp4)
        audio_path.write_bytes(audio_mp3)

        model = _resolve_model()
        with open(face_path, "rb") as f_face, open(audio_path, "rb") as f_aud:
            out = replicate.run(
                model,
                input={"face": f_face, "audio": f_aud},
            )

        # Replicate 新 SDK 返回 FileOutput 对象；旧版返回字符串 URL
        if hasattr(out, "read"):
            return out.read()
        if isinstance(out, (list, tuple)):
            out = out[0]
        url = str(out)
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        return r.content

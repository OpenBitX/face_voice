"""TTS 客户端：**仅使用 Cartesia TTS（付费）**。

不再支持 讯飞 / Fish Audio / Microsoft Edge TTS —— 全链路走 Cartesia Sonic。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterator

from . import cartesia_tts
from .cartesia_tts import CartesiaCredentials, CartesiaTTSError


@dataclass(slots=True)
class TTSConfig:
    cartesia_api_key: str = ""
    voice_id: str = cartesia_tts.DEFAULT_VOICE_ID
    model_id: str = cartesia_tts.DEFAULT_MODEL
    language: str = cartesia_tts.DEFAULT_LANGUAGE
    speed: str = "normal"

    @classmethod
    def from_env(cls) -> "TTSConfig":
        return cls(
            cartesia_api_key=os.getenv("CARTESIA_API_KEY", "").strip(),
            voice_id=(
                os.getenv("CARTESIA_VOICE_ID", "").strip()
                or cartesia_tts.DEFAULT_VOICE_ID
            ),
            model_id=(
                os.getenv("CARTESIA_MODEL", "").strip()
                or cartesia_tts.DEFAULT_MODEL
            ),
            language=(
                os.getenv("CARTESIA_LANGUAGE", "").strip()
                or cartesia_tts.DEFAULT_LANGUAGE
            ),
        )

    def credentials(self) -> CartesiaCredentials:
        return CartesiaCredentials(api_key=self.cartesia_api_key)


class TTSError(Exception):
    pass


def synthesize(text: str, cfg: TTSConfig) -> tuple[bytes, str]:
    """调用 Cartesia 合成整段 mp3，返回 (mp3_bytes, "cartesia")。"""
    creds = cfg.credentials()
    if not creds.ok():
        raise TTSError(
            "Cartesia 凭证未配置：请在 .env 里填 CARTESIA_API_KEY"
        )
    try:
        audio = cartesia_tts.synthesize(
            text,
            creds,
            voice_id=cfg.voice_id,
            model_id=cfg.model_id,
            language=cfg.language,
            speed=cfg.speed,
        )
    except CartesiaTTSError as exc:
        raise TTSError(f"cartesia: {exc}") from exc

    return audio, "cartesia"


def synthesize_stream(text: str, cfg: TTSConfig) -> Iterator[bytes]:
    """流式接口（对浏览器 <audio> 友好）；当前实现整段合成后一次 yield。"""
    audio, _ = synthesize(text, cfg)
    yield audio

"""语音转文字(ASR)：接收音频 blob，转码为 wav 后走录音文件识别极速版(AUC)。

前端 MediaRecorder 产出的通常是 webm/opus,而 AUC 接口只认 wav/ogg/mp3/mp4,
所以这里统一用 ffmpeg 转成 16k 单声道 wav,再以 base64 内联进 submit 请求。
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import config
from ..asr_client import AucFileAsrClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/asr", tags=["asr"])


def _to_wav(audio_bytes: bytes) -> bytes:
    """用 ffmpeg 把任意容器的音频转成 16k 单声道 wav。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(500, "服务器缺少 ffmpeg,无法转码音频")
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error",
         "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"],
        input=audio_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise HTTPException(
            400, "音频转码失败：" + proc.stderr.decode("utf-8", "replace")[:200]
        )
    return proc.stdout


def _transcribe(client: AucFileAsrClient, audio_bytes: bytes) -> str:
    wav = _to_wav(audio_bytes)
    return client.transcribe_bytes(wav, audio_format="wav").text


@router.post("")
async def transcribe(audio: UploadFile = File(...)):
    asr_cfg = config.get_asr_config()
    client = AucFileAsrClient(
        appid=asr_cfg.get("appid") or "",
        token=asr_cfg.get("token") or "",
        cluster=asr_cfg.get("cluster") or "",
        timeout=int(asr_cfg.get("timeout") or 60),
    )
    if not client.configured:
        raise HTTPException(
            400,
            "ASR 未配置：请在设置里填写 asr.appid / asr.token / asr.cluster",
        )

    data = await audio.read()
    if not data:
        raise HTTPException(400, "empty audio")

    try:
        text = await asyncio.to_thread(_transcribe, client, data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 面向前端返回可读错误
        logger.exception("ASR transcription failed")
        raise HTTPException(502, f"ASR 识别失败：{exc}") from exc

    return {"text": text}

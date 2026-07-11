"""录音文件识别极速版(AUC submit/query)客户端。

与豆包大模型 flash 接口不同,这套接口是两段式:
  1. POST /api/v1/auc/submit  提交任务(本 demo 走 base64 `data` 内联音频)
  2. POST /api/v1/auc/query   轮询任务结果

鉴权: header `Authorization: Bearer; {token}`,并在 body 的 app 段再带 appid/token/cluster。
凭证(appid / token / cluster)从控制台"创建应用并开通录音文件识别极速版服务"后获得。
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Optional

import requests

_SUBMIT_URL = "https://openspeech.bytedance.com/api/v1/auc/submit"
_QUERY_URL = "https://openspeech.bytedance.com/api/v1/auc/query"


@dataclass
class AsrResult:
    text: str
    raw: Optional[dict] = None


class AucFileAsrClient:
    def __init__(
        self,
        appid: str = "",
        token: str = "",
        cluster: str = "",
        timeout: int = 60,
        poll_interval: float = 1.0,
    ):
        self.appid = appid
        self.token = token
        self.cluster = cluster
        self.timeout = timeout
        self.poll_interval = poll_interval

    @property
    def configured(self) -> bool:
        return bool(self.appid and self.token and self.cluster)

    def _headers(self) -> dict:
        # 注意:官方示例就是 "Bearer; {token}"(分号 + 空格),不是标准 Bearer。
        return {
            "Authorization": "Bearer; {}".format(self.token),
            "Content-Type": "application/json",
        }

    def submit(self, audio_bytes: bytes, audio_format: str = "wav") -> str:
        b64 = base64.b64encode(audio_bytes).decode("utf-8")
        body = {
            "app": {"appid": self.appid, "token": self.token, "cluster": self.cluster},
            "user": {"uid": "miniapp-fortune-teller"},
            "audio": {"format": audio_format, "data": b64},
            "additions": {"use_itn": "True", "use_punc": "True"},
        }
        resp = requests.post(_SUBMIT_URL, json=body, headers=self._headers(), timeout=self.timeout)
        data = resp.json()
        r = data.get("resp", {})
        code = int(r.get("code", -1))
        if code != 1000:
            raise RuntimeError(
                "submit failed: code={}, message={}".format(code, r.get("message"))
            )
        task_id = r.get("id")
        if not task_id:
            raise RuntimeError("submit ok but no task id: {}".format(data))
        return task_id

    def query(self, task_id: str) -> dict:
        body = {
            "appid": self.appid,
            "token": self.token,
            "cluster": self.cluster,
            "id": task_id,
        }
        resp = requests.post(_QUERY_URL, json=body, headers=self._headers(), timeout=self.timeout)
        return resp.json().get("resp", {})

    def transcribe_bytes(self, audio_bytes: bytes, audio_format: str = "wav") -> AsrResult:
        task_id = self.submit(audio_bytes, audio_format=audio_format)
        deadline = time.time() + self.timeout
        while True:
            r = self.query(task_id)
            code = int(r.get("code", -1))
            if code == 1000:
                return AsrResult(text=r.get("text", ""), raw=r)
            if code == 1013:  # 静音,无文本
                return AsrResult(text="", raw=r)
            if code not in (2000, 2001):  # 非"处理中/排队中" -> 失败
                raise RuntimeError(
                    "query failed: code={}, message={}".format(code, r.get("message"))
                )
            if time.time() > deadline:
                raise RuntimeError("query timeout after {}s".format(self.timeout))
            time.sleep(self.poll_interval)

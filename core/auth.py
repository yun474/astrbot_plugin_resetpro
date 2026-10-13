from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent


def normalize_ids(raw_ids: Any) -> set[str]:
    """把列表或逗号/换行分隔的文本统一成去空白的字符串集合。"""
    if raw_ids is None:
        return set()

    if isinstance(raw_ids, str):
        raw_iterable: Iterable[Any] = (
            raw_ids.replace("，", ",").replace("\n", ",").split(",")
        )
    elif isinstance(raw_ids, Iterable):
        raw_iterable = raw_ids
    else:
        raw_iterable = [raw_ids]

    return {str(raw_id).strip() for raw_id in raw_iterable if str(raw_id).strip()}


def is_authorized(config: AstrBotConfig, event: AstrMessageEvent) -> bool:
    """判断发送者是否为 ResetPro 管理员。"""
    sender_id = str(event.get_sender_id() or "").strip()
    if sender_id and sender_id in normalize_ids(config.get("admin_ids", [])):
        return True
    if bool(config.get("use_astrbot_admins", True)) and event.is_admin():
        return True
    return False

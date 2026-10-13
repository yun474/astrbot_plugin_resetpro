from __future__ import annotations

from typing import Any

from astrbot.api import logger, sp
from astrbot.api.event import AstrMessageEvent
from astrbot.core.utils.active_event_registry import active_event_registry

CONVERSATION_PAGE_SIZE = 100
THIRD_PARTY_AGENT_STATE_KEYS = (
    "dify_conversation_id",
    "coze_conversation_id",
    "dashscope_conversation_id",
    "deerflow_thread_id",
)


async def get_all_conversations(conversation_manager: Any) -> list[Any]:
    """分页读取数据库中的全部对话（含历史内容）。"""
    conversations: list[Any] = []
    page = 1
    while True:
        batch = await conversation_manager.db.get_all_conversations(
            page=page,
            page_size=CONVERSATION_PAGE_SIZE,
        )
        conversations.extend(batch)
        if len(batch) < CONVERSATION_PAGE_SIZE:
            break
        page += 1
    return conversations


def collect_session_ids(conversations: list[Any]) -> list[str]:
    """按出现顺序收集对话所属的会话 ID（去重）。"""
    session_ids: list[str] = []
    seen: set[str] = set()
    for conversation in conversations:
        session_id = str(getattr(conversation, "user_id", "") or "")
        if session_id and session_id not in seen:
            session_ids.append(session_id)
            seen.add(session_id)
    return session_ids


def stop_active_events(
    session_ids: list[str],
    current_event: AstrMessageEvent | None = None,
) -> int:
    """停止指定会话中正在运行的事件，返回停止数量。"""
    stopped_count = 0
    for session_id in session_ids:
        try:
            stopped_count += active_event_registry.stop_all(
                session_id,
                exclude=current_event,
            )
        except Exception as exc:
            logger.warning(
                "ResetPro failed to stop active events for %s: %s",
                session_id,
                exc,
            )
    return stopped_count


def has_active_events(
    session_id: str,
    exclude: AstrMessageEvent | None = None,
) -> bool:
    """判断会话当前是否有正在处理的事件（不计 exclude，通常是触发巡检的指令本身）。

    注册表没有公开查询接口，这里读取其内部字典；读取失败时按无任务处理。
    """
    events = getattr(active_event_registry, "_events", None)
    if not isinstance(events, dict):
        return False
    return any(event is not exclude for event in events.get(session_id, ()))


async def clear_third_party_agent_state(session_ids: list[str]) -> None:
    """清除第三方 Agent Runner 在会话中保存的远端会话标识。"""
    for session_id in session_ids:
        for key in THIRD_PARTY_AGENT_STATE_KEYS:
            try:
                await sp.remove_async(
                    scope="umo",
                    scope_id=session_id,
                    key=key,
                )
            except Exception as exc:
                logger.warning(
                    "ResetPro failed to clear %s for %s: %s",
                    key,
                    session_id,
                    exc,
                )

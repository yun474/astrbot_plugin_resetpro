from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from astrbot.api import AstrBotConfig, logger, sp
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.active_event_registry import active_event_registry


CONVERSATION_PAGE_SIZE = 100
THIRD_PARTY_AGENT_STATE_KEYS = (
    "dify_conversation_id",
    "coze_conversation_id",
    "dashscope_conversation_id",
    "deerflow_thread_id",
)


@register(
    "astrbot_plugin_resetpro",
    "yun474",
    "One-command reset for every AstrBot conversation context.",
    "1.0.0",
)
class ResetProPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    @filter.command("resetpro")
    async def resetpro(self, event: AstrMessageEvent):
        """Clear all stored conversation contexts."""
        if not self._is_authorized(event):
            sender_id = event.get_sender_id() or "unknown"
            yield event.plain_result(
                f"主人，ResetPro 只给管理员用喔。当前 ID: {sender_id}"
            )
            return

        try:
            conversations = await self._get_all_conversations()
        except Exception as exc:
            logger.exception("ResetPro failed to load conversations: %s", exc)
            yield event.plain_result(f"ResetPro 读取会话失败：{exc}")
            return

        if not conversations:
            yield event.plain_result("ResetPro 没找到可清理的会话。")
            return

        session_ids = self._collect_session_ids(conversations)
        stopped_count = self._stop_active_events(session_ids, event)
        await self._clear_third_party_agent_state(session_ids)

        cleared_count = 0
        failed_items: list[str] = []
        conversation_manager = self.context.conversation_manager

        for conversation in conversations:
            conversation_id = getattr(conversation, "conversation_id", "")
            session_id = getattr(conversation, "user_id", "")
            if not conversation_id or not session_id:
                failed_items.append(conversation_id or session_id or "unknown")
                continue

            try:
                await conversation_manager.update_conversation(
                    session_id,
                    conversation_id,
                    [],
                    token_usage=0,
                )
                cleared_count += 1
            except Exception as exc:
                logger.warning(
                    "ResetPro failed to clear conversation %s: %s",
                    conversation_id,
                    exc,
                )
                failed_items.append(conversation_id)

        event.set_extra("_clean_ltm_session", True)
        result = (
            f"ResetPro 清理完成：已清空 {cleared_count} 个对话，"
            f"覆盖 {len(session_ids)} 个会话。"
        )
        if stopped_count:
            result += f" 已停止 {stopped_count} 个运行中的任务。"
        if failed_items:
            preview = ", ".join(failed_items[:5])
            suffix = "..." if len(failed_items) > 5 else ""
            result += f" 有 {len(failed_items)} 个对话清理失败：{preview}{suffix}"

        yield event.plain_result(result)

    async def _get_all_conversations(self) -> list[Any]:
        conversations: list[Any] = []
        page = 1
        while True:
            batch = await self.context.conversation_manager.db.get_all_conversations(
                page=page,
                page_size=CONVERSATION_PAGE_SIZE,
            )
            conversations.extend(batch)
            if len(batch) < CONVERSATION_PAGE_SIZE:
                break
            page += 1
        return conversations

    def _is_authorized(self, event: AstrMessageEvent) -> bool:
        sender_id = str(event.get_sender_id() or "").strip()
        if sender_id and sender_id in self._configured_admin_ids():
            return True
        if bool(self.config.get("use_astrbot_admins", True)) and event.is_admin():
            return True
        return False

    def _configured_admin_ids(self) -> set[str]:
        return self._normalize_ids(self.config.get("admin_ids", []))

    @staticmethod
    def _normalize_ids(raw_ids: Any) -> set[str]:
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

    @staticmethod
    def _collect_session_ids(conversations: list[Any]) -> list[str]:
        session_ids: list[str] = []
        seen: set[str] = set()
        for conversation in conversations:
            session_id = str(getattr(conversation, "user_id", "") or "")
            if session_id and session_id not in seen:
                session_ids.append(session_id)
                seen.add(session_id)
        return session_ids

    @staticmethod
    def _stop_active_events(
        session_ids: list[str],
        current_event: AstrMessageEvent,
    ) -> int:
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

    @staticmethod
    async def _clear_third_party_agent_state(session_ids: list[str]) -> None:
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

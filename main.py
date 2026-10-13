from __future__ import annotations

import time

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .core.auth import is_authorized
from .core.conversation_ops import (
    clear_third_party_agent_state,
    collect_session_ids,
    get_all_conversations,
    stop_active_events,
)
from .core.idle_cleaner import ACTION_COMPRESS, IdleCleaner


@register(
    "astrbot_plugin_resetpro",
    "yun474",
    "一键清空全部会话上下文，并可自动整理闲置会话。",
    "1.1.0",
    "https://github.com/yun474/astrbot_plugin_resetpro",
)
class ResetProPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.idle_cleaner = IdleCleaner(
            context, lambda: self.config.get("idle_cleanup", {})
        )

    async def initialize(self) -> None:
        self.idle_cleaner.start()

    async def terminate(self) -> None:
        await self.idle_cleaner.stop()

    def _deny_message(self, event: AstrMessageEvent) -> str:
        sender_id = event.get_sender_id() or "unknown"
        return f"主人，ResetPro 只给管理员用喔。当前 ID: {sender_id}"

    @filter.command("resetpro")
    async def resetpro(self, event: AstrMessageEvent):
        """清空全部会话的上下文。"""
        if not is_authorized(self.config, event):
            yield event.plain_result(self._deny_message(event))
            return

        try:
            conversations = await get_all_conversations(
                self.context.conversation_manager
            )
        except Exception as exc:
            logger.exception("ResetPro failed to load conversations: %s", exc)
            yield event.plain_result(f"ResetPro 读取会话失败：{exc}")
            return

        if not conversations:
            yield event.plain_result("ResetPro 没找到可清理的会话。")
            return

        session_ids = collect_session_ids(conversations)
        stopped_count = stop_active_events(session_ids, event)
        await clear_third_party_agent_state(session_ids)

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

        # 通知内置插件清空当前会话的群聊上下文缓存
        event.set_extra("_clean_group_context_session", True)
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

    @filter.command("resetidle")
    async def resetidle(self, event: AstrMessageEvent, action: str = ""):
        """查看闲置整理状态；/resetidle run 立即巡检一次。"""
        if not is_authorized(self.config, event):
            yield event.plain_result(self._deny_message(event))
            return

        if action == "run":
            result = await self.idle_cleaner.scan(exclude=event)
            yield event.plain_result(f"ResetPro 手动巡检完成：{result.summary()}")
            return

        settings = self.idle_cleaner.settings
        action_text = "LLM 压缩" if settings.action == ACTION_COMPRESS else "清空"
        scope_text = {"whitelist": "白名单", "blacklist": "黑名单"}.get(
            settings.scope_mode, "全部会话"
        )
        if settings.scope_mode in ("whitelist", "blacklist"):
            scope_text += f"（{len(settings.session_list)} 项）"
        lines = [
            f"闲置整理：{'已开启' if settings.enable else '未开启'}",
            (
                f"闲置 {settings.idle_minutes} 分钟后{action_text}，"
                f"每 {settings.scan_interval_minutes} 分钟巡检一次"
            ),
            f"范围：{scope_text}",
        ]
        last = self.idle_cleaner.last_result
        if last:
            when = time.strftime("%m-%d %H:%M", time.localtime(last.finished_at))
            lines.append(f"上次巡检（{when}）：{last.summary()}")
        else:
            lines.append("还没有巡检记录，可发送 /resetidle run 立即巡检。")
        yield event.plain_result("\n".join(lines))

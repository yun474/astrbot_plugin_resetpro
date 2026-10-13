from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from astrbot.api import logger, sp

from .compress import CompressFailed, CompressSkipped, compress_history
from .conversation_ops import has_active_events

PLUGIN_NAME = "astrbot_plugin_resetpro"
MARKS_KEY = "idle_cleanup_marks"
LIST_PAGE_SIZE = 200

ACTION_CLEAR = "clear"
ACTION_COMPRESS = "compress"
FAIL_CLEAR = "clear"


@dataclass
class IdleSettings:
    """闲置整理配置，取自插件配置的 idle_cleanup 段。"""

    enable: bool = False
    action: str = ACTION_CLEAR
    idle_minutes: int = 120
    scan_interval_minutes: int = 5
    only_current_conversation: bool = True
    scope_mode: str = "all"
    session_list: list[str] = field(default_factory=list)
    min_rounds: int = 3
    compress_provider_id: str = ""
    on_compress_fail: str = "skip"
    max_per_scan: int = 10

    @classmethod
    def from_config(cls, raw: Any) -> IdleSettings:
        raw = raw if isinstance(raw, dict) else {}
        defaults = cls()

        def _int(key: str, minimum: int) -> int:
            try:
                return max(minimum, int(raw.get(key, getattr(defaults, key))))
            except (TypeError, ValueError):
                return getattr(defaults, key)

        session_list = raw.get("session_list", [])
        if isinstance(session_list, str):
            session_list = session_list.replace("，", ",").replace("\n", ",").split(",")
        return cls(
            enable=bool(raw.get("enable", False)),
            action=str(raw.get("action", ACTION_CLEAR)),
            idle_minutes=_int("idle_minutes", 1),
            scan_interval_minutes=_int("scan_interval_minutes", 1),
            only_current_conversation=bool(raw.get("only_current_conversation", True)),
            scope_mode=str(raw.get("scope_mode", "all")),
            session_list=[str(s).strip() for s in session_list if str(s).strip()],
            min_rounds=_int("min_rounds", 1),
            compress_provider_id=str(raw.get("compress_provider_id", "") or ""),
            on_compress_fail=str(raw.get("on_compress_fail", "skip")),
            max_per_scan=_int("max_per_scan", 1),
        )

    def in_scope(self, session_id: str) -> bool:
        """会话是否在整理范围内。

        名单项可写完整会话 ID，也可只写最后一段（群号/QQ 号）。
        """
        if self.scope_mode not in ("whitelist", "blacklist"):
            return True
        matched = any(
            session_id == entry or session_id.endswith(f":{entry}")
            for entry in self.session_list
        )
        return matched if self.scope_mode == "whitelist" else not matched


@dataclass
class ScanResult:
    started_at: float = 0.0
    finished_at: float = 0.0
    idle_found: int = 0
    cleared: int = 0
    compressed: int = 0
    skipped: int = 0
    failed: int = 0
    deferred: int = 0
    error: str = ""

    def summary(self) -> str:
        if self.error:
            return f"巡检出错：{self.error}"
        text = (
            f"发现 {self.idle_found} 个闲置对话，清空 {self.cleared} 个，"
            f"压缩 {self.compressed} 个，跳过 {self.skipped} 个，失败 {self.failed} 个"
        )
        if self.deferred:
            text += f"，{self.deferred} 个超出单轮上限留到下次"
        return text + "。"


class IdleCleaner:
    """后台定时巡检，整理闲置会话的上下文。"""

    def __init__(self, context: Any, raw_config_getter) -> None:
        self.context = context
        self._get_raw_config = raw_config_getter
        self._task: asyncio.Task | None = None
        self._scan_lock = asyncio.Lock()
        self.last_result: ScanResult | None = None

    @property
    def settings(self) -> IdleSettings:
        return IdleSettings.from_config(self._get_raw_config())

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.scan_interval_minutes * 60)
            if not self.settings.enable:
                continue
            try:
                await self.scan()
            except Exception as exc:
                logger.exception("ResetPro 闲置巡检异常：%s", exc)

    async def scan(self, exclude: Any = None) -> ScanResult:
        """执行一轮巡检。同一时刻只允许一轮在跑。

        Args:
            exclude: 手动触发巡检的指令事件，判断会话是否繁忙时不计入。
        """
        async with self._scan_lock:
            settings = self.settings
            result = ScanResult(started_at=time.time())
            try:
                await self._scan(settings, result, exclude)
            except Exception as exc:
                logger.exception("ResetPro 闲置巡检失败：%s", exc)
                result.error = str(exc)
            result.finished_at = time.time()
            self.last_result = result
            if result.idle_found or result.error:
                logger.info("ResetPro 闲置巡检：%s", result.summary())
            return result

    async def _scan(
        self, settings: IdleSettings, result: ScanResult, exclude: Any
    ) -> None:
        conv_mgr = self.context.conversation_manager
        conversations = await self._list_conversations(conv_mgr)
        marks: dict[str, float] = await sp.get_async(
            scope="plugin", scope_id=PLUGIN_NAME, key=MARKS_KEY, default={}
        )
        if not isinstance(marks, dict):
            marks = {}
        # 只保留仍然存在的对话的标记
        marks = {cid: ts for cid, ts in marks.items() if cid in conversations}

        deadline = time.time() - settings.idle_minutes * 60
        candidates = []
        for conv in conversations.values():
            if not conv.updated_at or conv.updated_at > deadline:
                continue
            if conv.updated_at <= marks.get(conv.cid, 0):
                continue  # 上次处理过且之后没有新消息
            if not settings.in_scope(conv.user_id):
                continue
            if settings.only_current_conversation:
                curr_cid = await conv_mgr.get_curr_conversation_id(conv.user_id)
                if curr_cid != conv.cid:
                    continue
            candidates.append(conv)

        candidates.sort(key=lambda c: c.updated_at)
        handled = 0
        for conv in candidates:
            full = await conv_mgr.get_conversation(conv.user_id, conv.cid)
            history = _load_history(full)
            if not history:
                continue  # 已经是空的，不算闲置
            result.idle_found += 1
            if handled >= settings.max_per_scan:
                result.deferred += 1
                continue
            handled += 1
            try:
                new_mark = await self._process(settings, full, history, result, exclude)
            except Exception as exc:
                logger.exception("ResetPro 处理闲置对话 %s 失败：%s", conv.cid, exc)
                result.failed += 1
                continue
            if new_mark is not None:
                marks[conv.cid] = new_mark

        await sp.put_async(
            scope="plugin", scope_id=PLUGIN_NAME, key=MARKS_KEY, value=marks
        )

    async def _list_conversations(self, conv_mgr: Any) -> dict[str, Any]:
        """分页列出全部对话（不加载历史内容），按对话 ID 索引。"""
        conversations: dict[str, Any] = {}
        page = 1
        while True:
            batch, _ = await conv_mgr.get_filtered_conversations(
                page=page, page_size=LIST_PAGE_SIZE, include_history=False
            )
            for conv in batch:
                conversations[conv.cid] = conv
            if len(batch) < LIST_PAGE_SIZE:
                break
            page += 1
        return conversations

    async def _process(
        self,
        settings: IdleSettings,
        conv: Any,
        history: list[dict],
        result: ScanResult,
        exclude: Any,
    ) -> float | None:
        """处理单个闲置对话，返回应记录的标记时间；返回 None 表示下次继续尝试。"""
        session_id, cid = conv.user_id, conv.cid

        if self._runner_type(session_id) != "local":
            # 第三方 Agent 的上下文保存在远端，本地无法整理
            result.skipped += 1
            return conv.updated_at
        if has_active_events(session_id, exclude):
            result.skipped += 1
            return None

        action = settings.action
        new_history: list[dict] = []
        if action == ACTION_COMPRESS:
            try:
                new_history = await compress_history(
                    self.context,
                    session_id,
                    history,
                    plugin_provider_id=settings.compress_provider_id,
                    min_rounds=settings.min_rounds,
                )
            except CompressSkipped as exc:
                logger.debug("ResetPro 跳过压缩 %s：%s", session_id, exc)
                result.skipped += 1
                return conv.updated_at
            except Exception as exc:
                reason = str(exc) if isinstance(exc, CompressFailed) else repr(exc)
                if settings.on_compress_fail != FAIL_CLEAR:
                    logger.warning("ResetPro 压缩 %s 失败：%s", session_id, reason)
                    result.failed += 1
                    return conv.updated_at
                logger.warning(
                    "ResetPro 压缩 %s 失败，改为清空：%s", session_id, reason
                )
                action = ACTION_CLEAR

        # 写回前确认对话在此期间没有新消息，避免覆盖新内容
        latest = await self.context.conversation_manager.get_conversation(
            session_id, cid
        )
        if latest is None or latest.updated_at != conv.updated_at:
            result.skipped += 1
            return None

        if action == ACTION_COMPRESS:
            await self.context.conversation_manager.update_conversation(
                session_id, cid, new_history, token_usage=0
            )
            result.compressed += 1
            logger.info(
                "ResetPro 已压缩闲置对话 %s（%s 条 → %s 条）",
                session_id,
                len(history),
                len(new_history),
            )
        else:
            await self.context.conversation_manager.update_conversation(
                session_id, cid, [], token_usage=0
            )
            result.cleared += 1
            logger.info("ResetPro 已清空闲置对话 %s", session_id)

        updated = await self.context.conversation_manager.get_conversation(
            session_id, cid
        )
        return updated.updated_at if updated else time.time()

    def _runner_type(self, session_id: str) -> str:
        try:
            return str(
                self.context.get_config(umo=session_id)["agent_runner"]["runner_type"]
            )
        except (KeyError, TypeError):
            return "local"


def _load_history(conv: Any) -> list[dict]:
    if conv is None:
        return []
    try:
        history = json.loads(conv.history or "[]")
    except (TypeError, ValueError):
        return []
    return history if isinstance(history, list) else []

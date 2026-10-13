from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.core.agent.context.compressor import LLMSummaryCompressor
from astrbot.core.agent.message import (
    bind_checkpoint_messages,
    dump_messages_with_checkpoints,
)
from astrbot.core.provider.provider import Provider


class CompressSkipped(Exception):
    """对话不满足压缩条件（不视为失败）。"""


class CompressFailed(Exception):
    """压缩过程失败，例如没有可用模型或 LLM 调用失败。"""


def _compression_config(context: Any, session_id: str) -> dict:
    cfg = context.get_config(umo=session_id)
    try:
        return dict(cfg["agent_runner"]["config"]["compression"])
    except (KeyError, TypeError):
        return {}


async def resolve_provider(
    context: Any,
    session_id: str,
    plugin_provider_id: str,
    compression_cfg: dict,
) -> Provider | None:
    """按 插件指定模型 → 会话压缩模型 → 会话聊天模型 的顺序选择压缩模型。"""
    for provider_id in (plugin_provider_id, compression_cfg.get("provider_id", "")):
        if not provider_id:
            continue
        provider = context.get_provider_by_id(provider_id)
        if isinstance(provider, Provider):
            return provider
        logger.warning("ResetPro: 压缩模型 %s 不可用，尝试下一个候选", provider_id)

    try:
        provider = await context.get_using_provider_async(umo=session_id)
    except ValueError:
        return None
    return provider if isinstance(provider, Provider) else None


def count_rounds(history: list[dict]) -> int:
    """以用户消息条数作为对话轮数。"""
    return sum(1 for item in history if item.get("role") == "user")


async def compress_history(
    context: Any,
    session_id: str,
    history: list[dict],
    *,
    plugin_provider_id: str,
    min_rounds: int,
) -> list[dict]:
    """用 AstrBot 内置的 LLM 摘要压缩器压缩一段持久化历史，返回新的历史。

    Raises:
        CompressSkipped: 轮数不足，无需压缩。
        CompressFailed: 无可用模型，或 LLM 未返回有效摘要。
    """
    rounds = count_rounds(history)
    if rounds < max(1, min_rounds):
        raise CompressSkipped(f"只有 {rounds} 轮对话")

    compression_cfg = _compression_config(context, session_id)
    provider = await resolve_provider(
        context, session_id, plugin_provider_id, compression_cfg
    )
    if provider is None:
        raise CompressFailed("没有可用的压缩模型")

    messages = bind_checkpoint_messages(history)
    compressor = LLMSummaryCompressor(
        provider=provider,
        keep_recent_ratio=compression_cfg.get("keep_recent_ratio", 0.15),
        instruction_text=compression_cfg.get("instruction") or None,
    )
    result = await compressor(messages)
    # 内置压缩器在 LLM 失败或摘要为空时会原样返回输入列表
    if result is messages:
        raise CompressFailed("LLM 未返回有效摘要")
    return dump_messages_with_checkpoints(result)

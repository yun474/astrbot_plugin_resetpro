<div align="center">

# 🧹 ResetPro

**一键清空全部上下文，闲置会话自动整理。**

✨ [AstrBot](https://github.com/AstrBotDevs/AstrBot) · 全平台通用 · 一键重置与闲置会话自动清空 / 压缩 ✨

[![License: MIT](https://img.shields.io/badge/License-MIT-a3be8c.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-89b4fa.svg)](https://www.python.org/)
[![AstrBot 4.28.1+](https://img.shields.io/badge/AstrBot-4.28.1%2B-f2cd94.svg)](https://github.com/AstrBotDevs/AstrBot)
[![作者 yun474](https://img.shields.io/badge/作者-yun474-f5b7c7.svg)](https://github.com/yun474)

[功能亮点](#features) · [安装使用](#usage) · [闲置整理](#idle) · [配置说明](#config) · [注意事项](#notes)

</div>

---

<a id="features"></a>

## ✨ 能做什么

- **一键重置**：`/resetpro` 清空所有会话的上下文，保留会话、对话标题和人格设置，只清空历史消息。
- **闲置整理**：会话在机器人最后一次回复后闲置超过设定时长，自动清空上下文，或用 LLM 压缩成摘要。
- **安全可靠**：正在聊天的会话不会被打断，整理过程中有新消息时不会覆盖新内容；同一段闲置期只整理一次。
- **灵活管理**：支持白名单 / 黑名单限定范围，可单独设置 ResetPro 管理员。

<a id="usage"></a>

## 🚀 安装与使用

在 AstrBot 插件管理中使用仓库地址 `https://github.com/yun474/astrbot_plugin_resetpro` 安装。需要 AstrBot 4.28.1 或更新版本。

以下指令仅限 ResetPro 管理员使用：

| 指令 | 用途 |
| --- | --- |
| `/resetpro` | 清空所有会话的上下文，并停止这些会话中正在运行的任务 |
| `/resetidle` | 查看闲置整理的配置和上次巡检结果 |
| `/resetidle run` | 立即巡检一次闲置会话 |

管理员默认为 AstrBot 全局管理员，也可以在插件配置的 `admin_ids` 中单独添加 QQ 号。

<a id="idle"></a>

## 🌙 闲置整理

闲置整理默认关闭，在插件配置的「闲置会话自动整理」中开启 `enable` 后生效。

插件会在后台定时巡检（默认每 5 分钟），找出机器人最后一次回复后闲置超过设定时长（默认 120 分钟）的对话，按设置执行以下动作之一：

| 动作 | 效果 | 适合场景 |
| --- | --- | --- |
| 清空上下文（默认） | 与 `/reset` 效果相同，机器人忘掉之前的对话 | 话题跳跃大的群聊，希望每次都从头开始 |
| LLM 压缩成摘要 | 复用 AstrBot 内置的摘要压缩器，把旧历史写成摘要并保留最近几轮原文 | 希望机器人记得聊过什么，同时减少下次请求的 token |

整理时会自动避开这些情况：

- 会话正在处理消息时跳过，下一轮巡检再处理。
- 整理期间该对话出现新消息时放弃本次整理，不覆盖新内容。
- 同一段闲置期只整理一次；有新消息后重新计时。
- 默认只整理会话当前使用的对话，用户通过 `/new` 留下的旧对话保持不变。

压缩使用的模型按以下顺序选择：插件配置中指定的模型 → 会话配置中的上下文压缩模型 → 会话的对话模型。摘要指令和保留比例沿用会话配置里「上下文压缩」的设置。

<a id="config"></a>

## ⚙️ 配置项说明

| 基础设置 | 默认值 | 说明 |
| --- | --- | --- |
| `admin_ids`（管理员 QQ 号） | 留空 | 允许使用 ResetPro 指令的 QQ 号，也兼容逗号或换行分隔的文本 |
| `use_astrbot_admins`（使用全局管理员） | 开启 | AstrBot 全局管理员也可以使用 ResetPro 指令 |

**闲置会话自动整理：** 以下选项位于 `idle_cleanup` 分组中。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `enable` | 关闭 | 是否启用闲置整理 |
| `action` | 清空上下文 | 闲置后清空上下文，或用 LLM 压缩成摘要 |
| `idle_minutes` | `120` | 机器人最后一次回复后闲置多少分钟触发，最小 1 |
| `scan_interval_minutes` | `5` | 巡检间隔（分钟），最小 1 |
| `only_current_conversation` | 开启 | 只整理会话当前使用的对话 |
| `scope_mode` | 全部会话 | 全部会话 / 仅名单内的会话 / 名单外的会话 |
| `session_list` | 留空 | 会话名单；可填完整会话 ID（如 `aiocqhttp:GroupMessage:123456`），也可只填群号或 QQ 号 |
| `max_per_scan` | `10` | 单轮最多整理的对话数量，超出的留到下一轮 |

**压缩相关：** 仅在 `action` 为「LLM 压缩成摘要」时生效。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `min_rounds` | `3` | 对话轮数少于该值时不压缩 |
| `compress_provider_id` | 留空 | 压缩使用的模型；留空时按上文顺序自动选择 |
| `on_compress_fail` | 跳过 | 压缩失败时跳过（有新消息后再试），或改为清空上下文 |

<a id="notes"></a>

## ⚠️ 注意事项

- 闲置整理只对 AstrBot 内置 Agent 生效。Dify、Coze 等第三方 Agent Runner 的上下文保存在远端，会被跳过；`/resetpro` 仍会清除它们在本地记录的会话标识。
- 压缩模式每整理一个对话会产生一次 LLM 调用，会话较多时建议配合 `max_per_scan` 和名单使用。
- `/resetpro` 会清空**所有**会话（包括 `/new` 留下的旧对话），执行前请确认。

---

<div align="center">

喜欢的话，给云云点一颗 ⭐ 吧！

[更新日志](CHANGELOG.md) · [反馈问题](https://github.com/yun474/astrbot_plugin_resetpro/issues) · [MIT License](LICENSE)

**插件问题反馈 QQ 群：947667614**

</div>

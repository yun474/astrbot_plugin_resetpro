# AstrBot ResetPro

ResetPro 是一个 AstrBot 管理插件，提供 `/resetpro` 指令，用于一键清空所有已保存会话的上下文。

## 功能

- `/resetpro`：清空数据库中所有 conversation 的上下文内容。
- 保留会话、对话标题和人格配置，只清空历史消息内容。
- 执行前会停止相关会话里正在运行的任务，避免旧任务继续写入上下文。
- 支持独立配置 ResetPro 管理员 QQ 号。
- 可选择是否把 AstrBot 全局管理员也视作 ResetPro 管理员。

## 配置

在 AstrBot WebUI 的插件配置里填写：

- `admin_ids`：允许使用 `/resetpro` 的 QQ 号列表，只填写 QQ 号。
- `use_astrbot_admins`：是否允许 AstrBot 全局管理员使用该指令，默认开启。

## 使用

在任意已接入的会话里发送：

```text
/resetpro
```

执行成功后，插件会返回清理的对话数量和覆盖的会话数量。

## 安装

将本仓库克隆到 AstrBot 的插件目录：

```bash
cd AstrBot/data/plugins
git clone https://github.com/yun474/astrbot_plugin_resetpro
```

然后在 AstrBot WebUI 中重载或启用插件。

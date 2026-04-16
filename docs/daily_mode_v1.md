# 云汐日常模式 v1 封板说明

最后更新：2026-04-16

## 状态

日常模式 v1 已进入完成候选状态。当前目标不是立刻转入工厂模式，而是在这个稳定基线上继续打磨长期陪伴体验。

## v1 已完成能力

- 飞书作为唯一正式日常聊天入口。
- 云汐主动消息通过飞书触达。
- 工具请求通过 pending confirmation 协议等待确认后执行。
- WebUI/Tray 定位为状态、日志、healthcheck 和控制入口，不承载正式聊天。
- Desktop MCP、Filesystem/Document MCP、Browser MCP、GUI Agent MCP 默认接入日常模式。
- 情感、记忆、主动性、工具调用和 daemon 生命周期均有自动化或 live 验证记录。

## 默认工具清单

- Desktop：`screenshot_capture`、`clipboard_read`、`clipboard_write`、`desktop_notify`、`app_launch_ui`、`window_focus_ui`、`window_minimize_ui`
- Filesystem/Document：`list_dir`、`file_read`、`file_write`、`file_append`、`file_copy`、`file_move`、`glob`、`grep`、`document_read`
- Browser：`browser_open`、`browser_search`、`web_page_read`、`browser_extract_links`、`browser_click`、`browser_type`
- GUI Agent：`gui_observe`、`gui_click`、`gui_type`、`gui_hotkey`、`gui_run_task`、`gui_save_macro`、`gui_list_macros`、`gui_run_macro`

## 一键命令

启动日常模式：

```bat
start_daily_mode.bat
```

执行深度健康检查：

```bat
healthcheck_daily_mode.bat
```

常用环境变量：

- `YUNXI_PROVIDER`：默认 `moonshot`
- `YUNXI_EMBEDDING_PROVIDER`：默认 `lexical`
- `YUNXI_TICK_INTERVAL`：默认 `300`
- `YUNXI_RUN_SECONDS`：默认不设置，常驻运行；设置后有界退出
- `YUNXI_SKIP_DESKTOP_MCP`：设置为 `1` 时跳过 Desktop MCP
- `YUNXI_SKIP_LLM_PING`：设置为 `0` 时 healthcheck 会真实 ping LLM

## v1 验收记录

- 飞书 live 主动发送：passed
- 飞书真实入站消息和工具确认闭环：passed
- 全量默认 MCP 工具直接矩阵：8 passed
- 飞书启用状态 deep healthcheck：passed
- 30 分钟 daemon 浸泡测试：passed
- 浸泡后资源关闭和进程残留检查：passed

## v1 已知限制

- 飞书机器人 API 不能伪造“用户入站消息”；真实入站聊天仍需要用户在飞书中发送。
- Browser MCP 当前是轻量 HTML/URL 工具，不是完整 Playwright 自动化。
- GUI Agent MCP 当前是低风险首版，复杂视觉规划和失败回退还需要继续增强。
- 记忆系统已可用，但长期关系摘要、情绪轨迹摘要、上下文压缩仍需要下一阶段打磨。
- HeartLake 情绪系统仍有规则/阈值成分，深层语义情绪评估还不成熟。
- 自主学习框架已打通，但多日真实使用中的技能沉淀和复用还需要长期验证。

## 后续重点

下一阶段继续打磨日常模式，不进入工厂模式。优先方向：

1. 长期记忆摘要和上下文压缩。
2. 情绪语义评估和情绪惯性/恢复机制。
3. 主动性策略自然度。
4. 浏览器和 GUI Agent 的更强真实任务能力。
5. 多日常驻稳定性和日志可观测性。

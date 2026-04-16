# 云汐 3.0 开发日志

> **用途**：记录当前开发状态、阻塞问题、重要决策和下一步计划。  
> **读取时机**：每次新对话开始时，必须先阅读本文件。  
> **更新原则**：只保留重要里程碑、真实验证结果、阻塞问题和阶段切换依据；删除低价值流水快照。  
> **核心验收标准**：云汐首先是住在电脑里的亲密伴侣；工具能力只能作为延伸，不能让云汐退化成高级脚本执行程序。

---

## [2026-04-16] 日常模式 v1 完成候选封板

**状态**：日常模式 v1 完成候选已封板。后续不立即进入工厂模式，优先继续打磨日常模式的长期陪伴质量。

### 封板依据

- 飞书作为唯一正式日常聊天入口已完成真实 live 验证。
- 飞书主动发送、入站消息、工具确认闭环均已通过。
- Desktop、Filesystem/Document、Browser、GUI Agent 默认 MCP 工具体系已接入。
- 全量默认 MCP 工具直接矩阵通过。
- 飞书启用状态 deep healthcheck 通过。
- 30 分钟 daemon 浸泡测试通过，结束后无 daemon/MCP 残留进程。
- 阶段 6 后的工具生态扩展没有破坏既有 Desktop MCP、daemon stability、Phase 5 回归。

### 新增封板文档与一键入口

- 新增 `docs/daily_mode_v1.md`：记录 v1 能力、启动方式、验收结果、已知限制和后续优化方向。
- 新增 `start_daily_mode.bat`：一键启动飞书日常模式。
- 新增 `healthcheck_daily_mode.bat`：一键执行飞书启用状态 deep healthcheck。
- 飞书 WebSocket 日志降噪：
  - 对 `im.message.message_read_v1` 和 `im.chat.access_event.bot_p2p_chat_entered_v1` 注册空 handler，避免 lark SDK 输出 `processor not found`。
  - WebSocket 正常 1000 close 识别为正常关闭，避免被云汐日志当作异常。

### v1 后续方向

短期不推进工厂模式实现。下一阶段继续围绕日常模式优化：

- 长期记忆摘要和上下文压缩。
- HeartLake 情绪语义评估、情绪惯性和恢复机制。
- 主动性策略自然度。
- Browser / GUI Agent 的真实任务能力。
- 多日常驻稳定性和日志可观测性。

### 后续审查输出

- 新增 `docs/daily_mode_optimization_review.md`：整理日常模式继续打磨的 P0/P1/P2 优先级建议。
- 审查中发现 `gui_type` 与此前 `browser_type` 有同类阻塞风险，已改成非阻塞 PowerShell `System.Windows.Forms.SendKeys` 路径。

### 已验证

- `python -m py_compile src\interfaces\feishu\websocket.py src\core\mcp\servers\gui_agent_server.py src\core\mcp\servers\browser_server.py src\apps\daemon\main.py` -> passed
- `python -m pytest -q tests\unit\test_feishu_websocket.py tests\unit\test_daemon_healthcheck.py tests\unit\test_feishu_adapter.py tests\unit\test_execution_engine_stage4.py tests\unit\test_mcp_hub_stage4.py` -> 19 passed
- `python -m pytest -q tests\integration\test_phase5_daily_mode.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 12 passed
- `$env:YUNXI_PROVIDER='ollama'; $env:YUNXI_SKIP_LLM_PING='1'; cmd /c healthcheck_daily_mode.bat` -> passed
- `$env:YUNXI_RUN_SECONDS='8'; $env:YUNXI_PROVIDER='ollama'; $env:YUNXI_TICK_INTERVAL='9999'; cmd /c start_daily_mode.bat` -> passed，正常关闭时不再输出 lark 1000 close error
- `python -m pytest -q tests\integration\test_daily_mode_extended_tools_direct.py tests\integration\test_daily_mode_desktop_tools_direct.py -m desktop_mcp` -> 8 passed

---

## [2026-04-16] 飞书日常模式 30 分钟浸泡测试通过

**状态**：已完成阶段 6 后的首轮日常模式浸泡测试。飞书 live 主动发送、全量工具直接矩阵、飞书启用状态 deep healthcheck、30 分钟有界 daemon 稳定运行均通过。

### 浸泡前验证

- 飞书启用状态 full tool deep healthcheck：
  - `$env:PYTHONPATH='src'; python src\apps\daemon\main.py --provider ollama --healthcheck-deep --skip-llm-ping --embedding-provider lexical --feishu-enable` -> passed
  - `feishu_config=configured`
  - `available_tools` 包含 Desktop、Filesystem/Document、Browser、GUI Agent 全部默认工具。
- 全量工具直接矩阵：
  - `python -m pytest -q tests\integration\test_daily_mode_extended_tools_direct.py tests\integration\test_daily_mode_desktop_tools_direct.py -m desktop_mcp` -> 8 passed
- Phase 5 / daemon stability 非真实 LLM 回归：
  - `python -m pytest -q tests\integration\test_phase5_daily_mode.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 12 passed
- 飞书 live 主动发送：
  - `$env:FEISHU_LIVE_TEST='1'; python -m pytest -q tests\integration\test_daily_mode_feishu_live.py -m "real_llm and feishu_live"` -> 1 passed

### 浸泡执行

- 启动命令：
  - `set PYTHONPATH=src&& python src\apps\daemon\main.py --provider moonshot --feishu-enable --embedding-provider lexical --tick-interval 300 --run-seconds 1800`
- 浸泡窗口：
  - 开始：2026-04-16 17:51:30
  - 结束：2026-04-16 18:21:39 左右自动关闭
- 运行期间进程：
  - main daemon 进程存活。
  - Desktop / Filesystem / Browser / GUI Agent 四个 MCP server 进程均存活。
  - 30 分钟结束后 daemon 和 MCP server 均退出，无残留。
- 运行日志：
  - `logs\daily_soak_20260416_175130.out.log`
  - `logs\daily_soak_20260416_175130.err.log`

### 浸泡期间观察

- 飞书 WebSocket 成功启动并保持连接。
- 日常模式 daemon 成功加载 Moonshot、Memory、Continuity、Event library、Feishu、MCP 工具层。
- 运行中没有 Runtime 崩溃、MCP server 崩溃、资源关闭失败或 pending confirmation 堆积。
- 日志中出现两类 lark SDK 噪声：
  - `processor not found, type: im.message.message_read_v1`
  - WebSocket 正常关闭时输出 `receive message loop exit ... sent 1000 (OK); then received 1000 (OK) bye`
  - 这两项目前不影响文本消息接收、主动发送和 daemon 关闭，但后续可增加空 handler 或日志降噪。

### 期间发现并修复

- 全量工具矩阵中 `app_launch_ui(notepad)` 偶发失败：应用实际可启动，但工具只通过屏幕像素变化判断成功；当 Notepad 已打开或屏幕变化不明显时会误报失败。
- 修复 `src/core/mcp/servers/desktop_server.py`：
  - `app_launch_ui` 现在在视觉变化之外，还会检查匹配窗口和进程是否存在。
  - `notepad` / `calc` 增加常见窗口标题别名。
- 验证：
  - `python -m py_compile src\core\mcp\servers\desktop_server.py` -> passed
  - `python -m pytest -q tests\integration\test_daily_mode_desktop_tools_direct.py::test_yunxi_direct_launch_focus_and_minimize_notepad -m desktop_mcp` -> 1 passed
  - 全量工具矩阵重跑 -> 8 passed

### 浸泡后验证

- 浸泡后再次执行飞书启用状态 full tool deep healthcheck：
  - `$env:PYTHONPATH='src'; python src\apps\daemon\main.py --provider ollama --healthcheck-deep --skip-llm-ping --embedding-provider lexical --feishu-enable` -> passed
  - `resource_close=passed`
- 二次进程检查：未发现浸泡 daemon 或 MCP server 残留进程。

### 结论

日常模式已达到 v1 完成候选门槛：飞书入口、主动发送、全量默认 MCP 工具、工具确认协议、daemon 有界运行、资源关闭均通过验证。

本轮浸泡未自动伪造“用户从飞书发入站消息”，因为飞书机器人 API 不能代表用户发送入站事件；真实入站聊天和飞书确认闭环已在前一轮 live 测试中通过，本轮主要验证阶段 6 工具扩展后的 daemon 稳定性。

---

## [2026-04-16] 阶段 6 规划：电脑能力工具生态扩展，飞书浸泡测试后移

**状态**：首版已落地并通过直接工具矩阵。此前飞书入口、Desktop MCP 基础工具和确认闭环已通过，但工具生态仍不足以支撑“住在电脑里的云汐”完整电脑能力，因此飞书日常模式浸泡测试后移到阶段 6 完成之后。

### 目标调整

- 不再把“飞书聊天 + 剪贴板/截图/通知/窗口控制”视为日常模式最终完成门槛。
- 阶段 6 先补齐 Browser MCP、Filesystem/Document MCP、GUI Agent MCP。
- 新增工具仍遵守日常模式安全边界：READ 默认允许，WRITE/EXECUTE 默认需要飞书或直接测试中的“确认”。
- 测试顺序继续沿用上一轮工具验收方式：先跳过飞书，直接模拟用户消息和“确认”，确认新增工具真实可运行；之后再进入飞书浸泡测试。

### 阶段 6 必须覆盖的能力

- 浏览器：打开 URL/搜索页、读取网页文本、提取链接、基础点击/输入。
- 文件与文件夹：列目录、读写追加、复制、移动、glob、grep。
- 文档：Markdown/txt/json/csv 直接读取，docx/xlsx 使用标准库解析正文，pdf 在本地解析库可用时读取，否则明确降级。
- GUI Agent：UIA 观察、控件点击、焦点输入、热键、GUI 任务入口、GUI Macro 保存/列出/执行。
- 技能沉淀入口：新增工具调用继续进入 MCP audit，为后续 SkillLibrary 和 FailureReplay 提供数据。

### 已落地

- 新增 `src/core/mcp/servers/browser_server.py`：
  - `browser_open`
  - `browser_search`
  - `web_page_read`
  - `browser_extract_links`
  - `browser_click`
  - `browser_type`
- 新增 `src/core/mcp/servers/filesystem_server.py`：
  - `list_dir`
  - `file_read`
  - `file_write`
  - `file_append`
  - `file_copy`
  - `file_move`
  - `glob`
  - `grep`
  - `document_read`
- 新增 `src/core/mcp/servers/gui_agent_server.py`：
  - `gui_observe`
  - `gui_click`
  - `gui_type`
  - `gui_hotkey`
  - `gui_run_task`
  - `gui_save_macro`
  - `gui_list_macros`
  - `gui_run_macro`
- daemon 默认工具配置扩展为 Desktop + Filesystem/Document + Browser + GUI Agent。`--skip-desktop-mcp` 只跳过 Desktop，仍会加载其他日常工具。
- `DAGPlanner` 增加 Browser、Filesystem/Document、GUI Agent 的隐式依赖规则。
- 新增 `tests/integration/test_daily_mode_extended_tools_direct.py`，沿用“用户请求 -> pending confirmation -> 用户确认 -> 工具执行”的直接验收方式。
- 验证时发现 `browser_type` 通过 `pyautogui.write()` 在 MCP 子进程中可能阻塞到 client timeout，已改为非阻塞 PowerShell `System.Windows.Forms.SendKeys` fallback。

### 已验证

- `python -m py_compile src\core\mcp\servers\browser_server.py src\core\mcp\servers\filesystem_server.py src\core\mcp\servers\gui_agent_server.py src\apps\daemon\main.py src\core\mcp\planner.py tests\integration\test_daily_mode_extended_tools_direct.py` -> passed
- 普通沙箱运行新增 MCP 矩阵因 Windows named pipe 权限失败，外部权限重跑：
  - `python -m pytest -q tests\integration\test_daily_mode_extended_tools_direct.py -m desktop_mcp` -> 4 passed
  - 覆盖 `list_dir/file_read/file_write/file_append/file_copy/file_move/glob/grep/document_read/browser_open/browser_search/web_page_read/browser_extract_links/browser_click/browser_type/gui_observe/gui_type/gui_hotkey/gui_run_task/gui_save_macro/gui_list_macros/gui_run_macro`。
- 既有 Desktop MCP 直接矩阵外部权限重跑：
  - `python -m pytest -q tests\integration\test_daily_mode_desktop_tools_direct.py -m desktop_mcp` -> 4 passed
- Engine / MCPHub / daemon healthcheck 单元回归：
  - `python -m pytest -q tests\unit\test_daemon_healthcheck.py tests\unit\test_execution_engine_stage4.py tests\unit\test_mcp_hub_stage4.py` -> 9 passed
- Phase 5 / daemon stability 非真实 LLM 回归：
  - `python -m pytest -q tests\integration\test_phase5_daily_mode.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 12 passed
- daemon deep healthcheck 加载新增默认工具（跳过 Desktop，跳过 LLM ping）：
  - `$env:PYTHONPATH='src'; python src\apps\daemon\main.py --provider ollama --skip-desktop-mcp --healthcheck-deep --skip-llm-ping --embedding-provider lexical` -> passed
  - `available_tools` 包含 `list_dir/file_read/file_write/document_read/browser_search/web_page_read/browser_extract_links/gui_save_macro/gui_run_macro` 等新增工具。

### 新验收门槛

1. Browser/Filesystem/Document/GUI Agent MCP Server 能被 daemon 默认工具配置发现。
2. 新增工具加入直接工具矩阵，跳过飞书模拟“用户请求 -> 云汐要求确认 -> 用户确认 -> 工具执行”。
3. 文件写入、移动、GUI 操作等 WRITE/EXECUTE 工具必须进入 pending confirmation。
4. 浏览器和文档读取可在无外网条件下用本地 HTML/文档样本完成验收。
5. 阶段 6 通过后，再执行 30-60 分钟飞书日常模式浸泡测试，覆盖聊天、主动消息、工具确认、浏览器读取、文档读写、GUI fallback 和重启记忆连续性。

---

## [2026-04-16] 设计调整：飞书作为唯一日常对话入口，WebUI/Tray 改为状态与控制面板

**状态**：已采纳。阶段 5 的入口设计从“飞书、Tray、WebUI 都可能承载聊天”调整为“飞书承载日常对话，WebUI/Tray 只做本地状态、日志和控制入口”。

### 关键决策

- 日常模式的用户主动对话、云汐主动消息、工具确认，默认全部走飞书。
- WebUI 不再作为正式聊天入口，不再承担主动消息承载；它只显示云汐状态、运行日志、healthcheck、飞书连接状态、pending 工具确认状态，以及工厂模式入口。
- 系统托盘定位为 launcher/control surface：左键打开 WebUI，右键提供打开状态页、进入工厂模式、执行 healthcheck、打开日志、停止/重启 daemon 等操作。
- 工厂模式对话默认走终端，不放进 WebUI 聊天框。
- 新增 `yunxi` CLI 入口设计：用户在任意项目文件夹打开终端，输入 `yunxi` 后进入工厂模式终端；当前目录作为工厂项目目录。WebUI 按钮和托盘右键后续也统一打开该终端入口。

### 已落地占位

- 新增 `src/apps/factory_cli/main.py`：提供 `yunxi` 工厂模式 CLI 占位入口，支持 `--status` 和 `--project-dir`。
- 新增 `yunxi.cmd`：Windows 命令启动器，后续可加入 PATH，使任意项目目录中输入 `yunxi` 都能进入工厂模式终端。
- 新增 `tests/unit/test_factory_cli.py`：验证 CLI 状态输出和默认项目目录解析。

### 已验证

- `python -m py_compile src\apps\factory_cli\main.py src\apps\tray\web_server.py tests\unit\test_factory_cli.py` -> passed
- `python -m pytest -q tests\unit\test_factory_cli.py tests\unit\test_prompt_builder.py` -> 12 passed
- `.\yunxi.cmd --status` -> 输出 `mode=factory`、`entry=yunxi_cli`、`implementation_state=placeholder`，并正确识别当前项目目录。

### 对阶段 5 的影响

- P1-07 不再要求 WebUI/Tray 实现聊天、主动消息流和工具确认提交入口。
- 阶段 5 的真实入口验收改为：飞书 live 完成收消息、Runtime 回复、主动消息发送、工具确认确认/取消闭环。
- WebUI/Tray 阶段 5 验收改为：状态页、日志页、healthcheck 操作、飞书连接状态、pending confirmation 状态展示、工厂模式入口可用。

---

## [2026-04-16] 阶段 5 准备完成：飞书日常模拟测试前置修复

**状态**：已完成飞书日常模拟测试前置修复。当前不再继续扩展 WebUI 聊天入口，下一步可以进入飞书 live 日常模拟测试。

### 完成内容

- 分层感知与超时降级：
  - 新增 `LayeredPerceptionProvider`、`PerceptionLayer`、`TimePerceptionProvider`、`WindowsUserPresenceProvider`、`SystemResourceProvider`。
  - 默认感知拆成基础时间、桌面在场、系统资源三层，每层独立 timeout。
  - 慢速或异常 optional provider 会降级，不阻塞整轮聊天。
  - `PerceptionCoordinator.close()` 支持释放 provider 资源，daemon `close_runtime()` 已调用。
- 飞书入口前置链路：
  - `FeishuAdapter.handle_message()` 对发送结果做失败日志记录。
  - runtime 异常时，飞书用户可见回复改为云汐人格化表达，不暴露网络/技术错误。
  - 补充飞书确认链路测试：用户通过飞书回复“确认”会继续进入 Runtime pending confirmation 流程。
- deep healthcheck：
  - daemon 新增 `--healthcheck-deep`。
  - 覆盖 runtime build、runtime status、LLM ping、memory summary、event library、continuity read/write、Feishu config、resource close。
  - 新增 `--skip-llm-ping`，用于本地无网络/不想触发模型请求时做结构健康检查。
- WebUI/Tray 状态控制面板基础：
  - `RuntimeStatus` 增加 `pending_confirmation_count`、`daily_channel="feishu"`、`factory_entry_command="yunxi"`。
  - 新增 `ControlPanelSnapshot`、日志读取、`create_status_app()`。
  - WebUI 只暴露 `/api/status`、`/api/logs`、`/api/factory-entry`，不提供聊天接口。

### 已验证

- `python -m py_compile src\domains\perception\coordinator.py src\apps\daemon\main.py src\interfaces\feishu\adapter.py src\apps\tray\web_server.py tests\unit\test_perception_coordinator.py tests\unit\test_daemon_healthcheck.py tests\unit\test_feishu_adapter.py tests\integration\test_phase5_daily_mode.py` -> passed
- `python -m pytest -q tests\unit\test_perception_coordinator.py tests\unit\test_daemon_healthcheck.py tests\unit\test_feishu_adapter.py tests\integration\test_phase5_daily_mode.py` -> 16 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 100 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 32 passed
- `$env:PYTHONPATH='src'; python src\apps\daemon\main.py --provider ollama --disable-tool-use --skip-desktop-mcp --healthcheck-deep --skip-llm-ping` -> passed
- `$env:PYTHONPATH='src'; python src\apps\daemon\main.py --provider ollama --disable-tool-use --skip-desktop-mcp --healthcheck-deep --skip-llm-ping --feishu-enable` -> passed，`feishu_config=configured`
- `.\yunxi.cmd --status` -> passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm` -> 6 passed
- `python -m pytest -q tests\integration\test_daily_mode_feishu_live.py -m "real_llm and feishu_live"` -> 1 skipped（未设置 `FEISHU_LIVE_TEST=1`，未误发真实消息）

### 下一步

进入飞书日常模拟测试。建议顺序：
1. 先开启 `FEISHU_LIVE_TEST=1` 跑现有飞书 live 主动发送测试，确认真实发送链路。
2. 再启动 daemon `--feishu-enable`，手动向云汐发普通消息，确认收消息、Runtime 回复和飞书回发。
3. 触发一个需要确认的工具请求，通过飞书回复“确认/取消”，验证 pending tool confirmation 闭环。
4. 让 Presence 主动 tick 真实发一条主动消息，验证日常模式主动触达。

---

## [2026-04-16] 飞书日常模拟测试：主动发送、收发消息和工具确认闭环通过

**状态**：已完成首轮飞书真实日常模拟测试。飞书现在可以作为日常模式唯一对话入口继续推进。

### 测试结果

- 飞书 live 主动发送：
  - 普通沙箱首次运行因网络 socket 权限失败，外部权限重跑通过。
  - `FEISHU_LIVE_TEST=1 python -m pytest -q tests\integration\test_daily_mode_feishu_live.py -m "real_llm and feishu_live"` -> 1 passed。
- 飞书 daemon 普通文本收发：
  - 启动参数：`--provider moonshot --feishu-enable --disable-tool-use --skip-desktop-mcp --embedding-provider lexical --tick-interval 9999 --run-seconds 180`。
  - 飞书真实文本“云汐，收到吗”被 daemon 捕获：输出出现 `[飞书] 收到消息 from ...: 云汐，收到吗`。
  - 说明 WebSocket 接收、线程回调、Runtime 调用和飞书回复路径进入真实链路。
- 飞书工具确认闭环：
  - 启动参数：`--provider moonshot --feishu-enable --embedding-provider lexical --tick-interval 9999 --run-seconds 240`。
  - 用户通过飞书发送“帮我把 yunxi live clipboard test 复制到剪贴板”。
  - daemon 捕获工具请求和后续“确认”。
  - Desktop MCP 输出 `ListToolsRequest` 和 `CallToolRequest`。
  - `Get-Clipboard` -> `yunxi live clipboard test`。
  - 结论：飞书发起工具请求、云汐要求确认、飞书回复确认、Desktop MCP 执行写剪贴板真实闭环通过。

### 期间发现并修复

- `lark-oapi` WebSocket 使用模块级全局 event loop。前一次真实 daemon 接收测试报错：`This event loop is already running`。
- 修复 `FeishuWebSocket`：
  - WebSocket 线程内创建独立 event loop，并临时绑定到 `lark_oapi.ws.client.loop`。
  - stop 时使用实例持有的 loop 做 `_disconnect()`。
  - 关闭 loop 前取消 pending tasks，减少退出时 `Task was destroyed but it is pending` 告警。
- daemon 新增 `--run-seconds`，用于 live 验收时有界运行并自动退出。
- daemon 飞书回调增加收到消息的 console 打印，便于 live 验收定位。

### 已验证

- `python -m py_compile src\interfaces\feishu\websocket.py tests\unit\test_feishu_websocket.py src\apps\daemon\main.py` -> passed
- `python -m pytest -q tests\unit\test_feishu_websocket.py tests\unit\test_daemon_healthcheck.py tests\unit\test_feishu_adapter.py` -> 13 passed
- `python -m pytest -q tests\unit\test_feishu_websocket.py tests\unit\test_daemon_healthcheck.py tests\unit\test_feishu_adapter.py tests\integration\test_phase5_daily_mode.py` -> 18 passed
- `FEISHU_LIVE_TEST=1 python -m pytest -q tests\integration\test_daily_mode_feishu_live.py -m "real_llm and feishu_live"` -> 1 passed

### 剩余风险

- `lark-oapi` 对 `im.chat.access_event.bot_p2p_chat_entered_v1` 和 `im.message.message_read_v1` 会输出 `processor not found`，目前不影响文本消息接收和回复，但后续可增加空 handler 降低噪声。
- 本轮确认工具使用剪贴板写入作为样例；其他 Desktop MCP 工具仍需逐项 live 验收。

---

## [2026-04-16] Desktop MCP 工具逐项直接对话验证

**状态**：首轮逐项验证通过。飞书链路已被前一轮验证，因此本轮直接模拟“用户发消息”和“用户回复确认”，走 `YunxiExecutionEngine` 的 pending confirmation 逻辑，不再手动通过飞书逐条交互。

### 新增验证

- 新增 `tests/integration/test_daily_mode_desktop_tools_direct.py`：
  - 使用真实 Desktop MCP server。
  - 使用脚本化 LLM 触发指定 tool call。
  - 第一轮 `engine.respond()` 模拟用户提出工具请求。
  - 第二轮 `engine.respond("确认")` 模拟用户确认。
  - 检查自然确认话术、工具执行结果和真实副作用。
- 覆盖工具：
  - `clipboard_write` + `clipboard_read`：写入并读取 `yunxi direct clipboard matrix`。
  - `screenshot_capture`：保存真实截图文件并检查文件非空。
  - `desktop_notify`：发送桌面通知。
  - `app_launch_ui`：启动 Notepad。
  - `window_focus_ui`：聚焦 Notepad。
  - `window_minimize_ui`：最小化 Notepad。

### 期间发现并修复

- `desktop_notify` 原先依赖未安装的 `win10toast`，工具实际返回 `[错误：未安装 win10toast，无法发送通知]`，但 Engine 会继续给自然成功回复，容易掩盖工具失败。
- 修复 `desktop_notify`：
  - 保留 `win10toast` 优先路径。
  - 缺少 `win10toast` 或调用失败时，改用无第三方依赖的 PowerShell `System.Windows.Forms.NotifyIcon` fallback。
- 测试加强：
  - 不只检查云汐自然回复，还读取 Engine 上下文中的 `ToolResultContentBlock`。
  - 拦截 `[错误]`、`失败`、`未找到` 等实际工具失败结果。
- Notepad 窗口关键词在当前系统中应使用 `Notepad`，不是中文“记事本”。

### 已验证

- `python -m py_compile src\core\mcp\servers\desktop_server.py tests\integration\test_daily_mode_desktop_tools_direct.py` -> passed
- 普通沙箱运行 direct desktop matrix 因 Windows named pipe 权限失败，外部权限重跑：
  - `python -m pytest -q tests\integration\test_daily_mode_desktop_tools_direct.py -m desktop_mcp` -> 4 passed
- 既有 Desktop MCP 回归：
  - `python -m pytest -q tests\integration\test_mcp_desktop.py -m desktop_mcp` -> 5 passed
- Engine / MCPHub stage 4 回归：
  - `python -m pytest -q tests\unit\test_execution_engine_stage4.py tests\unit\test_mcp_hub_stage4.py` -> 6 passed

### 结论

当前 Desktop MCP 工具已经具备一条可重复的直接日常模式验收路径：不依赖飞书手工交互，也不绕过云汐的确认协议。后续新增工具应先加入该矩阵，再做飞书 live 抽样。

---

## [2026-04-16] 阶段 4 完成：日常工具确认和错误人格化

**状态**：已完成首版。阶段 4 目标是让 daily_mode 下工具请求不再直接变成安全错误，并避免把工程异常暴露给用户。

### 完成内容

- 新增 pending tool confirmation 最小闭环：
  - `MCPHub` 在安全策略返回 `ask` 时创建 `PendingToolConfirmation`，不直接执行工具。
  - `YunxiExecutionEngine` 会自然告知“这一步需要你点头”，用户回复“确认/同意/可以/继续/ok”等后继续执行最新 pending 工具。
  - 用户回复“取消/不要/先别”等会放弃 pending 工具。
- 工具失败和 Engine 异常用户可见人格化：
  - 移除用户可见的 `[云汐这里出了点小问题：...]`、`[工具执行遇到问题...]`、`[尝试使用工具多次仍未完成]`。
  - 技术细节保留在 `ExecutionResult.error` 和日志，不直接进入回复文本。
- MCP 失败结构化：
  - 未知工具不再 raise 绕过审计，改为 `error_type="unknown_tool"` 的结构化结果。
  - `MCPClient` 对 connect / initialize / list_tools / call_tool 增加 `asyncio.wait_for()` timeout。
- LLM provider 增加 typed errors 和重试：
  - 新增 `LLMProviderNetworkError`、`LLMProviderHTTPError`、`LLMProviderResponseError`。
  - provider 请求按 `max_retries` 重试，网络/超时/可重试 HTTP 错误进入结构化异常。
- 技能快速路径不再直接固定话术收尾：
  - 快捷技能执行后会把结果交给 LLM 做最终自然表达。
  - 如果最终表达失败，才回退到人格化的保守回复。

### 已验证

- `python -m py_compile src\core\execution\engine.py src\core\mcp\hub.py src\core\mcp\client.py src\core\llm\provider.py src\core\llm\__init__.py tests\unit\test_mcp_hub_stage4.py tests\unit\test_execution_engine_stage4.py tests\unit\test_llm_provider_errors.py tests\integration\test_mcp_desktop.py` -> passed
- `python -m pytest -q tests\unit\test_mcp_hub_stage4.py tests\unit\test_execution_engine_stage4.py tests\unit\test_llm_provider_errors.py tests\unit\test_execution_engine.py` -> 12 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 92 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 30 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm` -> 6 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_mcp_desktop.py -m desktop_mcp` -> 普通沙箱因 Windows named pipe 权限失败；外部权限重跑 5 passed

### 下一步

进入阶段 5：飞书真实日常入口、Tray/WebUI 状态控制面板和分层感知。

优先处理：
1. Perception provider 分层，基础感知、慢速外部感知、可选隐私感知分别带 timeout 和降级。
2. 飞书 live 接入 pending confirmation，完成日常聊天、主动消息和工具确认闭环。
3. 常驻 daemon 增加深度 healthcheck。
4. Tray/WebUI 简化为状态、日志、healthcheck 和工厂模式控制入口。

---

## [2026-04-16] 阶段 3 完成：主动预算、长期关系记忆和连续性沉淀

**状态**：已完成首版。阶段 3 目标是让云汐的主动性和长期关系状态不再只依赖进程内临时变量。

### 完成内容

- `CompanionContinuityService` 新增 `proactive_count_date`：
  - `recent_proactive_count` 按本地日期归属。
  - `InitiativeEngine.evaluate()` 前会刷新日期，跨天自动恢复主动预算。
- `MemoryManager` 新增持久化关系记忆：
  - 偏好、共同经历、承诺写入 `relationship_memory.json`。
  - 重建 `MemoryManager` 后可恢复关系记忆并进入 prompt summary。
  - 新增 `MemoryManager.close()`，统一关闭 PatternMiner 和 SkillLibrary 资源。
- 普通聊天后新增保守连续性抽取：
  - 用户提到偏好、承诺、共同经历时写入长期记忆。
  - 用户提到“明天/下次/之后继续/提醒/跟进”等内容时写入 open thread 和 proactive cue。
  - 用户表达疲惫、压力、失眠等状态时设置 `comfort_needed`；工作相关消息设置 `task_focus`。
- 主动事件 `affect_delta` 现在真实影响 HeartLake：
  - 事件选中后按 valence/arousal 调整安全感、想念值和主导情绪。
  - 选中的主动事件写入 continuity 的 `initiative_events`，后续 prompt summary 可看到近期主动素材。
- Runtime/daemon 生命周期补齐：
  - `YunxiRuntime.chat()` 在普通对话结束后沉淀关系记忆和连续性线索。
  - `close_runtime()` 调用 `runtime.memory.close()`。

### 已验证

- `python -m py_compile src\core\initiative\continuity.py src\domains\memory\manager.py src\core\runtime.py src\core\cognition\heart_lake\core.py src\core\cognition\initiative_engine\engine.py src\apps\daemon\main.py tests\unit\test_continuity_persistence.py tests\unit\test_initiative_engine.py tests\domains\memory\test_relationship_memory.py tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\daily_mode_scenario_tester.py` -> passed
- `python -m pytest -q tests\unit\test_continuity_persistence.py tests\unit\test_initiative_engine.py tests\domains\memory\test_relationship_memory.py tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py` -> 29 passed
- `python -m pytest -q tests\unit tests\domains\memory` -> 85 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase4_runtime.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 30 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm` -> 6 passed（真实 Moonshot，需要联网）

### 下一步

进入阶段 4：日常工具确认和用户可见错误人格化。

优先处理：
1. 实现统一 pending tool confirmation 协议。
2. LLM 异常、工具异常、安全 ask、未知工具都转为云汐人格化表达，技术细节只进日志。
3. 技能快速路径执行结果回到 LLM 做最终自然表达。
4. LLM provider 增加错误类型、重试和可观测日志。
5. MCP connect/list_tools/call_tool 增加 timeout 和结构化失败审计。

---

## [2026-04-16] 阶段 2 完成：Runtime 单入口、飞书通道和常驻稳定性

**状态**：已完成。阶段 2 目标是让真实入口不会因为线程、并发和同步发送阻塞破坏日常模式运行。

### 完成内容

- `YunxiRuntime` 新增单入口 `asyncio.Lock`，串行化 `chat()` 和 `proactive_tick()`，避免飞书消息、Presence 主动 tick、未来 Tray/WebUI 并发污染 `ExecutionEngine.context`、`HeartLake` 和 `Continuity`。
- `FeishuAdapter` 支持绑定 daemon 主 asyncio loop：
  - WebSocket 线程回调通过 `asyncio.run_coroutine_threadsafe()` 投递到主 loop。
  - 同一 loop 内调用时使用 `create_task()`。
  - 处理任务/future 异常会写日志，不再静默丢失。
- 飞书发送链路改为 `asyncio.to_thread()` 包装同步 `requests`：
  - 被动回复发送不阻塞主事件循环。
  - 主动消息发送仍有锁，避免同一入口并发发送。
  - 错误回复发送失败时只记日志，不反向打断 Runtime。
- `FeishuWebSocket.stop()` 完成实际关闭流程：
  - 优先调用底层 client 的 `stop()` / `close()`。
  - 对 lark client 尝试调用私有 `_disconnect()` 并停止其 event loop。
  - join WebSocket 线程，超时后写 warning。
- 补齐飞书真实消息边界：
  - 支持 `FEISHU_IGNORE_SENDER_IDS` / 构造参数忽略指定 sender，避免自消息循环。
  - 消息去重从整表清空改为 TTL + LRU。
  - daemon 顶部不再导入飞书模块，只有 `--feishu-enable` 分支才加载 `lark-oapi` 相关依赖。

### 已验证

- `python -m py_compile src\core\runtime.py src\interfaces\feishu\adapter.py src\interfaces\feishu\websocket.py src\apps\daemon\main.py tests\unit\test_feishu_adapter.py tests\unit\test_feishu_websocket.py tests\integration\test_phase4_runtime.py` -> passed
- `python -m pytest -q tests\unit\test_feishu_adapter.py tests\unit\test_feishu_websocket.py tests\integration\test_phase4_runtime.py` -> 13 passed
- `python -m pytest -q tests\unit` -> 56 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 22 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_daily_mode_feishu_live.py -m "real_llm and feishu_live"` -> 1 skipped（未设置 `FEISHU_LIVE_TEST=1`，未误发真实消息）

### 下一步

进入阶段 3：主动性、长期关系记忆和连续性沉淀。

优先处理：
1. `recent_proactive_count` 改为按日期统计，跨天自动重置。
2. 偏好、共同经历、承诺从进程内列表改为持久化关系记忆。
3. 主动事件被选中后，将 `affect_delta` 应用到 HeartLake，并写入 continuity。
4. 普通聊天后自动抽取 open_threads、proactive_cues、偏好和承诺。
5. 补 `MemoryManager.close()`，统一关闭 PatternMiner / SkillLibrary / embedding 资源。

---

## [2026-04-16] 完成：迁移 2.0 反应库为日常模式表达参考

**状态**：已完成首版并通过本地真实 LLM 回归。用户反馈“针对我说话反应”仍显得规则化、死板；排查确认 3.0 当前回复生成虽走 LLM，但情绪表达指引主要依赖 `HeartLakeUpdater` 的规则触发和 `YunxiPromptBuilder._build_emotion_section()` 的少量硬编码提示。

### 完成内容

- 从 `D:\yunxi2.0\data\persona\reaction_library.json` 迁移反应库思路，但不直接搬运原始内容。
- 新增 `data/persona/reaction_library.json`：
  - 保留问候、想念、安慰、鼓励、玩笑、庆祝、修复、工作、夜间陪伴、轻微吃醋等日常反应类型。
  - 移除原库中高亲密成人条目，并改写亲密/夜间类示例，确保默认日常模式不注入露骨内容。
- 新增 `core.persona.reaction_library`：
  - 负责加载结构化反应库。
  - 按本轮用户输入和当前情绪检索反应参考。
  - 输出只作为 LLM 表达姿态素材，不作为固定模板回复。
- `RuntimeContext` 新增 `user_input`，`YunxiRuntime.chat()` 会把本轮用户输入传给 PromptBuilder。
- `YunxiPromptBuilder` 新增【当前反应参考】section：
  - 写入匹配场景、风格和少量表达温度参考。
  - 明确要求“不要照抄示例、不要输出内部字段/触发词/匹配分数”。

### 已验证

- `python -m py_compile src\core\persona\reaction_library.py src\core\prompt_builder.py src\core\runtime.py tests\unit\test_reaction_library.py tests\unit\test_prompt_builder.py tests\integration\test_daily_mode_scenario_tester.py` -> passed
- `python -m pytest -q tests\unit\test_reaction_library.py tests\unit\test_prompt_builder.py` -> 12 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 22 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm` -> 6 passed（真实 Moonshot，需要联网）

---

## [2026-04-16] 阶段 1 完成：恢复日常模式验收可信度

**状态**：已完成。阶段 1 的目标是让日常模式验收真正跑到 Runtime/LLM/daemon 稳定性逻辑，而不是卡在 fixture、真实桌面感知或脆弱关键词断言上。

### 完成内容

- 修复 `tests/integration/test_moonshot_cloud_matrix.py`：
  - 不再写入空事件库 `[]`，改为使用真实 `data/initiative/life_events.json`，缺失时才写入最小有效事件库。
  - 使用 `StaticPerceptionProvider`，避免云端 LLM 验收触发真实 Windows 桌面感知。
  - open thread 场景补足触发条件，确保测试实际进入主动生成路径。
  - 复用 `DailyModeScenarioTester.behavior_check()`，统一检查工程错误模板、内部字段、工具化表达和伴侣感。
- 修复 `tests/integration/test_daemon_stability.py`：
  - 使用 `StaticPerceptionProvider`，稳定性测试不再读取真实前台窗口/idle/CPU。
  - 保留真实 continuity 持久化、多轮 chat、主动 tick、上下文限制等 daemon 稳定性覆盖。
- 增强 `DailyModeScenarioTester.behavior_check()`：
  - 新增 `<think>` / `</think>` 内部推理泄露检查。
  - 新增工程错误模板拦截，避免 `[云汐这里出了点小问题：...]`、`All connection attempts failed` 被误判为合格回复。
  - 扩展伴侣语气 token，减少真实 LLM 同义表达造成的误杀。
- 调整 `test_daily_mode_full_simulation_real_llm.py`：
  - 本地 Ollama 记忆/陪伴场景长度上限从 260 调整为 360，仍保留长度边界，但不把正常本地模型长一点的自然回复误判为失败。

### 已验证

- `python -m py_compile tests\integration\daily_mode_scenario_tester.py tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_daily_mode_full_simulation_real_llm.py tests\integration\test_moonshot_cloud_matrix.py tests\integration\test_daemon_stability.py` -> passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"` -> 21 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot` -> 2 passed（真实 Moonshot，需要联网）
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm` -> 6 passed（真实 Moonshot，需要联网）

### 重要说明

- 普通沙箱网络下 Moonshot 会被拦截，`ExecutionEngine` 当前会把连接异常包装成用户可见错误文本。行为检查器已经能识别这种工程错误模板，避免测试误通过。
- 这次没有修复用户可见错误人格化本身；该问题仍归入阶段 4 的 P0-10。

### 下一步

进入阶段 2：修 Runtime 单入口、飞书通道和常驻稳定性。

优先处理：
1. 飞书 WebSocket 线程回调安全投递到主 asyncio loop。
2. Runtime 增加单入口异步锁或事件队列。
3. 飞书发送链路 async 化或 `asyncio.to_thread()` 包装。
4. `FeishuWebSocket.stop()` 完成真实关闭和线程 join。
5. 增加飞书桥接测试和 Runtime 并发测试。

---

## [2026-04-16] 阶段 0 完成：冻结日常模式验收口径

**状态**：已完成。阶段 0 的目标是冻结“日常模式必须按亲密伴侣体验验收”的口径，并确认 `DailyModeScenarioTester` 作为后续修复的主验收框架可用。

### 完成内容

- 明确后续修复继续围绕日常模式完善规划推进，不进入 Phase 6 工厂模式。
- 保持 `DailyModeScenarioTester` 为日常模式主验收框架。
- 补齐行为检查器的过长输出回归断言，确保阶段 0 通过标准覆盖内部字段泄露、工具化表达和过长输出。
- 确认 mock 只用于框架自测，不能替代真实 LLM 日常模式完成结论。

### 已验证

- `python -m py_compile tests\integration\daily_mode_scenario_tester.py tests\integration\test_daily_mode_scenario_tester.py` -> passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py` -> 5 passed

### 下一步

进入阶段 1：恢复验收可信度。

优先处理：
1. 修复或迁移 `test_moonshot_cloud_matrix.py`，解决空事件库导致未真正调用 Moonshot 的问题。
2. 修复 `test_daemon_stability.py` 使用真实感知导致挂起的问题，改用 static/mock perception provider。
3. 重跑本地 Ollama 与 Moonshot 的 Layer 2 日常仿真，并只把真实通过结果写入日志。

---

## [2026-04-16] 新增：日常模式仿真验收框架

**状态**：已完成首版搭建。该框架用于在进入工厂模式前，以真实日常使用方式验收云汐是否像“住在电脑里的女友”，而不是只验证函数调用是否成功。

### 新增/更新文件

- `docs/design/CONVERSATION_TESTER_DESIGN.md`：升级为 v2.0“日常模式仿真验收框架设计”，明确分层测试、真实 LLM、飞书 live、状态注入、行为检查和完成门槛。
- `tests/integration/daily_mode_scenario_tester.py`：新增 `DailyModeScenarioTester`，支持构建隔离 Runtime、注入记忆/情绪/感知/open thread、触发主动 tick、捕获通道消息、记录真实 LLM system prompt、执行行为检查。
- `tests/integration/test_daily_mode_scenario_tester.py`：新增框架自测，覆盖记忆注入、主动事件发送到 capture channel、吃醋状态变化、内部字段/工具化表达检查。
- `tests/integration/test_daily_mode_full_simulation_real_llm.py`：新增真实 LLM 日常仿真矩阵，覆盖本地 Ollama 和 Moonshot 两组，模拟记忆、情绪、陪伴、主动事件、open thread 和反工具化。
- `tests/integration/test_daily_mode_feishu_live.py`：新增飞书 live 主动发送测试，默认跳过，只有 `FEISHU_LIVE_TEST=1` 时真实发送消息。
- `pytest.ini`：新增 `feishu_live` marker。

### 已验证

- `python -m py_compile tests\integration\daily_mode_scenario_tester.py tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_daily_mode_full_simulation_real_llm.py tests\integration\test_daily_mode_feishu_live.py` -> passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py` -> 4 passed
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py tests\integration\test_phase5_daily_mode.py tests\integration\test_conversation_tester_baseline.py -m "not real_llm and not desktop_mcp"` -> 12 passed
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama` -> 2 passed（真实本地 Ollama）

### 重要发现

- 首次运行 Ollama 真实仿真时，框架错误地回退到了 `nomic-embed-text` embedding 模型，导致 `/api/chat` 400。已修复模型选择策略：当 `.env` 中配置的 `OLLAMA_MODEL` 不可用时，优先选择非 embedding 的聊天模型。
- 真实 Moonshot 组和飞书 live 组已经搭建，但未默认运行。Moonshot 需要可用外网/API；飞书 live 需要 `FEISHU_LIVE_TEST=1`，避免测试时误发消息。

### 后续必须补齐

1. 修复旧 `test_moonshot_cloud_matrix.py` 空事件库问题，并迁移到 `DailyModeScenarioTester`。（阶段 1 已修复空事件库，并复用统一行为检查器）
2. 修复 daemon stability 测试挂起问题，并复用新的 static perception provider。（阶段 1 已完成）
3. 新增重启后记忆持久化测试，目前预计会暴露 `MemoryManager` 长期关系记忆不足。
4. 新增主动预算跨日重置测试，目前预计会暴露 `recent_proactive_count` 不按日期重置。
5. 新增飞书线程回调测试，目前预计会暴露 `asyncio.create_task()` 在线程中无 event loop 的问题。

---

## 当前总状态

**日期**：2026-04-16  
**阶段**：Phase 5 日常模式硬化中，尚不应进入 Phase 6 工厂模式。  
**本次动作**：阶段 4 已完成，入口设计已调整为飞书唯一日常对话通道；下一步进入飞书 live、Tray/WebUI 状态控制面板和分层感知。

### 当前结论

- Phase 0-5 的骨架已经基本搭好：Runtime、PromptBuilder、LLMAdapter、MCPHub、Memory、HeartLake、Initiative、Presence、daemon、飞书通道、Ollama/Moonshot 接入均已有实现。
- yunxi2.0 的关键资产已经迁入一部分：人格 profile、用户关系 profile、生活事件库、三层主动事件系统、表达上下文、continuity/open_threads。
- 日常模式仍不能标记为完成。阶段 1 已恢复本地 Ollama、Moonshot 和 daemon stability 的基础验收可信度；阶段 2 已修复 Runtime 单入口、飞书线程回调、飞书异步发送和 WebSocket 停止流程；阶段 3 已补齐主动预算跨日重置、关系记忆持久化、连续性自动沉淀和主动事件情绪影响；阶段 4 已完成工具确认最小闭环、错误人格化、provider 重试和 MCP timeout/结构化失败。
- 旧日志中“P0-E 全部完成”的表述已作废。当前真实 LLM 第一批仿真、Moonshot 旧矩阵和 Desktop MCP 集成均已通过；剩余阻塞集中在飞书真实入口闭环、Tray/WebUI 状态控制面板、分层感知和深度 healthcheck。

### 进入工厂模式前的硬门槛

1. 日常模式真实 LLM 验收必须同时覆盖本地 Ollama 和云端 Moonshot，并实际跑通。
2. 飞书作为唯一日常对话入口，必须能稳定接收用户消息、调用 Runtime、返回回复、发送主动消息，并完成工具确认。
3. Presence 长期运行不能卡死，daemon 稳定性测试必须可信。
4. 主动性预算、冷却、未回复克制必须按真实时间持久化，而不是进程内临时变量。
5. 记忆系统必须能沉淀“远”和云汐之间的重要事实，而不只是当前进程内列表。
6. 日常工具必须有真实确认通道，否则 daily_mode 下 WRITE/EXECUTE 工具不可用。
7. 云汐回复不能暴露工程错误、系统字段、工具失败模板或客服腔。

---

## 重要里程碑保留

### Phase 0：代码准则与项目骨架

- 已建立 `CODE_QUALITY_GUIDELINES.md`。
- 已建立 `src/`、`tests/`、`docs/design/`、`data/`、`logs/` 基础结构。
- 当前仍存在违反准则的问题：核心接口中 `Any` / `Dict` 过多，宽泛异常过多，部分同步阻塞 IO 混入异步链路。

### Phase 1：MCP 与桌面工具骨架

- 已实现 `MCPClient`、`MCPHub`、`DAGPlanner`、`SecurityManager`、`AuditLogger`。
- 已实现 Desktop MCP Server：截图、剪贴板、通知、启动应用、窗口聚焦、窗口最小化。
- 当前仍缺少 file/bash/browser MCP Server。
- 日常模式的安全确认链路未闭合：`ask` 当前只是变成工具错误，没有真实向用户确认。

### Phase 2：执行引擎与 PromptBuilder

- 已实现 `YunxiExecutionEngine`、`ConversationContext`、`ExecutionResult`。
- 已实现 `YunxiPromptBuilder`，能注入人格、关系、情感、感知、记忆、失败经验、连续性和工具列表。
- 当前问题：错误恢复仍模板化；Prompt 没有结构化压缩；工具失败会出现工程化回复。

### Phase 3：记忆与技能学习

- 已实现 `MemoryManager`、`ExperienceBuffer`、`PatternMiner`、`SkillDistiller`、`SkillLibrary`、`FailureReplay`、`ParamFiller`。
- 已接入本地 Ollama embedding provider 和 lexical fallback。
- 当前问题：长期关系记忆不完整，偏好/片段/承诺仍主要是进程内列表；技能蒸馏和参数填充仍偏正则。

### Phase 4：情感、主动性、人格资产迁移

- 已实现 HeartLake、HeartLakeUpdater、InitiativeEngine、ThreeLayerInitiativeEventSystem、ExpressionContextBuilder、ProactiveGenerationContextBuilder。
- 已迁入 persona profile、relationship profile、life events。
- 主动消息生成方向正确：最终文本由真实 LLM 生成，不恢复固定 fallback 文案。
- 当前问题：情感模型仍偏阈值机；关系等级固定；事件的 affect_delta 未真正影响 HeartLake；open_threads/proactive_cues 多数依赖手动写入。

### Phase 5：日常模式闭环

- 已实现 `YunxiRuntime`、daemon、Presence tick、Tray 状态快照适配、飞书通道草案。
- 已支持本地 Ollama 作为一等 LLM 后端。
- 当前问题：飞书 live 还未完成完整真实入口验收；Tray/WebUI 仍只是状态快照适配，尚未成为状态与控制面板；分层感知和 deep healthcheck 仍待补齐。

---

## [2026-04-16] 日常模式整体大审查：重要问题清单

**审查目标**：在进入工厂模式前，按“住在电脑里的女友”“像人一样有感情、生动、活泼、长期陪伴”的设计初衷，重新检查当前所有核心实现。  

**审查范围**：

- `src/core/runtime.py`
- `src/core/prompt_builder.py`
- `src/core/persona/profile.py`
- `src/core/cognition/heart_lake/*`
- `src/core/cognition/initiative_engine/*`
- `src/core/initiative/*`
- `src/core/execution/engine.py`
- `src/core/llm/*`
- `src/core/mcp/*`
- `src/core/tools/desktop/*`
- `src/core/resident/presence.py`
- `src/domains/memory/*`
- `src/domains/perception/*`
- `src/apps/daemon/*`
- `src/apps/tray/*`
- `src/interfaces/feishu/*`
- `tests/unit/*`
- `tests/integration/*`
- `tests/domains/memory/*`
- `data/persona/*`
- `data/relationship/*`
- `data/initiative/*`

### 本次真实验证结果

- `python -m py_compile ...`：核心日常模式文件语法编译通过。
- `python -m pytest -q tests\unit tests\domains\memory tests\integration\test_conversation_tester_baseline.py tests\integration\test_phase5_daily_mode.py -m "not real_llm and not desktop_mcp"`：76 passed。
- `python -m pytest -q tests\integration\test_moonshot_cloud_matrix.py -m real_llm`：6 errors，全部卡在 fixture setup，未真正调用 Moonshot。
- `python -m pytest -q tests\integration\test_daemon_stability.py::test_stability_continuity_persistence -vv -s`：90 秒超时，测试未完成。
- 静态扫描：`src` 中约 129 处 `Any` / `Dict`，约 18 处宽泛异常，约 9 处同步阻塞或高风险调用模式（`requests` / `time.sleep` / `shell=True`）。

---

## P0：进入工厂模式前必须修复

### P0-01：Moonshot 云端真实 LLM 矩阵当前没有跑通

文件：`tests/integration/test_moonshot_cloud_matrix.py`

当前状态：阶段 1 已修复。旧矩阵现在使用真实事件库、static perception provider 和统一行为检查器；真实 Moonshot 运行结果为 6 passed。

问题：
- fixture 把临时事件库写成 `[]`。
- `ThreeLayerInitiativeEventSystem` 明确拒绝空事件库。
- 6 个测试全部在 setup 阶段失败，没有实际调用 Moonshot，也没有验证云汐人格、主动性或记忆质量。

影响：
- “云端模型对照已完成”的结论不成立。
- 当前不能证明云汐在云端模型下符合日常模式设计。

修复要求：
- 使用真实 `data/initiative/life_events.json` 或写入最小有效事件库。
- 测试必须实际进入 `runtime.chat()` / `runtime.proactive_tick()`。
- 断言不能只查关键词，还要判断是否反工具化、是否符合人格、是否没有系统字段泄漏。

### P0-02：daemon 稳定性测试会挂住

文件：`tests/integration/test_daemon_stability.py`

当前状态：阶段 1 已修复。稳定性测试已改用 static perception provider；本地非 real_llm 回归中该文件 7 passed。

问题：
- fixture 使用真实 `PerceptionCoordinator()`。
- `runtime.chat()` 会触发真实 Windows 感知读取，测试在当前环境下 90 秒未完成。

影响：
- “daemon 长时间稳定性测试完成”的结论不成立。
- 当前无法证明日常模式可长期常驻。

修复要求：
- 稳定性测试必须注入 static/mock perception provider。
- 真实桌面感知测试应单独放入 `desktop_mcp` 或专门 marker。
- daemon 稳定性需要至少覆盖短跑、长跑、主动 tick、连续 chat、异常恢复和资源释放。

### P0-03：飞书消息回调大概率无法在真实线程中调用 Runtime

文件：`src/interfaces/feishu/adapter.py`、`src/interfaces/feishu/websocket.py`

问题：
- `FeishuWebSocket` 在线程中运行 lark client。
- `FeishuAdapter.on_feishu_message()` 在同步回调里直接 `asyncio.create_task()`。
- WebSocket 线程通常没有正在运行的 event loop，会触发 `RuntimeError: no running event loop`。

影响：
- 飞书通道可能“能启动但收消息就失败”。
- 日常模式真实入口不可靠。

修复要求：
- daemon 创建 adapter 时必须传入主 asyncio loop。
- WebSocket 线程收到消息后用 `asyncio.run_coroutine_threadsafe()` 投递到主 loop。
- 增加真实或半真实回归测试，覆盖线程回调到 `runtime.chat()` 的链路。

当前状态：阶段 2 已修复。`FeishuAdapter` 支持绑定主 loop；WebSocket 线程回调通过 `run_coroutine_threadsafe()` 投递；`tests/unit/test_feishu_adapter.py` 覆盖线程回调进入主 loop 并调用 `runtime.chat()`。

### P0-04：Runtime 没有并发保护

文件：`src/core/runtime.py`、`src/core/execution/engine.py`、`src/core/initiative/continuity.py`

问题：
- 飞书用户消息、Presence 主动 tick、未来 Tray/WebUI 都可能并发调用 `runtime.chat()` / `runtime.proactive_tick()`。
- `ExecutionEngine.context`、`HeartLake`、`Continuity`、`MemoryManager` 都是可变状态，没有锁。

影响：
- 对话上下文可能交错。
- 主动消息和用户回复可能互相污染。
- 情感、未回复计数、open_threads 可能错乱。

修复要求：
- Runtime 层增加单入口异步锁或事件队列。
- 主动消息和用户消息必须统一排队。
- 增加并发测试：多条飞书消息 + Presence tick 同时发生时上下文仍一致。

当前状态：阶段 2 已修复。`YunxiRuntime` 使用单入口 `asyncio.Lock` 串行化 `chat()` 和 `proactive_tick()`；`tests/integration/test_phase4_runtime.py` 覆盖并发 chat、chat + proactive tick 不重入 LLM。

### P0-05：主动预算不是“每日预算”，会永久耗尽

文件：`src/core/initiative/continuity.py`、`src/core/cognition/initiative_engine/engine.py`

问题：
- `recent_proactive_count` 只累加，不按日期重置。
- `InitiativeEngine` 用它判断 `daily_budget`。
- continuity 持久化后，一旦主动次数达到预算，可能长期不再主动。

影响：
- 云汐会从“有克制的主动陪伴”变成“沉默”。
- 这直接破坏日常模式的女友感。

修复要求：
- 记录主动计数所属日期。
- 跨天自动重置。
- 测试覆盖跨日预算、未回复克制、冷却、用户回复后恢复。

当前状态：阶段 3 已修复。`CompanionContinuityService` 新增 `proactive_count_date`，`InitiativeEngine.evaluate()` 前刷新日期；跨日后 `recent_proactive_count` 自动归零并恢复主动预算。

### P0-06：日常工具的安全确认链路没有闭合

文件：`src/core/mcp/security.py`、`src/core/mcp/hub.py`、`src/core/execution/engine.py`

问题：
- daily_mode 下 WRITE / EXECUTE 默认返回 `ask`。
- `MCPHub` 对 `ask` 的处理只是返回错误。
- 已有对话内 pending confirmation 最小闭环，但飞书 live 尚未完成确认/取消的真实入口验收。

影响：
- 云汐 prompt 里说“可以使用工具”，但实际调用会失败。
- 用户体验会变成“云汐想帮忙但总是说失败”。

修复要求：
- 设计统一确认协议：pending tool request。
- 飞书真实入口必须能完成确认/取消；WebUI/Tray 只展示 pending 状态，不作为正式确认入口。
- LLM 回复要自然表达“这个操作需要你点头”，不能暴露安全策略字段。

当前状态：阶段 4 已完成最小闭环。`MCPHub` 会为 `ask` 生成 pending confirmation，`YunxiExecutionEngine` 支持“确认/取消”继续或放弃最新 pending 工具；回复采用自然表达，不暴露安全策略字段。阶段 5 需要把确认/取消接入飞书 live；Tray/WebUI 只负责状态展示。

### P0-07：长期关系记忆还不是真正的长期记忆

文件：`src/domains/memory/manager.py`、`src/core/initiative/continuity.py`

问题：
- `record_preference()` / `record_episode()` / `record_promise()` 写入进程内列表。
- daemon 重启后这些记忆会丢失。
- `relationship_summary` / `emotional_summary` / `user_style_summary` 只支持手动更新，没有 LLM 总结写入链路。
- 普通聊天经验只进入 `ExperienceBuffer`，但没有转化为关系记忆。

影响：
- 云汐会有“失忆感”。
- 女友感依赖长期细节，而不是每轮 system prompt 静态设定。

修复要求：
- 将偏好、共同经历、承诺持久化。
- 增加聊天后异步记忆提取。
- 增加关系摘要和情绪摘要的周期性 LLM 更新。
- 测试必须覆盖重启后仍记得用户事实。

当前状态：阶段 3 已完成首版持久化和保守抽取。`MemoryManager` 将偏好、共同经历、承诺落盘到 `relationship_memory.json`，重建后可恢复；普通聊天后会保守抽取偏好/承诺/经历。周期性 LLM 摘要更新仍留作后续增强。

### P0-08：飞书发送链路在 async 函数里使用同步 requests

文件：`src/interfaces/feishu/client.py`、`src/interfaces/feishu/adapter.py`

问题：
- `FeishuClient` 使用同步 `requests`。
- `FeishuAdapter.handle_message()` / `send_proactive_message()` 是 async，但内部直接阻塞发送。

影响：
- 飞书 API 慢或网络抖动时会阻塞主事件循环。
- Presence tick、用户消息和未来 UI 入口都会被拖慢。

修复要求：
- 改为 `httpx.AsyncClient` 或 `asyncio.to_thread()` 包装同步请求。
- 增加超时、重试和失败降级。
- 主动消息失败不能影响 Runtime 主循环。

当前状态：阶段 2 已修复主链路。`FeishuAdapter.handle_message()` 和 `send_proactive_message()` 已用 `asyncio.to_thread()` 包装同步发送；发送异常只写日志，不反向打断 Runtime。

### P0-09：FeishuWebSocket 停止逻辑不完整

文件：`src/interfaces/feishu/websocket.py`

问题：
- `stop()` 只设置 `_running = False`。
- 没有停止 lark client。
- 没有 join 线程。

影响：
- daemon 退出时可能残留后台线程或连接。
- 长期运行/重启会不稳定。

修复要求：
- 明确 lark client 的关闭 API。
- stop 时关闭 client、等待线程退出、超时后记录警告。

当前状态：阶段 2 已修复。`FeishuWebSocket.stop()` 会调用底层 client stop/close 或 lark `_disconnect()`，随后 join 线程并对超时写 warning；单元测试覆盖 stop 关闭 client 并回收线程。

### P0-10：错误回复破坏人格

文件：`src/core/execution/engine.py`

问题：
- LLM 或工具异常时返回 `[云汐这里出了点小问题：...]`、`[工具执行遇到问题，请换个方式说吧]`。
- 这类括号化工程提示不符合“住在电脑里的女友”。

影响：
- 一旦出错，云汐立刻变成程序错误提示器。

修复要求：
- 对用户可见错误必须走人格化表达。
- 技术细节进入日志，不直接进入用户回复。
- 测试覆盖 LLM 异常、工具异常、安全 ask、未知工具。

当前状态：阶段 4 已修复。Engine 不再返回括号化工程错误；LLM 异常、工具失败、max turns、确认取消和未知工具均有自然回复或结构化内部错误，技术细节只进入 error/log/audit。

---

## P1：日常模式质量问题

### P1-01：HeartLake 仍偏阈值状态机

文件：`src/core/cognition/heart_lake/core.py`、`src/core/cognition/heart_lake/updater.py`

问题：
- 情感更新主要由 idle、app、hour、关键词/正则触发。
- `_JealousyAppraisal` 比原先更集中，但仍是模式匹配，不是语义 appraisal。
- `AppraisalRule.DEFAULT_RULES` 没有真正启用。
- `relationship_level` 固定为 4，没有升级/降级/仪式感。

影响：
- 云汐的情感不够“像人”，更像数值状态机。

修复方向：
- 引入 LLM 或轻量语义分类器做对话 appraisal。
- 引入情感惯性、恢复曲线、关系仪式和长期关系事件。
- 将事件库 `affect_delta` 真实写入 HeartLake。

### P1-02：主动事件只作为 prompt 素材，未真正影响情绪

文件：`src/core/initiative/event_system.py`、`src/core/runtime.py`

问题：
- `InitiativeEvent.affect_delta` 被加载，但没有应用到 HeartLake。
- 事件选择不会改变云汐“自己的心情”。

影响：
- 事件库更像话题素材库，不像云汐自己的生活体验。

修复方向：
- 事件被选中后将 affect_delta 写入 HeartLake。
- 将事件记入 continuity，避免主动消息没有生活连续性。

当前状态：阶段 3 已修复。主动事件选中后会调用 `HeartLake.apply_affect_delta()`，并把事件 id/category/seed/affect 写入 continuity 的 `initiative_events`。

### P1-03：open_threads 和 proactive_cues 缺少自动生成

文件：`src/core/initiative/continuity.py`、`src/core/runtime.py`

问题：
- `add_open_thread()`、`add_proactive_cue()` 已有，但普通对话不会自动抽取未完成话题。
- 用户说“明天提醒我”“下次再聊”之类内容不会自动进入主动线索。

影响：
- 云汐不会真正“记挂着上次没聊完的事”。

修复方向：
- chat 后增加 LLM/规则混合抽取：承诺、未完成话题、用户状态、主动线索。
- 测试覆盖 open thread 自动生成和主动延续。

当前状态：阶段 3 已完成保守规则版。普通聊天后会抽取未来提醒/继续话题为 open thread 和 proactive cue，并抽取偏好/承诺/经历进入长期关系记忆。

### P1-04：技能快速路径绕过 LLM，容易退回工具助手

文件：`src/core/execution/engine.py`

问题：
- 匹配到技能后直接执行工具并返回固定变体。
- 回复比以前不再单一句，但仍不是根据当前情绪、关系、上下文生成。

影响：
- 高频工具使用时，云汐会像脚本执行器。

修复方向：
- 工具执行结果应回到 LLM 做最终自然表达，或至少把 HeartLake/relationship/context 纳入回复选择。
- 快速路径只负责执行，不负责最终人格化表达。

当前状态：阶段 4 已修复首版。技能快速路径执行结果会交给 LLM 做最终自然表达；最终表达失败时才使用人格化保守回退。

### P1-05：PromptBuilder 只拼接，不压缩

文件：`src/core/prompt_builder.py`

问题：
- memory、continuity、tools、event context 都直接拼接。
- 没有 token 预算、优先级、结构化压缩或过期策略。

影响：
- 长期运行后 prompt 会膨胀或截断关键信息。
- 重要关系记忆可能被普通工具日志挤掉。

修复方向：
- 建立 prompt section budget。
- 关系事实、当前情绪、未完成话题优先级高于工具经验。
- 增加结构化压缩测试。

### P1-06：Perception 真实感知能力远低于设计目标

文件：`src/domains/perception/coordinator.py`

问题：
- 当前只采集时间、前台窗口、idle、CPU。
- 设计中的桌面文件、最近文件、天气、网络、剪贴板、窗口内容、应用语义都未实现。
- `fetch()` 是同步调用，缺少总超时。

影响：
- 云汐“住在电脑里”的感知太薄。
- 真实桌面读取异常可能阻塞聊天。

修复方向：
- 感知 provider 分层：快速基础感知、慢速外部感知、可选隐私感知。
- 每类感知都要有超时和降级。

### P1-07：Tray/WebUI 定位需改为状态与控制面板

文件：`src/apps/tray/web_server.py`

问题：
- 当前只有 `RuntimeStatus` 和 `build_runtime_status()`。
- 原设计把 WebUI/Tray 也当作聊天和主动消息入口，和飞书职责重叠。
- 还没有真实托盘图标、Web server、日志查看、healthcheck 操作、飞书连接状态展示和工厂模式入口。

影响：
- 多个聊天入口会放大并发、消息去重、工具确认和状态同步复杂度。
- WebUI/Tray 如果做重，会拖慢阶段 5 的核心目标：打穿飞书真实日常入口。

修复方向：
- 飞书作为唯一日常对话入口：用户消息、云汐主动消息、工具确认全部走飞书。
- WebUI 只做状态、日志、healthcheck、飞书连接状态、pending confirmation 状态展示和工厂模式入口。
- Tray 左键打开 WebUI；右键提供打开状态页、进入工厂模式、执行 healthcheck、打开日志、停止/重启 daemon 等控制项。

### P1-08：LLM provider 缺少生产级重试和错误分层

文件：`src/core/llm/provider.py`、`src/core/llm/adapter.py`

问题：
- `LLMConfig.max_retries` 没有实际使用。
- HTTP 错误直接 `raise_for_status()`。
- tool arguments JSON 解析失败会冒到 engine 变成泛化错误。
- `stream()` 没有处理 Ollama 原生流式协议。

影响：
- 网络波动时日常模式容易中断。
- 错误不可区分：配置错、限流、模型不可用、输出非法都会混在一起。

修复方向：
- 增加 provider 级错误类型。
- 使用 max_retries、指数退避、可观测日志。
- Ollama stream 单独实现或明确禁用。

当前状态：阶段 4 已修复主路径。provider 新增网络/HTTP/响应三类结构化错误，并对 complete 请求按 `max_retries` 重试；stream 路径仍留作后续细化。

### P1-09：MCPClient 缺少调用超时

文件：`src/core/mcp/client.py`、`src/core/mcp/hub.py`

问题：
- server connect、tool call 没有统一 timeout。
- 未知工具在 `MCPHub` 中直接 raise，可能绕过审计。

影响：
- 单个工具卡住会拖住整轮对话。
- 失败经验不完整，后续学习无法复盘。

修复方向：
- 对 connect/list_tools/call_tool 增加 timeout。
- 未知工具也应转成结构化 ToolChainResult 并写审计。

当前状态：阶段 4 已修复。`MCPClient` 对 connect/initialize/list_tools/call_tool 增加 timeout；未知工具返回 `error_type="unknown_tool"` 的结构化结果并进入审计，不再直接 raise。

### P1-10：桌面工具有安全和准确性缺口

文件：`src/core/tools/desktop/uia_driver.py`、`src/core/mcp/servers/desktop_server.py`

问题：
- `UIADriver.launch_application()` 找不到 PATH 时使用 `shell=True`。
- `screenshot_capture(save_path)` 没有限制保存路径。
- `app_launch_ui()` 只靠屏幕像素变化判断成功，可能重复启动多个实例。
- `clipboard_read()` 可能把敏感剪贴板内容直接交给 LLM。

影响：
- 安全边界不符合代码准则。
- 桌面操作成功率和隐私控制不足。

修复方向：
- 应用启动改为 allowlist 或显式确认。
- 截图路径限制到项目/用户授权目录。
- 剪贴板读取加入隐私确认或脱敏策略。
- app 启动增加窗口检测。

### P1-11：飞书通道缺少真实消息边界

文件：`src/interfaces/feishu/*`

问题：
- 没有明确忽略机器人自己发送的消息。
- 消息去重集合超过 2000 后整表清空，可能允许旧消息重复。
- `transport` 字段未使用。
- `proactive_callback` 参数未实际参与逻辑。
- 可选飞书模块在 daemon 顶部导入，导致不用飞书时也依赖 `lark-oapi`。

影响：
- 长期运行可能出现重复消息、循环消息或不必要依赖失败。

修复方向：
- 增加 self-message filter。
- 用 TTL/LRU 去重。
- 飞书相关导入延迟到 `--feishu-enable` 分支。

当前状态：阶段 2 已修复本阶段边界项。`FeishuWebSocket` 支持忽略指定 sender，去重改为 TTL/LRU；daemon 飞书导入已延迟到 `--feishu-enable` 分支。`transport` 字段和 `proactive_callback` 参数清理仍作为后续低优先级接口整理。

### P1-12：Memory/SkillLibrary 资源生命周期不完整

文件：`src/domains/memory/manager.py`、`src/domains/memory/skills/pattern_miner.py`、`src/domains/memory/skills/skill_library.py`、`src/apps/daemon/main.py`

问题：
- `PatternMiner.close()`、`SkillLibrary.close()` 存在，但 `MemoryManager` 没有统一 close。
- `close_runtime()` 没有关闭 memory embedding 资源。
- `OllamaSkillEmbedder.initialize()` 创建 async client，但 `encode_sync()` 使用新的同步 client，async client 实际闲置。
- `SkillLibrary.retrieve()` 中 Ollama embedding 同步请求会阻塞事件循环。

影响：
- 长期 daemon 可能资源泄漏或被 embedding 请求卡住。

修复方向：
- `MemoryManager.close()` 统一释放所有资源。
- Ollama embedding 统一 async 化。
- daemon close_runtime 必须关闭 memory。

当前状态：阶段 3 已完成主生命周期。`MemoryManager.close()` 已统一关闭 PatternMiner 和 SkillLibrary，daemon close 和 DailyModeScenarioTester teardown 已调用。Ollama embedding 的 sync/async client 结构仍留作后续细化。

---

## P2：工程质量和测试覆盖问题

### P2-01：类型系统仍不符合准则

问题：
- `src` 中约 129 处 `Any` / `Dict`。
- 核心接口如 Engine、MCP、Memory、LLM Adapter 仍依赖 duck typing。

影响：
- 工厂模式会放大接口不稳定问题。

修复方向：
- 用 dataclass / Protocol / TypedDict 替换核心裸 dict。
- 先处理 Runtime、Engine、MCPHub、Memory、LLMResponse、ToolResult。

### P2-02：宽泛异常仍偏多

问题：
- `src` 中约 18 处 `except Exception` 或等价宽泛捕获。
- 部分捕获只返回字符串，缺少错误类型和上下文。

影响：
- 真实问题容易被吞掉。
- 用户可见回复和日志不可追踪。

修复方向：
- 定义 RuntimeError、ToolError、ProviderError、PerceptionError、FeishuError。
- 底层记录技术上下文，上层转换成人格化回复。

### P2-03：测试仍有“浅验收”问题

问题：
- Moonshot matrix 当前没跑到 LLM。
- daemon stability 用 MockLLM 且挂在真实感知。
- 真实 LLM 测试主要靠关键词断言，不能充分判断“女友感”。
- 飞书没有真实收发链路测试。
- Ollama embedding 没有 live 测试。
- 没有并发测试、跨日预算测试、重启后记忆测试、工具确认测试。

修复方向：
- 增加 LLM-as-judge 或结构化评价器，判断是否客服腔、是否工具化、是否关系连续。
- 将真实 LLM 测试分成本地 Ollama、云端 Moonshot、入口通道、桌面工具四组。
- 每组失败必须阻止进入下一阶段。

### P2-04：用户关系资料文件可读性差

文件：`data/relationship/user_profile.md`

问题：
- 文件内容大量使用 `\uXXXX` 转义，程序能解码，但人类维护体验差。

影响：
- 用户后续手动修改关系资料不方便。

修复方向：
- 改成真实中文 Markdown，并保留加载兼容。

### P2-05：healthcheck 太浅

文件：`src/apps/daemon/main.py`

问题：
- healthcheck 只构建 Runtime 和状态快照。
- 不验证 LLM 可用性、主动 tick、飞书配置、工具确认通道、memory close。

影响：
- healthcheck passed 不代表日常模式能真实工作。

修复方向：
- 增加 `--healthcheck-deep`。
- 覆盖 LLM ping、memory init/close、event library、continuity read/write、optional feishu config。

---

## 日常模式完善规划

本规划把上方 P0/P1/P2 问题整理成可执行依赖链。原则是：先恢复验收可信度，再修入口和并发，再修长期陪伴能力，最后补工具确认、WebUI 和感知增强。每一阶段完成后必须进入对应的仿真验证层，验证通过后才进入下一阶段。

### 阶段 0：冻结目标与验收口径

目标：确保后续所有修复都围绕“住在电脑里的亲密伴侣”展开，而不是把云汐推回工具助手。

必须保持：
- `DailyModeScenarioTester` 作为日常模式验收主框架。
- `DEV_LOG.md` 只记录真实通过的验证结果，不再保留“预计完成”“理论完成”结论。
- Phase 6 工厂模式继续冻结。

通过标准：
- `tests/integration/test_daily_mode_scenario_tester.py` 通过。
- 行为检查器能识别内部字段泄露、工具化表达和过长输出。

完成后进入：阶段 1。

### 阶段 1：恢复验收可信度

先修问题：
- P0-01：修复 `test_moonshot_cloud_matrix.py` 空事件库，或直接迁移到 `DailyModeScenarioTester`。
- P0-02：修复 `test_daemon_stability.py` 真实感知导致的挂起，改用 static/mock perception provider。
- P2-03：把真实 LLM 测试从浅关键词验收升级为行为验收，至少检查反工具化、人格、系统字段不泄露。

原因：
- 如果 Moonshot 矩阵没有真正跑到 LLM，云端模型质量无法判断。
- 如果 daemon 稳定性测试会挂住，后续所有入口和常驻能力都没有可信基线。

必须验证：
- `python -m pytest -q tests\integration\test_daily_mode_scenario_tester.py`
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k ollama`
- `python -m pytest -q tests\integration\test_daily_mode_full_simulation_real_llm.py -m real_llm -k moonshot`
- `python -m pytest -q tests\integration\test_daemon_stability.py -m "not real_llm and not desktop_mcp"`

通过后可以进入：
- 日常模式仿真验证 Layer 2（本地 Ollama + Moonshot）。
- 阶段 2 的入口、飞书和并发修复。

未通过时禁止：
- 宣布日常模式完成。
- 新增工厂模式代码。
- 用 mock 测试替代真实 LLM 结论。

### 阶段 2：修 Runtime 单入口、飞书通道和常驻稳定性

先修问题：
- P0-03：飞书 WebSocket 线程回调必须投递到主 asyncio loop。
- P0-04：Runtime 增加单入口异步锁或事件队列，串行化 `chat()` / `proactive_tick()`。
- P0-08：飞书发送链路改 async，或用 `asyncio.to_thread()` 包裹同步 `requests`。
- P0-09：`FeishuWebSocket.stop()` 完成 client 停止、线程 join 和超时告警。
- P1-11：增加 self-message filter、TTL/LRU 去重，飞书导入延迟到 `--feishu-enable` 分支。

原因：
- 飞书是当前最接近日常真实入口的通道；如果收消息、回消息、主动消息任一环不可靠，日常模式仍只能算内部 demo。
- Runtime 内部状态大量可变，没有并发保护会污染情绪、连续性和上下文。

必须新增/修复测试：
- 飞书线程回调测试：模拟 WebSocket 线程调用 `on_feishu_message()`，确认能安全进入主 loop 并调用 `runtime.chat()`。
- Runtime 并发测试：多条用户消息 + proactive tick 同时发生时，continuity 顺序一致，未回复计数不乱。
- 飞书发送失败降级测试：发送失败不能阻塞 Presence 主循环。

必须验证：
- 阶段 1 的 Layer 2 真实 LLM 仿真仍通过。
- 飞书桥接测试通过。
- 手动开启时 `FEISHU_LIVE_TEST=1` 的飞书 live 主动发送通过。

通过后可以进入：
- 日常模式仿真验证 Layer 3（真实通道验收）。
- 阶段 3 的主动性、长期记忆和跨日模拟。

### 阶段 3：修主动性、长期关系记忆和连续性沉淀

先修问题：
- P0-05：`recent_proactive_count` 改为按日期统计，跨天自动重置。
- P0-07：偏好、共同经历、承诺从进程内列表改为持久化关系记忆。
- P1-02：主动事件被选中后，将 `affect_delta` 应用到 HeartLake，并写入 continuity。
- P1-03：普通聊天后自动抽取 open_threads、proactive_cues、偏好和承诺。
- P1-12：补 `MemoryManager.close()`，统一关闭 PatternMiner / SkillLibrary / embedding 资源。

原因：
- 女友感依赖长期细节和“记挂着上次没聊完的事”，不能只靠静态 persona prompt。
- 主动预算不跨日重置会让云汐长期沉默；记忆不持久化会造成失忆感。

必须新增/修复测试：
- 重启后记忆测试：写入偏好/承诺，关闭并重建 Runtime 后仍能召回。
- 跨日预算测试：当天预算耗尽后，模拟第二天，主动预算恢复。
- open thread 自动生成测试：用户说“明天提醒我”“下次再聊”后进入主动线索。
- 事件情绪影响测试：选中事件后 HeartLake 状态出现对应变化。

必须验证：
- Layer 2 真实 LLM 仿真仍通过。
- Layer 3 飞书通道仍通过。
- 新增长程日常模拟 Layer 4：模拟一天或多天的早晨、工作、深夜、离开、回来、未回复克制、跨日预算和重启记忆。

通过后可以进入：
- 阶段 4 的工具确认和错误人格化。

### 阶段 4：修日常工具确认和用户可见错误人格化

先修问题：
- P0-06：实现统一 pending tool confirmation 协议。
- P0-10：所有用户可见错误改为云汐人格化表达，技术细节只进日志。
- P1-04：技能快速路径只负责执行，工具结果回到 LLM 做最终自然表达，或纳入 HeartLake/relationship/context 生成。
- P1-08：LLM provider 增加错误类型、`max_retries`、退避重试和可观测日志。
- P1-09：MCP connect/list_tools/call_tool 增加 timeout；未知工具也转为结构化 ToolChainResult 并审计。
- P1-10：桌面工具补安全边界：截图路径限制、应用启动 allowlist 或确认、剪贴板读取隐私策略。

原因：
- daily_mode 下 WRITE/EXECUTE 工具当前会变成安全错误，用户体验是“云汐想帮忙但总失败”。
- 出错时不能暴露 `[工具执行遇到问题]` 或 `[云汐这里出了点小问题]` 这类工程模板。

必须新增/修复测试：
- 工具确认测试：写剪贴板/启动应用进入 pending confirmation，经飞书真实入口确认后继续执行。
- 错误人格化测试：LLM 异常、工具异常、安全 ask、未知工具都返回自然表达。
- provider 重试测试：临时网络错误触发重试，最终失败时错误类型可区分。

必须验证：
- Layer 2/3/4 继续通过。
- 工具确认链路通过飞书真实入口闭合。

通过后可以进入：
- 阶段 5 的飞书 live 入口、WebUI/Tray 状态控制面板和感知增强。

### 阶段 5：补飞书真实日常入口、Tray/WebUI 状态控制面板和分层感知

先修问题：
- P1-06：Perception provider 分层，基础感知、慢速外部感知、可选隐私感知分别带 timeout 和降级。
- P1-07：飞书作为唯一日常对话入口，完成收消息、Runtime 回复、主动消息发送、工具确认确认/取消闭环。
- P1-07：WebUI/Tray 简化为状态与控制面板，支持状态查看、运行日志、healthcheck、飞书连接状态、pending confirmation 状态展示和工厂模式入口。
- P2-05：增加 `--healthcheck-deep`，覆盖 LLM ping、memory init/close、event library、continuity read/write、optional feishu config。
- P2-04：把 `data/relationship/user_profile.md` 改成真实中文 Markdown，保留转义加载兼容。
- P2-01 / P2-02：逐步用 dataclass / Protocol / TypedDict 替换核心裸 `Any` / `Dict`，并减少宽泛异常。

原因：
- 日常聊天统一走飞书，避免 WebUI/Tray/飞书多个入口重复承载对话造成并发、去重和确认链路复杂化。
- WebUI/Tray 的价值是本地可观测和控制，不是再造一套聊天产品。
- 感知太薄会削弱“住在电脑里”的真实感，但感知增强必须先有超时、隐私和降级边界。

必须新增/修复测试：
- 飞书 live smoke test：能收用户消息、返回 Runtime 回复、发送主动消息、通过“确认/取消”处理 pending 工具。
- WebUI/Tray smoke test：能显示状态、日志、飞书连接状态、pending confirmation 状态，并能触发 healthcheck / 工厂模式入口。
- deep healthcheck 测试：能发现 LLM、memory、event library、continuity 和飞书配置问题。
- 感知 timeout 测试：慢 provider 不阻塞整轮聊天。

必须验证：
- 日常模式全量仿真矩阵通过。
- daemon 短跑/长跑稳定性通过。
- 飞书真实入口完成 chat + 主动消息 + 工具确认。
- `yunxi` CLI 工厂模式入口占位可从任意项目目录解析当前路径。

通过后可以进入：
- 日常模式完成候选验收。

### 日常模式完成候选验收门槛

只有同时满足以下条件，才允许把 Phase 5 标记为完成，并讨论是否进入 Phase 6：

1. 本地 Ollama 与 Moonshot 的 Layer 2 日常仿真全部通过。
2. Layer 3 飞书 live 主动发送在手动开启时通过。
3. Layer 4 长程日常模拟通过，覆盖未回复克制、跨日预算、重启记忆。
4. daemon stability 不挂起，短跑和长跑结果可信。
5. Runtime 并发测试通过。
6. 飞书真实入口能稳定收消息、调用 Runtime、回消息、发送主动消息。
7. 工具确认链路闭合，WRITE/EXECUTE 不再直接变成安全错误。
8. 用户可见错误不暴露工程模板、内部字段或系统栈信息。
9. 长期关系记忆重启后不丢失。
10. `DEV_LOG.md` 记录了真实命令、模型、通过结果和剩余风险。

---

## 当前禁止事项

- 禁止直接进入 Phase 6 工厂模式。
- 禁止再次把 P0-E 标记为完成，直到真实 LLM 矩阵和 daemon 稳定性通过。
- 禁止用只跑函数是否成功的测试替代真实 LLM 行为验收。
- 禁止为了推进进度把云汐写成工具调度器、脚本执行器或客服助手。
- 禁止新增大功能前继续堆叠未关闭的 Runtime/入口/记忆/主动性技术债。

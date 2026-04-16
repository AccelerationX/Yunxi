# 日常模式后续优化审查

最后更新：2026-04-16

## 结论

日常模式 v1 已经可以作为稳定基线继续使用，但还没有达到“长期陪伴体验最好”的状态。下一阶段不建议进入工厂模式，建议继续围绕情感自然度、长期记忆、自主学习、真实电脑能力和多日常驻稳定性打磨。

## P0：下一轮优先处理

### 1. 长期记忆摘要与上下文压缩

现状：

- `MemoryManager.capture_relationship_memory()` 仍是保守关键词抽取。
- `CompanionContinuityService` 已有 `relationship_summary`、`emotional_summary`、`user_style_summary` 字段，但缺少定期 LLM 总结任务。
- `ConversationContext` 只保留最近 20 条消息，长对话容易丢失微妙关系线索。

建议：

- 新增 `DailyMemorySummarizer`，按会话结束、每日、每 N 轮对话生成三类摘要：关系事实、情绪轨迹、用户表达习惯。
- 摘要写入 continuity 和 relationship memory，并进入 prompt builder。
- 给摘要增加“可人工阅读”的 Markdown 导出，方便手动维护。

### 2. 情绪系统从规则触发升级到语义评估

现状：

- `HeartLakeUpdater` 的吃醋、担心、想念等仍主要依赖规则和感知事件。
- ReactionLibrary 已改善表达风格，但不是情绪评估本身。

建议：

- 新增轻量 `EmotionAppraiser`：输入用户话语、最近上下文、关系摘要，输出情绪 delta 和理由。
- HeartLake 保留动力学和边界，语义 appraiser 只提供建议 delta。
- 增加情绪惯性、恢复速度、误触发抑制，避免一条消息让情绪跳太硬。

### 3. 主动性策略自然度

现状：

- `InitiativeEngine` 已有冷却、预算、未回复克制和打扰成本。
- 但主动消息仍偏“触发一次就发一次”，缺少多日节奏和关系仪式感。

建议：

- 增加主动消息类型：轻触达、关心、延续话题、分享生活、提醒承诺。
- 为不同类型设置独立预算和冷却。
- 增加“沉默也是陪伴”的策略：检测用户高专注时只记录 cue，不立刻发。

### 4. 工具执行后的自然闭环

现状：

- pending confirmation 已稳定。
- 工具执行后当前回复多是固定话术，例如“已经按你点头的那一步处理好了”。

建议：

- 工具结果回到 LLM 做最终表达，要求云汐简短说明真实结果。
- 对失败结果做分层表达：权限问题、路径问题、页面不可读、GUI 未找到控件分别说清楚。
- 成功工具链自动沉淀成技能候选，而不是只写审计日志。

## P1：体验增强

### 5. Browser MCP 升级为 Playwright 后端

现状：

- Browser MCP 当前是轻量 URL/HTML 读取和链接打开。
- 对登录态页面、SPA、表单、多步网页操作能力有限。

建议：

- 保留当前轻量工具作为 fast path。
- 新增 Playwright Browser Session：打开、截图、DOM 读取、点击、输入、等待、下载。
- 浏览器提交、登录、上传、支付类操作必须确认。

### 6. GUI Agent 增加闭环验证和失败恢复

现状：

- GUI Agent 有观察、点击、输入、热键、宏。
- 还没有完整 observe-plan-act-verify-replan 循环。

建议：

- 把 `13_computer_use_agent` 的闭环能力按 yunxi3.0 风格重写：每步执行前后观察，失败时重规划。
- GUI Macro 增加成功率、最近失败原因和参数 schema。
- 对 GUI 操作增加视觉/控件双重断言。

### 7. 文件工具安全边界更细

现状：

- Filesystem MCP 有 allowed roots 和 pending confirmation。
- 默认 allowed roots 包含项目、用户目录、D 盘，个人环境可用但边界较宽。

建议：

- 默认只开放 `D:\yunxi3.0`、`D:\Trading`、用户显式配置目录。
- 对覆盖、移动、批量写入、跨目录复制增加二次摘要确认。
- 增加只读敏感路径屏蔽规则，例如 `.env`、密钥、浏览器配置、聊天数据库。

## P2：长期稳定性

### 8. 多日常驻观测

现状：

- 30 分钟浸泡已通过。
- 还没有 2 小时、过夜、多日重启恢复测试。

建议：

- 做 2 小时浸泡，再做过夜浸泡。
- 记录内存、线程数、MCP server 存活、飞书重连次数、LLM 错误率。
- 增加 `logs/runtime_metrics.jsonl`。

### 9. 日志与 WebUI 可观测性

现状：

- WebUI/Tray 定位正确，但状态还偏基础。

建议：

- WebUI 展示最近工具调用、pending confirmation、Feishu 状态、主动预算、最近情绪曲线。
- 日志按 runtime、feishu、mcp、memory、initiative 分文件。
- 对用户可见错误和内部错误建立统一 error code。

### 10. 自主学习从框架变成真实能力

现状：

- ExperienceBuffer、SkillLibrary、FailureReplay 已接入。
- 真实多日技能沉淀和复用还未充分验证。

建议：

- 对 MCP audit 定期聚类，生成“技能候选”而不是直接自动启用。
- WebUI 显示技能候选，由用户确认后启用。
- 技能执行失败自动降级到普通 LLM + 工具规划。

## 推荐下一阶段顺序

1. 长期记忆摘要与上下文压缩。
2. 工具执行后自然表达和失败分层。
3. 主动性策略自然度。
4. 2 小时浸泡和 runtime metrics。
5. Playwright Browser MCP。
6. GUI Agent 闭环验证。

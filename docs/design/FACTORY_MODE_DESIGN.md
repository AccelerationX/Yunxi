# 云汐 3.0 工厂模式（CodeFactory）设计文档（基于 MACP 重写版）

> **定位**：云汐作为"厂长"，基于 `03_multi_agent_collaboration_protocol_v2` 的核心研究成果，在 yunxi3.0 内重写一套多 Worker 并行调度引擎，调度多个 Claude Code Worker 完成软件开发项目。  
> **核心原则**：任务隔离为前提，Git Branch 为边界，DAG 为调度逻辑，厂长负责调度、验收与异常恢复。  
> **验证任务**：以"云汐桌宠"（`yunxi-pet`）作为工厂跑通后的首个完整项目。

---

## 一、研究成果借鉴与重写声明

### 1.1 借鉴 `03_multi_agent_collaboration_protocol_v2`

**借鉴内容**：
- `CollaborationFramework` + `Scheduler` 的 DAG 调度核心逻辑
- `Job` / `Task` 的状态机设计（PENDING → RUNNING → COMPLETED / FAILED / BLOCKED）
- `AgentRegistry` 的 Agent 生命周期管理（注册、发现、状态跟踪、idle/busy/error 状态机）
- `WebDashboard` 的 2 秒轮询监控机制
- `DomainTemplate` 的领域模板分离思想（业务逻辑与调度引擎解耦）
- `Workspace` 的状态持久化设计

**重写声明**：
- 不在 yunxi3.0 中 import `ResearchProjects/03_macp/` 的任何文件。
- 在 `yunxi3.0/factory/` 目录下重写所有核心类：`FactoryEngine`、`DAGScheduler`、`WorkerRegistry`、`FactoryDashboard`、`ProjectTemplate`、`Workspace`。
- 接口设计会根据"Claude Code CLI 子进程"这一特殊 Worker 形态重新设计，不再假设 Worker 是 LLM 直接对话的协程/线程。

### 1.2 借鉴 Anthropic "Effective Harnesses for Long-Running Agents"

**借鉴内容**：
- Initializer Agent 负责环境搭建（`init.sh`、`task.json`、`progress.txt`）
- Coding Agent 只做增量进展，每次 session 结束必须留下清晰 artifacts
- `feature_list.json` 作为验收标准清单
- 每个 session 开始时必须运行基础验证（`git log` → `read progress` → `run init.sh` → `e2e test`）

### 1.3 借鉴 auto-coding-agent-demo

**借鉴内容**：
- `CLAUDE.md` 作为标准化执行规范
- `task.json` 驱动的工作流
- `progress.txt` 作为进度日志
- `--dangerously-skip-permissions` 的自动批处理模式

---

## 二、工厂整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        表现层（Interfaces）                      │
│  ┌──────────────┐  ┌─────────────────────────────────────────┐  │
│  │ 系统托盘右键  │  │ WebUI "云汐的房间" → 工厂终端         │  │
│  │ 进入工厂模式  │  │  ├── 项目列表                           │  │
│  └──────────────┘  │  ├── 实时进度面板（来自 Dashboard）     │  │
│                    │  ├── Worker 状态监控                     │  │
│                    │  ├── 阻塞告警与人工干预入口              │  │
│                    │  └── [进入项目] 按钮                    │  │
│                    └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      厂长层（FactoryEngine）                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  DAGScheduler│  │ WorkerRegistry│  │   Workspace         │  │
│  │   DAG 调度器  │  │  Worker 注册表 │  │  项目状态持久化      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ProjectTemplate│  │MergeResolver │  │ ReportGenerator     │  │
│  │  项目类型模板  │  │  Merge 冲突解决│  │  进度汇报生成器      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Worker 层（Claude Code 进程）                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐ │
│  │ Worker-1   │  │ Worker-2   │  │ Worker-3   │  │ Worker-N  │ │
│  │ branch     │  │ branch     │  │ branch     │  │ branch    │ │
│  │ pet-ui     │  │ pet-state  │  │ pet-system │  │ pet-voice │ │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘ │
│                                                                 │
│  每个 Worker = 独立 OS 进程，运行 claude code CLI               │
│  每个 Worker 只处理一个任务（feature）                           │
│  通过 Git Branch 与主工作区隔离                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     项目工作区（Git Repository）                  │
│  ~/YunxiFactory/projects/yunxi-pet/                              │
│  ├── main branch          ← 稳定基线                            │
│  ├── worker/pet-ui        ← Worker-1 隔离分支                   │
│  ├── worker/pet-state     ← Worker-2 隔离分支                   │
│  ├── worker/pet-system    ← Worker-3 隔离分支                   │
│  ├── task.json            ← 任务清单（DAG + 验收标准）           │
│  ├── progress.txt         ← 人工/AI 可读进度日志                 │
│  ├── CLAUDE.md            ← Worker 执行规范                      │
│  ├── init.sh              ← 环境初始化脚本                       │
│  ├── INTERFACE_CONTRACT.md← 跨 Worker 接口契约                   │
│  └── src/                 ← 项目代码                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FactoryDashboard                             │
│  (Web 监控面板，2 秒轮询，借鉴 MACP WebDashboard 思想重写)        │
│  - 整体进度条                                                   │
│  - Worker 状态面板 (idle/busy/error)                            │
│  - 任务列表及依赖图可视化                                        │
│  - 告警面板 (阻塞/Merge冲突/超时)                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、核心组件设计（全部在 yunxi3.0/factory/ 内重写）

### 3.1 FactoryEngine（厂长核心）

```python
# factory/engine.py
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

@dataclass
class FactoryConfig:
    max_concurrent_workers: int = 3
    worker_timeout_seconds: int = 1800  # 30 分钟
    check_interval_seconds: int = 30    # 厂长轮询间隔
    project_dir: str = ""

class FactoryEngine:
    """
    云汐工厂的核心引擎。
    借鉴 MACP CollaborationFramework 的调度思想，但完全适配 Claude Code CLI 子进程模型。
    """
    def __init__(self, config: FactoryConfig, template: "ProjectTemplate"):
        self.config = config
        self.template = template
        self.scheduler = DAGScheduler()
        self.registry = WorkerRegistry()
        self.workspace = Workspace(config.project_dir)
        self.merge_resolver = MergeResolver(config.project_dir)
        self.reporter = ReportGenerator()
        self.dashboard = FactoryDashboard(self)
        self._running = False
    
    async def start_project(self, user_requirement: str):
        """启动一个新项目"""
        # 1. 初始化工作区
        await self.workspace.initialize(user_requirement, self.template)
        
        # 2. 加载任务到调度器
        tasks = await self.workspace.load_tasks()
        self.scheduler.load_tasks(tasks)
        
        # 3. 启动调度循环
        self._running = True
        asyncio.create_task(self._main_loop())
        
        # 4. 启动监控面板
        await self.dashboard.start()
    
    async def _main_loop(self):
        """厂长主调度循环"""
        while self._running:
            try:
                await self._schedule_ready_tasks()
                await self._check_completed_workers()
                await self._handle_zombies()
                await self._report_progress()
                await asyncio.sleep(self.config.check_interval_seconds)
            except Exception as e:
                await self._report_error(f"厂长调度循环异常: {e}")
    
    async def _schedule_ready_tasks(self):
        """为就绪任务分配 Worker"""
        ready = self.scheduler.get_ready_tasks()
        available_slots = self.config.max_concurrent_workers - self.registry.busy_count()
        
        for task in ready[:available_slots]:
            worker = await self._create_worker(task)
            self.registry.register(worker)
            await worker.start()
    
    async def _create_worker(self, task: "FactoryTask") -> "ClaudeWorker":
        """为任务创建一个 Claude Code Worker"""
        branch_name = f"worker/{task.task_id}"
        
        # 生成该任务的 CLAUDE.md 提示词
        prompt = self.template.generate_worker_prompt(
            task=task,
            project_dir=self.config.project_dir,
            context=self.workspace.get_project_context()
        )
        
        return ClaudeWorker(
            task_id=task.task_id,
            project_dir=self.config.project_dir,
            branch=branch_name,
            prompt=prompt,
            timeout=self.config.worker_timeout_seconds,
        )
    
    async def _check_completed_workers(self):
        """检查已完成的 Worker，处理结果并尝试 Merge"""
        completed = self.registry.get_completed()
        
        for worker in completed:
            result = await self.workspace.inspect_worker_result(worker)
            
            if result.success:
                merge_ok = await self.merge_resolver.merge(worker.branch)
                if merge_ok:
                    self.scheduler.mark_passed(worker.task_id)
                    await self.workspace.archive_worker_branch(worker.branch)
                else:
                    # Merge 冲突：启动 Conflict Worker 或标记阻塞
                    conflict_worker = await self._create_conflict_worker(worker)
                    self.registry.register(conflict_worker)
                    await conflict_worker.start()
            else:
                retry_count = self.scheduler.get_retry_count(worker.task_id)
                if retry_count >= 3:
                    self.scheduler.mark_blocked(worker.task_id, result.failure_reason)
                else:
                    self.scheduler.mark_failed(worker.task_id, result.failure_reason)
    
    async def _handle_zombies(self):
        """处理超时/僵死 Worker"""
        zombies = self.registry.find_zombies(
            timeout_threshold=self.config.worker_timeout_seconds
        )
        for worker in zombies:
            await worker.kill()
            self.scheduler.mark_failed(worker.task_id, "worker timeout/zombie")
    
    async def _report_progress(self):
        """向用户汇报进度"""
        summary = self.reporter.generate(self.scheduler, self.registry)
        # 通过 YunxiRuntime 的工厂模式汇报接口发送给用户
        await self._notify_user(summary)
    
    async def stop(self):
        self._running = False
        for worker in self.registry.get_all():
            await worker.kill()
        await self.dashboard.stop()
```

### 3.2 DAGScheduler（DAG 调度器）

```python
# factory/scheduler.py
from typing import List, Dict, Optional
from enum import Enum

class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"

@dataclass
class FactoryTask:
    task_id: str
    title: str
    description: str
    dependencies: List[str]
    passes: bool = False
    state: TaskState = TaskState.PENDING
    assigned_worker: Optional[str] = None
    retry_count: int = 0
    failure_reason: Optional[str] = None
    verification: Dict[str, Any] = field(default_factory=dict)

class DAGScheduler:
    """
    借鉴 MACP Scheduler 的 DAG 调度思想重写。
    负责解析任务依赖、维护状态机、找出就绪任务。
    """
    def __init__(self):
        self.tasks: Dict[str, FactoryTask] = {}
    
    def load_tasks(self, tasks: List[FactoryTask]):
        self.tasks = {t.task_id: t for t in tasks}
    
    def get_ready_tasks(self) -> List[FactoryTask]:
        """返回依赖已完成、状态为 PENDING 的任务"""
        ready = []
        for task in self.tasks.values():
            if task.state != TaskState.PENDING:
                continue
            if task.assigned_worker is not None:
                continue
            deps_satisfied = all(
                self.tasks[d].state == TaskState.COMPLETED
                for d in task.dependencies
            )
            if deps_satisfied:
                ready.append(task)
        
        # 排序：依赖深度浅的优先
        ready.sort(key=lambda t: self._dependency_depth(t.task_id))
        return ready
    
    def _dependency_depth(self, task_id: str, memo=None) -> int:
        if memo is None:
            memo = {}
        if task_id in memo:
            return memo[task_id]
        task = self.tasks.get(task_id)
        if not task or not task.dependencies:
            memo[task_id] = 0
            return 0
        depth = 1 + max(self._dependency_depth(d, memo) for d in task.dependencies)
        memo[task_id] = depth
        return depth
    
    def mark_running(self, task_id: str, worker_id: str):
        self.tasks[task_id].state = TaskState.RUNNING
        self.tasks[task_id].assigned_worker = worker_id
    
    def mark_passed(self, task_id: str):
        self.tasks[task_id].state = TaskState.COMPLETED
        self.tasks[task_id].passes = True
        self.tasks[task_id].assigned_worker = None
    
    def mark_failed(self, task_id: str, reason: str):
        self.tasks[task_id].state = TaskState.PENDING
        self.tasks[task_id].assigned_worker = None
        self.tasks[task_id].retry_count += 1
        self.tasks[task_id].failure_reason = reason
    
    def mark_blocked(self, task_id: str, reason: str):
        self.tasks[task_id].state = TaskState.BLOCKED
        self.tasks[task_id].assigned_worker = None
        self.tasks[task_id].failure_reason = reason
    
    def get_retry_count(self, task_id: str) -> int:
        return self.tasks[task_id].retry_count
    
    def is_complete(self) -> bool:
        return all(t.state == TaskState.COMPLETED for t in self.tasks.values())
    
    def get_blocked_tasks(self) -> List[FactoryTask]:
        return [t for t in self.tasks.values() if t.state == TaskState.BLOCKED]
    
    def get_progress(self) -> Dict[str, Any]:
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks.values() if t.state == TaskState.COMPLETED)
        running = sum(1 for t in self.tasks.values() if t.state == TaskState.RUNNING)
        blocked = sum(1 for t in self.tasks.values() if t.state == TaskState.BLOCKED)
        pending = total - completed - running - blocked
        return {
            "total": total,
            "completed": completed,
            "running": running,
            "blocked": blocked,
            "pending": pending,
            "percent": int(completed / total * 100) if total > 0 else 0,
        }
```

### 3.3 WorkerRegistry（Worker 注册表）

```python
# factory/registry.py
from typing import List, Dict
from enum import Enum

class WorkerState(Enum):
    IDLE = "idle"
    BUSY = "busy"
    COMPLETED = "completed"
    ERROR = "error"

class WorkerRegistry:
    """
    借鉴 MACP AgentRegistry 的注册与状态跟踪思想重写。
    """
    def __init__(self):
        self._workers: Dict[str, "ClaudeWorker"] = {}
        self._states: Dict[str, WorkerState] = {}
    
    def register(self, worker: "ClaudeWorker"):
        self._workers[worker.worker_id] = worker
        self._states[worker.worker_id] = WorkerState.BUSY
    
    def mark_completed(self, worker_id: str):
        self._states[worker_id] = WorkerState.COMPLETED
    
    def mark_error(self, worker_id: str):
        self._states[worker_id] = WorkerState.ERROR
    
    def busy_count(self) -> int:
        return sum(1 for s in self._states.values() if s == WorkerState.BUSY)
    
    def get_completed(self) -> List["ClaudeWorker"]:
        return [self._workers[w] for w, s in self._states.items() if s == WorkerState.COMPLETED]
    
    def find_zombies(self, timeout_threshold: int) -> List["ClaudeWorker"]:
        zombies = []
        for w in self._workers.values():
            if self._states[w.worker_id] == WorkerState.BUSY:
                if w.is_zombie(timeout_threshold):
                    zombies.append(w)
        return zombies
    
    def get_all(self) -> List["ClaudeWorker"]:
        return list(self._workers.values())
```

### 3.4 ClaudeWorker（Claude Code CLI 子进程包装器）

```python
# factory/worker.py
import asyncio
import os
import subprocess
from typing import Optional
from datetime import datetime

class ClaudeWorker:
    """
    包装 Claude Code CLI 为工厂 Worker。
    """
    def __init__(self, task_id: str, project_dir: str, branch: str, prompt: str, timeout: int = 1800):
        self.task_id = task_id
        self.project_dir = project_dir
        self.branch = branch
        self.prompt = prompt
        self.timeout = timeout
        self.worker_id = f"{task_id}_{datetime.now().strftime('%H%M%S')}"
        self.process: Optional[asyncio.subprocess.Process] = None
        self.start_time: Optional[datetime] = None
    
    async def start(self):
        """创建 branch 并启动 Claude Code CLI"""
        await self._ensure_branch()
        
        # 将 prompt 写入临时文件，避免命令行过长
        prompt_path = os.path.join(self.project_dir, f".yunxi_prompt_{self.task_id}.md")
        with open(prompt_path, 'w', encoding='utf-8') as f:
            f.write(self.prompt)
        
        cmd = [
            "claude", "code",
            "--cwd", self.project_dir,
            "--prompt-file", prompt_path,
            "--dangerously-skip-permissions",
        ]
        
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.start_time = datetime.now()
    
    async def _ensure_branch(self):
        cmds = [
            ["git", "-C", self.project_dir, "checkout", "main"],
            ["git", "-C", self.project_dir, "pull", "--ff-only"],
            ["git", "-C", self.project_dir, "checkout", "-B", self.branch],
        ]
        for cmd in cmds:
            proc = await asyncio.create_subprocess_exec(*cmd)
            await proc.wait()
    
    async def wait(self) -> "WorkerResult":
        try:
            stdout, stderr = await asyncio.wait_for(
                self.process.communicate(),
                timeout=self.timeout
            )
            returncode = self.process.returncode
            success = (returncode == 0)
        except asyncio.TimeoutError:
            await self.kill()
            success = False
            stdout = b""
            stderr = b"Worker timed out"
        
        return WorkerResult(
            worker_id=self.worker_id,
            task_id=self.task_id,
            branch=self.branch,
            success=success,
            stdout=stdout.decode('utf-8', errors='replace'),
            stderr=stderr.decode('utf-8', errors='replace') if isinstance(stderr, bytes) else stderr,
        )
    
    async def kill(self):
        if self.process and self.process.returncode is None:
            self.process.kill()
            await self.process.wait()
    
    def is_zombie(self, timeout_threshold: int) -> bool:
        if not self.start_time:
            return False
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return elapsed > timeout_threshold

@dataclass
class WorkerResult:
    worker_id: str
    task_id: str
    branch: str
    success: bool
    stdout: str
    stderr: str
```

### 3.5 Workspace（项目工作区管理）

```python
# factory/workspace.py
import json
import os
import subprocess
from typing import List, Dict, Any

class Workspace:
    """
    管理工厂项目的文件、Git 状态、任务清单和进度日志。
    借鉴 MACP Workspace 的持久化思想重写。
    """
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
    
    async def initialize(self, user_requirement: str, template: "ProjectTemplate"):
        """初始化一个新的工厂项目"""
        os.makedirs(self.project_dir, exist_ok=True)
        
        # 1. 初始化 git
        if not os.path.exists(os.path.join(self.project_dir, ".git")):
            proc = await asyncio.create_subprocess_exec(
                "git", "init", cwd=self.project_dir
            )
            await proc.wait()
        
        # 2. 生成项目文件
        template.setup_project(self.project_dir, user_requirement)
        
        # 3. 初始 commit
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", self.project_dir, "add", "."
        )
        await proc.wait()
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", self.project_dir, "commit", "-m", "[init] 项目初始化"
        )
        await proc.wait()
    
    async def load_tasks(self) -> List[FactoryTask]:
        task_path = os.path.join(self.project_dir, "task.json")
        with open(task_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [
            FactoryTask(
                task_id=t["id"],
                title=t["title"],
                description=t["description"],
                dependencies=t.get("dependencies", []),
                passes=t.get("passes", False),
                verification=t.get("verification", {}),
            )
            for t in data.get("tasks", [])
        ]
    
    async def inspect_worker_result(self, worker: ClaudeWorker) -> "WorkerInspectionResult":
        """检查 Worker 分支的执行结果"""
        result = WorkerInspectionResult(success=False)
        
        # 1. 检查是否有新 commit
        try:
            log = subprocess.check_output(
                ["git", "-C", self.project_dir, "log", f"main..{worker.branch}", "--oneline"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            result.has_commit = bool(log.strip())
            result.commit_message = log.strip().split("\n")[0] if log.strip() else ""
        except subprocess.CalledProcessError:
            result.has_commit = False
        
        # 2. 检查 task.json
        task_path = os.path.join(self.project_dir, "task.json")
        with open(task_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for t in data.get("tasks", []):
            if t["id"] == worker.task_id:
                result.task_passed = t.get("passes", False)
                break
        
        # 3. 判定成功与否
        if result.task_passed and result.has_commit:
            result.success = True
        elif not result.has_commit:
            result.failure_reason = "Worker 没有提交任何 commit"
        elif not result.task_passed:
            result.failure_reason = "Worker 已提交但未通过 task 验收"
        
        return result
    
    async def archive_worker_branch(self, branch: str):
        """可选：合并成功后删除 worker branch"""
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", self.project_dir, "branch", "-D", branch
        )
        await proc.wait()
    
    def get_project_context(self) -> Dict[str, Any]:
        """获取当前项目的上下文信息，用于生成 Worker Prompt"""
        progress_path = os.path.join(self.project_dir, "progress.txt")
        progress = ""
        if os.path.exists(progress_path):
            with open(progress_path, 'r', encoding='utf-8') as f:
                progress = f.read()[-2000:]  # 最后 2000 字符
        
        return {
            "project_dir": self.project_dir,
            "recent_progress": progress,
        }

@dataclass
class WorkerInspectionResult:
    success: bool = False
    has_commit: bool = False
    commit_message: str = ""
    task_passed: bool = False
    failure_reason: Optional[str] = None
```

### 3.6 MergeResolver（Merge 冲突处理）

```python
# factory/merge_resolver.py
import subprocess
import asyncio

class MergeResolver:
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
    
    async def merge(self, branch: str) -> bool:
        """尝试将 worker branch merge 到 main"""
        try:
            # checkout main
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", self.project_dir, "checkout", "main"
            )
            await proc.wait()
            
            # merge
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", self.project_dir, "merge", branch, "--no-edit"
            )
            ret = await proc.wait()
            
            if ret == 0:
                return True
            
            # merge 失败，abort
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", self.project_dir, "merge", "--abort"
            )
            await proc.wait()
            return False
            
        except Exception:
            return False
```

### 3.7 FactoryDashboard（工厂监控面板）

```python
# factory/dashboard.py
from aiohttp import web
import json

class FactoryDashboard:
    """
    借鉴 MACP WebDashboard 的轮询监控思想重写。
    提供工厂实时状态的可视化面板。
    """
    def __init__(self, engine: FactoryEngine, port: int = 8089):
        self.engine = engine
        self.port = port
        self.app = web.Application()
        self.app.router.add_get('/api/status', self.handle_status)
        self.app.router.add_get('/', self.handle_index)
        self.runner = None
    
    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, 'localhost', self.port)
        await site.start()
    
    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
    
    async def handle_status(self, request):
        data = {
            "progress": self.engine.scheduler.get_progress(),
            "workers": [
                {
                    "id": w.worker_id,
                    "task_id": w.task_id,
                    "state": self.engine.registry._states.get(w.worker_id, "unknown").value,
                }
                for w in self.engine.registry.get_all()
            ],
            "blocked": [
                {"id": t.task_id, "reason": t.failure_reason}
                for t in self.engine.scheduler.get_blocked_tasks()
            ],
        }
        return web.json_response(data)
    
    async def handle_index(self, request):
        html = """<!DOCTYPE html>
<html>
<head><title>云汐工厂监控面板</title></head>
<body>
<h1>🏭 云汐工厂 - 实时监控</h1>
<div id="progress"></div>
<div id="workers"></div>
<div id="blocked"></div>
<script>
async function refresh() {
  const res = await fetch('/api/status');
  const data = await res.json();
  document.getElementById('progress').innerHTML = 
    `<h2>进度: ${data.progress.percent}% (${data.progress.completed}/${data.progress.total})</h2>`;
  document.getElementById('workers').innerHTML = 
    '<h2>Workers</h2>' + data.workers.map(w => `<p>${w.id}: ${w.task_id} [${w.state}]</p>`).join('');
  document.getElementById('blocked').innerHTML = 
    '<h2>阻塞</h2>' + data.blocked.map(b => `<p>${b.id}: ${b.reason}</p>`).join('');
}
setInterval(refresh, 2000);
refresh();
</script>
</body>
</html>"""
        return web.Response(text=html, content_type='text/html')
```

---

## 四、ProjectTemplate（项目类型模板）

```python
# factory/templates/base.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class ProjectTemplate(ABC):
    """
    借鉴 MACP DomainTemplate 的模板分离思想重写。
    每个项目类型对应一个 Template 实现。
    """
    @abstractmethod
    def setup_project(self, project_dir: str, user_requirement: str):
        """初始化项目目录结构、生成 task.json、CLAUDE.md、init.sh"""
        pass
    
    @abstractmethod
    def generate_worker_prompt(self, task: FactoryTask, project_dir: str, context: Dict[str, Any]) -> str:
        """为特定任务生成 Worker 的 CLAUDE.md 提示词"""
        pass
    
    @abstractmethod
    def get_verification_commands(self, task: FactoryTask) -> Dict[str, str]:
        """返回该任务类型对应的验证命令"""
        pass
```

### 4.1 PythonDesktopTemplate（桌宠项目模板）

```python
# factory/templates/python_desktop.py
import os
import json

class PythonDesktopTemplate(ProjectTemplate):
    def setup_project(self, project_dir: str, user_requirement: str):
        # 1. task.json
        tasks = self._decompose_tasks(user_requirement)
        with open(os.path.join(project_dir, "task.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "project_type": "python-desktop",
                "project_name": "yunxi-pet",
                "tasks": tasks,
            }, f, ensure_ascii=False, indent=2)
        
        # 2. CLAUDE.md
        claude_md = self._generate_base_claude_md()
        with open(os.path.join(project_dir, "CLAUDE.md"), 'w', encoding='utf-8') as f:
            f.write(claude_md)
        
        # 3. init.sh
        init_sh = "#!/bin/bash\npip install -r requirements.txt\npytest tests/ -q || true\n"
        with open(os.path.join(project_dir, "init.sh"), 'w', encoding='utf-8') as f:
            f.write(init_sh)
        
        # 4. INTERFACE_CONTRACT.md
        contract = self._generate_interface_contract()
        with open(os.path.join(project_dir, "INTERFACE_CONTRACT.md"), 'w', encoding='utf-8') as f:
            f.write(contract)
        
        # 5. requirements.txt
        reqs = "pyqt6\nuiautomation\npytest\nPillow\n"
        with open(os.path.join(project_dir, "requirements.txt"), 'w', encoding='utf-8') as f:
            f.write(reqs)
    
    def _decompose_tasks(self, user_requirement: str) -> List[Dict[str, Any]]:
        # 桌宠项目的固定任务分解
        return [
            {
                "id": "pet-window",
                "title": "实现透明悬浮窗",
                "description": "PyQt6 无边框透明窗体，支持拖动",
                "dependencies": [],
                "passes": False,
                "verification": {"build_cmd": "python -m yunxi_pet --test-window", "e2e_type": "screenshot"},
            },
            {
                "id": "pet-render",
                "title": "集成 Live2D / 序列帧渲染",
                "description": "在悬浮窗中渲染角色，实现 idle 呼吸动画",
                "dependencies": ["pet-window"],
                "passes": False,
                "verification": {"build_cmd": "python -m yunxi_pet --test-render", "e2e_type": "screenshot"},
            },
            {
                "id": "pet-state",
                "title": "实现行为状态机",
                "description": "idle, speak, clicked, sleep 四态及切换",
                "dependencies": ["pet-render"],
                "passes": False,
                "verification": {"build_cmd": "pytest tests/test_state.py -q", "e2e_type": "cli_output"},
            },
            {
                "id": "pet-system",
                "title": "系统集成层",
                "description": "托盘图标、窗口置顶、鼠标穿透",
                "dependencies": ["pet-window"],
                "passes": False,
                "verification": {"build_cmd": "python -m yunxi_pet --test-system", "e2e_type": "screenshot"},
            },
            {
                "id": "pet-voice",
                "title": "语音联动与口型同步",
                "description": "TTS 触发 speak 状态，口型/表情同步",
                "dependencies": ["pet-state", "pet-system"],
                "passes": False,
                "verification": {"build_cmd": "python -m yunxi_pet --test-voice", "e2e_type": "screenshot"},
            },
            {
                "id": "pet-heartlake",
                "title": "情感驱动表情切换",
                "description": "根据 HeartLake 情绪切换表情和动作",
                "dependencies": ["pet-state", "pet-system"],
                "passes": False,
                "verification": {"build_cmd": "pytest tests/test_heartlake_bridge.py -q", "e2e_type": "cli_output"},
            },
        ]
    
    def generate_worker_prompt(self, task, project_dir, context) -> str:
        return f"""# Claude Code 工作规范

## 当前任务
- 任务 ID：{task.task_id}
- 任务名称：{task.title}
- 任务描述：{task.description}

## 工作流
1. 阅读 `CLAUDE.md`、`task.json`、`progress.txt`
2. 运行 `git log --oneline -10` 了解最近变更
3. 阅读 `INTERFACE_CONTRACT.md` 了解接口契约
4. 如有 `init.sh`，先运行：`bash init.sh`
5. 实现当前任务（只实现这一个，不要改其他任务）
6. 运行验证：`{task.verification.get('build_cmd', 'echo 无验证命令')}`
7. 在 `task.json` 中将此任务标记为 `passes: true`
8. 追加 `progress.txt`
9. `git commit -am "[{task.task_id}] {task.title}"`

## 接口契约约束
- 不要修改 `INTERFACE_CONTRACT.md` 中已由其他 Worker 实现的接口签名
- 如需新增公共接口，请在 `INTERFACE_CONTRACT.md` 中声明
"""
    
    def get_verification_commands(self, task: FactoryTask) -> Dict[str, str]:
        return task.verification
    
    def _generate_base_claude_md(self) -> str:
        return """# 云汐工厂 - Python 桌面项目规范

你是一个专业的 Python 桌面应用开发工程师。
每次 session 只完成一个任务，保持代码整洁，提交前删除调试代码。
"""
    
    def _generate_interface_contract(self) -> str:
        return """# 接口契约

## PetWindow
- `show()`: 显示窗口
- `move(x, y)`: 移动窗口
- `set_transparent(enable: bool)`: 设置透明

## PetRenderer
- `play_motion(name: str)`: 播放动作
- `play_expression(name: str)`: 播放表情

## PetStateMachine
- `transition_to(state: str)`: 切换状态
- `on_click()`: 点击响应
"""
```

---

## 五、厂长人格与汇报生成器

```python
# factory/reporter.py
class ReportGenerator:
    def generate(self, scheduler: DAGScheduler, registry: WorkerRegistry) -> str:
        progress = scheduler.get_progress()
        workers = registry.get_all()
        blocked = scheduler.get_blocked_tasks()
        
        lines = [f"🏭 云汐工厂进度汇报"]
        lines.append(f"进度：{progress['percent']}% ({progress['completed']}/{progress['total']})")
        
        if progress['running'] > 0:
            lines.append(f"🔄 进行中：{progress['running']} 个任务")
        
        if progress['pending'] > 0:
            lines.append(f"⏳ 等待中：{progress['pending']} 个任务")
        
        if blocked:
            lines.append("🚨 阻塞任务：")
            for b in blocked:
                lines.append(f"  - {b.task_id}: {b.failure_reason}")
        
        if progress['completed'] == progress['total']:
            lines.append("🎉 所有任务已完成！")
        
        return "\n".join(lines)
```

---

## 六、异常恢复策略

| 异常场景 | 恢复策略 |
|---------|---------|
| Worker 超时 | `kill` → `mark_failed` → 若重试 < 3 次则重新调度 |
| Worker 无 commit | `mark_failed` → 重新调度 |
| task.json 未更新但 has_commit=True | 厂长读取 diff，若看起来合理则手动更新 task.json 再 merge |
| Merge conflict（简单） | 厂长 LLM 自动解决（< 3 个文件冲突） |
| Merge conflict（复杂） | 启动 Conflict Worker 专门解决 |
| 同一任务连续失败 3 次 | `mark_blocked`，暂停该任务及其下游，通知用户 |
| 项目级构建失败（merge 后） | `git revert` 到上一个稳定 commit，标记失败的 branch 为 BLOCKED |
| init.sh 失败 | 标记项目 BLOCKED，通知用户检查环境 |

---

## 七、实施路径

### Phase A：单 Worker 跑通（验证核心流程）
1. 实现 `FactoryEngine` + `DAGScheduler` + `ClaudeWorker` + `Workspace`
2. 选择 `hello-world-python-cli` 项目模板
3. 单 Worker 按 `CLAUDE.md` 跑通完整 loop

### Phase B：多 Worker 并行调度（验证 DAG）
1. 实现 `WorkerRegistry`、`MergeResolver`、`FactoryDashboard`
2. 用桌宠前 3 个无依赖任务测试并行
3. 验证两个 Worker 同时运行、merge、进度更新

### Phase C：完整桌宠项目（验证端到端）
1. 实现 `PythonDesktopTemplate`
2. 生成完整的 `yunxi-pet` task.json
3. 启动工厂自动调度 6 个任务
4. 人工验收最终桌宠功能

### Phase D：专业化 Worker（远期）
1. Conflict Worker
2. Review Worker（自动 lint + 风格检查）
3. Test Worker（专门做 E2E 验证）

---

## 八、验收标准

1. `FactoryEngine.start_project()` 能成功初始化 git 仓库、生成 `task.json`、`CLAUDE.md`。
2. `DAGScheduler` 能正确解析 6 个桌宠任务的依赖关系，按 DAG 顺序调度。
3. 两个无依赖任务能同时启动 Worker，各自在独立 branch 上工作。
4. Worker 完成后，`MergeResolver` 能成功 merge 到 `main`。
5. 监控面板 `FactoryDashboard` 能实时显示进度、Worker 状态、阻塞告警。
6. 桌宠项目的 6 个任务全部完成后，`main` branch 包含可运行的桌宠代码。
7. 启动桌宠后，能通过人工验收：显示窗口、播放 idle 动画、响应点击、与系统托盘集成。

---

*文档创建时间：2026-04-14*  
*最后更新时间：2026-04-14*  
*版本：v2.0*

"""云汐在场系统。"""

import asyncio
import logging
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

if TYPE_CHECKING:
    from domains.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

ProactiveCallback = Callable[[str], Awaitable[None] | None]
TickCallback = Callable[[], Awaitable[Optional[str]]]

# 技能学习周期：每 10 个主动 tick 执行一次（约 5 分钟）
SKILL_LEARNING_INTERVAL_TICKS = 10


class YunxiPresence:
    """运行后台 tick 循环，并把主动消息交给上层发送。"""

    def __init__(
        self,
        proactive_tick: TickCallback,
        on_proactive_message: ProactiveCallback,
        tick_interval: float = 30.0,
        memory_manager: Optional["MemoryManager"] = None,
    ) -> None:
        self.proactive_tick = proactive_tick
        self.on_proactive_message = on_proactive_message
        self.tick_interval = tick_interval
        self.memory = memory_manager
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._tick_count: int = 0

    def start(self) -> None:
        """启动后台在场循环。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        """停止后台在场循环。"""
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def run_once(self) -> Optional[str]:
        """执行一次主动性检查，便于 daemon 与测试直接调用。"""
        message = await self.proactive_tick()
        if message:
            callback_result = self.on_proactive_message(message)
            if asyncio.iscoroutine(callback_result):
                await callback_result
        return message

    async def _tick_loop(self) -> None:
        while self._running:
            try:
                await self.run_once()
                self._tick_count += 1
                await self._maybe_run_skill_learning()
            except Exception as exc:
                logger.exception("Presence tick failed: %s", exc)
            await asyncio.sleep(self.tick_interval)

    async def _maybe_run_skill_learning(self) -> None:
        """按固定周期执行技能学习，积累经验池中的模式。"""
        if self.memory is None:
            return
        if self._tick_count % SKILL_LEARNING_INTERVAL_TICKS != 0:
            return
        try:
            await self.memory.run_skill_learning_cycle()
            logger.debug("Skill learning cycle completed")
        except Exception as exc:
            logger.warning("Skill learning cycle failed: %s", exc)

"""Shared definitions and an asyncio runtime for the private agent workers."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
from core.brain import CloudflareWorkersAI
from connectors.cakto_connector import CaktoConnector
from core.storage import mock_mode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    system_instruction: str


@dataclass
class AgentJob:
    prompt: str
    result: asyncio.Future[str]
    max_tokens: int = 768
    system_instruction: str | None = None


StatusCallback = Callable[[str, str, str], Awaitable[None]]


class AgentRuntime:
    """Runs one bounded asyncio queue consumer for each configured agent."""

    def __init__(
        self,
        definitions: tuple[AgentDefinition, ...],
        brain: CloudflareWorkersAI,
        on_status: StatusCallback,
        queue_size: int = 8,
    ) -> None:
        self.definitions = {agent.id: agent for agent in definitions}
        self._brain = brain
        self._on_status = on_status
        self._queues = {
            agent_id: asyncio.Queue[AgentJob](maxsize=queue_size)
            for agent_id in self.definitions
        }
        self._tasks: list[asyncio.Task[None]] = []
        self._resumed = asyncio.Event()
        self._resumed.set()
        self._busy: set[str] = set()

    async def start(self) -> None:
        if self._tasks:
            raise RuntimeError("Agent runtime has already been started.")
        self._tasks = [
            asyncio.create_task(self._run(agent_id), name=f"neris-{agent_id}")
            for agent_id in self.definitions
        ]
        for agent_id in self.definitions:
            await self._on_status(agent_id, "idle", "Worker online; awaiting a task.")

    async def stop(self) -> None:
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for queue in self._queues.values():
            while not queue.empty():
                job = queue.get_nowait()
                if not job.result.done():
                    job.result.cancel()
                queue.task_done()
        for agent_id in self.definitions:
            await self._on_status(agent_id, "offline", "Worker stopped.")

    async def pause(self) -> None:
        self._resumed.clear()
        for agent_id in self.definitions:
            if agent_id not in self._busy:
                await self._on_status(agent_id, "paused", "New tasks are paused.")

    async def resume(self) -> None:
        self._resumed.set()
        for agent_id in self.definitions:
            if agent_id not in self._busy:
                await self._on_status(agent_id, "idle", "Task queue resumed.")

    async def submit(
        self,
        agent_id: str,
        prompt: str,
        timeout: float = 120,
        *,
        max_tokens: int = 768,
        system_instruction: str | None = None,
    ) -> str:
        if agent_id not in self.definitions:
            raise KeyError(f"Unknown agent: {agent_id}")
        if not self._tasks:
            raise RuntimeError("Agent runtime is not running.")
        if not 1 <= max_tokens <= 4096:
            raise ValueError("max_tokens must be between 1 and 4096.")

        result = asyncio.get_running_loop().create_future()
        job = AgentJob(
            prompt=prompt,
            result=result,
            max_tokens=max_tokens,
            system_instruction=system_instruction,
        )
        try:
            self._queues[agent_id].put_nowait(job)
        except asyncio.QueueFull as exc:
            raise RuntimeError(f"Agent queue is full: {agent_id}") from exc
        try:
            return await asyncio.wait_for(result, timeout=timeout)
        except asyncio.TimeoutError:
            result.cancel()
            raise

    async def _run(self, agent_id: str) -> None:
        definition = self.definitions[agent_id]
        queue = self._queues[agent_id]
        while True:
            job = await queue.get()
            failed = False
            try:
                await self._resumed.wait()
                self._busy.add(agent_id)
                await self._on_status(
                    agent_id, "running", "Processing an administrator task."
                )
                prompt = job.prompt
                if agent_id == "agent-10" and mock_mode():
                    metrics = await CaktoConnector().sales_metrics()
                    prompt += (
                        "\n\nMetricas agregadas de vendas para analise (simulacao; "
                        "nao representam dados reais):\n"
                        + json.dumps(metrics, ensure_ascii=False)
                    )
                answer = await self._brain.complete(
                    [{"role": "user", "content": prompt}],
                    system_instruction=job.system_instruction or definition.system_instruction,
                    max_tokens=job.max_tokens,
                )
            except asyncio.CancelledError:
                if not job.result.done():
                    job.result.cancel()
                raise
            except (RuntimeError, ValueError, httpx.HTTPError) as exc:
                failed = True
                logger.error(
                    "Agent task failed: id=%s error_type=%s",
                    agent_id,
                    type(exc).__name__,
                )
                if not job.result.done():
                    job.result.set_exception(exc)
                await self._on_status(
                    agent_id, "error", "Task failed; inspect service configuration."
                )
            else:
                if not job.result.done():
                    job.result.set_result(answer)
            finally:
                self._busy.discard(agent_id)
                await self._on_status(
                    agent_id,
                    "error"
                    if failed
                    else ("paused" if not self._resumed.is_set() else "idle"),
                    "Task failed; inspect service configuration."
                    if failed
                    else (
                        "Task completed; queue paused."
                        if not self._resumed.is_set()
                        else "Task completed; awaiting the next task."
                    ),
                )
                queue.task_done()

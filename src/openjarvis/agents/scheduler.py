"""AgentScheduler — cron/interval tick scheduling for managed agents."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from openjarvis.core.events import EventType

if TYPE_CHECKING:
    from openjarvis.agents.executor import AgentExecutor
    from openjarvis.agents.manager import AgentManager

logger = logging.getLogger(__name__)


def _next_cron_fire(
    cron_expr: str,
    now: float | None = None,
    timezone_name: str | None = None,
) -> float:
    """Calculate the next fire time for a cron expression.

    ``timezone_name`` is an optional IANA timezone. Without one, preserve the
    historical host-local interpretation. Missing cron support is fatal: an
    hourly approximation would silently change the schedule's meaning.
    """
    try:
        from croniter import croniter
    except ImportError as exc:
        raise RuntimeError(
            "croniter is required for cron schedules; reinstall OpenJarvis"
        ) from exc

    base = time.time() if now is None else now
    tz = ZoneInfo(timezone_name) if timezone_name else None
    dt = (
        datetime.fromtimestamp(base, tz=tz)
        if tz is not None
        else datetime.fromtimestamp(base).astimezone()
    )
    cron = croniter(cron_expr, dt)
    next_dt = cron.get_next(datetime)
    return next_dt.timestamp()


class AgentScheduler:
    """Schedules managed agent ticks based on cron/interval configs.

    Runs a background thread that checks for due agents and dispatches
    ticks to the executor.
    """

    def __init__(
        self,
        manager: AgentManager,
        executor: AgentExecutor | Any,
        tick_interval: float = 1.0,
        event_bus: Any = None,
    ) -> None:
        self._manager = manager
        self._executor = executor
        self._tick_interval = tick_interval
        self._bus = event_bus
        # agent_id -> {schedule_type, schedule_value, next_fire}
        self._agents: dict[str, dict] = {}
        self._tick_counts: dict[str, int] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._worker_lock = threading.Lock()
        self._workers: dict[str, threading.Thread] = {}
        self._stall_notified: set[str] = set()

    @property
    def registered_agents(self) -> set[str]:
        with self._lock:
            return set(self._agents.keys())

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def register_agent(self, agent_id: str) -> None:
        """Register an agent for scheduling."""
        agent = self._manager.get_agent(agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id} not found")

        config = agent.get("config", {})
        schedule_type = config.get("schedule_type", "manual")
        schedule_value = config.get("schedule_value", 0)
        timezone_name = config.get("timezone") or None

        now = time.time()
        if schedule_type == "cron":
            next_fire = _next_cron_fire(str(schedule_value), now, timezone_name)
        elif schedule_type == "interval":
            next_fire = now + float(schedule_value)
        else:
            next_fire = float("inf")  # Manual: never auto-fires

        with self._lock:
            self._agents[agent_id] = {
                "schedule_type": schedule_type,
                "schedule_value": schedule_value,
                "timezone": timezone_name,
                "next_fire": next_fire,
            }

        logger.info(
            "Registered agent %s (%s), next fire: %s",
            agent_id,
            schedule_type,
            next_fire,
        )

    def deregister_agent(self, agent_id: str) -> None:
        """Remove an agent from scheduling."""
        with self._lock:
            self._agents.pop(agent_id, None)
        logger.info("Deregistered agent %s", agent_id)

    def start(self) -> None:
        """Start the scheduler background thread."""
        if self.is_running:
            return
        if self._bus:
            self._bus.subscribe(EventType.AGENT_TICK_END, self._on_tick_event)
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="agent-scheduler"
        )
        self._thread.start()
        logger.info("Agent scheduler started")

    def request_stop(self) -> None:
        """Prevent new scheduled ticks without waiting for the worker."""

        self._stop_event.set()
        if self._bus:
            self._bus.unsubscribe(EventType.AGENT_TICK_END, self._on_tick_event)

    def wait_stopped(self, timeout: float = 10.0) -> bool:
        """Wait for scheduler and active tick workers to stop."""

        deadline = time.monotonic() + timeout
        thread = self._thread
        if thread is not None:
            if thread is threading.current_thread():
                return False
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
            if thread.is_alive():
                logger.warning("Agent scheduler did not stop within %.1fs", timeout)
                return False

        with self._worker_lock:
            workers = list(self._workers.values())
        for worker in workers:
            if worker is threading.current_thread():
                return False
            worker.join(timeout=max(0.0, deadline - time.monotonic()))
            if worker.is_alive():
                logger.warning(
                    "Agent scheduler worker did not stop within %.1fs",
                    timeout,
                )
                return False

        if self._thread is thread:
            self._thread = None
        return True

    def stop(self, timeout: float = 10.0) -> None:
        """Stop dispatching and wait for the scheduler worker."""

        self.request_stop()
        if self.wait_stopped(timeout=timeout):
            logger.info("Agent scheduler stopped")

    def _loop(self) -> None:
        """Main scheduler loop."""
        last_reconcile = 0.0
        reconcile_interval = 30
        while not self._stop_event.is_set():
            try:
                self._check_due_agents()
                now = time.time()
                if now - last_reconcile >= reconcile_interval:
                    self._reconcile()
                    last_reconcile = now
            except Exception:
                logger.exception("Scheduler tick error")
            self._stop_event.wait(self._tick_interval)

    def _worker_alive(self, agent_id: str) -> bool:
        with self._worker_lock:
            worker = self._workers.get(agent_id)
        return worker is not None and worker.is_alive()

    def wait_for_workers(self, timeout: float = 10.0) -> bool:
        """Wait for currently dispatched ticks without stopping the scheduler."""
        deadline = time.monotonic() + timeout
        while True:
            with self._worker_lock:
                workers = [
                    worker
                    for worker in self._workers.values()
                    if worker.is_alive()
                ]
            if not workers:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            workers[0].join(timeout=remaining)

    def _run_tick_worker(self, agent_id: str) -> None:
        try:
            self._executor.execute_tick(agent_id)
        except Exception:
            logger.exception("Error executing tick for agent %s", agent_id)
        finally:
            with self._worker_lock:
                current = self._workers.get(agent_id)
                if current is threading.current_thread():
                    self._workers.pop(agent_id, None)
                self._stall_notified.discard(agent_id)

    def _dispatch_tick(self, agent_id: str) -> None:
        with self._worker_lock:
            existing = self._workers.get(agent_id)
            if existing is not None and existing.is_alive():
                return
            worker = threading.Thread(
                target=self._run_tick_worker,
                args=(agent_id,),
                daemon=True,
                name=f"agent-tick-{agent_id}",
            )
            self._workers[agent_id] = worker
        worker.start()

    def _check_due_agents(self) -> None:
        """Check all registered agents and dispatch due ticks without blocking."""
        now = time.time()

        with self._lock:
            due = [
                (aid, info.copy())
                for aid, info in self._agents.items()
                if info["next_fire"] <= now
            ]

        for agent_id, info in due:
            if self._stop_event.is_set():
                break
            agent = self._manager.get_agent(agent_id)
            if agent is None or agent["status"] in (
                "paused",
                "archived",
                "running",
                "budget_exceeded",
                "stalled",
            ):
                continue
            if self._worker_alive(agent_id):
                continue

            with self._lock:
                if agent_id in self._agents:
                    if info["schedule_type"] == "cron":
                        self._agents[agent_id]["next_fire"] = _next_cron_fire(
                            str(info["schedule_value"]),
                            now,
                            info.get("timezone"),
                        )
                    elif info["schedule_type"] == "interval":
                        self._agents[agent_id]["next_fire"] = now + float(
                            info["schedule_value"]
                        )

            logger.info("Dispatching tick for agent %s", agent_id)
            self._dispatch_tick(agent_id)

    def _reconcile(self) -> None:
        """Check running agents for stalls and handle retries."""
        agents = self._manager.list_agents()
        now = time.time()

        for agent in agents:
            if agent["status"] != "running":
                continue

            config = agent.get("config", {})
            timeout = config.get("timeout_seconds", 0)
            if timeout <= 0:
                continue

            last_activity = agent.get("last_activity_at")
            if last_activity is None:
                continue

            if now - last_activity <= timeout:
                continue

            # Agent is stalled. Never overlap a still-live worker with a retry.
            max_retries = config.get("max_stall_retries", 5)
            current_retries = agent.get("stall_retries", 0)
            agent_id = agent["id"]

            if self._worker_alive(agent_id):
                with self._worker_lock:
                    first_notice = agent_id not in self._stall_notified
                    if first_notice:
                        self._stall_notified.add(agent_id)
                if first_notice:
                    if self._bus:
                        self._bus.publish(
                            EventType.AGENT_STALL_DETECTED,
                            {
                                "agent_id": agent_id,
                                "last_activity_at": last_activity,
                                "stall_retries": current_retries,
                                "worker_alive": True,
                            },
                        )
                    logger.warning(
                        "Agent %s exceeded timeout but worker is still alive; "
                        "not starting an overlapping retry",
                        agent_id,
                    )
                continue

            if current_retries >= max_retries:
                self._manager.update_agent(agent_id, status="error")
                logger.warning(
                    "Agent %s stall retries exhausted (%d/%d), setting error",
                    agent_id,
                    current_retries,
                    max_retries,
                )
                continue

            # The worker is gone but left a stale running lock. Release it so
            # the next scheduler pass can safely dispatch a retry.
            self._manager.end_tick(agent_id)
            self._manager.update_agent(
                agent_id,
                stall_retries=current_retries + 1,
            )
            with self._worker_lock:
                self._stall_notified.discard(agent_id)
            if self._bus:
                self._bus.publish(
                    EventType.AGENT_STALL_DETECTED,
                    {
                        "agent_id": agent_id,
                        "last_activity_at": last_activity,
                        "stall_retries": current_retries + 1,
                        "worker_alive": False,
                    },
                )
            logger.warning(
                "Agent %s stalled with no live worker (retry %d/%d)",
                agent_id,
                current_retries + 1,
                max_retries,
            )

    # -- Learning tick counting ------------------------------------------------

    def _on_tick_completed(self, agent_id: str) -> None:
        """Track completed ticks and trigger learning if schedule is met."""
        self._tick_counts[agent_id] = self._tick_counts.get(agent_id, 0) + 1

        agent = self._manager.get_agent(agent_id)
        if agent is None:
            return

        config = agent.get("config", {})
        if not config.get("learning_enabled", False):
            return

        schedule = config.get("learning_schedule", "every_20_ticks")
        if schedule.startswith("every_"):
            try:
                threshold = int(schedule.split("_")[1].replace("ticks", ""))
            except (IndexError, ValueError):
                threshold = 20
        else:
            return

        if self._tick_counts[agent_id] >= threshold:
            self._tick_counts[agent_id] = 0
            if self._bus:
                self._bus.publish(
                    EventType.AGENT_LEARNING_STARTED,
                    {
                        "agent_id": agent_id,
                    },
                )
            logger.info(
                "Learning triggered for agent %s after %d ticks",
                agent_id,
                threshold,
            )

    def _on_tick_event(self, event: Any) -> None:
        """Handle AGENT_TICK_END to count ticks."""
        agent_id = event.data.get("agent_id")
        if agent_id and event.data.get("status") == "ok":
            self._on_tick_completed(agent_id)

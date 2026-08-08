"""Cooperative, monotonic deadline control for one fuzzing run."""

from __future__ import annotations

from collections.abc import Callable
import threading
import time


class RunController:
    """Own a fuzz-run deadline without allowing phases to reset it.

    The controller has one absolute monotonic deadline.  Components call
    :meth:`should_stop` at safe boundaries, while the watcher also signals the
    shared stop event if a component is currently blocked.  The owner of the
    run remains responsible for cleanup.
    """

    def __init__(
        self,
        duration_s: float,
        stop_event: threading.Event,
        request_stop: Callable[[str], None],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if duration_s <= 0:
            raise ValueError('duration_s must be positive')
        self.duration_s = float(duration_s)
        self.stop_event = stop_event
        self._request_stop = request_stop
        self._clock = clock
        self.started_monotonic = clock()
        self.deadline_monotonic = self.started_monotonic + self.duration_s
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None
        self._closed = False
        self._deadline_requested = False

    def elapsed_s(self) -> float:
        return max(0.0, self._clock() - self.started_monotonic)

    def remaining_s(self) -> float:
        return max(0.0, self.deadline_monotonic - self._clock())

    def expired(self) -> bool:
        return self._clock() >= self.deadline_monotonic

    def request_stop(self, reason: str = 'deadline') -> None:
        """Signal a classified stop exactly once for the global deadline."""
        with self._lock:
            if self._closed or self.stop_event.is_set():
                return
            if reason == 'deadline':
                if self._deadline_requested:
                    return
                self._deadline_requested = True
        self._request_stop(reason)

    def should_stop(self) -> bool:
        """Return whether work must stop, signalling an expired deadline."""
        if self.stop_event.is_set():
            return True
        if self.expired():
            self.request_stop('deadline')
            return True
        return False

    def start(self) -> None:
        """Start the background deadline watcher once the run starts."""
        with self._lock:
            if self._closed or self._timer is not None:
                return
            self._schedule_locked()

    def close(self) -> None:
        """Stop the watcher; this never clears the shared stop event."""
        with self._lock:
            self._closed = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _schedule_locked(self) -> None:
        timer = threading.Timer(self.remaining_s(), self._on_timer)
        timer.name = 'voltron-deadline'
        timer.daemon = True
        self._timer = timer
        timer.start()

    def _on_timer(self) -> None:
        with self._lock:
            self._timer = None
            if self._closed or self.stop_event.is_set():
                return
            if not self.expired():
                self._schedule_locked()
                return
        self.request_stop('deadline')

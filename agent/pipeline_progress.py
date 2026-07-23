"""Run LangGraph pipeline on a background thread with live Streamlit-friendly progress."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from agent.graph import (
    PIPELINE_NEXT_STEP,
    PIPELINE_STEP_COUNT,
    REGEN_PIPELINE_STEP_COUNT,
    get_step_hint,
    get_step_label,
    run_generation_stream,
    run_regen_stream,
)
from agent.state import TestGenState
from services.supabase_repo import SupabaseRepo


def run_pipeline_with_live_progress(
    repo: SupabaseRepo,
    initial: TestGenState,
    *,
    on_tick: Callable[[dict[str, Any]], None],
    poll_interval: float = 0.8,
    regen: bool = False,
) -> TestGenState:
    """
    Run generation on a worker thread; call on_tick(live_state) on the **main**
    thread every poll_interval. Do not touch Streamlit widgets from on_tick
    callbacks invoked elsewhere — only from the thread that called this function.

    The worker only updates an in-memory `live` dict; all UI must happen in on_tick.
    """
    step_count = REGEN_PIPELINE_STEP_COUNT if regen else PIPELINE_STEP_COUNT
    live: dict[str, Any] = {
        "running_step": "generate_cases" if regen else "retrieve_history",
        "completed_steps": [],
        "step_index": 0,
        "started_at": time.time(),
        "done": False,
        "error": None,
        "final": None,
        "step_count": step_count,
    }
    lock = threading.Lock()

    def _on_step(step: str, state: TestGenState, step_index: int) -> None:
        # Worker thread: state only — never call Streamlit here.
        with lock:
            if step not in live["completed_steps"]:
                live["completed_steps"].append(step)
            live["step_index"] = step_index
            live["running_step"] = PIPELINE_NEXT_STEP.get(step)
            live["last_state"] = state

    def _worker() -> None:
        try:
            runner = run_regen_stream if regen else run_generation_stream
            result = runner(repo, initial, on_step=_on_step)
            with lock:
                live["final"] = result
                live["running_step"] = None
        except Exception as exc:
            with lock:
                live["error"] = exc
        finally:
            with lock:
                live["done"] = True

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    snapshot: dict[str, Any] = {}
    while True:
        with lock:
            snapshot = {
                **live,
                "completed_steps": list(live["completed_steps"]),
            }
        on_tick(snapshot)
        if snapshot["done"]:
            break
        time.sleep(poll_interval)

    if snapshot.get("error"):
        raise snapshot["error"]
    return snapshot.get("final") or dict(initial)


def format_live_progress(snapshot: dict[str, Any]) -> tuple[float, str]:
    """Return (progress_fraction, progress_bar_text) for st.progress."""
    completed = int(snapshot.get("step_index") or 0)
    running = snapshot.get("running_step")
    elapsed = int(time.time() - float(snapshot.get("started_at") or time.time()))
    step_count = int(snapshot.get("step_count") or PIPELINE_STEP_COUNT)

    if running:
        display_index = completed + 1
        label = get_step_label(running)
        hint = get_step_hint(running)
        fraction = min(completed / step_count, 0.99)
        text = (
            f"Step {display_index}/{step_count}: {label} "
            f"- {elapsed}s elapsed. {hint}"
        )
        return fraction, text

    if completed >= step_count:
        return 1.0, "Pipeline complete."
    fraction = min(completed / step_count, 0.99)
    return fraction, f"Finishing… ({elapsed}s elapsed)"


def newly_completed_steps(
    snapshot: dict[str, Any], already_logged: int
) -> list[tuple[int, str]]:
    """Return (1-based index, step_id) for steps not yet written to the status log."""
    steps = snapshot.get("completed_steps") or []
    out: list[tuple[int, str]] = []
    for i in range(already_logged, len(steps)):
        out.append((i + 1, steps[i]))
    return out

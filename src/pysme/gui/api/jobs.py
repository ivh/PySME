# -*- coding: utf-8 -*-
"""Out-of-process execution of the heavy PySME computations.

Synthesis, fitting and MCMC all run in a separate worker process, which is what
makes them cancellable: the native SME library never releases the GIL, so an
in-process thread freezes the whole server for the duration of every native call
and can only be interrupted at Python-level checkpoints. Sending a signal to a
process is immediate, and it cannot leave the process-global state of the native
library half-updated.

The SME_Structure crosses the process boundary as a ``.sme`` file (a full
round-trip is lossless and costs milliseconds). The parent therefore keeps a
pristine copy while a job runs, and only replaces it once the job succeeds, so a
cancelled fit leaves the session exactly as it was instead of parked on the last
trial point the optimizer happened to evaluate.

Only one job runs at a time, and the worker is recycled after every job so that
each computation starts from clean native state. A replacement worker is spawned
immediately in the background, which hides the ~6 s interpreter start-up from
the user.

This module must not import anything from the web layer: with the "spawn" start
method the child re-imports it by name.
"""

import asyncio
import atexit
import logging
import multiprocessing as mp
import os
import queue as _queue
import signal
import shutil
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ...sme import SME_Structure
from ...solve import SME_MCMC, SME_Solver
from ...synthesize import synthesize_spectrum

logger = logging.getLogger(__name__)

INPUT_NAME = "input.sme"
OUTPUT_NAME = "output.sme"
SAMPLES_NAME = "mcmc_samples.npy"

KINDS = ("synthesize", "solve", "mcmc")

_CTX = mp.get_context("spawn")

# How long to wait for a killed worker before escalating SIGTERM -> SIGKILL
_KILL_GRACE = 3.0


# --------------------------------------------------------------------------- #
# Worker process
# --------------------------------------------------------------------------- #


class _QueueLogHandler(logging.Handler):
    """Forwards the worker's log records to the parent process."""

    def __init__(self, events):
        super().__init__()
        self._events = events

    def emit(self, record):
        try:
            self._events.put(
                {
                    "type": "log",
                    "level": record.levelname,
                    "message": self.format(record),
                }
            )
        except Exception:
            pass


class _ProgressReporter:
    """Polls an iteration counter and reports changes to the parent."""

    def __init__(self, getter, events, interval=0.4):
        self._getter = getter
        self._events = events
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        return False

    def _run(self):
        last = None
        while not self._stop.wait(self._interval):
            try:
                current = int(self._getter())
            except Exception:
                continue
            if current != last:
                last = current
                try:
                    self._events.put({"type": "progress", "iteration": current})
                except Exception:
                    return


def _run_synthesize(sme, payload, events):
    segments = payload.get("segments") or "all"
    return synthesize_spectrum(sme, segments=segments), {}


def _run_solve(sme, payload, events):
    solver = SME_Solver()
    with _ProgressReporter(lambda: solver.iteration, events):
        sme = solver.solve(sme, payload["parameters"])
    return sme, {}


def _run_mcmc(sme, payload, events):
    mcmc = SME_MCMC(
        sme,
        nwalkers=payload["nwalkers"],
        nsteps=payload["nsteps"],
        nburn=payload["nburn"],
    )
    with _ProgressReporter(lambda: mcmc.iteration, events):
        results = mcmc.run(payload["parameters"], progress=False)

    # The chain is too big to push through the event queue, and the GUI only
    # needs the summary; keep it on disk next to the job for later inspection.
    samples = results.pop("samples", None)
    samples_file = None
    if samples is not None:
        samples_file = Path(payload["job_dir"]) / SAMPLES_NAME
        np.save(samples_file, samples)

    summary = {
        "parameters": list(results.get("parameters", [])),
        "values": [float(v) for v in results.get("values", [])],
        "uncertainties": [float(v) for v in results.get("uncertainties", [])],
        "uncertainties_low": [float(v) for v in results.get("uncertainties_low", [])],
        "uncertainties_high": [float(v) for v in results.get("uncertainties_high", [])],
        "acceptance_fraction": float(results.get("acceptance_fraction", 0.0)),
        "samples_file": str(samples_file) if samples_file is not None else None,
    }
    return mcmc.sme, summary


_RUNNERS = {
    "synthesize": _run_synthesize,
    "solve": _run_solve,
    "mcmc": _run_mcmc,
}


def _execute(command, events):
    job_dir = Path(command["job_dir"])
    payload = dict(command.get("payload") or {})
    payload["job_dir"] = str(job_dir)

    try:
        sme = SME_Structure.load(str(job_dir / INPUT_NAME))
        sme, result = _RUNNERS[command["kind"]](sme, payload, events)
        sme.save(str(job_dir / OUTPUT_NAME))
    except BaseException as ex:  # noqa: BLE001 - report everything, never die silently
        events.put(
            {
                "type": "error",
                "message": str(ex) or ex.__class__.__name__,
                "traceback": traceback.format_exc(),
            }
        )
        return
    events.put({"type": "done", "result": result})


def _watch_parent(ppid, interval=1.0):
    """Leave no orphan behind if the server dies without cleaning up.

    ``ppid`` is passed in by the parent rather than read here: importing PySME
    takes seconds, and a server that dies during that window would already have
    left us with a reparented process to compare against.
    """
    while True:
        if os.getppid() != ppid:
            os._exit(1)
        time.sleep(interval)


def _worker_main(commands, events, ppid):
    """Entry point of the worker process."""
    # Become a process group leader so that cancelling can take down any
    # children the computation spawned itself (line selection uses pqdm).
    if hasattr(os, "setsid"):
        try:
            os.setsid()
        except OSError:
            pass

    threading.Thread(target=_watch_parent, args=(ppid,), daemon=True).start()

    handler = _QueueLogHandler(events)
    handler.setFormatter(logging.Formatter("%(name)s - %(message)s"))
    handler.setLevel(logging.DEBUG)
    pysme_logger = logging.getLogger("pysme")
    pysme_logger.addHandler(handler)
    pysme_logger.setLevel(logging.INFO)

    events.put({"type": "ready"})

    while True:
        try:
            command = commands.get()
        except (EOFError, OSError):
            break
        if command is None:
            break
        _execute(command, events)


# --------------------------------------------------------------------------- #
# Parent process
# --------------------------------------------------------------------------- #


class _Worker:
    """A pre-imported PySME process waiting for a command."""

    def __init__(self):
        self.commands = _CTX.Queue()
        self.events = _CTX.Queue()
        self.process = _CTX.Process(
            target=_worker_main,
            args=(self.commands, self.events, os.getpid()),
            name="pysme-worker",
            # Not daemonic: the computation may spawn its own child processes.
            daemon=False,
        )
        self.process.start()

    def submit(self, command):
        self.commands.put(command)

    def kill(self):
        """Stop the worker and anything it spawned."""
        process = self.process
        if process is None or process.pid is None:
            return
        if process.is_alive():
            self._signal(process, signal.SIGTERM)
            process.join(timeout=_KILL_GRACE)
        if process.is_alive():
            self._signal(process, getattr(signal, "SIGKILL", signal.SIGTERM))
            process.join(timeout=_KILL_GRACE)
        for q in (self.commands, self.events):
            try:
                q.close()
            except Exception:
                pass

    @staticmethod
    def _signal(process, sig):
        """Signal the worker's process group, or the worker alone if it has none."""
        try:
            # Only ever use killpg when the worker really is the group leader:
            # otherwise the group is the server's own, and we would kill it.
            if hasattr(os, "killpg") and os.getpgid(process.pid) == process.pid:
                os.killpg(process.pid, sig)
                return
        except (OSError, AttributeError):
            pass
        try:
            if sig == getattr(signal, "SIGKILL", None):
                process.kill()
            else:
                process.terminate()
        except (OSError, ValueError):
            pass


class Job:
    """State of a single computation, as seen by the server."""

    def __init__(self, kind: str, job_dir: Path, payload: dict):
        self.kind = kind
        self.dir = job_dir
        self.payload = payload
        self.status = "running"  # running | done | error | cancelled
        self.error: Optional[str] = None
        self.iteration = 0
        self.result: dict = {}
        self.started = time.time()
        self.finished: Optional[float] = None
        self.cancel_requested = False

    @property
    def running(self) -> bool:
        return self.status == "running"

    @property
    def elapsed(self) -> float:
        return (self.finished or time.time()) - self.started

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "status": self.status,
            "iteration": self.iteration,
            "elapsed": round(self.elapsed, 1),
            "error": self.error,
        }

    async def wait(self, interval: float = 0.1):
        """Await completion without blocking the event loop."""
        while self.running:
            await asyncio.sleep(interval)
        return self


class JobRunner:
    """Runs one computation at a time in a recycled worker process."""

    def __init__(
        self,
        on_log: Optional[Callable[[dict], None]] = None,
        on_result: Optional[Callable[[Job, SME_Structure], None]] = None,
    ):
        self.on_log = on_log
        self.on_result = on_result
        # Reentrant: start() spawns a worker while holding the lock.
        self._lock = threading.RLock()
        self._worker: Optional[_Worker] = None
        self._live: set = set()
        self._job: Optional[Job] = None
        self._closed = False
        atexit.register(self.shutdown)

    # -- worker lifecycle -------------------------------------------------- #

    def prewarm(self):
        """Start a worker now so the first computation does not pay for imports."""
        with self._lock:
            if self._closed or self._worker is not None:
                return
        worker = self._spawn()
        with self._lock:
            if self._worker is None and not self._closed:
                self._worker = worker
                return
        self._discard(worker)

    def _spawn(self) -> Optional[_Worker]:
        """Create a worker, unless the server is (or turns out to be) shutting down."""
        with self._lock:
            if self._closed:
                return None
        try:
            worker = _Worker()
        except Exception:
            logger.exception("Could not start the PySME worker process")
            return None
        with self._lock:
            if self._closed:
                closed = True
            else:
                closed = False
                self._live.add(worker)
        if closed:
            worker.kill()
            return None
        return worker

    def _discard(self, worker: Optional[_Worker]):
        if worker is None:
            return
        with self._lock:
            self._live.discard(worker)
        worker.kill()

    def _recycle(self, old: Optional[_Worker]):
        """Replace the worker, so the next job starts from clean native state."""
        self._discard(old)
        with self._lock:
            if self._closed or self._worker is not old:
                return
            self._worker = None
        replacement = self._spawn()
        with self._lock:
            keep = not self._closed and self._worker is None
            if keep:
                self._worker = replacement
        if not keep:
            self._discard(replacement)

    def shutdown(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            workers, job = list(self._live), self._job
            self._live.clear()
            self._worker = None
        if job is not None:
            if job.running:
                job.cancel_requested = True
            shutil.rmtree(job.dir, ignore_errors=True)
        for worker in workers:
            worker.kill()

    # -- job control ------------------------------------------------------- #

    @property
    def job(self) -> Optional[Job]:
        return self._job

    def job_of_kind(self, kind: str) -> Optional[Job]:
        job = self._job
        return job if job is not None and job.kind == kind else None

    def start(self, kind: str, sme: SME_Structure, payload: Optional[dict] = None) -> Job:
        if kind not in KINDS:
            raise ValueError(f"Unknown job kind {kind!r}")
        with self._lock:
            if self._closed:
                raise RuntimeError("The server is shutting down")
            if self._job is not None and self._job.running:
                raise RuntimeError(
                    f"A {self._job.kind} computation is already running; cancel it first"
                )
            previous = self._job
            if self._worker is None:
                self._worker = self._spawn()
            worker = self._worker
            if worker is None:
                raise RuntimeError("Could not start the PySME worker process")
            job = Job(kind, Path(tempfile.mkdtemp(prefix="pysme-job-")), payload or {})
            self._job = job
        if previous is not None:
            shutil.rmtree(previous.dir, ignore_errors=True)

        # The hand-off (writing the .sme file) happens on the job thread so that
        # a large linelist cannot stall the event loop.
        threading.Thread(
            target=self._run,
            args=(job, worker, sme),
            name=f"pysme-job-{kind}",
            daemon=True,
        ).start()
        return job

    def cancel(self, kind: Optional[str] = None) -> Optional[Job]:
        """Kill the running computation. Returns the job that was cancelled."""
        with self._lock:
            job, worker = self._job, self._worker
            if job is None or not job.running:
                return None
            if kind is not None and job.kind != kind:
                return None
            job.cancel_requested = True
        if worker is not None:
            worker.kill()
        return job

    # -- job thread -------------------------------------------------------- #

    def _run(self, job: Job, worker: _Worker, sme: SME_Structure):
        try:
            sme.save(str(job.dir / INPUT_NAME))
        except Exception as ex:
            logger.exception("Could not hand the SME structure to the worker")
            self._finish(job, "error", f"Could not prepare the computation: {ex}")
            self._recycle(worker)
            return

        worker.submit(
            {"kind": job.kind, "job_dir": str(job.dir), "payload": job.payload}
        )
        status, error = self._drain(job, worker)

        if status == "done":
            try:
                result = SME_Structure.load(str(job.dir / OUTPUT_NAME))
                if self.on_result is not None:
                    self.on_result(job, result)
            except Exception as ex:
                logger.exception("Could not apply the result of the %s job", job.kind)
                status, error = "error", f"Could not read back the result: {ex}"

        (job.dir / INPUT_NAME).unlink(missing_ok=True)
        (job.dir / OUTPUT_NAME).unlink(missing_ok=True)
        self._finish(job, status, error)
        self._recycle(worker)

    def _drain(self, job: Job, worker: _Worker):
        """Consume worker events until the job ends or the worker dies."""
        deadline = None
        while True:
            try:
                event = worker.events.get(timeout=0.25)
            except _queue.Empty:
                if worker.process.is_alive():
                    continue
                # The process is gone; give any buffered events a moment to
                # arrive before deciding why it ended.
                if deadline is None:
                    deadline = time.time() + 0.75
                    continue
                if time.time() < deadline:
                    continue
                return self._died(job, worker)
            except Exception:
                return self._died(job, worker)

            deadline = None  # an event arrived, so keep draining
            kind = event.get("type")
            if kind == "log":
                if self.on_log is not None:
                    self.on_log(event)
            elif kind == "progress":
                job.iteration = int(event.get("iteration", job.iteration))
            elif kind == "done":
                job.result = event.get("result") or {}
                return "done", None
            elif kind == "error":
                if event.get("traceback"):
                    logger.debug("Worker traceback:\n%s", event["traceback"])
                return "error", event.get("message") or "The computation failed"

    def _died(self, job: Job, worker: _Worker):
        if job.cancel_requested:
            return "cancelled", None
        code = worker.process.exitcode
        if code is not None and code < 0:
            try:
                name = signal.Signals(-code).name
            except ValueError:
                name = f"signal {-code}"
            return (
                "error",
                f"The computation died on {name}. This usually means the native "
                "SME library aborted; the server itself is unaffected.",
            )
        return "error", f"The worker process exited unexpectedly (code {code})"

    def _finish(self, job: Job, status: str, error: Optional[str] = None):
        job.error = error
        job.finished = time.time()
        job.status = status  # set last: the SSE streams key off it

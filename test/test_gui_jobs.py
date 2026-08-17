# -*- coding: utf-8 -*-
"""End-to-end tests for the out-of-process job runner behind the web GUI.

Every test here drives a real uvicorn server, a real worker process and real
syntheses, so the whole module is marked ``slow``::

    pytest -m "not slow"     # skip this module
    pytest -m slow           # run only this module

What is being tested is not the numbers (other tests cover synthesis) but the
process machinery: that computations run outside the server, that killing them
works, that a cancelled run leaves the session untouched, and that no worker is
left behind.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from importlib.util import find_spec

import pytest
import requests

from pysme.large_file_storage import setup_atmo

from test.conftest import skipif_smelib

pytestmark = [pytest.mark.slow, skipif_smelib]

SERVER_CODE = (
    "from pysme.gui.server import run_server; "
    "run_server(port={port}, open_browser=False)"
)

# A six parameter fit takes long enough that we can reliably interrupt it.
LONG_FIT = ["teff", "logg", "monh", "vmic", "vmac", "vsini"]


def gui_available():
    return all(find_spec(m) is not None for m in ("fastapi", "uvicorn"))


def data_available(*keys):
    """Each datafile must be cached already or still be downloadable.

    The file server has no directory index, so a HEAD on its root is useless;
    ask the LargeFileStorage for the actual candidate URLs of the files a
    synthesis needs.
    """
    lfs = setup_atmo()
    for key in keys:
        try:
            urls = lfs.get_urls(key)
        except Exception:
            return False
        for url in urls:
            if url.startswith("file://"):
                if os.path.exists(url[7:]):
                    break
            else:
                try:
                    if requests.head(url, timeout=15, allow_redirects=True).ok:
                        break
                except requests.RequestException:
                    continue
        else:
            return False
    return True


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def worker_pids(server_pid):
    """The server's worker processes, excluding its resource tracker."""
    out = subprocess.run(
        ["ps", "-eo", "pid,ppid,command"], capture_output=True, text=True
    ).stdout
    pids = []
    for line in out.splitlines()[1:]:
        parts = line.split(maxsplit=2)
        if len(parts) < 3 or not parts[1].isdigit():
            continue
        if int(parts[1]) == server_pid and "spawn_main" in parts[2]:
            pids.append(int(parts[0]))
    return pids


def is_running(pid):
    """True while the process exists and has not become a zombie."""
    out = subprocess.run(
        ["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True
    ).stdout.strip()
    return bool(out) and not out.startswith("Z")


class Client:
    """Minimal driver for the GUI API."""

    def __init__(self, port, process):
        self.base = f"http://127.0.0.1:{port}/api"
        self.process = process

    def get(self, path, **kw):
        return requests.get(f"{self.base}{path}", timeout=kw.pop("timeout", 30), **kw)

    def post(self, path, **kw):
        return requests.post(f"{self.base}{path}", timeout=kw.pop("timeout", 120), **kw)

    def put(self, path, **kw):
        return requests.put(f"{self.base}{path}", timeout=kw.pop("timeout", 30), **kw)

    def job(self):
        return self.get("/job").json()

    def params(self):
        return self.get("/params").json()

    def events(self, path, timeout=900):
        """Yield the Server-Sent Events of a progress stream."""
        with requests.get(f"{self.base}{path}", stream=True, timeout=timeout) as response:
            for line in response.iter_lines(decode_unicode=True):
                if line and line.startswith("data: "):
                    yield json.loads(line[6:])

    def final_event(self, path, timeout=900):
        for event in self.events(path, timeout=timeout):
            if event["type"] in ("done", "error", "cancelled"):
                return event
        raise AssertionError(f"{path} closed without a final event")

    def wait_for(self, predicate, timeout, message):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.job()
            if predicate(job):
                return job
            time.sleep(0.2)
        raise AssertionError(f"{message}; last job state: {job}")

    def wait_until_idle(self, timeout=60):
        return self.wait_for(lambda job: not job["running"], timeout, "job kept running")


class Poller(threading.Thread):
    """Polls a cheap endpoint to measure how responsive the event loop stays."""

    def __init__(self, client):
        super().__init__(daemon=True)
        self.client = client
        self.stop = threading.Event()
        self.max_latency = 0.0
        self.polls = 0

    def run(self):
        while not self.stop.wait(0.1):
            start = time.time()
            try:
                self.client.get("/session", timeout=60)
            except requests.RequestException:
                continue
            self.max_latency = max(self.max_latency, time.time() - start)
            self.polls += 1

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.join(timeout=5)
        return False


def start_server(log_path):
    """Launch the GUI server and wait until it answers."""
    port = free_port()
    with open(log_path, "w") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", SERVER_CODE.format(port=port)],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    client = Client(port, process)

    deadline = time.time() + 120
    while time.time() < deadline:
        if process.poll() is not None:
            raise AssertionError(
                f"server exited with {process.returncode}:\n{open(log_path).read()}"
            )
        try:
            if client.get("/session", timeout=2).status_code == 200:
                return client
        except requests.RequestException:
            time.sleep(0.3)
    raise AssertionError(f"server did not start:\n{open(log_path).read()}")


def stop_server(client):
    process = client.process
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    if not gui_available():
        pytest.skip("GUI extra (fastapi, uvicorn) not installed")
    if not data_available("marcs2012.sav", "nso.bin"):
        pytest.skip("atmosphere grid / solar atlas neither cached nor downloadable")

    log_path = tmp_path_factory.mktemp("gui") / "server.log"
    client = start_server(log_path)
    workers = worker_pids(client.process.pid)
    try:
        yield client
    finally:
        stop_server(client)
        # Whatever the tests did, no worker may outlive the server.
        time.sleep(2.0)
        leaked = [pid for pid in workers + worker_pids(client.process.pid) if is_running(pid)]
        for pid in leaked:
            os.kill(pid, 9)
        assert not leaked, f"worker processes outlived the server: {leaked}"


@pytest.fixture
def session(server):
    """A solar spectrum with the bundled linelist, ready to synthesize."""
    server.post("/cancel")
    server.wait_until_idle()

    assert server.post("/session/load-solar", timeout=300).status_code == 200
    response = server.post(
        "/linelist/load-builtin", json={"name": "solar_6436_6444"}, timeout=120
    )
    assert response.status_code == 200, response.text

    # Start away from the solution so that fits need several iterations.
    params = server.params()
    assert server.put("/params", json={**params, "teff": 5200, "logg": 4.0}).status_code == 200
    return server


def test_computation_runs_in_a_separate_process(session):
    """The pre-warmed worker is a child process, not a thread of the server."""
    assert worker_pids(session.process.pid), "no worker process was pre-warmed"


def test_synthesis_keeps_the_server_responsive(session):
    with Poller(session) as poller:
        response = session.post("/synthesize", json={"segments": None}, timeout=900)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"

    # The native library never releases the GIL, so this only holds as long as
    # the synthesis really runs in another process.
    assert poller.polls > 0
    assert poller.max_latency < 2.0, f"event loop stalled for {poller.max_latency:.1f}s"
    assert session.get("/session").json()["has_synthetic"] is True


def test_cancelling_a_fit_stops_it_and_leaves_the_session_untouched(session):
    before = session.params()

    assert session.post("/solve", json={"parameters": LONG_FIT}).status_code == 200
    session.wait_for(
        lambda job: not job["running"] or job["iteration"] >= 2,
        120,
        "fit never reported progress",
    )
    assert session.job()["running"], "fit finished before it could be cancelled"

    started = time.time()
    response = session.post("/cancel", timeout=60)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    job = session.wait_until_idle(timeout=30)
    assert job["status"] == "cancelled"
    assert time.time() - started < 20, "cancelling took too long"

    # The worker held a snapshot, so the trial parameters it was evaluating
    # must not have leaked into the session.
    assert session.params() == before


def test_a_fit_completes_on_the_recycled_worker(session):
    # Cancel one fit first: the worker is replaced afterwards, and the next fit
    # has to run on the replacement.
    assert session.post("/solve", json={"parameters": LONG_FIT}).status_code == 200
    session.wait_for(
        lambda job: not job["running"] or job["iteration"] >= 1, 120, "fit did not start"
    )
    session.post("/cancel", timeout=60)
    session.wait_until_idle(timeout=30)

    assert session.post("/solve", json={"parameters": ["teff"]}).status_code == 200
    event = session.final_event("/solve/stream")
    assert event["type"] == "done", event
    assert event["parameters"] == ["teff"]

    results = session.get("/fit-results").json()
    assert results["parameters"] == ["teff"]
    assert results["chisq"] is not None


def test_cancelling_mcmc_stops_it(session):
    request = {"parameters": ["teff"], "nwalkers": 4, "nsteps": 400, "nburn": 10}
    assert session.post("/mcmc", json=request).status_code == 200
    session.wait_for(
        lambda job: not job["running"] or job["iteration"] >= 1,
        180,
        "MCMC never reported a step",
    )
    assert session.job()["running"], "MCMC finished before it could be cancelled"

    response = session.post("/mcmc/cancel", timeout=60)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    job = session.wait_until_idle(timeout=30)
    assert job["status"] == "cancelled"
    # This is the event the browser waits for.
    assert session.final_event("/mcmc/stream", timeout=30)["type"] == "cancelled"


def test_mcmc_completes_and_reports_results(session):
    request = {"parameters": ["teff"], "nwalkers": 4, "nsteps": 10, "nburn": 1}
    assert session.post("/mcmc", json=request).status_code == 200

    event = session.final_event("/mcmc/stream")
    assert event["type"] == "done", event

    results = session.get("/mcmc/results").json()
    assert results["parameters"] == ["teff"]
    assert results["uncertainties"][0] > 0
    assert 0.0 <= results["acceptance_fraction"] <= 1.0


def test_session_changes_are_refused_while_a_computation_runs(session):
    params = session.params()
    assert session.post("/solve", json={"parameters": LONG_FIT}).status_code == 200
    try:
        # Accepting these would silently discard them when the result lands.
        assert session.put("/params", json={**params, "teff": 6000}).status_code == 409
        assert session.post("/solve", json={"parameters": ["teff"]}).status_code == 409
        assert session.post("/session/load-test").status_code == 409
    finally:
        session.post("/cancel", timeout=60)
        session.wait_until_idle(timeout=30)


def test_cancelling_when_nothing_runs_is_harmless(session):
    for path in ("/cancel", "/solve/cancel", "/mcmc/cancel"):
        response = session.post(path)
        assert response.status_code == 200
        assert response.json()["status"] == "idle", path


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups needed")
def test_worker_does_not_outlive_a_killed_server(tmp_path):
    """A hard kill of the server must not leave a worker computing forever."""
    if not gui_available():
        pytest.skip("GUI extra (fastapi, uvicorn) not installed")

    client = start_server(tmp_path / "server.log")
    try:
        deadline = time.time() + 60
        workers = []
        while time.time() < deadline and not workers:
            workers = worker_pids(client.process.pid)
            time.sleep(0.5)
        assert workers, "no worker process was pre-warmed"

        client.process.kill()
        client.process.wait(timeout=30)

        deadline = time.time() + 30
        while time.time() < deadline and any(is_running(pid) for pid in workers):
            time.sleep(0.5)
        alive = [pid for pid in workers if is_running(pid)]
        for pid in alive:
            os.kill(pid, 9)
        assert not alive, f"orphaned workers: {alive}"
    finally:
        stop_server(client)

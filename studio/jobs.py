"""Durable local queue. One worker serializes all GPU stages."""
from collections import deque
import os
import subprocess
import threading
import time
import traceback
import uuid

from studio.paths import DATA, ROOT, initialize, read_json, write_json


class Cancelled(Exception):
    pass


class Context:
    def __init__(self, manager, job):
        self.manager, self.job = manager, job
        self.directory = DATA / "jobs" / job["id"]

    def check(self):
        if self.job.get("cancel_requested"):
            raise Cancelled()

    def stage(self, name, action, valid=lambda result: True):
        self.check()
        self.manager.update(self.job, stage=name)
        marker = self.directory / f"stage-{name}.json"
        if marker.exists():
            previous = read_json(marker)
            if valid(previous):
                self.publish(previous)
                return previous
        result = action()
        self.check()
        if not valid(result):
            raise RuntimeError(f"Output validation failed: {name}")
        write_json(marker, result)
        self.publish(result)
        return result

    def publish(self, result):
        visible = {"source", "vocals", "instrumental", "dry", "reverb", "echo", "converted", "mix", "manifest", "checkpoint", "dataset"}
        added = [a for a in result.get("artifacts", []) if a["kind"] in visible]
        if added:
            merged = {a["file"]: a for a in self.job["artifacts"]}
            merged.update({a["file"]: a for a in added})
            self.manager.update(self.job, artifacts=list(merged.values()))

    def run(self, args, cwd=ROOT, env=None):
        """Poll independently of stdout so silent child processes remain cancellable."""
        self.check()
        settings = os.environ.copy()
        settings.update({"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"})
        settings.update(env or {})
        with (self.directory / "worker.log").open("ab") as log:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen([str(x) for x in args], cwd=cwd, env=settings,
                                       stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                                       start_new_session=os.name != "nt")
            try:
                while process.poll() is None:
                    self.check()
                    time.sleep(0.25)
            except BaseException:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=log, stderr=log, creationflags=flags)
                else:
                    import signal
                    os.killpg(process.pid, signal.SIGTERM)
                process.wait()
                raise
            if process.returncode:
                raise RuntimeError(f"Worker exited with code {process.returncode}. See worker.log")


class JobManager:
    def __init__(self):
        initialize()
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.queue = deque()
        self.jobs = {}
        self.closed = False
        for path in (DATA / "jobs").glob("*/job.json"):
            job = read_json(path)
            if job["status"] in ("queued", "running"):
                job["status"] = "interrupted"
                job["error"] = "Server stopped; retry to resume completed stages."
                write_json(path, job)
            self.jobs[job["id"]] = job
        self.thread = threading.Thread(target=self._work, daemon=True)

    def start(self):
        self.thread.start()

    def update(self, job, **values):
        with self.lock:
            job.update(values, updated=time.time())
            write_json(DATA / "jobs" / job["id"] / "job.json", job)

    def submit(self, kind, request):
        with self.lock:
            job = {"id": uuid.uuid4().hex, "kind": kind, "request": request,
                   "status": "queued", "stage": "queued", "created": time.time(),
                   "cancel_requested": False, "attempt": 1, "artifacts": []}
            self.jobs[job["id"]] = job
            self.update(job)
            self.queue.append(job["id"])
            self.wake.set()
            return job.copy()

    def retry(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] not in ("failed", "cancelled", "interrupted"):
                raise ValueError("Only failed, cancelled or interrupted jobs can be retried")
            self.update(job, status="queued", error=None, cancel_requested=False, attempt=job["attempt"] + 1)
            self.queue.append(job_id)
            self.wake.set()
            return job.copy()

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] in ("running", "queued"):
                self.update(job, cancel_requested=True)
            return job.copy()

    def snapshot(self):
        with self.lock:
            return sorted([j.copy() for j in self.jobs.values()], key=lambda j: j["created"], reverse=True)

    def close(self):
        self.closed = True
        with self.lock:
            for job in self.jobs.values():
                if job["status"] == "running":
                    self.update(job, cancel_requested=True)
        self.wake.set()
        self.thread.join(timeout=10)

    def _work(self):
        from studio.pipeline import execute
        while not self.closed:
            self.wake.wait(1)
            with self.lock:
                if not self.queue:
                    self.wake.clear()
                    continue
                job = self.jobs[self.queue.popleft()]
            try:
                context = Context(self, job)
                context.check()
                self.update(job, status="running", error=None)
                result = execute(context)
                context.check()
                self.update(job, status="succeeded", stage="done", **result)
            except Cancelled:
                self.update(job, status="cancelled", error="Task cancelled; last completed stages are retained.")
            except Exception as error:
                (DATA / "jobs" / job["id"] / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
                self.update(job, status="failed", error=str(error))

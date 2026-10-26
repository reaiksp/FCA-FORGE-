import sys
import threading
import time

from studio.jobs import JobManager, Context, Cancelled
from studio.paths import DATA, read_json


def test_restart_marks_unfinished_job_and_retry_retains_completed_stage():
    first = JobManager()
    job = first.submit("prepare", {"name": "test"})
    ctx = Context(first, first.jobs[job["id"]])
    calls = []
    assert ctx.stage("one", lambda: calls.append(1) or {"value": 42}) == {"value": 42}
    second = JobManager()
    restored = second.jobs[job["id"]]
    assert restored["status"] == "interrupted"
    second.retry(job["id"])
    result = Context(second, restored).stage("one", lambda: calls.append(2))
    assert result == {"value": 42}
    assert calls == [1]
    assert read_json(DATA / "jobs" / job["id"] / "job.json")["attempt"] == 2


def test_silent_subprocess_can_be_cancelled():
    manager = JobManager()
    submitted = manager.submit("prepare", {})
    job = manager.jobs[submitted["id"]]
    ctx = Context(manager, job)
    failures = []
    def run():
        try:
            ctx.run([sys.executable, "-c", "import time; time.sleep(30)"])
        except Cancelled:
            failures.append("cancelled")
    thread = threading.Thread(target=run)
    thread.start()
    time.sleep(.4)
    manager.cancel(job["id"])
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert failures == ["cancelled"]

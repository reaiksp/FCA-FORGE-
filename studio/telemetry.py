"""Read-only RVC training curves and byte-cursor console access.

The pinned Applio worker writes scalars to ``voice_<job_id>/eval``. Its
``training_data.json`` variable is unused: stdout progress must never be
misrepresented as a complete loss history. No PyTorch import is required here.
"""
from collections import OrderedDict
import codecs
import math
import os
from pathlib import Path
import re
import threading

from studio.paths import DATA

MAX_POINTS = 1000
MAX_RAW_POINTS = 6000
MAX_EVENT_FILES = 16
MAX_CONSOLE_BYTES = 256 * 1024
_MAX_CACHE_RUNS = 3
_ID = re.compile(r"^[a-f0-9]{32}$")
_PROGRESS = re.compile(
    r"\bepoch=(\d+)\s*\|\s*step=(\d+)(?:\s*\|\s*batch=(\d+)/(\d+))?"
)
_COMPLETED = re.compile(
    r"Training has been successfully completed with (\d+) epoch, (\d+) steps "
    r"and ([+\-\deE.]+) loss gen\."
)
_TAGS = (
    "loss/g/total", "loss/d/adv", "loss/g/mel", "loss/g/kl", "loss/g/adv", "loss/g/fm",
    "learning_rate", "grad/norm_g", "grad/norm_d", "loss_avg_50/g/total",
    "loss_avg_50/d/adv", "loss_avg_50/g/mel", "loss_avg_50/g/kl", "loss_avg_50/g/adv",
    "loss_avg_50/g/fm", "grad_avg_50/norm_g", "grad_avg_50/norm_d",
)
_cache = OrderedDict()
_cache_lock = threading.RLock()


def _job_paths(job):
    job_id = str(job.get("id", ""))
    if not _ID.fullmatch(job_id):
        raise ValueError("Invalid job identifier")
    console = (DATA / "jobs" / job_id / "worker.log").resolve()
    experiment = (DATA / "experiments" / f"voice_{job_id}").resolve()
    if not console.is_relative_to(DATA) or not experiment.is_relative_to(DATA):
        raise ValueError("Telemetry path escapes the data directory")
    return console, experiment


def read_console(job: dict, cursor: int | None = None, limit: int = 65536) -> dict:
    """Read a bounded console tail initially, then stream from an exact byte cursor.

    ``cursor=None`` requests the latest ``limit`` bytes. An offset beyond EOF
    means the file was truncated and sets ``reset``. Trailing incomplete UTF-8
    is not consumed, so appending its remaining bytes never loses a character.
    Text is plain console output: clients must render it as text, never HTML.
    """
    if cursor is not None and (not isinstance(cursor, int) or cursor < 0):
        raise ValueError("Console cursor must be a non-negative integer")
    if not isinstance(limit, int) or not 1 <= limit <= MAX_CONSOLE_BYTES:
        raise ValueError(f"Console limit must be between 1 and {MAX_CONSOLE_BYTES}")
    path, _ = _job_paths(job)
    try:
        with path.open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            reset = cursor is not None and cursor > size
            start = max(0, size - limit) if cursor is None or reset else cursor
            stream.seek(start)
            data = stream.read(limit)
    except FileNotFoundError:
        return {"text": "", "cursor": 0, "start": 0, "size": 0, "exists": False,
                "reset": cursor not in (None, 0), "truncated": False, "has_more": False}
    # Initial tail can start in the middle of a multibyte character.
    if (cursor is None or reset) and start:
        skipped = 0
        while skipped < len(data) and data[skipped] & 0xC0 == 0x80:
            skipped += 1
        data = data[skipped:]
        start += skipped
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    text = decoder.decode(data, final=False)
    pending, _ = decoder.getstate()
    consumed = len(data) - len(pending)
    next_cursor = start + consumed
    return {"text": text, "cursor": next_cursor, "start": start, "size": size,
            "exists": True, "reset": reset, "truncated": (cursor is None or reset) and start > 0,
            "has_more": start + len(data) < size}


def _downsample(points, limit=MAX_POINTS):
    """Bound chart size while retaining first/last points and local extrema."""
    if len(points) <= limit:
        return points
    if limit < 4:
        return [points[0], points[-1]][:limit]
    interior = points[1:-1]
    buckets = max(1, (limit - 2) // 2)
    selected = [points[0]]
    for index in range(buckets):
        left = index * len(interior) // buckets
        right = (index + 1) * len(interior) // buckets
        bucket = interior[left:right]
        if not bucket:
            continue
        low = min(range(len(bucket)), key=lambda i: bucket[i]["value"])
        high = max(range(len(bucket)), key=lambda i: bucket[i]["value"])
        selected.extend(bucket[i] for i in sorted({low, high}))
    selected.append(points[-1])
    return selected


def _tensorboard_series(experiment):
    try:
        from tensorboard.backend.event_processing import event_accumulator
    except ImportError:
        return [], ["TensorBoard reader is not installed; install the application dependencies."]
    event_files = []
    for file in experiment.rglob("events.out.tfevents.*") if experiment.exists() else []:
        try:
            resolved = file.resolve()
            if resolved.is_relative_to(experiment) and resolved.is_file():
                event_files.append((resolved, resolved.stat()))
        except FileNotFoundError:
            continue
    if not event_files:
        return [], []
    # Per-file readers avoid session purging across resumed training runs. Duplicate
    # steps below are replaced by the latest wall-time, then later-read event.
    warnings = []
    event_files.sort(key=lambda item: (item[1].st_mtime_ns, str(item[0])))
    if len(event_files) > MAX_EVENT_FILES:
        event_files = event_files[-MAX_EVENT_FILES:]
        warnings.append(f"Only the latest {MAX_EVENT_FILES} event files are shown; older training sessions are omitted.")
    signature = tuple(sorted((str(p), s.st_size, s.st_mtime_ns, s.st_ino) for p, s in event_files))
    key = str(experiment)
    scalar_budget = max(2, MAX_RAW_POINTS // len(event_files))
    with _cache_lock:
        entry = _cache.get(key)
        if entry and entry["signature"] == signature:
            _cache.move_to_end(key)
            return entry["series"], entry["warnings"]
        if entry is None or entry.get("scalar_budget") != scalar_budget:
            entry = {"readers": {}}
        readers = entry["readers"]
        current_paths = {str(p) for p, _ in event_files}
        for stale in list(readers):
            if stale not in current_paths:
                del readers[stale]
        values = {tag: {} for tag in _TAGS}
        class ScalarOnlyAccumulator(event_accumulator.EventAccumulator):
            def _ProcessEvent(self, event):
                # Per-tag image/audio reservoirs are otherwise unbounded when the
                # worker creates a fresh tag per checkpoint. Filter before storage.
                if not event.HasField("summary"):
                    return
                scalars = [value for value in event.summary.value
                           if value.tag in _TAGS and value.HasField("simple_value")]
                if scalars:
                    filtered = type(event)(wall_time=event.wall_time, step=event.step)
                    filtered.summary.value.extend(scalars)
                    super()._ProcessEvent(filtered)

        for path, stat in event_files:
            path_key = str(path)
            cached = readers.get(path_key)
            if (cached is None or stat.st_size < cached["size"] or stat.st_ino != cached.get("inode")
                    or (stat.st_size == cached["size"] and stat.st_mtime_ns != cached.get("mtime_ns"))):
                reader = ScalarOnlyAccumulator(
                    str(path), purge_orphaned_data=False,
                    size_guidance={"scalars": scalar_budget, "images": 1, "audio": 1,
                                   "histograms": 1, "compressedHistograms": 1, "tensors": 1},
                )
                cached = {"reader": reader, "size": 0}
                readers[path_key] = cached
            try:
                reader = cached["reader"].Reload()
                cached["size"] = stat.st_size
                cached["mtime_ns"] = stat.st_mtime_ns
                cached["inode"] = stat.st_ino
                available = set(reader.Tags().get("scalars", []))
                for tag in available.intersection(_TAGS):
                    events = reader.Scalars(tag)
                    if len(events) >= scalar_budget:
                        warnings.append("Scalar buffers are capped; charts retain a bounded sample of events.")
                    for event in events:
                        if event.step < 0 or not math.isfinite(event.value) or not math.isfinite(event.wall_time):
                            continue
                        point = {"step": int(event.step), "value": float(event.value), "wall_time": float(event.wall_time)}
                        previous = values[tag].get(point["step"])
                        if previous is None or point["wall_time"] >= previous["wall_time"]:
                            values[tag][point["step"]] = point
            except Exception as error:
                # A writer may be in the middle of a record; retry on its next update.
                warnings.append(f"Unable to read an event file ({type(error).__name__}); retry after the writer flushes.")
                readers.pop(path_key, None)
        series = []
        for tag in _TAGS:
            points = sorted(values[tag].values(), key=lambda p: p["step"])
            if points:
                retained = _downsample(points, MAX_POINTS)
                series.append({"tag": tag, "points": retained, "count": len(points),
                               "downsampled": len(retained) < len(points)})
        warnings = list(dict.fromkeys(warnings))
        entry.update(signature=signature, series=series, warnings=warnings, scalar_budget=scalar_budget)
        _cache[key] = entry
        _cache.move_to_end(key)
        while len(_cache) > _MAX_CACHE_RUNS:
            _cache.popitem(last=False)
        return series, warnings


def _progress(text, total_epochs, job_status):
    epoch = step = batch = total_batches = None
    latest_position = -1
    for match in _PROGRESS.finditer(text):
        epoch, step = int(match[1]), int(match[2])
        batch, total_batches = (int(match[3]), int(match[4])) if match[3] else (None, None)
        latest_position = match.start()
    completions = list(_COMPLETED.finditer(text))
    if completions and completions[-1].start() > latest_position:
        epoch, step = int(completions[-1][1]), int(completions[-1][2])
        batch = total_batches = None
    percent = None
    if epoch is not None and total_epochs:
        fraction = min(1.0, batch / total_batches) if total_batches and batch is not None else 1.0
        percent = max(0.0, min(100.0, (epoch - 1 + fraction) / total_epochs * 100))
    if job_status == "succeeded":
        percent = 100.0
    return {"epoch": epoch, "total_epochs": total_epochs, "step": step,
            "batch": batch, "total_batches": total_batches, "percent": percent}


def training_metrics(job: dict) -> dict:
    """Return actual scalar history plus observed stdout progress for a train job."""
    _, experiment = _job_paths(job)
    total_epochs = job.get("request", {}).get("epochs")
    if not isinstance(total_epochs, int) or isinstance(total_epochs, bool) or total_epochs <= 0:
        total_epochs = None
    progress = _progress("", total_epochs, job.get("status"))
    if job.get("kind") != "train":
        return {"status": "not_applicable", "source": "none", "series": [],
                "progress": {**progress, "percent": None}, "warnings": []}
    console = read_console(job, limit=MAX_CONSOLE_BYTES)
    progress = _progress(console["text"], total_epochs, job.get("status"))
    series, warnings = _tensorboard_series(experiment)
    source = "tensorboard" if series else "none"
    # The final completion line contains one actual generator-loss measurement.
    # Do not turn `lowest_value` (a historical minimum) into a fake loss curve.
    if not series:
        completions = list(_COMPLETED.finditer(console["text"]))
        if completions:
            last = completions[-1]
            try:
                value = float(last[3])
            except ValueError:
                value = float('nan')
            if math.isfinite(value):
                series = [{"tag": "loss/g/total", "points": [{"step": int(last[2]),
                           "value": value, "wall_time": None}], "count": 1, "downsampled": False}]
                source = "console"
    if series:
        last_step = max(item["points"][-1]["step"] for item in series)
        if progress["step"] is None or last_step > progress["step"]:
            progress["step"] = last_step
    return {"status": "ready" if series else "waiting", "source": source, "series": series,
            "progress": progress, "warnings": warnings}

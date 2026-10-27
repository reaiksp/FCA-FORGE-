import json
import os
from pathlib import Path
import uuid

import pytest

from studio.paths import DATA
from studio import telemetry


def make_job(kind="train"):
    job = {"id": uuid.uuid4().hex, "kind": kind, "status": "running", "request": {"epochs": 20}}
    directory = DATA / "jobs" / job["id"]
    directory.mkdir(parents=True)
    experiment = DATA / "experiments" / f"voice_{job['id']}" / "eval"
    experiment.mkdir(parents=True)
    return job, directory / "worker.log", experiment


def write_events(directory, points):
    pytest.importorskip("tensorboard")
    from tensorboard.compat.proto.event_pb2 import Event
    from tensorboard.compat.proto.summary_pb2 import Summary
    from tensorboard.summary.writer.event_file_writer import EventFileWriter
    writer = EventFileWriter(str(directory))
    for tag, step, value, wall_time in points:
        writer.add_event(Event(step=step, wall_time=wall_time,
                              summary=Summary(value=[Summary.Value(tag=tag, simple_value=value)])))
    writer.flush()
    writer.close()


def test_real_events_are_sorted_deduplicated_and_non_finite_values_excluded():
    job, log, experiment = make_job()
    log.write_text(f"voice_{job['id']} | epoch=3 | step=150 | batch=5/10\n", encoding="utf-8")
    write_events(experiment, [("loss/g/total", 50, 12, 100), ("loss/g/total", 100, 9, 101),
                              ("loss/g/mel", 50, 6, 100), ("loss/g/total", 125, float("nan"), 102)])
    write_events(experiment, [("loss/g/total", 100, 8, 103), ("learning_rate", 100, 0.0001, 103)])
    result = telemetry.training_metrics(job)
    assert result["status"] == "ready"
    assert result["source"] == "tensorboard"
    generator = next(item for item in result["series"] if item["tag"] == "loss/g/total")
    assert [(p["step"], p["value"]) for p in generator["points"]] == [(50, 12), (100, 8)]
    assert result["progress"] == {"epoch": 3, "total_epochs": 20, "step": 150,
                                    "batch": 5, "total_batches": 10, "percent": 12.5}
    json.dumps(result, allow_nan=False)


def test_log_progress_is_not_presented_as_a_loss_curve():
    job, log, experiment = make_job()
    log.write_text("voice_x | epoch=2 | step=40 | time=13:20:00 | training_speed=0:00:10 "
                   "| lowest_value=7.1 (epoch 1 and step 7)\n", encoding="utf-8")
    # Upstream declares this filename but does not write a documented history there.
    (experiment.parent / "training_data.json").write_text('{"loss": [9, 8]}')
    result = telemetry.training_metrics(job)
    assert result["series"] == []
    assert result["status"] == "waiting"
    assert result["progress"]["epoch"] == 2
    assert result["progress"]["percent"] == 10


def test_final_log_fallback_contains_only_the_observed_final_loss():
    job, log, _ = make_job()
    log.write_text("Training has been successfully completed with 20 epoch, 2000 steps "
                   "and 4.375 loss gen.\n", encoding="utf-8")
    result = telemetry.training_metrics(job)
    assert result["source"] == "console"
    assert result["series"][0]["points"] == [{"step": 2000, "value": 4.375, "wall_time": None}]
    assert result["progress"]["percent"] == 100
    log.write_text("Training has been successfully completed with 20 epoch, 2000 steps "
                   "and . loss gen.\n", encoding="utf-8")
    assert telemetry.training_metrics(job)["series"] == []


def test_event_sampling_keeps_endpoints_and_spike(monkeypatch):
    job, _, experiment = make_job()
    monkeypatch.setattr(telemetry, "MAX_POINTS", 12)
    write_events(experiment, [("loss/g/total", i, 1000 if i == 51 else i / 100, i + 100) for i in range(100)])
    result = telemetry.training_metrics(job)["series"][0]
    assert result["count"] == 100
    assert result["downsampled"]
    assert len(result["points"]) <= 12
    assert result["points"][0]["step"] == 0
    assert result["points"][-1]["step"] == 99
    assert any(point["value"] == 1000 for point in result["points"])


def test_missing_data_other_job_kind_and_identifier_validation():
    job, _, _ = make_job("cover")
    assert telemetry.training_metrics(job)["status"] == "not_applicable"
    assert telemetry.read_console(job)["exists"] is False
    with pytest.raises(ValueError, match="identifier"):
        telemetry.training_metrics({"id": "../../elsewhere", "kind": "train"})


def test_incremental_console_preserves_unicode_boundary_and_handles_truncation():
    job, log, _ = make_job()
    encoded = "开始训练\n".encode("utf-8")
    log.write_bytes(encoded[:2])
    first = telemetry.read_console(job, cursor=0)
    assert first["text"] == ""
    assert first["cursor"] == 0
    with log.open("ab") as stream:
        stream.write(encoded[2:])
    second = telemetry.read_console(job, cursor=first["cursor"])
    assert second["text"] == "开始训练\n"
    assert second["cursor"] == len(encoded)
    assert telemetry.read_console(job, cursor=second["cursor"])["text"] == ""
    log.write_bytes(b"new\n")
    reset = telemetry.read_console(job, cursor=second["cursor"])
    assert reset["reset"] and reset["text"] == "new\n"


def test_console_tail_and_chunk_limits_are_bounded():
    job, log, _ = make_job()
    log.write_bytes(b"abcdefghij")
    first = telemetry.read_console(job, limit=4)
    assert first["text"] == "ghij"
    assert first["truncated"] and first["start"] == 6 and first["cursor"] == 10
    first = telemetry.read_console(job, cursor=0, limit=4)
    assert first["text"] == "abcd" and first["has_more"]
    second = telemetry.read_console(job, cursor=first["cursor"], limit=4)
    assert second["text"] == "efgh" and second["has_more"]
    with pytest.raises(ValueError, match="cursor"):
        telemetry.read_console(job, cursor=-1)
    with pytest.raises(ValueError, match="limit"):
        telemetry.read_console(job, limit=telemetry.MAX_CONSOLE_BYTES + 1)


def test_console_tail_skips_leading_utf8_continuation_bytes():
    job, log, _ = make_job()
    log.write_bytes("甲乙丙\n".encode("utf-8"))
    result = telemetry.read_console(job, limit=6)
    assert result["text"] == "丙\n"
    assert "\ufffd" not in result["text"]


def test_partial_event_record_is_safe_and_existing_scalars_remain_available():
    job, _, experiment = make_job()
    write_events(experiment, [("loss/g/total", 50, 7.25, 100)])
    event_file = next(experiment.glob("events.out.tfevents.*"))
    with event_file.open("ab") as stream:
        stream.write(b"\x05\x00\x00")
    result = telemetry.training_metrics(job)
    assert result["series"][0]["points"][0]["value"] == 7.25
    json.dumps(result, allow_nan=False)


def test_event_file_replacement_at_same_length_reloads_instead_of_returning_stale_data(tmp_path):
    job, _, experiment = make_job()
    write_events(experiment, [("loss/g/total", 50, 7.25, 100)])
    assert telemetry.training_metrics(job)["series"][0]["points"][0]["value"] == 7.25
    write_events(tmp_path, [("loss/g/total", 50, 3.25, 101)])
    target = next(experiment.glob("events.out.tfevents.*"))
    source = next(tmp_path.glob("events.out.tfevents.*"))
    previous = target.stat()
    assert target.stat().st_size == source.stat().st_size
    target.write_bytes(source.read_bytes())
    os.utime(target, ns=(previous.st_atime_ns, previous.st_mtime_ns + 10_000_000))
    assert telemetry.training_metrics(job)["series"][0]["points"][0]["value"] == 3.25


def test_reader_count_is_bounded_and_non_scalar_tags_are_not_retained(monkeypatch):
    pytest.importorskip("tensorboard")
    from tensorboard.compat.proto.event_pb2 import Event
    from tensorboard.compat.proto.summary_pb2 import Summary
    from tensorboard.summary.writer.event_file_writer import EventFileWriter
    job, _, experiment = make_job()
    monkeypatch.setattr(telemetry, "MAX_EVENT_FILES", 2)
    for number in range(3):
        write_events(experiment, [("loss/g/total", number, 5, 100 + number)])
    writer = EventFileWriter(str(experiment))
    for index in range(100):
        writer.add_event(Event(step=index, wall_time=200 + index,
                         summary=Summary(value=[Summary.Value(tag=f"gen/audio_{index}",
                                         audio=Summary.Audio(encoded_audio_string=b"audio" * 100))])))
    writer.flush()
    writer.close()
    result = telemetry.training_metrics(job)
    assert any("latest 2 event files" in warning for warning in result["warnings"])
    cache = telemetry._cache[str(experiment.parent.resolve())]
    assert len(cache["readers"]) == 2
    assert all(not entry["reader"].Tags().get("audio") for entry in cache["readers"].values())

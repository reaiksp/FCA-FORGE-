"""Create explicitly synthetic event files in dist/ for manual UI QA; no model training."""
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studio.paths import write_json


def main():
    from tensorboard.compat.proto.event_pb2 import Event
    from tensorboard.compat.proto.summary_pb2 import Summary
    from tensorboard.summary.writer.event_file_writer import EventFileWriter
    directory = ROOT / 'dist' / 'monitor-qa'
    job_id = 'c' * 32
    now = time.time()
    job_dir = directory / 'jobs' / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    write_json(job_dir / 'job.json', {'id': job_id, 'kind': 'train', 'status': 'succeeded',
        'stage': 'done', 'request': {'epochs': 20, 'name': 'QA · synthetic events / 测试事件'},
        'created': now - 1200, 'updated': now, 'attempt': 1, 'artifacts': []})
    lines = ['[QA FIXTURE] Synthetic TensorBoard events and logs. No model was trained.\n']
    writer = EventFileWriter(str(directory / 'experiments' / ('voice_' + job_id) / 'eval'))
    for epoch in range(1, 21):
        step = epoch * 100
        for tag, value in (('loss/g/total', 18 * math.exp(-epoch / 8) + 4),
                           ('loss/d/adv', 2 + .2 * math.sin(epoch)),
                           ('loss/g/mel', 10 * math.exp(-epoch / 9) + 1),
                           ('learning_rate', .0001 * .98 ** epoch)):
            writer.add_event(Event(step=step, wall_time=now - 1200 + epoch * 60,
                                  summary=Summary(value=[Summary.Value(tag=tag, simple_value=value)])))
        lines.append(f'voice_{job_id} | epoch={epoch} | step={step} | time=19:00:00 | training_speed=0:01:00\n')
    writer.flush()
    writer.close()
    (job_dir / 'worker.log').write_text(''.join(lines), encoding='utf-8')
    print(directory)


if __name__ == '__main__':
    main()

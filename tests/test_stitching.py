import importlib.util
import json
from pathlib import Path
import sys
import types

import numpy as np
import soundfile as sf


def test_context_stitching_preserves_timing_and_samples_with_identity_engine(tmp_path, monkeypatch):
    # Exercise the real chunk/context/crossfade algorithm, substituting only the neural converter.
    fake = types.ModuleType("rvc.infer.infer")
    class IdentityConverter:
        def convert_audio(self, **kwargs):
            data, rate = sf.read(kwargs['audio_input_path'])
            sf.write(kwargs['audio_output_path'], data, rate, subtype='FLOAT')
    fake.VoiceConverter = IdentityConverter
    monkeypatch.setitem(sys.modules, 'rvc.infer.infer', fake)
    rate = 8000
    data = .3 * np.sin(2 * np.pi * 137 * np.arange(rate * 12 + 100) / rate)
    source, output = tmp_path / 'source.wav', tmp_path / 'converted.wav'
    sf.write(source, data, rate, subtype='FLOAT')
    config = tmp_path / 'request.json'
    config.write_text(json.dumps({'source': str(source), 'output': str(output), 'root': str(tmp_path),
                                 'model': 'placeholder', 'index': '', 'pitch': 0, 'index_rate': 0,
                                 'protect': .33, 'chunk_seconds': 5}))
    module_path = Path(__file__).resolve().parents[1] / 'scripts/rvc_worker.py'
    spec = importlib.util.spec_from_file_location('worker_under_test', module_path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    monkeypatch.setattr(sys, 'argv', ['rvc_worker.py', str(config)])
    monkeypatch.chdir(tmp_path)
    worker.main()
    actual, actual_rate = sf.read(output)
    assert actual_rate == rate
    assert len(actual) == len(data)
    assert np.max(np.abs(actual - data)) < 1e-5

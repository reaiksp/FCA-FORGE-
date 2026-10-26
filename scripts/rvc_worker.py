"""Isolated RVC inference with context overlap and exact-length stitching."""
import json
import os
from pathlib import Path
import sys
import tempfile


def main():
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    import math

    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    root = Path(request["root"])
    os.chdir(root)
    sys.path.insert(0, str(root))
    from rvc.infer.infer import VoiceConverter
    converter = VoiceConverter()
    source, rate = sf.read(request["source"], dtype="float32", always_2d=True)
    source = source.mean(axis=1)
    if not len(source) or not np.isfinite(source).all():
        raise ValueError("Invalid source audio")
    chunk = int(request["chunk_seconds"] * rate)
    # Extra context avoids a hard cut at chunk boundaries; weighted overlap smooths the join.
    overlap = int(0.2 * rate)
    context = int(0.5 * rate)
    total = np.zeros(len(source), dtype=np.float32)
    weights = np.zeros(len(source), dtype=np.float32)
    with tempfile.TemporaryDirectory(prefix="rvc-", dir=Path(request["output"]).parent) as temp:
        for start in range(0, len(source), chunk):
            left = max(0, start - overlap)
            right = min(len(source), start + chunk + overlap)
            a, b = max(0, left - context), min(len(source), right + context)
            raw = Path(temp) / "input.wav"
            out = Path(temp) / "output.wav"
            out.unlink(missing_ok=True)
            sf.write(raw, source[a:b], rate, subtype="PCM_24")
            converter.convert_audio(audio_input_path=str(raw), audio_output_path=str(out),
                                    model_path=request["model"], index_path=request["index"],
                                    pitch=request["pitch"], index_rate=request["index_rate"],
                                    protect=request["protect"], volume_envelope=1.0,
                                    f0_method="rmvpe", export_format="WAV", embedder_model="contentvec")
            data, output_rate = sf.read(out, dtype="float32", always_2d=True)
            data = data.mean(axis=1)
            if rate != output_rate:
                d = math.gcd(rate, output_rate)
                data = resample_poly(data, rate // d, output_rate // d)
            expected = b - a
            if not len(data) or not np.isfinite(data).all() or abs(len(data) - expected) > 0.15 * rate:
                raise ValueError("Invalid or truncated RVC output")
            data = np.pad(data[:expected], (0, max(0, expected - len(data))))
            data = data[left - a:right - a]
            window = np.ones(right - left, dtype=np.float32)
            if left:
                window[:2 * overlap] = np.linspace(0, 1, min(2 * overlap, len(window)))
            if right < len(source):
                window[-2 * overlap:] = np.linspace(1, 0, min(2 * overlap, len(window)))
            total[left:right] += data * window
            weights[left:right] += window
            print(f"Converted {min(start + chunk, len(source)) / rate:.1f}/{len(source) / rate:.1f}s", flush=True)
    if np.any(weights <= 0):
        raise ValueError("Uncovered samples during stitching")
    sf.write(request["output"], total / weights, rate, subtype="PCM_24")


if __name__ == "__main__":
    main()

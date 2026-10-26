"""Deterministic audio preparation and mixing; no ML dependencies."""
import math
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from scipy import signal
import soundfile as sf


def ffmpeg():
    return imageio_ffmpeg.get_ffmpeg_exe()


def decode_command(source, destination, rate=44100, mono=False):
    args = [ffmpeg(), "-nostdin", "-y", "-i", str(source), "-vn", "-ar", str(rate)]
    if mono:
        args += ["-ac", "1"]
    return args + ["-c:a", "pcm_f32le", str(destination)]


def inspect(path):
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    if len(data) == 0 or not np.isfinite(data).all():
        raise ValueError(f"Empty or non-finite audio: {Path(path).name}")
    peak = float(np.max(np.abs(data)))
    rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
    return {"duration": len(data) / rate, "sample_rate": rate, "channels": data.shape[1],
            "peak": peak, "rms_db": max(-120.0, 20 * math.log10(max(rms, 1e-6))),
            "clipped_ratio": float(np.mean(np.abs(data) >= 0.999))}


def slice_audio(source, directory, prefix, seconds=6, highpass=False):
    """Keep source offsets; exclude near-silence and flag potentially clipped clips."""
    data, rate = sf.read(source, dtype="float32", always_2d=True)
    data = data.mean(axis=1)
    if not np.isfinite(data).all():
        raise ValueError("Non-finite input audio")
    data -= data.mean() if len(data) else 0
    if highpass:
        data = signal.sosfilt(signal.butter(2, 60, fs=rate, btype="highpass", output="sos"), data)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    clips = []
    count = max(1, round(seconds * rate))
    for number, start in enumerate(range(0, len(data), count)):
        clip = data[start:start + count]
        if len(clip) < rate:
            continue
        path = directory / f"{prefix}_{number:05d}.wav"
        sf.write(path, clip, rate, subtype="PCM_24")
        info = inspect(path)
        flags = []
        if info["rms_db"] < -50:
            flags.append("quiet")
        if info["clipped_ratio"] > 0.01:
            flags.append("clipped")
        clips.append({"file": str(path), "start": start / rate, "included": "quiet" not in flags,
                      "flags": flags, **info})
    return clips


def mix(vocal, instrumental, output, vocal_db=0, music_db=-3, reverb=0):
    voice, rate = sf.read(vocal, dtype="float32", always_2d=True)
    music, music_rate = sf.read(instrumental, dtype="float32", always_2d=True)
    if rate != music_rate:
        divisor = math.gcd(rate, music_rate)
        music = signal.resample_poly(music, rate // divisor, music_rate // divisor, axis=0)
    if abs(len(voice) - len(music)) / rate > 0.3:
        raise ValueError("Vocal and instrumental differ by more than 0.3 seconds")
    channels = max(voice.shape[1], music.shape[1])
    if channels > 2:
        raise ValueError("Only mono/stereo mixing is supported")
    if voice.shape[1] == 1:
        voice = np.repeat(voice, channels, axis=1)
    if music.shape[1] == 1:
        music = np.repeat(music, channels, axis=1)
    length = max(len(voice), len(music))
    voice = np.pad(voice, ((0, length - len(voice)), (0, 0)))
    music = np.pad(music, ((0, length - len(music)), (0, 0)))
    # Short multi-tap ambience. Dry conversion is always preserved separately.
    dry = voice.copy()
    for delay, gain in ((0.041, 0.32), (0.079, 0.22), (0.137, 0.12)):
        samples = int(delay * rate)
        if samples < length:
            voice[samples:] += dry[:-samples] * reverb * gain
    mixed = voice * 10 ** (vocal_db / 20) + music * 10 ** (music_db / 20)
    if not np.isfinite(mixed).all():
        raise ValueError("Non-finite mix")
    peak = float(np.max(np.abs(mixed)))
    attenuation = min(1.0, 0.98 / max(peak, 1e-6))
    sf.write(output, mixed * attenuation, rate, subtype="PCM_24")
    return {"peak_attenuation_db": 20 * math.log10(attenuation), **inspect(output)}

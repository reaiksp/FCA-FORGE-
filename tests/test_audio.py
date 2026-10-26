import numpy as np
import pytest
import soundfile as sf

from studio.audio import inspect, mix, slice_audio


def test_mix_resamples_mono_voice_keeps_stereo_and_limits_peak(tmp_path):
    voice = tmp_path / "voice.wav"
    music = tmp_path / "music.wav"
    output = tmp_path / "mix.wav"
    sf.write(voice, np.ones(40000, dtype=np.float32) * .8, 40000, subtype="FLOAT")
    sf.write(music, np.full((48000, 2), .8, dtype=np.float32), 48000, subtype="FLOAT")
    stats = mix(voice, music, output, music_db=0)
    assert stats["sample_rate"] == 40000
    assert stats["channels"] == 2
    assert stats["duration"] == 1
    assert .97 < stats["peak"] <= .981
    assert stats["peak_attenuation_db"] < 0


def test_mix_rejects_drift_instead_of_silently_stretching(tmp_path):
    paths = [tmp_path / n for n in ("a.wav", "b.wav")]
    sf.write(paths[0], np.ones(8000), 8000)
    sf.write(paths[1], np.ones(16000), 8000)
    with pytest.raises(ValueError, match="0.3 seconds"):
        mix(*paths, tmp_path / "bad.wav")


def test_slicing_preserves_offsets_and_excludes_silence(tmp_path):
    rate = 8000
    source = tmp_path / "source.wav"
    wave = .2 * np.sin(2 * np.pi * 220 * np.arange(2 * rate) / rate)
    sf.write(source, np.concatenate([wave, np.zeros(2 * rate), wave]), rate)
    clips = slice_audio(source, tmp_path / "clips", "source", seconds=2)
    assert [c["start"] for c in clips] == [0, 2, 4]
    assert [c["included"] for c in clips] == [True, False, True]
    assert clips[1]["flags"] == ["quiet"]


def test_non_finite_audio_rejected(tmp_path):
    source = tmp_path / "bad.wav"
    sf.write(source, [0.0, float("nan")], 8000, subtype="FLOAT")
    with pytest.raises(ValueError, match="non-finite"):
        inspect(source)

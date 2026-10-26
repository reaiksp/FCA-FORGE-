import shutil
import os
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

from studio import audio
from studio.engines import engine_command, convert_command, rvc_environment
from studio.paths import DATA, ROOT, UPSTREAM, CONFIG, python_for, read_json, write_json, digest, relative, resolve


def artifact(path, kind):
    path = Path(path)
    record = {"file": relative(path), "kind": kind, "name": path.name, "sha256": digest(path)}
    if path.suffix.lower() == ".wav":
        record.update(audio.inspect(path))
    return record


def valid_files(record):
    try:
        return all(resolve(value["file"]).stat().st_size > 0 and digest(resolve(value["file"])) == value["sha256"]
                   for value in record["artifacts"])
    except (OSError, ValueError, KeyError):
        return False


def valid_weights(record):
    try:
        return bool(record['weights']) and all(digest(p['path']) == p['sha256'] for p in record['weights'])
    except (OSError, KeyError):
        return False


def decode(ctx, source, name, mono=False):
    output = ctx.directory / f"{name}.wav"
    def action():
        ctx.run(audio.decode_command(source, output, mono=mono))
        return {"artifacts": [artifact(output, name)]}
    ctx.stage(name, action, valid_files)
    return output


def separate(ctx, source, name, model, cleanup=False):
    directory = ctx.directory / name
    def action():
        directory.mkdir(exist_ok=True)
        request = directory / "request.json"
        result = directory / "result.json"
        write_json(request, {"source": str(source), "model": model, "output": str(directory),
                             "result": str(result), "cleanup": cleanup})
        executable = python_for(".venv-separator")
        if not executable.exists():
            raise RuntimeError("Separation environment missing. Run scripts/setup.ps1 -Separator")
        # audio-separator checks the ffmpeg command; expose the bundled executable locally.
        tools = DATA / 'tools'
        tools.mkdir(exist_ok=True)
        binary = tools / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
        if not binary.exists():
            shutil.copy2(audio.ffmpeg(), binary)
        ctx.run([executable, ROOT / "scripts" / "separator_worker.py", request],
                env={'PATH': str(tools) + os.pathsep + os.environ.get('PATH', '')})
        output = read_json(result)
        items = [artifact(p, kind) for kind, p in output.items()]
        return {"artifacts": items}
    return ctx.stage(name, action, valid_files)


def find_stem(record, kind):
    return resolve(next(item["file"] for item in record["artifacts"] if item["kind"] == kind))


def prepare(ctx):
    request = ctx.job["request"]
    dataset_id = ctx.job["id"]
    directory = DATA / "datasets" / dataset_id
    directory.mkdir(exist_ok=True)
    clips = []
    artifacts = []
    sources = []
    for number, value in enumerate(request["files"]):
        source = resolve(value)
        sources.append({"file": value, "sha256": digest(source)})
        clean = decode(ctx, source, f"source-{number}", mono=True)
        if request["separate"]:
            stems = separate(ctx, clean, f"separate-{number}", CONFIG["separation_model"])
            artifacts += stems["artifacts"]
            clean = find_stem(stems, "vocals")
        if request.get("dereverb"):
            stems = separate(ctx, clean, f"dereverb-{number}", request["dereverb"], cleanup=True)
            artifacts += stems["artifacts"]
            clean = find_stem(stems, "dry")
        def cut():
            result = audio.slice_audio(clean, directory / "clips", f"s{number:04d}",
                                       request["clip_seconds"], request["highpass"])
            for item in result:
                item["file"] = relative(item["file"])
                item["source"] = value
                item["sha256"] = digest(resolve(item["file"]))
            return {"clips": result, "artifacts": [artifact(resolve(c["file"]), "clip") for c in result]}
        sliced = ctx.stage(f"slice-{number}", cut, valid_files)
        clips += sliced["clips"]
        ctx.check()
    if not clips or not any(c["included"] for c in clips):
        raise ValueError("No usable clips. Check duration and silence level.")
    write_json(directory / "dataset.json", {"id": dataset_id, "name": request["name"],
               "sources": sources, "processing": request, "clips": clips})
    return {"dataset_id": dataset_id, "artifacts": artifacts + [artifact(directory / "dataset.json", "dataset")]}


def train(ctx):
    request = ctx.job["request"]
    dataset = read_json(DATA / "datasets" / request["dataset_id"] / "dataset.json")
    # Snapshot reviewed selection on first attempt. Retry never changes training inputs.
    snapshot = ctx.directory / "dataset-snapshot.json"
    if snapshot.exists():
        selected = read_json(snapshot)
    else:
        selected = [item for item in dataset["clips"] if item["included"]]
        if not selected:
            raise ValueError("Dataset has no selected clips")
        write_json(snapshot, selected)
    name = "voice_" + ctx.job["id"]
    experiment = DATA / "experiments" / name
    train_input = ctx.directory / "training-input"
    train_input.mkdir(exist_ok=True)
    for item in selected:
        source = resolve(item["file"])
        if digest(source) != item["sha256"]:
            raise ValueError("Dataset clip changed after preparation")
        target = train_input / source.name
        if not target.exists():
            shutil.copy2(source, target)
    sr, cores = request["sample_rate"], request["cpu_cores"]
    env = rvc_environment()
    ctx.stage("pretrained", lambda: _pretrained(ctx, sr, env), valid_weights)
    def upstream_stage(stage, script, args, outputs):
        def action():
            ctx.run(engine_command(script, *args), cwd=UPSTREAM, env=env)
            files = outputs()
            if not files:
                raise RuntimeError(f"No outputs from {stage}")
            return {"artifacts": [artifact(p, stage) for p in files]}
        return ctx.stage(stage, action, valid_files)
    upstream_stage("preprocess", "rvc/train/preprocess/preprocess.py",
                   [experiment, train_input, sr, cores, "Skip", False, 3.0, 0.3, "none"],
                   lambda: list((experiment / "sliced_audios").glob("*.wav")))
    def feature_files():
        files = [experiment / "filelist.txt", experiment / "config.json"]
        for wav in (experiment / "sliced_audios").glob("*.wav"):
            for feature in (experiment / "extracted" / f"{wav.stem}.npy",
                            experiment / "f0" / f"{wav.name}.npy", experiment / "f0_voiced" / f"{wav.name}.npy"):
                values = np.load(feature, allow_pickle=False)
                if not values.size or not np.isfinite(values).all():
                    raise ValueError(f"Invalid extracted feature: {feature.name}")
                files.append(feature)
        return files
    upstream_stage("features", "rvc/train/extract/extract.py",
                   [experiment, "rmvpe", cores, "0", sr, "contentvec", "None", 0],
                   feature_files)
    # Upstream extraction can log warnings and return zero; verify matching features ourselves.
    for wav in (experiment / "sliced_audios").glob("*.wav"):
        files = [experiment / "extracted" / f"{wav.stem}.npy",
                 experiment / "f0" / f"{wav.name}.npy", experiment / "f0_voiced" / f"{wav.name}.npy"]
        for file in files:
            values = np.load(file, allow_pickle=False)
            if values.size == 0 or not np.isfinite(values).all():
                raise ValueError(f"Invalid extracted feature: {file.name}")
    if not (experiment / "filelist.txt").read_text(encoding="utf-8").strip():
        raise ValueError("Empty training file list")
    folder = UPSTREAM / "rvc/models/pretraineds/hifi-gan"
    def weights():
        return [p for p in experiment.glob("*.pth") if not p.name.startswith(("G_", "D_"))]
    upstream_stage("training", "rvc/train/train.py", [name, request["save_every"], request["epochs"],
                   folder / f"f0G{sr // 1000}k.pth", folder / f"f0D{sr // 1000}k.pth", "0",
                   request["batch_size"], sr, True, True, False, False, "HiFi-GAN", True], weights)
    upstream_stage("index", "rvc/train/process/extract_index.py", [experiment, "Auto"],
                   lambda: list(experiment.glob("*.index")))
    # Keep all checkpoints for user listening; newest becomes the initial default.
    exports = sorted(weights(), key=lambda p: p.stat().st_mtime, reverse=True)
    voice = register_voice(request["name"], exports[0], next(experiment.glob("*.index")),
                           voice_id=ctx.job["id"], provenance={"dataset": request["dataset_id"],
                           "training_job": ctx.job["id"], "upstream": CONFIG["commit"]})
    return {"voice_id": voice["id"], "artifacts": [artifact(p, "checkpoint") for p in exports] +
            [artifact(experiment / "config.json", "config"), artifact(snapshot, "dataset_snapshot")]}


def _pretrained(ctx, sr, env):
    options = ['--sample-rate', str(sr)] if sr else ['--inference-only']
    ctx.run([python_for('.venv-rvc'), ROOT / 'scripts/download_models.py', *options],
            cwd=UPSTREAM, env=env)
    # These files are outside DATA. Record external hashes without exposing a download endpoint.
    manifest = read_json(ROOT / 'configs/models.json')
    files = [UPSTREAM / item['destination'] for item in manifest['files']
             if not item.get('sample_rate') or item['sample_rate'] == sr]
    return {"artifacts": [], "weights": [{"path": str(p), "sha256": digest(p)} for p in files]}


def register_voice(name, model, index=None, voice_id=None, provenance=None):
    voice_id = voice_id or uuid.uuid4().hex
    folder = DATA / "voices" / voice_id
    folder.mkdir(exist_ok=True)
    target = folder / "model.pth"
    shutil.copy2(model, target)
    index_target = folder / "model.index"
    if index:
        shutil.copy2(index, index_target)
    voice = {"id": voice_id, "name": name, "engine": "rvc", "model": relative(target),
             "index": relative(index_target) if index else None, "sha256": digest(target),
             "provenance": provenance or {"imported": True}}
    write_json(folder / "voice.json", voice)
    return voice


def cover(ctx):
    request = ctx.job["request"]
    source = decode(ctx, resolve(request["source"]), "source")
    artifacts = [artifact(source, "source")]
    if request["input_kind"] == "song":
        stems = separate(ctx, source, "separation", CONFIG["separation_model"])
        vocals, music = find_stem(stems, "vocals"), find_stem(stems, "instrumental")
        artifacts += stems["artifacts"]
    else:
        vocals = source
        music = decode(ctx, resolve(request["instrumental"]), "instrumental") if request.get("instrumental") else None
        if music:
            artifacts.append(artifact(music, "instrumental"))
    if request.get("dereverb"):
        clean = separate(ctx, vocals, "dereverb", request["dereverb"], cleanup=True)
        vocals = find_stem(clean, "dry")
        artifacts += clean["artifacts"]
    voice = read_json(DATA / "voices" / request["voice_id"] / "voice.json")
    model = resolve(voice["model"])
    if digest(model) != voice["sha256"]:
        raise ValueError("Voice checkpoint hash changed")
    converted = ctx.directory / "converted.wav"
    ctx.stage('base-models', lambda: _pretrained(ctx, None, rvc_environment()), valid_weights)
    def conversion():
        payload = {"source": str(vocals), "output": str(converted), "model": str(model),
                   "index": str(resolve(voice["index"])) if voice["index"] else "",
                   "pitch": request["pitch"], "index_rate": request["index_rate"] if voice["index"] else 0,
                   "protect": request["protect"], "chunk_seconds": request["chunk_seconds"],
                   "root": str(UPSTREAM)}
        config = ctx.directory / "conversion.json"
        write_json(config, payload)
        ctx.run(convert_command(config), cwd=UPSTREAM, env=rvc_environment())
        if abs(audio.inspect(converted)["duration"] - audio.inspect(vocals)["duration"]) > 0.15:
            raise ValueError("Converted audio duration drift exceeds 0.15 seconds")
        return {"artifacts": [artifact(converted, "converted")]}
    artifacts += ctx.stage("conversion", conversion, valid_files)["artifacts"]
    if music:
        output = ctx.directory / "cover.wav"
        def mixing():
            stats = audio.mix(converted, music, output, request["vocal_db"], request["music_db"], request["reverb"])
            return {"artifacts": [artifact(output, "mix")], "stats": stats}
        artifacts += ctx.stage("mix", mixing, valid_files)["artifacts"]
    manifest = ctx.directory / "export.json"
    write_json(manifest, {"request": request, "voice": voice, "upstream": CONFIG,
                           "artifacts": artifacts, "job_id": ctx.job["id"]})
    artifacts.append(artifact(manifest, "manifest"))
    return {"artifacts": artifacts}


def execute(ctx):
    # A retry may reuse decoded stems only when its original uploaded files are unchanged.
    request = ctx.job['request']
    inputs = request.get('files', []) if ctx.job['kind'] == 'prepare' else (
        [value for value in (request.get('source'), request.get('instrumental')) if value]
        if ctx.job['kind'] == 'cover' else [])
    snapshot = ctx.directory / 'input-hashes.json'
    actual = {name: digest(resolve(name)) for name in inputs}
    if snapshot.exists() and read_json(snapshot) != actual:
        raise ValueError('Input files changed since the original run; create a new job.')
    if not snapshot.exists():
        write_json(snapshot, actual)
    return {"prepare": prepare, "train": train, "cover": cover}[ctx.job["kind"]](ctx)

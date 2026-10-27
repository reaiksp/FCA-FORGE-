from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
import shutil
import uuid
import zipfile

from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.background import BackgroundTask

from studio.engines import capabilities
from studio.jobs import JobManager
from studio.paths import ROOT, DATA, CONFIG, initialize, resolve, relative, read_json, write_json, digest

ID = r"^[a-f0-9]{32}$"


class Prepare(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    files: list[str] = Field(min_length=1, max_length=300)
    separate: bool = False
    dereverb: str = ""
    clip_seconds: float = Field(default=6, ge=2, le=15)
    highpass: bool = False


class Train(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    dataset_id: str = Field(pattern=ID)
    sample_rate: Literal[40000, 48000] = 40000
    epochs: int = Field(default=200, ge=1, le=10000)
    batch_size: int = Field(default=4, ge=1, le=32)
    save_every: int = Field(default=10, ge=1, le=1000)
    cpu_cores: int = Field(default=4, ge=1, le=32)


class Cover(BaseModel):
    source: str
    input_kind: Literal["song", "dry"] = "song"
    instrumental: str | None = None
    voice_id: str = Field(pattern=ID)
    pitch: int = Field(default=0, ge=-24, le=24)
    index_rate: float = Field(default=0.3, ge=0, le=1)
    protect: float = Field(default=0.33, ge=0, le=0.5)
    chunk_seconds: int = Field(default=30, ge=5, le=60)
    dereverb: str = ""
    vocal_db: float = Field(default=0, ge=-24, le=12)
    music_db: float = Field(default=-3, ge=-24, le=12)
    reverb: float = Field(default=0.1, ge=0, le=1)


class ClipSelection(BaseModel):
    included: list[str]


class VoiceImport(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    model: str
    index: str | None = None


def check_cleanup(value):
    if value and (Path(value).name != value or not value.endswith((".onnx", ".pth", ".ckpt"))):
        raise ValueError("Cleanup model must be a model filename")


@asynccontextmanager
async def lifespan(app):
    app.state.manager = JobManager()
    app.state.manager.start()
    yield
    app.state.manager.close()


app = FastAPI(title="Cover Studio", version="0.2.0", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])


@app.middleware("http")
async def local_origin(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin write rejected"}, status_code=403)
    return await call_next(request)


@app.exception_handler(ValueError)
async def invalid_value(request, error):
    return JSONResponse({"detail": str(error)}, status_code=400)


def manager(request):
    return request.app.state.manager


def collection(name, filename):
    return [read_json(p) for p in sorted((DATA / name).glob(f"*/{filename}"), key=lambda p: p.stat().st_mtime, reverse=True)]


@app.get("/api/state")
def state(request: Request):
    return {"jobs": manager(request).snapshot(), "datasets": collection("datasets", "dataset.json"),
            "voices": collection("voices", "voice.json"), "engines": capabilities(), "defaults": CONFIG, "version": app.version}


@app.get("/api/diagnostics")
def diagnostics():
    path = DATA / "diagnostics.json"
    return read_json(path) if path.exists() else {"status": "not_run", "message": "Run scripts/doctor.py"}


@app.post("/api/uploads")
async def upload(files: list[UploadFile] = File(...)):
    initialize()
    output = []
    allowed = {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus", ".aac", ".mp4", ".wma", ".pth", ".index"}
    if not 1 <= len(files) <= 300:
        raise ValueError("Select 1–300 files")
    for file in files:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in allowed:
            raise ValueError("Unsupported file type")
        folder = DATA / "uploads" / uuid.uuid4().hex
        folder.mkdir()
        target = folder / ("input" + suffix)
        temporary = folder / "upload.part"
        size = 0
        try:
            with temporary.open("wb") as stream:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 2 * 1024 ** 3:
                        raise ValueError("Each file must be under 2 GiB")
                    stream.write(chunk)
            if size == 0:
                raise ValueError("Empty file")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
            await file.close()
        value = {"file": relative(target), "name": file.filename, "size": size, "sha256": digest(target)}
        write_json(folder / "upload.json", value)
        output.append(value)
    return output


@app.post("/api/jobs/prepare")
def prepare_job(payload: Prepare, request: Request):
    check_cleanup(payload.dereverb)
    for file in payload.files:
        resolve(file)
    return manager(request).submit("prepare", payload.model_dump())


@app.post("/api/jobs/train")
def train_job(payload: Train, request: Request):
    resolve(f"datasets/{payload.dataset_id}/dataset.json")
    if payload.save_every > payload.epochs:
        raise ValueError("Save interval must not exceed total epochs")
    return manager(request).submit("train", payload.model_dump())


@app.post("/api/jobs/cover")
def cover_job(payload: Cover, request: Request):
    resolve(payload.source)
    if payload.instrumental:
        resolve(payload.instrumental)
    resolve(f"voices/{payload.voice_id}/voice.json")
    check_cleanup(payload.dereverb)
    return manager(request).submit("cover", payload.model_dump())


@app.patch("/api/datasets/{dataset_id}")
def select_clips(dataset_id: str, payload: ClipSelection, request: Request):
    if any(j["kind"] == "train" and j["status"] in ("queued", "running") and
           j["request"]["dataset_id"] == dataset_id for j in manager(request).snapshot()):
        raise ValueError("Dataset is in use by a queued/running training job")
    path = resolve(f"datasets/{dataset_id}/dataset.json")
    data = read_json(path)
    known = {c["file"] for c in data["clips"]}
    if not set(payload.included) <= known:
        raise ValueError("Unknown dataset clip")
    for clip in data["clips"]:
        clip["included"] = clip["file"] in payload.included
    write_json(path, data)
    return data


@app.post("/api/voices/import")
def import_voice(payload: VoiceImport):
    from studio.pipeline import register_voice
    model = resolve(payload.model)
    index = resolve(payload.index) if payload.index else None
    if model.suffix != ".pth" or (index and index.suffix != ".index"):
        raise ValueError("Expected a .pth checkpoint and optional .index")
    return register_voice(payload.name, model, index)


@app.get("/api/voices/{voice_id}/export")
def export_voice(voice_id: str):
    voice = read_json(resolve(f"voices/{voice_id}/voice.json"))
    target = DATA / "voices" / voice["id"] / f"export-{uuid.uuid4().hex}.zip"
    manifest = {**voice, "model": "model.pth", "index": "model.index" if voice["index"] else None}
    import json
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(resolve(voice["model"]), "model.pth")
        if voice["index"]:
            archive.write(resolve(voice["index"]), "model.index")
        archive.writestr("voice.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return FileResponse(target, filename=f"voice-{voice['id'][:8]}.zip", background=BackgroundTask(target.unlink, missing_ok=True))


@app.post("/api/jobs/{job_id}/{action}")
def job_action(job_id: str, action: Literal["cancel", "retry"], request: Request):
    try:
        return getattr(manager(request), action)(job_id)
    except KeyError:
        raise HTTPException(404, "Job not found")


def existing_job(request: Request, job_id: str):
    with manager(request).lock:
        job = manager(request).jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        return job.copy()


@app.get("/api/jobs/{job_id}/metrics")
def metrics(job_id: str, request: Request):
    from studio.telemetry import training_metrics
    return training_metrics(existing_job(request, job_id))


@app.get("/api/jobs/{job_id}/console")
def console(job_id: str, request: Request, cursor: int | None = Query(default=None, ge=0)):
    from studio.telemetry import read_console
    return read_console(existing_job(request, job_id), cursor=cursor)


@app.get("/api/jobs/{job_id}/log")
def log(job_id: str, request: Request):
    from studio.telemetry import read_console
    return {"text": read_console(existing_job(request, job_id), limit=24000)["text"]}


@app.get("/api/files/{file:path}")
def file_response(file: str, download: bool = False):
    try:
        path = resolve(file)
    except ValueError:
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=path.name if download else None)


app.mount("/", StaticFiles(directory=ROOT / "studio" / "static", html=True), name="web")

import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("COVER_STUDIO_DATA", ROOT / "data")).resolve()
UPSTREAM = ROOT / "vendor" / "Applio"
CONFIG = json.loads((ROOT / "configs" / "upstream.json").read_text(encoding="utf-8"))


def python_for(name):
    directory = ROOT / name
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def initialize():
    for name in ("uploads", "jobs", "datasets", "voices", "experiments", "settings"):
        (DATA / name).mkdir(parents=True, exist_ok=True)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = Path(stream.name)
    os.replace(temporary, path)


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def relative(path):
    return Path(path).resolve().relative_to(DATA).as_posix()


def resolve(value):
    path = (DATA / value).resolve()
    if not path.is_relative_to(DATA) or not path.is_file():
        raise ValueError("File is missing or outside the data directory")
    return path

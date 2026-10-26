"""Read-only engine/GPU checks. Does not train or convert audio."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studio.paths import DATA, UPSTREAM, CONFIG, python_for, initialize, write_json


def probe(executable, code, cwd=ROOT):
    if not Path(executable).exists():
        return {"ok": False, "detail": "Environment is not installed"}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        result = subprocess.run([str(executable), "-c", code], cwd=cwd, capture_output=True,
                                encoding="utf-8", errors="replace", timeout=90, creationflags=flags,
                                env={**os.environ, "PYTHONUTF8": "1", "APPLIO_CONFIG_DIR": str(DATA / "settings")})
        return {"ok": result.returncode == 0, "detail": (result.stdout + result.stderr).strip()[-12000:]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "detail": str(error)}


def main():
    initialize()
    gpu = """import torch, json
assert torch.cuda.is_available(), 'CUDA unavailable'
x = torch.randn((256, 256), device='cuda')
y = x @ x.T
torch.cuda.synchronize()
assert torch.isfinite(y).all()
print(json.dumps({'torch': torch.__version__, 'cuda': torch.version.cuda, 'gpu': torch.cuda.get_device_name(), 'capability': torch.cuda.get_device_capability(), 'matrix_test': True}))
"""
    report = {"python": sys.version, "scope": "imports + CUDA matrix operation; no training or real conversion",
              "upstream_expected": CONFIG["commit"],
              "app": probe(sys.executable, "import fastapi, numpy, scipy, soundfile, imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"),
              "rvc_gpu": probe(python_for(".venv-rvc"), gpu),
              "rvc_import": probe(python_for(".venv-rvc"),
                 "from rvc.infer.infer import VoiceConverter; from rvc.lib.utils import get_hubert_model_class; get_hubert_model_class(); import faiss, sklearn; print('RVC / HuBERT / FAISS imports OK')", UPSTREAM),
              "separator_gpu": probe(python_for(".venv-separator"), gpu),
              "separator_import": probe(python_for(".venv-separator"),
                 "from audio_separator.separator import Separator; print('Separator import OK')")}
    if (UPSTREAM / ".git").exists():
        revision = subprocess.run(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], capture_output=True, text=True)
        report["upstream_actual"] = revision.stdout.strip()
    report["status"] = "ready" if all(report[k]["ok"] for k in ("app", "rvc_gpu", "rvc_import", "separator_gpu", "separator_import")) and report.get("upstream_actual") == CONFIG["commit"] else "needs_attention"
    write_json(DATA / "diagnostics.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

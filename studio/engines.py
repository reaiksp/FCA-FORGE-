"""Adapters contain no GPU imports; workers run in their own environments."""
from studio.paths import DATA, ROOT, UPSTREAM, CONFIG, python_for


def rvc_environment():
    return {"APPLIO_LOGS_DIR": str(DATA / "experiments"),
            "APPLIO_CONFIG_DIR": str(DATA / "settings"),
            "APPLIO_ROOT": str(UPSTREAM), "APPLIO_CODE_ROOT": str(UPSTREAM),
            "OMP_NUM_THREADS": "4"}


def engine_command(script, *arguments):
    executable = python_for(".venv-rvc")
    if not executable.exists() or not (UPSTREAM / "core.py").exists():
        raise RuntimeError("RVC environment is missing. Run scripts/setup.ps1 -Engine")
    return [executable, UPSTREAM / script, *map(str, arguments)]


def capabilities():
    return {"rvc": {"train": True, "convert": True, "needs_reference": False,
                    "sample_rates": [40000, 48000], "f0": ["rmvpe"]},
            "seed_vc": {"available": False, "handoff": "docs/SEED_VC_B_ARCHITECTURE_HANDOFF.md"}}


def convert_command(request_file):
    return [python_for(".venv-rvc"), ROOT / "scripts" / "rvc_worker.py", request_file]

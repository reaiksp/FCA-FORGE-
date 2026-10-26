"""Download the explicit A-model manifest using upstream's resume-capable client."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor" / "Applio"))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample-rate', type=int, choices=[40000, 48000], default=40000)
    parser.add_argument('--inference-only', action='store_true')
    args = parser.parse_args()
    # Run through the RVC environment, where the upstream downloader's dependencies live.
    from rvc.lib.tools.http_download import download_http
    from studio.paths import digest, write_json, DATA
    manifest = json.loads((ROOT / "configs" / "models.json").read_text(encoding="utf-8"))
    root = ROOT / "vendor" / "Applio"
    records = []
    for item in manifest["files"]:
        if args.inference_only and item.get('sample_rate'):
            continue
        if item.get('sample_rate') and item['sample_rate'] != args.sample_rate:
            continue
        target = root / item["destination"]
        print(f"Downloading / verifying {target.name}", flush=True)
        expected = item.get("sha256")
        if not target.exists() or (expected and digest(target) != expected):
            download_http(item["url"], target, sha256=expected)
        actual = digest(target)
        if expected and actual != expected:
            raise ValueError(f"Hash mismatch: {target.name}")
        records.append({**item, "observed_sha256": actual, "size": target.stat().st_size})
    write_json(DATA / "model-downloads.json", {"files": records})
    print("Model downloads complete. No training was started.")


if __name__ == "__main__":
    main()

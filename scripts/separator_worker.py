"""Audio-separator adapter; select explicit stems instead of guessing file order."""
import json
from pathlib import Path
import sys


def main():
    from audio_separator.separator import Separator
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    output = Path(request["output"])
    separator = Separator(output_dir=str(output), output_format="WAV", use_soundfile=True,
                          normalization_threshold=0.99, amplification_threshold=0.0,
                          model_file_dir=str(root / "models" / "separation"))
    separator.load_model(model_filename=request["model"])
    names = {"Vocals": "vocals", "Instrumental": "instrumental", "No Reverb": "dry",
             "Reverb": "reverb", "No Echo": "dry", "Echo": "echo", "Dry": "dry", "No dry": "reverb"}
    files = separator.separate(request["source"], custom_output_names=names)
    stems = {}
    for file in files:
        path = Path(file)
        if not path.is_absolute():
            path = output / path
        stem = path.stem.lower()
        for kind in ("vocals", "instrumental", "dry", "reverb", "echo"):
            if stem == kind:
                stems[kind] = str(path.resolve())
    if request["cleanup"]:
        if "dry" not in stems:
            raise ValueError("Cleanup model must expose a 'Dry', 'No Reverb' or 'No Echo' stem")
    elif not {"vocals", "instrumental"} <= stems.keys():
        raise ValueError(f"Expected vocals/instrumental stems, received: {files}")
    Path(request["result"]).write_text(json.dumps(stems), encoding="utf-8")


if __name__ == "__main__":
    main()

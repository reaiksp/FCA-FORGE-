import os
from pathlib import Path
import sys
import threading
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    import uvicorn
    # Loopback only; use a single worker to preserve GPU task serialization.
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:7860")).start()
    uvicorn.run("studio.app:app", host="127.0.0.1", port=7860, workers=1)

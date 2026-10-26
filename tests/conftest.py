import os
from pathlib import Path
import tempfile

# Tests never touch the user's real datasets, models or jobs.
TEST_DIRECTORY = tempfile.TemporaryDirectory(prefix="cover-studio-tests-")
os.environ["COVER_STUDIO_DATA"] = str(Path(TEST_DIRECTORY.name) / "data")

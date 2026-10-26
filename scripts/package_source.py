"""Build a Git-ready source ZIP, respecting .gitignore and excluding local data."""
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    entries = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT)
    names = sorted({n.decode('utf-8') for n in entries.split(b'\0') if n})
    blocked = {'.git', 'data', 'models', 'vendor', 'reference', 'dist'}
    target = ROOT / 'dist' / 'CoverStudio-source.zip'
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            path = ROOT / name
            if path.is_symlink() or not path.is_file() or Path(name).parts[0] in blocked or Path(name).parts[0].startswith('.venv'):
                continue
            archive.write(path, 'CoverStudio/' + name)
    print(target)


if __name__ == '__main__':
    main()

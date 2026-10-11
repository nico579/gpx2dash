"""Build the standalone folder in an isolated environment (used by GitHub Actions)."""
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    environment = ROOT / "build_venv"
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    for command in [
        [str(python), "-m", "pip", "install", "--require-hashes", "-r", str(ROOT / "requirements-build.txt")],
        [str(python), "-m", "pip", "check"],
        [str(python), "-m", "PyInstaller", "--noconfirm", "--clean", str(ROOT / "gpx2dash.spec")],
    ]:
        subprocess.run(command, cwd=ROOT, check=True)
    executable = ROOT / "dist/gpx2dash" / ("gpx2dash.exe" if sys.platform == "win32" else "gpx2dash")
    if not executable.is_file():
        raise SystemExit("Built executable missing: " + str(executable))
    print("Bundle ready: " + str(executable))


if __name__ == "__main__":
    main()

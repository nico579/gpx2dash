"""Archive the tested folder, preserving executable bits on Unix."""
import argparse
import hashlib
from pathlib import Path
import shutil

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("asset")
    parser.add_argument("--format", choices=("zip", "gztar"), required=True)
    args = parser.parse_args()
    base = Path("dist")
    archive = Path(shutil.make_archive(str(base / args.asset), args.format, root_dir=base, base_dir="gpx2dash"))
    archive.with_name(archive.name + ".sha256").write_text(
        hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n", encoding="ascii")
    print(archive)


if __name__ == "__main__":
    main()

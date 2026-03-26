"""Build helper for packaging C4D2GS for commercial distribution.

Usage:
    python build.py

This script produces:
    release/C4D2GS_v1.0.0.zip
"""

import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import re

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src" / "c4d2gs"
RELEASE_DIR = ROOT / "release"


def ensure_release_dir():
    if RELEASE_DIR.exists():
        print(f"Cleaning existing release folder: {RELEASE_DIR}")
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)


def create_install_file():
    install_path = RELEASE_DIR / "INSTALL.txt"
    install_path.write_text(
        "C4D2GS Installation Instructions\n\n"
        "1) Extract the ZIP to a temporary folder.\n"
        "2) Copy the c4d2gs/ folder to your Cinema 4D plugins directory:\n"
        "   - Windows: %APPDATA%\\Maxon\\Maxon Cinema 4D <version>\\plugins\\\n"
        "   - macOS: ~/Library/Preferences/Maxon/Maxon Cinema 4D <version>/plugins/\n"
        "3) Restart Cinema 4D.\n"
        "4) Open Extensions -> C4D2GS and run the plugin.\n\n"
        "License: use is governed by EULA.txt. Resale/re-distribution is prohibited unless approved.\n"
    )
    return install_path


def copy_documents():
    for name in ["README.md", "EULA.txt", "INSTALL.txt"]:
        src = ROOT / "docs" / name
        if src.exists():
            shutil.copy(src, RELEASE_DIR / name)
        else:
            print(f"Warning: missing {name}")


def make_release_zip():
    zip_path = RELEASE_DIR / "C4D2GS_v1.0.0.zip"
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as z:
        # Add all .py and .pyp files from SRC_DIR
        for item in SRC_DIR.rglob("*.py"):
            z.write(item, Path("c4d2gs") / item.relative_to(SRC_DIR))
        for item in SRC_DIR.rglob("*.pyp"):
            z.write(item, Path("c4d2gs") / item.relative_to(SRC_DIR))

        # Add documentation files
        for name in ["README.md", "EULA.txt", "INSTALL.txt"]:
            doc_path = RELEASE_DIR / name
            if doc_path.exists():
                z.write(doc_path, f"c4d2gs/{name}")
            else:
                print(f"Warning: {name} not found for release package.")

    print(f"Created release zip: {zip_path}")
    return zip_path


def reset_output_path():
    settings_path = SRC_DIR / "_settings.py"
    if settings_path.exists():
        content = settings_path.read_text()
        # Replace any existing output path with a default or empty value
        content = re.sub(r'output_path\s*=\s*".*?"', 'output_path = ""', content)
        settings_path.write_text(content)
        print("Output path reset in _settings.py")
    else:
        print("Warning: _settings.py not found. Output path not reset.")


def main():
    print("Building release package...")
    reset_output_path()
    ensure_release_dir()
    create_install_file()
    copy_documents()
    make_release_zip()
    print("Release build completed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Build failed:", e)
        raise

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
import tokenize
from io import StringIO

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


def copy_source_files():
    """Copy all .py and .pyp files from SRC_DIR to RELEASE_DIR/c4d2gs for processing."""
    c4d2gs_dir = RELEASE_DIR / "c4d2gs"
    c4d2gs_dir.mkdir(exist_ok=True)

    # Copy all Python files
    for item in SRC_DIR.rglob("*.py"):
        dest = c4d2gs_dir / item.relative_to(SRC_DIR)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(item, dest)

    # Copy all .pyp files
    for item in SRC_DIR.rglob("*.pyp"):
        dest = c4d2gs_dir / item.relative_to(SRC_DIR)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(item, dest)


def clean_release_files():
    """Remove comments and docstrings from all Python files in the release directory."""
    c4d2gs_dir = RELEASE_DIR / "c4d2gs"
    for file in c4d2gs_dir.rglob("*.py"):
        print(f"Cleaning comments from {file}...")
        remove_comments_from_python(file)


def make_release_zip():
    zip_path = RELEASE_DIR / "C4D2GS_v1.0.0.zip"
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as z:
        # Add all .py and .pyp files from RELEASE_DIR/c4d2gs
        c4d2gs_dir = RELEASE_DIR / "c4d2gs"
        for item in c4d2gs_dir.rglob("*.py"):
            z.write(item, item.relative_to(RELEASE_DIR))
        for item in c4d2gs_dir.rglob("*.pyp"):
            z.write(item, item.relative_to(RELEASE_DIR))

        # Add documentation files
        for name in ["README.md", "EULA.txt", "INSTALL.txt"]:
            doc_path = RELEASE_DIR / name
            if doc_path.exists():
                z.write(doc_path, f"c4d2gs/{name}")
            else:
                print(f"Warning: {name} not found for release package.")

    print(f"Created release zip: {zip_path}")
    return zip_path


def remove_comments_from_python(file_path):
    """Remove # comments and triple-quoted docstrings, preserving code structure."""
    with open(file_path, 'r', encoding='utf-8') as file:
        source = file.read()

    # Step 1: Remove """ docstrings only
    source = re.sub(r'"""[\s\S]*?"""', '', source)

    # Step 2: Remove # comments using tokenize
    try:
        tokens = list(tokenize.generate_tokens(StringIO(source).readline))
    except tokenize.TokenError as e:
        print(f"Error tokenizing {file_path}: {e}")
        return

    lines = source.split('\n')
    for token in tokens:
        if token.type == tokenize.COMMENT:
            row = token.start[0] - 1
            col_start = token.start[1]
            col_end = token.end[1]
            line = lines[row]
            lines[row] = line[:col_start].rstrip() + line[col_end:]

    source = '\n'.join(lines)

    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(source)


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
    copy_source_files()
    clean_release_files()
    make_release_zip()
    print("Release build completed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Build failed:", e)
        raise
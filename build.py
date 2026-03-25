"""Build helper for packaging C4D2GS for commercial distribution.

Usage:
    python build.py

This script produces:
    release/C4D2GS_source.zip
    release/C4D2GS_compiled.zip
    release/INSTALL.txt
    release/{LICENSE,EULA.txt,README.md}

The compiled bundle uses precompiled .pyc files to reduce plain source visibility.
"""

import compileall
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "c4d2gs"
RELEASE_DIR = ROOT / "release"

def ensure_release_dir():
    if RELEASE_DIR.exists():
        print(f"Cleaning existing release folder: {RELEASE_DIR}")
        shutil.rmtree(RELEASE_DIR)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)


def create_install_file():
    install_path = RELEASE_DIR / "INSTALL.txt"
    install_path.write_text(
        """C4D2GS Installation Instructions\n\n"
        "1) Extract the ZIP to a temporary folder.\n"
        "2) Copy the `c4d2gs/` folder to your Cinema 4D plugins directory:\n"
        "   - Windows: %APPDATA%\\Maxon\\Maxon Cinema 4D <version>\\plugins\\\n"
        "   - macOS: ~/Library/Preferences/Maxon/Maxon Cinema 4D <version>/plugins/\n"
        "3) Restart Cinema 4D.\n"
        "4) Open Extensions -> C4D2GS and run the plugin.\n\n"
        "License: use is governed by EULA.txt. Resale/re-distribution is prohibited unless approved.\n"
        """
    )
    return install_path


def copy_documents():
    for name in ["LICENSE", "EULA.txt", "README.md"]:
        src = ROOT / name
        if src.exists():
            shutil.copy(src, RELEASE_DIR / name)
        else:
            print(f"Warning: missing {name}")


def make_source_zip():
    zip_path = RELEASE_DIR / "C4D2GS_source.zip"
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as z:
        for item in SRC_DIR.rglob("*"):
            if item.is_file():
                archive_name = Path("c4d2gs") / item.relative_to(SRC_DIR)
                z.write(item, archive_name.as_posix())
    return zip_path


def compile_source():
    print("Compiling source to .pyc...")
    success = compileall.compile_dir(str(SRC_DIR), force=True, quiet=1)
    if not success:
        raise RuntimeError("compileall failed")


def make_compiled_zip():
    zip_path = RELEASE_DIR / "C4D2GS_compiled.zip"
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as z:
        # include precompiled .pyc from __pycache__
        for py_file in SRC_DIR.rglob("*.py"):
            pycache_dir = py_file.parent / "__pycache__"
            if not pycache_dir.exists():
                continue
            matches = list(pycache_dir.glob(f"{py_file.stem}*.pyc"))
            if not matches:
                continue
            pyc_file = matches[0]
            dst = Path("c4d2gs") / py_file.relative_to(SRC_DIR).with_suffix(".pyc")
            z.write(pyc_file, dst.as_posix())

        # include __init__.pyc in package roots where needed
        for pkg in SRC_DIR.rglob("__pycache__"):
            for pyc in pkg.glob("*.pyc"):
                relative = pyc.relative_to(SRC_DIR)
                # This includes __pycache__ paths; we want normalized path without __pycache__
                base = Path("c4d2gs") / relative.parent.parent / (relative.stem.split(".")[0] + ".pyc")
                z.write(pyc, base.as_posix())

        # include doc files
        for name in ["LICENSE", "EULA.txt", "README.md", "INSTALL.txt"]:
            path = RELEASE_DIR / name
            if path.exists():
                z.write(path, name)
            else:
                print(f"Warning: {name} not found for compiled package.")

    return zip_path


def main():
    print("Building release package...")
    ensure_release_dir()
    create_install_file()
    copy_documents()
    src_zip = make_source_zip()
    print(f"Created source zip: {src_zip}")
    compile_source()
    compiled_zip = make_compiled_zip()
    print(f"Created compiled zip: {compiled_zip}")
    print("Release build completed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Build failed:", e)
        sys.exit(1)

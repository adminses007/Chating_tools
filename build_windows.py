# Build Windows executables with PyInstaller (Phase 10)
# Run from project root:  python build_windows.py

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> None:
    run([sys.executable, "-m", "pip", "install", "pyinstaller", "-q"])

    # Server.exe
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--name",
            "Server",
            "--onefile",
            "--console",
            "--add-data",
            f"config{(';' if sys.platform == 'win32' else ':')}config",
            "--add-data",
            f"server/admin/static{(';' if sys.platform == 'win32' else ':')}server/admin/static",
            "--add-data",
            f"client/ui{(';' if sys.platform == 'win32' else ':')}client/ui",
            "server/main.py",
        ]
    )

    # LANChat.exe (Client)
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--name",
            "LANChat",
            "--onefile",
            "--windowed",
            "--add-data",
            f"client/ui{(';' if sys.platform == 'win32' else ':')}client/ui",
            "--add-data",
            f"config{(';' if sys.platform == 'win32' else ':')}config",
            "client/main.py",
        ]
    )

    print("\nBuild complete. Outputs in dist/Server.exe and dist/LANChat.exe")
    print("Place config/ next to the exe or edit embedded defaults.")
    print("For Server, ensure writable data/ and logs/ folders beside the exe.")


if __name__ == "__main__":
    main()

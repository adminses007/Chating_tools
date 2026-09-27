# PyInstaller packaging notes for Windows

## Build

```bat
build_windows.bat
```

or:

```bash
python build_windows.py
```

Outputs:

- `dist/Server.exe`
- `dist/LANChat.exe`

## Run Server.exe

1. Copy `config/server.json` next to `Server.exe` (optional; embedded defaults used otherwise)
2. Create writable folders beside the exe: `data/`, `data/files/`, `logs/`
3. Double-click `Server.exe` or run from cmd
4. Open `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/admin`

## Run LANChat.exe

1. Optionally place `config/client.json` beside the exe
2. Launch `LANChat.exe`
3. Set Server Address (LAN IP or VPS URL) and login

## Auto-start Server (optional)

Task Scheduler → Create Basic Task → trigger At log on → start `Server.exe`.

## Installer (optional)

Use Inno Setup to wrap `Server.exe` + `LANChat.exe` + `config/` into a single installer.

"""Windows development bootstrap/supervisor; no third-party Python packages required."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
STATE = ROOT / "tmp" / "dev"
VENV_PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
HIDDEN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class StartupError(RuntimeError):
    pass


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=ROOT, check=False, text=True, encoding="utf-8", errors="replace",
                            stdout=subprocess.PIPE if capture else None, stderr=subprocess.STDOUT if capture else None)
    if result.returncode:
        if capture and result.stdout:
            print(result.stdout, flush=True)
        raise StartupError(f"Command failed (exit {result.returncode}): {subprocess.list2cmdline(command)}")
    return result


def fingerprint(*paths: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def pinned_backend_installed() -> bool:
    code = """
import importlib.metadata as metadata
from pathlib import Path
import sys
for filename in sys.argv[1:]:
    for raw in Path(filename).read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if line and not line.startswith(('#', '-')):
            name, wanted = line.split('==', 1)
            try:
                actual = metadata.version(name)
            except metadata.PackageNotFoundError:
                raise SystemExit(1)
            if actual != wanted:
                raise SystemExit(1)
"""
    return subprocess.run([str(VENV_PYTHON), "-c", code, str(BACKEND / "requirements.txt"),
                           str(BACKEND / "requirements-dev.txt")], cwd=ROOT, check=False).returncode == 0


def prepare() -> tuple[str, str]:
    if os.name != "nt" or sys.version_info[:2] != (3, 15):
        raise StartupError("Use start.bat on Windows with Python 3.15.")
    node, npm = shutil.which("node"), shutil.which("npm.cmd")
    if not node or not npm:
        raise StartupError("Node.js >=22.12 and npm are required on PATH. Reopen the terminal after installation.")
    node_version = run([node, "--version"], capture=True).stdout.strip()
    if tuple(int(part) for part in node_version.lstrip("v").split(".")[:2]) < (22, 12):
        raise StartupError(f"Node.js >=22.12 is required; found {node_version}.")
    npm_version = run([npm, "--version"], capture=True).stdout.strip()
    print(f"[OK] Python {sys.version.split()[0]}, Node {node_version}, npm {npm_version}", flush=True)
    STATE.mkdir(parents=True, exist_ok=True)
    # Local temp directories also work inside restricted execution environments.
    install_temp = ROOT / "tmp" / "install"
    install_temp.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = str(install_temp)
    os.environ["TMP"] = str(install_temp)

    if not VENV_PYTHON.exists():
        print("[SETUP] Creating backend/.venv ...", flush=True)
        run([sys.executable, "-m", "venv", str(BACKEND / ".venv")])
    run([str(VENV_PYTHON), "-c", "import sys; assert sys.version_info[:2] == (3, 15), 'Existing backend/.venv must use Python 3.15. Rename it and rerun start.bat.'"], capture=True)
    pip_ready = subprocess.run([str(VENV_PYTHON), "-m", "pip", "--version"], cwd=ROOT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0
    if not pip_ready:
        run([str(VENV_PYTHON), "-m", "ensurepip", "--upgrade"])
    if not pinned_backend_installed():
        print("[SETUP] Installing pinned backend runtime/test dependencies ...", flush=True)
        run([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(BACKEND / "requirements-dev.txt")])
    run([str(VENV_PYTHON), "-m", "pip", "check"], capture=True)
    run([str(VENV_PYTHON), "-c", "import sys; sys.path.insert(0, 'backend'); import app.main, pytest"], capture=True)
    print("[OK] Backend dependencies and imports", flush=True)

    stamp_file = STATE / "frontend-dependencies.json"
    wanted = {"manifest": fingerprint(FRONTEND / "package.json", FRONTEND / "package-lock.json"), "node": node_version}
    try:
        installed = json.loads(stamp_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        installed = None
    vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if installed != wanted or not vite.is_file():
        print("[SETUP] Installing frontend dependencies from package-lock.json ...", flush=True)
        run([npm, "--prefix", str(FRONTEND), "ci", "--no-audit", "--no-fund"])
    run([npm, "--prefix", str(FRONTEND), "ls", "--depth=0"], capture=True)
    stamp_file.write_text(json.dumps(wanted), encoding="utf-8")
    print("[OK] Frontend dependencies", flush=True)
    print("[SETUP] Initializing SQLite and seeding demo data (existing records preserved) ...", flush=True)
    run([str(VENV_PYTHON), "-c", "import sys; sys.path.insert(0, 'backend'); from app.database.seed import seed_database; import json; print(json.dumps(seed_database(), indent=2))"])
    return node, str(vite)


def check_ports() -> None:
    for port in (8000, 5173):
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError as error:
                raise StartupError(f"Port {port} is already in use or unavailable. Stop the existing service and retry; no process was terminated.") from error


def reachable(url: str, *, health: bool = False) -> bool:
    try:
        with urlopen(url, timeout=1) as response:
            return response.status == 200 and (not health or json.load(response) == {"status": "ok"})
    except (OSError, URLError, ValueError):
        return False


def stop_owned(process: subprocess.Popen) -> None:
    if process.poll() is None:
        stopped = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=HIDDEN)
        if stopped.returncode and process.poll() is None:
            print(f"[ERROR] Could not stop process {process.pid}; inspect it manually.", flush=True)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"[ERROR] Process {process.pid} did not stop; see logs.", flush=True)


def tail_logs() -> None:
    for name in ("backend", "frontend"):
        path = STATE / f"{name}.log"
        if path.exists():
            print(f"\n--- {name} log: {path} ---", flush=True)
            print("\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]), flush=True)


def serve(node: str, vite: str) -> None:
    processes = []
    logs = []
    try:
        commands = [
            ("backend", [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app", "--app-dir", str(BACKEND),
                "--host", "127.0.0.1", "--port", "8000", "--reload", "--reload-dir", str(BACKEND / "app")], ROOT),
            ("frontend", [node, vite, "--host", "127.0.0.1", "--port", "5173", "--strictPort"], FRONTEND),
        ]
        for name, command, cwd in commands:
            log = (STATE / f"{name}.log").open("wb")
            logs.append(log)
            process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                creationflags=HIDDEN | subprocess.CREATE_NEW_PROCESS_GROUP)
            processes.append(process)
            print(f"[START] {name} PID {process.pid}; log: {STATE / (name + '.log')}", flush=True)
        deadline = time.monotonic() + 40
        while True:
            for process in processes:
                if process.poll() is not None:
                    raise StartupError(f"Development process {process.pid} exited with code {process.returncode}.")
            if reachable("http://127.0.0.1:8000/health", health=True) and reachable("http://127.0.0.1:5173"):
                break
            if time.monotonic() > deadline:
                raise StartupError("Services did not become ready within 40 seconds.")
            time.sleep(0.25)
        print("[OK] Backend:  http://127.0.0.1:8000/health", flush=True)
        print("[OK] API docs: http://127.0.0.1:8000/docs", flush=True)
        print("[OK] Frontend: http://127.0.0.1:5173", flush=True)
        print("[READY] Keep this terminal open. Press Ctrl+C to stop BOTH services.", flush=True)
        while True:
            for process in processes:
                if process.poll() is not None:
                    raise StartupError(f"Development process {process.pid} exited with code {process.returncode}.")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[STOP] Stopping this launcher's services ...", flush=True)
    except BaseException:
        tail_logs()
        raise
    finally:
        for process in reversed(processes):
            stop_owned(process)
        for log in logs:
            log.close()
        print("[STOP] Launcher cleanup finished.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare and run the Certificate Admin Console on Windows.")
    parser.add_argument("--prepare-only", action="store_true", help="Install/check dependencies and seed SQLite, without starting services.")
    args = parser.parse_args()
    try:
        if not args.prepare_only:
            check_ports()
        node, vite = prepare()
        if args.prepare_only:
            print("[OK] Preparation complete. Run start.bat to start both services.", flush=True)
        else:
            serve(node, vite)
        return 0
    except KeyboardInterrupt:
        print("\n[STOP] Preparation interrupted; no services were started.", flush=True)
        return 130
    except (StartupError, OSError) as error:
        print(f"[ERROR] {error}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

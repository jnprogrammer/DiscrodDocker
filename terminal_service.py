import asyncio
import os
import socket
import subprocess
import threading
import time
from typing import Dict

import docker
from flask import Flask, abort, jsonify, redirect, request

from database import ContainerDB

SESSION_TIMEOUT = int(os.getenv("TERMINAL_SESSION_TIMEOUT", "3600"))
TTYD_PATH = os.getenv("TTYD_PATH", "ttyd")
DEFAULT_SHELL = os.getenv("TERMINAL_SHELL", "/bin/bash")

app = Flask(__name__)
db = ContainerDB()
docker_client = docker.from_env()
active_sessions: Dict[str, Dict] = {}


def init_database():
    """Ensure database tables exist before handling requests."""
    asyncio.run(db.init_db())


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def container_exists(container_id: str) -> bool:
    try:
        docker_client.containers.get(container_id)
        return True
    except docker.errors.NotFound:
        return False


def _watch_session(container_id: str, process: subprocess.Popen):
    """Wait for the ttyd process to exit and clean up session mapping."""
    process.wait()
    active_sessions.pop(container_id, None)


def wait_for_port(port: int, timeout: float = 5.0) -> bool:
    """Wait until a local port starts accepting TCP connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                sock.connect(("127.0.0.1", port))
                return True
            except (ConnectionRefusedError, socket.timeout):
                time.sleep(0.1)
    return False


def launch_ttyd(container_id: str) -> Dict:
    """Launch ttyd bound to docker exec for the container."""
    port = get_free_port()
    command = [
        TTYD_PATH,
        "--port",
        str(port),
        "--once",
        "docker",
        "exec",
        "-it",
        container_id,
        DEFAULT_SHELL,
    ]

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    active_sessions[container_id] = {
        "process": process,
        "port": port,
        "started_at": time.time(),
    }
    threading.Thread(target=_watch_session, args=(container_id, process), daemon=True).start()

    if not wait_for_port(port):
        process.terminate()
        active_sessions.pop(container_id, None)
        raise RuntimeError("Failed to start ttyd session")

    return active_sessions[container_id]


def get_or_launch_session(container_id: str) -> Dict:
    session = active_sessions.get(container_id)
    if session:
        process: subprocess.Popen = session["process"]
        if process.poll() is None and (time.time() - session["started_at"]) < SESSION_TIMEOUT:
            return session

        # session expired or process ended
        try:
            process.terminate()
        except Exception:
            pass
        active_sessions.pop(container_id, None)

    return launch_ttyd(container_id)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/terminal/<container_id>", methods=["GET"])
def terminal(container_id: str):
    token = request.args.get("token")
    if not token:
        abort(400, "token query parameter is required")

    # Validate token
    token_record = asyncio.run(db.get_terminal_token(container_id))
    if not token_record or token_record["token"] != token:
        abort(403, "invalid or expired token")

    # Ensure container exists
    if not container_exists(container_id):
        abort(404, "container not found")

    try:
        session = get_or_launch_session(container_id)
    except RuntimeError as exc:
        abort(500, str(exc))

    scheme = "https" if request.is_secure else "http"
    host = request.host.split(":")[0]
    target_url = f"{scheme}://{host}:{session['port']}"
    return redirect(target_url, code=302)


if __name__ == "__main__":
    init_database()
    app.run(host="0.0.0.0", port=int(os.getenv("TERMINAL_SERVICE_PORT", "5000")))


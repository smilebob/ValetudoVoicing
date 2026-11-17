"""Deploy a .pkg voicepack directly to a Valetudo robot via temporary HTTP server + REST API."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import threading
import time
import httpx

from .packager import compute_md5


def detect_local_ip(robot_ip: str) -> str:
    """Detect the local LAN IP address used to reach `robot_ip`."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((robot_ip, 80))
        return str(s.getsockname()[0])


class _TrackingHTTPHandler(SimpleHTTPRequestHandler):
    """HTTP handler that tracks when the target .pkg file has been downloaded."""

    target_filename: str = ""
    downloaded_event: threading.Event | None = None

    def do_GET(self) -> None:
        super().do_GET()
        if self.downloaded_event and self.path.lstrip("/") == self.target_filename:
            self.downloaded_event.set()

    def log_message(self, format: str, *args: object) -> None:
        # Suppress noisy stdout logging
        return


def deploy_to_valetudo(
    pkg_path: Path,
    robot_ip: str,
    language: str = "fr",
    port: int = 8765,
    timeout: int = 120,
) -> dict:
    """Serve `pkg_path` over HTTP and instruct Valetudo to download and install it."""
    if not pkg_path.exists():
        raise FileNotFoundError(f"Package not found: {pkg_path}")

    md5_hex = compute_md5(pkg_path)
    local_ip = detect_local_ip(robot_ip)
    downloaded_event = threading.Event()

    class Handler(_TrackingHTTPHandler):
        pass

    Handler.target_filename = pkg_path.name
    Handler.downloaded_event = downloaded_event

    bound_handler = partial(Handler, directory=str(pkg_path.parent))
    server = ThreadingHTTPServer(("0.0.0.0", port), bound_handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        download_url = f"http://{local_ip}:{port}/{pkg_path.name}"
        api_url = f"http://{robot_ip}/api/v2/robot/capabilities/VoicePackManagementCapability"
        payload = {
            "action": "download",
            "url": download_url,
            "hash": md5_hex,
            "language": language,
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.put(api_url, json=payload)
            resp.raise_for_status()

        # Wait for the robot to finish fetching the .pkg file
        completed = downloaded_event.wait(timeout=timeout)
        # Give the socket a brief moment to flush the final bytes
        if completed:
            time.sleep(1.5)

        return {
            "url": download_url,
            "md5": md5_hex,
            "language": language,
            "downloaded": completed,
        }
    finally:
        server.shutdown()
        server.server_close()

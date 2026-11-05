"""Start the dashboard: seed demo data if needed, serve on one port and open the browser."""

from __future__ import annotations

import socket
import sys
import threading
import webbrowser

import httpx
import uvicorn


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", port)) == 0


def _already_goldengate(url: str) -> bool:
    try:
        return httpx.get(f"{url}/api/health", timeout=2).json().get("status") == "ok"
    except (httpx.HTTPError, ValueError):
        return False


def launch(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True, seed: bool = True) -> None:
    """Blocking: run the FastAPI app with uvicorn."""
    url = f"http://localhost:{port}"
    if _port_in_use(host, port):
        if _already_goldengate(url):
            print(f"GoldenGate is already running at {url}", flush=True)
            if open_browser:
                webbrowser.open(url)
            return
        print(f"Port {port} is in use by another program. Start with --port <other port>.", file=sys.stderr)
        raise SystemExit(2)

    if seed:
        from goldengate.demo import ensure_demo_data

        seeded = ensure_demo_data(on_step=lambda i, n, label: print(f"  seeding demo data [{i}/{n}] {label}", flush=True))
        if seeded:
            print("Demo data ready: release_1.0 (baseline), 1.1, 1.2 and 1.3.", flush=True)

    from goldengate.server.app import create_app

    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"GoldenGate dashboard: {url}   (press Ctrl+C to stop)", flush=True)
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


def main() -> None:
    """Entry point for the PyInstaller executable: ``GoldenGate.exe [--port N] [--no-open]``.

    The port can also be set with the ``GOLDENGATE_PORT`` environment variable.
    """
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="GoldenGate", description="GoldenGate dashboard")
    parser.add_argument("--port", type=int, default=int(os.environ.get("GOLDENGATE_PORT", "8000")))
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    args = parser.parse_args()
    launch(port=args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    main()

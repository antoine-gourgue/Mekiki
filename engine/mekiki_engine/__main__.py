"""Entry point: ``uv run mekiki-engine`` in development, the bundled sidecar in release."""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

import uvicorn

from mekiki_engine.app import create_app
from mekiki_engine.config import DEFAULT_PORT, load_config, load_env_file


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mekiki-engine", description="Mekiki local engine.")
    parser.add_argument(
        "--port", type=int, help=f"port to listen on (MEKIKI_ENGINE_PORT, default {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--data-dir", help="folder holding the SQLite database (MEKIKI_DATA_DIR, default .data)"
    )
    parser.add_argument(
        "--host",
        help="address to listen on (MEKIKI_HOST, default 127.0.0.1; a server needs 0.0.0.0)",
    )
    parser.add_argument(
        "--exit-with-parent",
        action="store_true",
        help="stop when stdin reaches end of file, i.e. when the desktop app is gone",
    )
    args = parser.parse_args(argv)

    # Secrets such as the eBay keys live in a .env file next to the engine, never in git.
    load_env_file(Path(".env"))
    config = load_config(data_dir=args.data_dir, port=args.port, host=args.host)
    # The installed app starts the engine from no particular folder: its .env sits next to
    # the database instead. The first file read wins.
    load_env_file(config.data_dir / ".env")
    config = load_config(data_dir=args.data_dir, port=args.port, host=args.host)
    # Loopback unless deployed as a server (see config.DEFAULT_HOST).
    server = uvicorn.Server(uvicorn.Config(create_app(config), host=config.host, port=config.port))
    if args.exit_with_parent and sys.stdin is not None:
        threading.Thread(target=_stop_on_stdin_eof, args=(server,), daemon=True).start()
    server.run()


def _stop_on_stdin_eof(server: uvicorn.Server) -> None:
    # The desktop app holds the other end of our stdin. If it crashes, or kills only the
    # PyInstaller bootloader that started us, the pipe still closes and we follow.
    while sys.stdin.buffer.read(1024):
        pass
    server.should_exit = True


if __name__ == "__main__":
    main()

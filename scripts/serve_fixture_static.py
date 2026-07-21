"""Serve a built local fixture with explicit ES-module MIME types on Windows."""

from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from functools import partial


class FixtureHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".css": "text/css",
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".map": "application/json",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--port", default=5177, type=int)
    arguments = parser.parse_args()
    handler = partial(FixtureHandler, directory=str(arguments.directory.resolve()))
    ThreadingHTTPServer(("127.0.0.1", arguments.port), handler).serve_forever()


if __name__ == "__main__":
    main()

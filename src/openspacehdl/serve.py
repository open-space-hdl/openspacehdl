"""openspacehdl serve: the portal of the package version on 127.0.0.1 (docs/design.md, section 8).

    openspacehdl serve [--port <n>] [--no-browser]

The portal is the website with the Composer and its catalog at /, and the documentation site of every core and of
Open Logic FT at /<repository>/, at the commits the package version pins. The server binds to 127.0.0.1 only and
serves the files of openspacehdl/portal/ with the HTTP server of the standard library, without directory listings.

The default port is 8765. The Composer keeps its workspace in the storage of the browser, which belongs to the address
with its port: the same port finds the same workspace again, and another port starts with an empty one. The online
Composer (openspacehdl.org) has a workspace of its own; work moves between them as a saved file (Save, Open).
"""

from __future__ import annotations

import functools
import http.server
import sys
import webbrowser
from importlib import resources
from pathlib import Path

from openspacehdl.errors import OshError

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
# Media types of the portal, independent of the tables of the system: on Windows the registry can map .js to
# text/plain, and a browser does not run a module script of that type.
TYPES = {
    ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript",
    ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".gif": "image/gif", ".ico": "image/x-icon", ".woff2": "font/woff2", ".txt": "text/plain",
    ".xml": "application/xml", ".gz": "application/gzip",
}


class ServeError(OshError):
    """The portal cannot be served."""


def portal_dir() -> Path:
    """The portal of the installed package."""
    root = Path(str(resources.files("openspacehdl").joinpath("portal")))
    if not (root / "index.html").is_file():
        from openspacehdl import __version__

        raise ServeError(f"version {__version__} carries no portal")
    return root


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **TYPES}

    def list_directory(self, path):
        self.send_error(404, "Not found")
        return None

    def log_message(self, format, *args):  # noqa: A002 (the signature of the base class)
        pass


class Server(http.server.ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second server take a port that is in use; elsewhere it only skips TIME_WAIT
    allow_reuse_address = sys.platform != "win32"
    daemon_threads = True


def make_server(root: Path, port: int) -> Server:
    """A server of the files below root on 127.0.0.1:port (0: a free port)."""
    handler = functools.partial(Handler, directory=str(root))
    try:
        return Server((HOST, port), handler)
    except OSError as e:
        raise ServeError(f"cannot listen on {HOST}:{port} ({e.strerror or e}); --port chooses another port, where the "
                         f"Composer starts with an empty workspace") from e


def main(port: int = DEFAULT_PORT, browser: bool = True) -> int:
    try:
        server = make_server(portal_dir(), port)
    except ServeError as e:
        print(f"openspacehdl: {e}", file=sys.stderr)
        return 1
    url = f"http://{HOST}:{server.server_address[1]}/"
    # flushed: into a pipe or a log, the lines would otherwise wait in the buffer while the server runs
    print(f"Serving the portal at {url} (Ctrl+C stops).", flush=True)
    print(f"The Composer keeps its workspace in the browser storage of {url}; another port starts with an empty one.",
          flush=True)
    if browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0

"""Tests of openspacehdl serve: the server of the portal on 127.0.0.1, its media types and the command line."""

import socket
import threading
import urllib.error
import urllib.request

import pytest

from openspacehdl import cli, serve


@pytest.fixture
def portal(tmp_path):
    files = {
        "index.html": "<p>start</p>", "composer/index.html": "<p>composer</p>", "assets/composer/js/main.js": "x",
        "assets/model.mjs": "y", "assets/composer/catalog.json": "{}", "assets/img/logo.svg": "<svg/>",
        "assets/fonts/sora.woff2": "f", "assets/css/site.css": "c", "favicon.ico": "i", "openwire/index.html": "w",
        "openwire/search/search_index.json": "{}", "empty/readme.txt": "t",
    }
    for name, text in files.items():
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return tmp_path


@pytest.fixture
def server(portal):
    srv = serve.make_server(portal, 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def get(srv, path):
    url = f"http://127.0.0.1:{srv.server_address[1]}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.headers.get_content_type(), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, None, ""


def test_binds_to_127_0_0_1_only(server):
    assert server.server_address[0] == "127.0.0.1"


def test_pages_and_index_files(server):
    assert get(server, "/") == (200, "text/html", "<p>start</p>")
    assert get(server, "/composer/")[2] == "<p>composer</p>"
    assert get(server, "/openwire/")[2] == "w"


@pytest.mark.parametrize("path,kind", [
    ("/assets/composer/js/main.js", "text/javascript"),
    ("/assets/model.mjs", "text/javascript"),
    ("/assets/composer/catalog.json", "application/json"),
    ("/assets/img/logo.svg", "image/svg+xml"),
    ("/assets/fonts/sora.woff2", "font/woff2"),
    ("/assets/css/site.css", "text/css"),
    ("/openwire/search/search_index.json", "application/json"),
])
def test_media_types_do_not_depend_on_the_system(server, path, kind):
    # the Composer is a set of ES modules: a browser runs them only with a JavaScript type
    status, ctype, _ = get(server, path)
    assert (status, ctype) == (200, kind)


def test_no_directory_listing_and_no_missing_file(server):
    assert get(server, "/empty/")[0] == 404
    assert get(server, "/missing.html")[0] == 404


def test_no_path_outside_the_portal(server, portal):
    (portal.parent / "secret.txt").write_text("s", encoding="utf-8")
    assert get(server, "/../secret.txt")[0] == 404
    assert get(server, "/%2e%2e/secret.txt")[0] == 404


def test_a_port_in_use_is_an_error(portal):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        with pytest.raises(serve.ServeError, match="--port chooses another port"):
            serve.make_server(portal, s.getsockname()[1])


def test_a_package_without_portal(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(serve.resources, "files", lambda _: tmp_path)
    assert serve.main(0, browser=False) == 1
    assert "carries no portal" in capsys.readouterr().err


def test_the_portal_of_the_package(monkeypatch, portal):
    monkeypatch.setattr(serve.resources, "files", lambda _: portal.parent)
    (portal.parent / "portal").mkdir(exist_ok=True)
    (portal.parent / "portal" / "index.html").write_text("p", encoding="utf-8")
    assert serve.portal_dir() == portal.parent / "portal"


def test_main_says_where_the_workspace_lives(monkeypatch, portal, capsys):
    class Stopped:
        server_address = ("127.0.0.1", 8765)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            self.closed = True

    opened = []
    monkeypatch.setattr(serve, "portal_dir", lambda: portal)
    monkeypatch.setattr(serve, "make_server", lambda root, port: Stopped())
    monkeypatch.setattr(serve.webbrowser, "open", opened.append)
    assert serve.main() == 0
    out = capsys.readouterr().out
    assert "http://127.0.0.1:8765/" in out
    assert "workspace" in out and "another port starts with an empty one" in out
    assert opened == ["http://127.0.0.1:8765/"]


@pytest.mark.parametrize("argv,expected", [
    (["serve"], (8765, True)),
    (["serve", "--port", "9100", "--no-browser"], (9100, False)),
])
def test_command_line(monkeypatch, argv, expected):
    seen = []
    monkeypatch.setattr(serve, "main", lambda port, browser: seen.append((port, browser)) or 0)
    assert cli.main(argv) == 0
    assert seen == [expected]
    assert serve.DEFAULT_PORT == 8765

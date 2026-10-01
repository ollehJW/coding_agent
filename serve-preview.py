"""Serve the WiaCanDX and WiaCoding mockups on ports 6551 and 6552."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread, Event
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
PUBLIC = {
    path.name
    for path in ROOT.iterdir()
    if path.is_file() and path.suffix in {".html", ".css", ".js", ".png", ".svg", ".ico"}
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, landing, **kwargs):
        self.landing = landing
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        name = unquote(urlsplit(self.path).path).removeprefix("/")
        if not name:
            name = self.landing
        if name not in PUBLIC:
            self.send_error(404)
            return None
        self.path = "/" + name
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    servers = []
    try:
        for port, landing in [(6551, "index.html"), (6552, "wiacoding.html")]:
            server = ThreadingHTTPServer(("0.0.0.0", port), partial(Handler, landing=landing))
            servers.append(server)
        for server in servers:
            Thread(target=server.serve_forever, daemon=True).start()
            print(f"Serving http://0.0.0.0:{server.server_port}", flush=True)
        Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.server_close()

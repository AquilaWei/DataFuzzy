import hashlib
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datafuzzy.core.models import FileSpec, ModelSpec  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class FileServer:
    """Tiny HTTP server serving in-memory files, with optional Range support."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.requests: list[tuple[str, str | None]] = []  # (path, Range header)
        self.support_range = True
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                rng = self.headers.get("Range")
                server.requests.append((self.path, rng))
                body = server.files.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                start = 0
                if rng and server.support_range:
                    start = int(rng.split("=")[1].rstrip("-"))
                    self.send_response(206)
                else:
                    self.send_response(200)
                self.send_header("Content-Length", str(len(body) - start))
                self.end_headers()
                self.wfile.write(body[start:])

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def spec(self, model_id: str = "fake", contents: dict[str, bytes] | None = None,
             lang: str = "en") -> ModelSpec:
        contents = contents or {"a.bin": os.urandom(3 << 20), "b.txt": b"hello"}
        files = []
        for name, data in contents.items():
            path = f"/{model_id}/{name}"
            self.files[path] = data
            files.append(FileSpec(name, self.url + path, len(data), hashlib.sha256(data).hexdigest()))
        return ModelSpec(model_id, lang, "Fake", "test/fake", "MIT", {"PER": "PERSON"}, tuple(files))


@pytest.fixture
def file_server():
    server = FileServer()
    yield server
    server.httpd.shutdown()


def real_model_dir(lang: str = "en") -> Path | None:
    """The model for `lang`, if available locally (cached by tools/update_manifest.py or
    installed)."""
    from datafuzzy.core.models import is_installed, load_manifest, models_dir

    spec = next(s for s in load_manifest() if s.lang == lang)
    override = os.environ.get("DATAFUZZY_TEST_MODEL_DIR") if lang == "en" else None
    for c in (override, REPO_ROOT / "models/cache" / spec.id):
        if c and (Path(c) / "model.onnx").exists():
            return Path(c)
    if is_installed(spec, models_dir()):
        return models_dir() / spec.id
    return None

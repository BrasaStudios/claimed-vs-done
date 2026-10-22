"""Local-only HTTP fixtures; all temporary files stay in the repository."""

import json
import os
import socket
import tempfile
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

# Test containers get their own prefix, and every test helper lists and removes
# only these, so the suite can run beside a live benchmark batch (a cleanup
# fixture once deleted a live run's container). Child processes inherit it.
os.environ["CVD_SANDBOX_PREFIX"] = "cvdtest-"


@pytest.fixture
def tmp_path():
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix=".cvd-test-", dir=Path(__file__).resolve().parents[1]) as directory:
        try:
            yield Path(directory)
        finally:
            os.chdir(original_cwd)


@pytest.fixture
def fake_key():
    return "sk-test-SECRET-0123456789"


@pytest.fixture(autouse=True)
def local_network_only(monkeypatch):
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex

    def guarded_connect(sock, address):
        if not isinstance(address, tuple) or address[0] != "127.0.0.1":
            raise AssertionError("Tests may connect only to 127.0.0.1")
        return connect(sock, address)

    def guarded_connect_ex(sock, address):
        if not isinstance(address, tuple) or address[0] != "127.0.0.1":
            raise AssertionError("Tests may connect only to 127.0.0.1")
        return connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")


class MockAPI:
    def __init__(self):
        self.responses = deque()
        self.requests = []
        self.handler = None
        self.errors = []
        self.base_url = ""

    def __call__(self, handler=None):
        self.handler = handler
        return self

    def enqueue(self, status=200, headers=None, body=None):
        self.responses.append((status, headers or {}, body))


@pytest.fixture
def mock_api():
    api = MockAPI()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            request = {"path": self.path, "headers": dict(self.headers), "body": body}
            api.requests.append(request)
            try:
                if api.handler is not None:
                    response = api.handler(request)
                else:
                    response = api.responses.popleft()
                status, headers, payload = response
            except Exception as error:
                api.errors.append(error)
                status, headers, payload = 500, {}, {"error": "Mock handler failed"}
            if isinstance(payload, bytes):
                encoded = payload
            elif isinstance(payload, str):
                encoded = payload.encode("utf-8")
            else:
                encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    api.base_url = "http://127.0.0.1:" + str(server.server_port) + "/v1"
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield api
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert not api.errors, "The mock API handler failed"

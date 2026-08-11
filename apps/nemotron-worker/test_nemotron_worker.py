from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request


APP_DIR = Path(__file__).resolve().parent


class FakeOllama(BaseHTTPRequestHandler):
    def _send(self, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self._send({"models": [{"name": "nemotron-3-nano:4b"}]})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        assert payload["model"] == "nemotron-3-nano:4b"
        assert "Founder retains final authority" in payload["messages"][0]["content"]
        assert payload["think"] is False
        self._send(
            {
                "message": {"role": "assistant", "content": "verified"},
                "done_reason": "stop",
                "prompt_eval_count": 12,
                "eval_count": 1,
            }
        )

    def log_message(self, format: str, *args: object) -> None:
        return


class WorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 18080), FakeOllama)
        cls.thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.thread.start()
        env = {
            **os.environ,
            "OLLAMA_BASE_URL": "http://127.0.0.1:18080",
            "NEMOTRON_LISTEN_PORT": "18081",
        }
        cls.worker = subprocess.Popen([sys.executable, str(APP_DIR / "nemotron_worker.py")], env=env)
        for _ in range(30):
            try:
                request.urlopen("http://127.0.0.1:18081/health", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("worker did not become healthy")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.worker.terminate()
        cls.worker.wait(timeout=5)
        cls.upstream.shutdown()

    def test_health_and_chat_contract(self) -> None:
        health = json.loads(request.urlopen("http://127.0.0.1:18081/health").read())
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["founder_authority"], "final")

        payload = json.dumps(
            {"messages": [{"role": "user", "content": "status"}], "stream": False}
        ).encode()
        req = request.Request(
            "http://127.0.0.1:18081/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        result = json.loads(request.urlopen(req).read())
        self.assertEqual(result["choices"][0]["message"]["content"], "verified")


if __name__ == "__main__":
    unittest.main()

"""Exercise the real bundled Windows agent against a loopback mock Gemini endpoint."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from agent_runner import make_config
from progress import TranscriptTracker
from google.antigravity import Agent

REQUESTS = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        REQUESTS.append({"path": self.path, "body": body})
        response = {"candidates": [{"content": {"role": "model", "parts": [{"text": "MOCK_ANTIGRAVITY_OK"}]},
                                    "finishReason": "STOP", "index": 0}],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 3, "totalTokenCount": 13},
                    "modelVersion": "gemini-test"}
        streaming = "streamGenerateContent" in self.path
        data = (("data: " + json.dumps(response) + "\n\n").encode() if streaming else json.dumps(response).encode())
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if streaming else "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


async def main():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="gemini-agent-test-") as temporary:
            config = make_config(f"http://127.0.0.1:{httpd.server_port}", "fake-local-key", "gemini-test",
                                 APP, "review", Path(temporary).resolve())
            async with asyncio.timeout(45):
                async with Agent(config) as agent:
                    response = await agent.chat("Reply with MOCK_ANTIGRAVITY_OK. Do not use tools.")
                    text = await response.text()
            assert "MOCK_ANTIGRAVITY_OK" in text, repr(text)
            assert REQUESTS, "The mock endpoint was not called"
            activity = TranscriptTracker().update(Path(temporary))
            assert activity["model_calls"] >= 1, "The SDK transcript was not reflected in panel activity"
            assert activity["events"], "The SDK transcript produced no panel activity events"
            print(json.dumps({"ok": True, "reply": text, "paths": [r["path"] for r in REQUESTS],
                              "tool_config_sent": bool(REQUESTS[0]["body"].get("tools")),
                              "progress_model_calls": activity["model_calls"]}, ensure_ascii=False))
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

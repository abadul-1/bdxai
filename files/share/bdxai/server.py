#!/usr/bin/env python
"""
BDX AI - local-only HTTP server.
Serves the static chat UI and proxies chat requests to OpenRouter.
Binds to 127.0.0.1 only.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = int(os.environ.get("BDXAI_PORT", "8080"))
STATIC_DIR = Path(__file__).parent / "static"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")

SYSTEM_PROMPT = (
    "You are BDX AI, an ethical cybersecurity education assistant. "
    "You help users learn cybersecurity fundamentals, defensive security, "
    "secure programming, Linux/Termux, networking, and CTF-style educational "
    "exercises. You may explain vulnerabilities at a safe educational level "
    "and help users fix security problems in systems they own or are "
    "authorized to test. You must NOT provide instructions that facilitate "
    "unauthorized access, credential theft, malware deployment, phishing, "
    "evasion, or any harmful activity. If asked, refuse politely and "
    "redirect to an ethical learning path. Keep answers concise, clear, and "
    "well-formatted. Prefer code blocks and bullet lists when helpful."
)


def _send_json(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _send_file(handler, path: Path, content_type: str):
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        handler.send_error(404, "Not found")
        return
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _mime_for(path: Path) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
    }.get(path.suffix, "application/octet-stream")


def call_openrouter(messages):
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None, ("missing_key",
                      "OpenRouter API key is not set. "
                      "Export OPENROUTER_API_KEY and restart bdxai.")

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://127.0.0.1",
            "X-Title": "BDX AI",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        if e.code == 401:
            return None, ("invalid_key", "Invalid OpenRouter API key (401).")
        if e.code == 402:
            return None, ("payment", "OpenRouter requires payment/credits (402).")
        if e.code == 429:
            return None, ("rate_limit", "OpenRouter rate limit reached. Try again later.")
        return None, ("http_error", f"OpenRouter error {e.code}: {raw[:300]}")
    except urllib.error.URLError as e:
        return None, ("network", f"Network error: {e.reason}")
    except Exception as e:  # noqa
        return None, ("unknown", f"Unexpected error: {e}")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, ("invalid_json", "OpenRouter returned invalid JSON.")

    try:
        content = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None, ("shape", "Unexpected OpenRouter response shape.")

    return content, None


class Handler(BaseHTTPRequestHandler):
    server_version = "BDXAI/1.0"

    def log_message(self, fmt, *args):  # quieter logs (no conversation data)
        sys.stderr.write("[bdxai] %s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return _send_file(self, STATIC_DIR / "index.html", "text/html; charset=utf-8")
        if path == "/style.css":
            return _send_file(self, STATIC_DIR / "style.css", "text/css; charset=utf-8")
        if path == "/app.js":
            return _send_file(self, STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
        if path == "/health":
            return _send_json(self, 200, {
                "status": "ok",
                "model": OPENROUTER_MODEL,
                "has_key": bool(os.environ.get("OPENROUTER_API_KEY")),
            })
        self.send_error(404, "Not found")

    def do_POST(self):
        if self.path != "/api/chat":
            return _send_json(self, 404, {"error": "Not found"})

        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > 1_000_000:
            return _send_json(self, 400, {"error": "Invalid body size."})

        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _send_json(self, 400, {"error": "Invalid JSON."})

        messages = data.get("messages")
        if not isinstance(messages, list) or not messages:
            return _send_json(self, 400, {"error": "Missing 'messages'."})

        cleaned = []
        for m in messages[-40:]:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                cleaned.append({"role": role, "content": content[:8000]})
        if not cleaned:
            return _send_json(self, 400, {"error": "No valid messages."})

        content, err = call_openrouter(cleaned)
        if err:
            code, msg = err
            return _send_json(self, 200, {"error": msg, "code": code})
        return _send_json(self, 200, {"reply": content})


def main():
    if not STATIC_DIR.is_dir():
        print(f"[!] Static directory not found: {STATIC_DIR}")
        sys.exit(1)
    try:
        httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as e:
        print(f"[!] Could not bind {HOST}:{PORT} -> {e}")
        print("    Try: export BDXAI_PORT=8081 && bdxai")
        sys.exit(1)

    print(f"[bdxai] listening on http://{HOST}:{PORT}")
    print(f"[bdxai] model: {OPENROUTER_MODEL}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[bdxai] shutting down.")
        httpd.server_close()


if __name__ == "__main__":
    main()

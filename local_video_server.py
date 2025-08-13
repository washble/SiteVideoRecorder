#!/usr/bin/env python3

import os
import subprocess
import sys
import uuid
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from socketserver import ThreadingMixIn
from concurrent.futures import ThreadPoolExecutor

# pip install pyinstaller

'''
[exe build]
- Just make exe -
> pyinstaller local_video_server.py

- Only One exe File -
> pyinstaller -F local_video_server.py
'''

RECORD_DIR = "recordings"
os.makedirs(RECORD_DIR, exist_ok=True)

# session_id -> ffmpeg subprocess
sessions = {}

def start_ffmpeg(session_id: str):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(RECORD_DIR, f"{session_id}_{timestamp}.webm")
    return subprocess.Popen([
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-f", "webm",
        "-i", "pipe:0",
        "-c", "copy",
        output_file
    ], stdin=subprocess.PIPE)

class SimpleConcatHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # HTTP/1.1 사용 선언

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except ConnectionResetError:
            pass

    def _set_common_headers(self, body_len=0):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Content-Length', str(body_len))

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_common_headers(0)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Accept, X-Requested-With')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/session":
            # 발급된 고유 세션 ID 생성
            session_id = str(uuid.uuid4())
            # 세션별 ffmpeg 프로세스 시작
            sessions[session_id] = start_ffmpeg(session_id)

            body = session_id.encode()
            self.send_response(200)
            self._set_common_headers(len(body))
            self.end_headers()
            self.wfile.write(body)
            return

        # GET /merge 지원: merge도 POST로 처리하므로 여기선 404
        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        session_id = qs.get("session", [None])[0]
        idx = qs.get("part", ["0"])[0]

        if path == "/upload" and session_id in sessions:
            size = int(self.headers.get('Content-Length', 0))
            chunk = self.rfile.read(size)

            proc = sessions[session_id]
            try:
                proc.stdin.write(chunk)
                proc.stdin.flush()
            except Exception as e:
                print(f"[FEED ERROR] session={session_id} {e}")

            body = b"ok"
            self.send_response(200)
            self._set_common_headers(len(body))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/merge":
            # session 쿼리가 없더라도, 활성 세션이 하나면 자동으로 병합
            if session_id in sessions:
                sid = session_id
            elif session_id is None and len(sessions) == 1:
                sid = next(iter(sessions))
            else:
                self.send_error(404, "Session not found for merge")
                return

            proc = sessions.pop(sid)
            if proc.stdin:
                proc.stdin.close()
                proc.wait()
                print(f"[MERGE] session={sid} finalized")

            body = b"merge done"
            self.send_response(200)
            self._set_common_headers(len(body))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404, "Not Found")

class PoolMixIn:
    executor = ThreadPoolExecutor(max_workers=20)

    def process_request(self, request, client_address):
        self.executor.submit(self.finish_request, request, client_address)

class ThreadedHTTPServer(PoolMixIn, ThreadingMixIn, HTTPServer):
    daemon_threads = True  # 서버 종료 시 스레드 자동 정리

def run(port=5000):
    server = ThreadedHTTPServer(('', port), SimpleConcatHandler)
    print(f"Threaded Server running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown requested…")
    finally:
        server.shutdown()
        # 모든 세션 ffmpeg 프로세스 종료
        for session_id, proc in sessions.items():
            if proc.stdin:
                proc.stdin.close()
            proc.wait()
            print(f"[SHUTDOWN] session={session_id} process terminated")
        sys.exit(0)

if __name__ == "__main__":
    try:
        user_input = input("서버 포트를 입력하세요 (기본값: 5000): ").strip()
        port = int(user_input) if user_input else 5000
    except ValueError:
        print("잘못된 입력입니다. 기본 포트 5000번을 사용합니다.")
        port = 5000

    run(port)
#!/usr/bin/env python3
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

RECORD_DIR = "recordings"
FINAL_FILE = "final_recording.webm"

os.makedirs(RECORD_DIR, exist_ok=True)

def start_ffmpeg():
    return subprocess.Popen([
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-f", "webm",
        "-i", "pipe:0",
        "-c", "copy",
        os.path.join(RECORD_DIR, FINAL_FILE)
    ], stdin=subprocess.PIPE)

ffmpeg = start_ffmpeg()

# NOTE: chunk는 queue담고 feed pipe이 성공할 때만 chunk지우기 
# (현재 재녹화 시 ffmpeg = start_ffmpeg()가 제 때 되지 않음)
def feed_pipe(data: bytes):
    global ffmpeg
    try:
        # 1) 정상 쓰기 시도
        ffmpeg.stdin.write(data)
        ffmpeg.stdin.flush()

    except (BrokenPipeError, ValueError, OSError) as e:
        # 2) 에러 발생 시 종료 감지 → 재시작
        print(f"[FEED ERROR] {e}, restarting ffmpeg...")
        ffmpeg = start_ffmpeg()

        # 3) 한 번만 재시도
        try:
            ffmpeg.stdin.write(data)
            ffmpeg.stdin.flush()
        except Exception as e2:
            print(f"[FEED RETRY ERROR] {e2}")

class SimpleConcatHandler(BaseHTTPRequestHandler):
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except ConnectionResetError:
            pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        global ffmpeg
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/upload":
            qs    = parse_qs(parsed.query)
            idx   = qs.get("part", ["0"])[0]
            size  = int(self.headers.get('Content-Length', 0))
            chunk = self.rfile.read(size)

            fn = os.path.join(RECORD_DIR, f"chunk_{idx}.webm")
            with open(fn, "wb") as f:
                f.write(chunk)
            print(f"[UPLOAD] saved chunk_{idx}.webm ({size} bytes)")

            # 해당 chunk 데이터를 ffmpeg 파이프에 전달하여 녹화에 포함시킴
            feed_pipe(chunk)
            
            # chunk 파일을 디스크에서 삭제하여 저장 공간 낭비 방지
            os.remove(fn)

            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"ok")
            return

        if path == "/merge":
            if ffmpeg.stdin:
                ffmpeg.stdin.close()
                ffmpeg.wait()
                print("[MERGE] ffmpeg pipe closed, final file saved")

            ffmpeg = start_ffmpeg()

            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"reset done")
            return

        self.send_error(404, "Not Found")

    def do_GET(self):
        if urlparse(self.path).path == "/merge":
            return self.do_POST()
        self.send_error(404, "Not Found")

def run(port=5000):
    server = HTTPServer(('', port), SimpleConcatHandler)
    print(f"Server running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown requested…")
    finally:
        server.shutdown()
        if ffmpeg.stdin:
            ffmpeg.stdin.close()
        ffmpeg.wait()
        print("ffmpeg terminated cleanly.")
        sys.exit(0)

if __name__ == "__main__":
    run()
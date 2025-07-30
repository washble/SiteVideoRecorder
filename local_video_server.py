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

# pending_chunks: (filename, data) 를 쌓아두고, feed_pipe 성공 시에만 삭제
pending_chunks = []

def feed_pipe(data: bytes) -> bool:
    global ffmpeg
    try:
        ffmpeg.stdin.write(data)
        ffmpeg.stdin.flush()
        return True
    except (BrokenPipeError, ValueError, OSError) as e:
        print(f"[FEED ERROR] {e}, restarting ffmpeg...")
        ffmpeg = start_ffmpeg()
        try:
            ffmpeg.stdin.write(data)
            ffmpeg.stdin.flush()
            return True
        except Exception as e2:
            print(f"[FEED RETRY ERROR] {e2}")
            return False

def process_queue():
    global pending_chunks
    new_queue = []
    for fn, chunk in pending_chunks:
        success = feed_pipe(chunk)
        if success:
            try:
                os.remove(fn)
                print(f"[CLEANUP] removed {fn}")
            except OSError as e:
                print(f"[CLEANUP ERROR] {e}")
        else:
            new_queue.append((fn, chunk))
    pending_chunks = new_queue

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

            # 큐에 추가 → process_queue() 호출
            pending_chunks.append((fn, chunk))
            process_queue()

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
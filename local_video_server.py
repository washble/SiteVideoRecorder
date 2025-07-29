#!/usr/bin/env python3
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

RECORD_DIR = "recordings"
FINAL_FILE = "final_recording.webm"

os.makedirs(RECORD_DIR, exist_ok=True)

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
        parsed = urlparse(self.path)
        path = parsed.path

        # 조각 업로드
        if path == "/upload":
            qs    = parse_qs(parsed.query)
            idx   = qs.get("part", ["0"])[0]
            size  = int(self.headers.get('Content-Length', 0))
            chunk = self.rfile.read(size)

            fn = os.path.join(RECORD_DIR, f"chunk_{idx}.webm")
            with open(fn, "wb") as f:
                f.write(chunk)

            print(f"[UPLOAD] saved chunk_{idx}.webm ({size} bytes)")
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b"ok")
            return

        # 바이너리 단순 연결 병합
        if path == "/merge":
            try:
                final_path = os.path.join(RECORD_DIR, FINAL_FILE)

                # 기존 최종 파일 삭제
                if os.path.exists(final_path):
                    os.remove(final_path)

                # 조각 파일 인덱스 순 정렬
                chunk_files = sorted(
                    [fn for fn in os.listdir(RECORD_DIR)
                     if fn.startswith("chunk_") and fn.endswith(".webm")],
                    key=lambda x: int(x.split("_",1)[1].split(".")[0])
                )
                if not chunk_files:
                    raise RuntimeError("No chunks to merge")

                # 순서대로 바이너리 이어쓰기
                with open(final_path, "wb") as out:
                    for fn in chunk_files:
                        in_path = os.path.join(RECORD_DIR, fn)
                        with open(in_path, "rb") as inp:
                            out.write(inp.read())
                print("[MERGE] Concatenated:", chunk_files)

                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(b"merged")
            except Exception as e:
                print("[MERGE][ERROR]", e)
                self.send_response(500)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(f"merge error: {e}".encode())
            return

        self.send_error(404, "Not Found")

    def do_GET(self):
        if urlparse(self.path).path == "/merge":
            return self.do_POST()
        self.send_error(404, "Not Found")

def run(port=5000):
    print(f"Server running at http://localhost:{port}")
    HTTPServer(('', port), SimpleConcatHandler).serve_forever()

if __name__ == "__main__":
    run()
#!/usr/bin/env python3

import json
import os
import time
import random
import threading
import subprocess
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import WebDriverException, JavascriptException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# ==========================================
# 1. 크롬 실행 및 드라이버 연결 로직
# ==========================================

def find_chrome_exe(paths):
    for path in paths:
        for root, dirs, files in os.walk(path):
            if 'chrome.exe' in files:
                return os.path.join(root, 'chrome.exe')
    return None

def setup_driver_option(use_headless=False, debug_port=19440):
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
    if use_headless:
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
    options.add_argument("--incognito")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-popup-blocking")
    return options

def init_driver(use_headless=False, debug_port=19440):
    paths_to_search = [
        'C:\\Program Files\\Google\\Chrome\\Application',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application'
    ]
    chrome_path = find_chrome_exe(paths_to_search)
    if chrome_path:
        try:
            cmd = [
                chrome_path,
                f"--remote-debugging-port={debug_port}",
                f"--user-data-dir=C:\\chromeTemp{debug_port}",
                "--incognito",
                "--log-level=3",
                "--disable-popup-blocking",
            ]
            if use_headless:
                cmd += ["--headless", "--disable-gpu"]
            subprocess.Popen(cmd, shell=False)
            print("[Chrome 실행] 디버깅 모드로 크롬을 시작했습니다.")
        except FileNotFoundError as e:
            print(f"[오류] Chrome 실행 실패: {e}")
    else:
        print("[에러] chrome.exe 경로를 찾지 못했습니다.")

    try:
        service = ChromeService(ChromeDriverManager().install())
        options = setup_driver_option(use_headless, debug_port)
        driver = webdriver.Chrome(service=service, options=options)
        driver.implicitly_wait(3)
        print("WebDriver 초기화 성공")
        return driver
    except WebDriverException as e:
        print(f"[오류] WebDriver 초기화 실패: {e}")
        return None

# ==========================================
# 2. 기존 녹화 및 대기 로직
# ==========================================

def wait_for_page_and_video(driver, page_timeout=10, video_timeout=15):
    # 페이지 완독 대기
    WebDriverWait(driver, page_timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    
    # 디버깅 모드 연결 시 유튜브 내부에서 비디오 로딩을 잠시 대기
    time.sleep(2)
    
    # 안전하게 JavaScript로 동영상 재생 상태 프로미스 처리
    try:
        driver.execute_script("""
          function findVideo() {
            const v = document.querySelector('video');
            if (v) return v;
            for (const iframe of document.querySelectorAll('iframe')) {
              try {
                const doc = iframe.contentDocument || iframe.contentWindow.document;
                const vid = doc.querySelector('video');
                if (vid) return vid;
              } catch {}
            }
            return null;
          }
          const video = findVideo();
          if (!video) throw 'Video element not found';
          return new Promise(resolve => {
            if (video.readyState >= 2) {
              resolve();
            } else {
              video.onloadedmetadata = () => resolve();
            }
          });
        """)
    except JavascriptException as e:
        print(f"[주의] 비디오 엘리먼트 동기화 중 경고 발생 (무시하고 진행 가능): {e.message}")
    
    time.sleep(3)

def inject_recorder_script(driver, chunk_ms=1000):
    # 중괄호 충돌을 방지하기 위해 자바스크립트의 모든 { }를 {{ }}로 에스케이프 처리했습니다.
    # 파이썬에서 넘겨받는 변수인 {chunk_ms} 부분만 싱글 중괄호로 유지됩니다.
    js = f"""
    window._recorder_control = {{
      recorder: null,
      part: 0,
      uploads: [],
      session_id: null,
      start: async function() {{
        const sessionRes = await fetch('http://localhost:5000/session');
        this.session_id = await sessionRes.text();

        function findVideo() {{
          const v = document.querySelector('video');
          if (v) return v;
          for (const iframe of document.querySelectorAll('iframe')) {{
            try {{
              const doc = iframe.contentDocument || iframe.contentWindow.document;
              const vid = doc.querySelector('video');
              if (vid) return vid;
            }} catch {{ }}
          }}
          return null;
        }}
        const video = findVideo();
        if (!video) {{ alert("No video"); return; }}
        video.muted = true;
        await video.play();
        if (video.readyState < 2) await new Promise(r => video.onloadedmetadata = r);

        const stream = video.captureStream(60);
        const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
          ? 'video/webm;codecs=vp9'
          : 'video/webm';

        const recorder = new MediaRecorder(stream, {{
          mimeType: mime,
          videoBitsPerSecond: 12000000,
          audioBitsPerSecond: 192000
        }});
        this.recorder = recorder;

        recorder.ondataavailable = e => {{
          if (!e.data || e.data.size === 0) return;
          const p = fetch(
            'http://localhost:5000/upload?session=' + this.session_id + '&part=' + this.part, {{
              method: 'POST',
              mode: 'cors',
              headers: {{ 'Content-Type': 'video/webm' }},
              body: e.data
            }}
          )
          .then(res => console.log(`[chunk ${{this.part}}] upload status:`, res.status))
          .catch(err => console.error(`[chunk ${{this.part}}] upload failed:`, err));
          this.uploads.push(p);
          this.part++;
        }};

        recorder.onstop = async () => {{
          console.log('Recording stopped, waiting for uploads...');
          await Promise.all(this.uploads);
          console.log('All chunks uploaded, merging...');
          const res = await fetch('http://localhost:5000/merge?session=' + this.session_id, {{
            method: 'POST',
            mode: 'cors'
          }});
          console.log('Merge status:', res.status);
          console.log('Upload & merge done');
        }};

        // 파이썬 매개변수인 chunk_ms를 주입받는 유일한 공간
        recorder.start({chunk_ms});
        console.log("Recording started.");
      }},
      stop: function() {{
        if (this.recorder && this.recorder.state === "recording") {{
          this.recorder.stop();
          console.log("Recording stopped.");
        }} else {{
          console.log("Recorder not active.");
        }}
      }}
    }};
    """
    driver.execute_script(js)

    # 동영상 끝나면 자동으로 녹화 중지
    driver.execute_script("""
      const video = document.querySelector('video');
      if (video) {
        video.addEventListener('ended', () => {
          if (window._recorder_control?.recorder?.state === 'recording') {
            window._recorder_control.stop();
          }
        });
      }
    """)

def start_recording(driver):
    driver.execute_script("""
      if (window._recorder_control) {
        window._recorder_control.part = 0;
        window._recorder_control.uploads = [];
        window._recorder_control.start();
      }
    """)

def stop_recording(driver):
    driver.execute_script("""
      window._recorder_control?.stop?.();
      const video = document.querySelector('video');
      if (video) video.pause();
    """)

# ==========================================
# 3. 메인 실행 루프
# ==========================================

def main():
    url = "https://www.youtube.com/watch?v=lxGuMw4GcxM"
    debug_port = 19440
    
    # 대기 설정용 Lock (필요시 확장성용 기본 배치)
    driver_lock = threading.Lock()
    
    # 🔴 수정된 부분: 지정 방식으로 디버깅 크롬 구동 (False 전송으로 창 오픈 활성화)
    driver = init_driver(use_headless=False, debug_port=debug_port)
    if not driver:
        print("[에러] 드라이버 초기화에 실패하여 프로그램을 종료합니다.")
        return

    try:
        with driver_lock:
            driver.get(url)
            
        wait_for_page_and_video(driver)
        inject_recorder_script(driver, chunk_ms=1000)

        while True:
            cmd = input("🎬 Enter 키를 누르면 녹화를 시작합니다 (q + Enter → 종료): ")
            if cmd.lower() == 'q':
                break

            with driver_lock:
                start_recording(driver)
                
            input("🛑 Enter 키를 누르면 녹화를 종료합니다: ")
            
            with driver_lock:
                stop_recording(driver)

            print("✅ 녹화가 종료되었습니다. 다시 시작할 준비가 되었습니다.\n")
            time.sleep(1)

    finally:
        with driver_lock:
            driver.quit()

if __name__ == "__main__":
    main()
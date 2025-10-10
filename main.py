#!/usr/bin/env python3

import time
# pip install selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

def setup_driver(startup_url):
    options = Options()
    options.add_argument("--incognito")
    options.add_argument("--log-level=3")
    # options.add_argument("--headless")  # 필요 시 활성화

    driver = webdriver.Chrome(options=options)
    driver.get(startup_url)
    return driver

def wait_for_page_and_video(driver, page_timeout=10, video_timeout=15):
    WebDriverWait(driver, page_timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    WebDriverWait(driver, video_timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "video"))
    )
    driver.execute_script("""
      const video = document.querySelector('video');
      if (!video) throw 'Video element not found';
      return new Promise(resolve => {
        if (video.readyState >= 2) {
          resolve();
        } else {
          video.onloadedmetadata = () => resolve();
        }
      });
    """)
    time.sleep(5)

def inject_recorder_script(driver, chunk_ms=1000):
    js = rf"""
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

def main():
    url = "https://youtu.be/fUi4Ej9guxs?t=3584"
    driver = setup_driver(url)

    try:
        wait_for_page_and_video(driver)
        inject_recorder_script(driver, chunk_ms=1000)

        while True:
            cmd = input("🎬 Enter 키를 누르면 녹화를 시작합니다 (q + Enter → 종료): ")
            if cmd.lower() == 'q':
                break

            start_recording(driver)
            input("🛑 Enter 키를 누르면 녹화를 종료합니다: ")
            stop_recording(driver)

            print("✅ 녹화가 종료되었습니다. 다시 시작할 준비가 되었습니다.\n")
            time.sleep(1)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
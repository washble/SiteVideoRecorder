#!/usr/bin/env python3

import time
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
    # 1) 페이지 로드 완료 대기
    WebDriverWait(driver, page_timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    # 2) <video> 요소가 DOM에 나타날 때까지 대기
    WebDriverWait(driver, video_timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "video"))
    )
    # 3) 비디오 메타데이터 로드 대기
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
      start: async function() {{
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
        if (video.paused) {{
          await video.play();
        }}

        if (video.readyState < 2) {{
          await new Promise(r => video.onloadedmetadata = r);
        }}

        const stream = video.captureStream(60);
        const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
          ? 'video/webm;codecs=vp9'
          : 'video/webm';

        const recorder = new MediaRecorder(stream, {{ mimeType: mime }});
        this.recorder = recorder;

        recorder.ondataavailable = e => {{
          if (!e.data || e.data.size === 0) return;
          const p = fetch(
            'http://localhost:5000/upload?part=' + this.part, {{
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
          const res = await fetch('http://localhost:5000/merge', {{
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

def start_recording(driver):
    driver.execute_script("window._recorder_control?.start?.();")

def stop_recording(driver):
    driver.execute_script("window._recorder_control?.stop?.();")

def main():
    url = "https://www.youtube.com/watch?v=JvW29MP8Nxo"
    driver = setup_driver(url)

    try:
        wait_for_page_and_video(driver)
        inject_recorder_script(driver, chunk_ms=1000)

        input("🎬 Enter 키를 누르면 녹화를 시작합니다: ")
        start_recording(driver)

        input("🛑 Enter 키를 누르면 녹화를 종료합니다: ")
        stop_recording(driver)

        time.sleep(5)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
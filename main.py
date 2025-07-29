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

def inject_recorder_script(driver, record_seconds=10, chunk_ms=1000):
    js = rf"""
    (async function() {{
      // video 요소 찾기 (페이지 + iframe)
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

      // 재생 보장
      video.muted = true;
      if (video.paused) {{
        await video.play();
      }}

      // 메타데이터 로드 또는 canplay 대기
      if (video.readyState < 2) {{
        await new Promise(r => video.onloadedmetadata = r);
      }}

      // 스트림 확보
      const stream = video.captureStream(60);
      const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
        ? 'video/webm;codecs=vp9'
        : 'video/webm';

      let part = 0;
      const uploads = [];
      const recorder = new MediaRecorder(stream, {{ mimeType: mime }});

      recorder.ondataavailable = e => {{
        if (!e.data || e.data.size === 0) return;
        console.log(`[chunk ${{part}}] size=${{e.data.size}}`);
        const p = fetch(
          'http://localhost:5000/upload?part=' + part, {{
            method: 'POST',
            mode: 'cors',
            headers: {{ 'Content-Type': 'video/webm' }},
            body: e.data
          }}
        )
        .then(res => console.log(`[chunk ${{part}}] upload status:`, res.status))
        .catch(err => console.error(`[chunk ${{part}}] upload failed:`, err));
        uploads.push(p);
        part++;
      }};

      recorder.onstop = async () => {{
        console.log('Recording stopped, waiting for uploads...');
        await Promise.all(uploads);
        console.log('All chunks uploaded, merging...');
        const res = await fetch('http://localhost:5000/merge', {{
          method: 'POST',
          mode: 'cors'
        }});
        console.log('Merge status:', res.status);
        console.log('Upload & merge done');
      }};

      recorder.start({chunk_ms});                       // 1초 단위 청크
      setTimeout(() => recorder.stop(), {record_seconds * 1000});  // 녹화 시간
    }})();
    """
    driver.execute_script(js)

def main():
    url = "https://www.youtube.com/watch?v=JvW29MP8Nxo"
    driver = setup_driver(url)

    try:
        wait_for_page_and_video(driver)
        inject_recorder_script(driver, record_seconds=10, chunk_ms=1000)

        # 충분히 녹화 & 업로드 대기
        time.sleep(15)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
// 북마클릿 또는 Console에서 사용
// 녹화 시작
javascript:(function() {
  function findVideoInIframes() {
    const iframes = Array.from(document.querySelectorAll('iframe'));
    for (const iframe of iframes) {
      try {
        const doc = iframe.contentDocument || iframe.contentWindow.document;
        const vid = doc.querySelector('video');
        if (vid) return vid;
      } catch (e) {
        console.warn('⚠️ iframe 접근 불가:', e);
      }
    }
    return null;
  }

  let video = document.querySelector('video');
  if (!video) {
    console.log('👀 페이지에 직접 video 요소가 없습니다. iframe 내부 탐색…');
    video = findVideoInIframes();
  }

  if (!video) {
    alert('❌ <video> 요소를 찾을 수 없습니다.');
    return;
  }

  let recorder;
  let part = 0;
  const uploadedChunks = [];

  function startRecording() {
    const stream = video.captureStream(60);
    const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
      ? 'video/webm;codecs=vp9,opus'
      : 'video/webm;codecs=vp8,opus';

    recorder = new MediaRecorder(stream, {
      mimeType: mime,
      videoBitsPerSecond: 60000000,
      audioBitsPerSecond: 320000
    });

    recorder.ondataavailable = e => {
      if (!e.data || e.data.size === 0) return;

      const uploadPromise = fetch(`http://localhost:5000/upload?part=${part}`, {
        method: 'POST',
        mode: 'cors',
        headers: { 'Content-Type': 'video/webm' },
        body: e.data
      })
      .then(res => console.log(`[chunk ${part}] upload status:`, res.status))
      .catch(err => console.error(`[chunk ${part}] upload failed:`, err));

      uploadedChunks.push(uploadPromise);
      part++;
    };

    recorder.onstop = () => {
      console.log('🎬 녹화 종료, 업로드된 청크 병합 요청 중…');
      Promise.all(uploadedChunks)
        .then(() => fetch('http://localhost:5000/merge', { method: 'POST', mode: 'cors' }))
        .then(res => console.log('🧩 병합 응답:', res.status))
        .catch(err => console.error('⚠️ 병합 실패:', err));
    };

    recorder.start(1000);
    console.log('🔴 녹화 시작됨');
    window.recorder = recorder;
  }

  if (video.readyState >= 1) {
    startRecording();
  } else {
    video.addEventListener('loadedmetadata', startRecording);
  }

  console.log('📌 브라우저에서 하드웨어 인코딩 활성화: chrome://flags/#enable-webrtc-hw-encoding');
})();

// 녹화 정지
javascript:(function() {
  try {
    recorder.stop();
  } catch (e) {
    alert('recorder 객체가 존재하지 않거나 오류가 발생했습니다.');
  }
})();


// 녹화 시작 : 청크 백그라운드 통신
// 주석은 지우고 Bookmarklet으로 사용
javascript:(function() {
  // 1. <video> 요소 찾기
  function findVideoInIframes() {
    const iframes = Array.from(document.querySelectorAll('iframe'));
    for (const iframe of iframes) {
      try {
        const doc = iframe.contentDocument || iframe.contentWindow.document;
        const vid = doc.querySelector('video');
        if (vid) return vid;
      } catch (e) {
        console.warn('⚠️ iframe 접근 불가:', e);
      }
    }
    return null;
  }

  let video = document.querySelector('video');
  if (!video) {
    console.log('👀 페이지에 <video> 요소가 없습니다. iframe 내부 탐색…');
    video = findVideoInIframes();
  }
  if (!video) {
    return alert('❌ <video> 요소를 찾을 수 없습니다.');
  }

  // 2. TrustedTypes policy 생성 (Chrome 등에서 getPolicy 미지원)
  let policy = null;
  if (window.trustedTypes && typeof trustedTypes.createPolicy === 'function') {
    try {
      policy = trustedTypes.createPolicy('upload-worker-policy', {
        createScriptURL: input => {
          if (input.startsWith('blob:')) return input;
          throw new Error('허용되지 않는 URL');
        }
      });
    } catch (e) {
      console.warn('⚠️ TrustedTypes policy 생성 실패:', e);
    }
  }

  // 3. 세션 발급
  let sessionId = null;
  fetch('http://localhost:5000/session', { method: 'GET', mode: 'cors' })
    .then(res => res.text())
    .then(id => {
      sessionId = id;
      console.log('🎫 세션 ID:', sessionId);

      // 4. Web Worker 스크립트 (세션 ID 포함)
      const workerCode = `
        self.onmessage = async function(e) {
          const { chunk, part, sessionId } = e.data;
          try {
            const res = await fetch('http://localhost:5000/upload?session=' + sessionId + '&part=' + part, {
              method: 'POST',
              mode: 'cors',
              headers: { 'Content-Type': 'video/webm' },
              body: chunk
            });
            self.postMessage({ part, status: res.status });
          } catch (err) {
            self.postMessage({ part, error: err.message });
          }
        };
      `;

      // 5. Blob → URL → TrustedScriptURL
      const blob = new Blob([workerCode], { type: 'application/javascript' });
      let workerUrl = URL.createObjectURL(blob);
      if (policy) {
        try {
          workerUrl = policy.createScriptURL(workerUrl);
        } catch (e) {
          console.warn('⚠️ TrustedScriptURL 변환 실패:', e);
        }
      }

      // 6. Worker 생성
      const uploadWorker = new Worker(workerUrl);

      // 7. 전역 상태 및 업로드 추적
      let recorder = null;
      let part = 0;
      const pendingUploads = [];

      uploadWorker.onmessage = e => {
        console.log('[upload-worker]', e.data);
      };

      // 8. 녹화 시작
      function startRecording() {
        const stream = video.captureStream(60);
        const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
          ? 'video/webm;codecs=vp9,opus'
          : 'video/webm;codecs=vp8,opus';

        recorder = new MediaRecorder(stream, {
          mimeType,
          videoBitsPerSecond: 60000000,
          audioBitsPerSecond: 320000
        });

        recorder.ondataavailable = e => {
          if (!e.data || e.data.size === 0) return;
          const currentPart = part++;
          const uploadPromise = new Promise((resolve, reject) => {
            function onMsg(ev) {
              if (ev.data.part !== currentPart) return;
              ev.data.error ? reject(ev.data.error) : resolve(ev.data.status);
              uploadWorker.removeEventListener('message', onMsg);
            }
            uploadWorker.addEventListener('message', onMsg);
          });
          pendingUploads.push(uploadPromise);
          uploadWorker.postMessage({ chunk: e.data, part: currentPart, sessionId });
        };

        recorder.onstop = () => {
          console.log('🎬 녹화 종료 – 모든 청크 업로드 후 병합 요청…');

          Promise.all(pendingUploads)
            .then(() => {
              console.log('✅ 업로드 완료, 병합 요청');
              return fetch('http://localhost:5000/merge?session=' + sessionId, {
                method: 'POST',
                mode: 'cors'
              });
            })
            .then(res => console.log('🧩 병합 응답 상태:', res.status))
            .catch(err => console.error('⚠️ 병합 실패:', err))
            .finally(() => {
              uploadWorker.terminate();
              URL.revokeObjectURL(workerUrl);
              console.log('🛑 워커 종료 완료');
            });
        };

        recorder.start(1000);
        console.log('🔴 녹화 시작됨');

        window.recorder = recorder;
        window.uploadWorker = uploadWorker;
        window.uploadWorkerUrl = workerUrl;
      }

      if (video.readyState >= 1) {
        startRecording();
      } else {
        video.addEventListener('loadedmetadata', startRecording);
      }
    })
    .catch(err => {
      console.error('❌ 세션 발급 실패:', err);
      alert('❌ 서버로부터 세션을 가져오는데 실패했습니다.');
    });

})();

// 녹화 정지용 북마클릿
javascript:(function() {
  if (!window.recorder) {
    return alert('❌ recorder 객체가 없습니다.');
  }

  window.recorder.stop();
  console.log('⏹ 녹화 중지 요청 보냄');
})();

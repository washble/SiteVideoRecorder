// 북마클릿 또는 Console에서 사용
// 녹화 시작 최적화
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
      audioBitsPerSecond: 256000
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

    recorder.start(1000);  // 1초마다 ondataavailable 호출
    console.log('🔴 녹화 시작됨');
    console.log('📌 크롬 성능 향상 팁: chrome://flags/#enable-webrtc-hw-encoding');

    window.recorder = recorder;
  }

  if (video.readyState >= 1) {
    startRecording();
  } else {
    video.addEventListener('loadedmetadata', startRecording);
  }
})();


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
    const stream = video.captureStream();
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
})();

// 녹화 정지
javascript:(function() {
  try {
    recorder.stop();
  } catch (e) {
    alert('recorder 객체가 존재하지 않거나 오류가 발생했습니다.');
  }
})();
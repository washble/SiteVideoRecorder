// 북마클릿 또는 Console에서 사용
javascript:(function() {
    const video = document.querySelector('video');
    if (!video) {
      alert('❌ <video> 요소를 찾을 수 없습니다.');
      return;
    }
  
    let recorder;
    let part = 0;
    let uploadedChunks = [];
  
    function startRecording() {
      const stream = video.captureStream();
      const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
        ? 'video/webm;codecs=vp9,opus'
        : 'video/webm;codecs=vp8,opus';
  
      recorder = new MediaRecorder(stream, {
          mimeType: mime,
          videoBitsPerSecond: 12000000,
          audioBitsPerSecond: 192000
      });
  
      recorder.ondataavailable = e => {
        if (!e.data || e.data.size === 0) return;
  
        const upload = fetch('http://localhost:5000/upload?part=' + part, {
          method: 'POST',
          mode: 'cors',
          headers: { 'Content-Type': 'video/webm' },
          body: e.data
        })
        .then(res => {
          console.log(`[chunk ${part}] upload status:`, res.status);
        })
        .catch(err => {
          console.error(`[chunk ${part}] upload failed:`, err);
        });
  
        uploadedChunks.push(upload);
        part++;
      };
  
      recorder.onstop = () => {
        console.log('🎬 녹화 종료, 업로드된 청크 병합 요청 중…');
        Promise.all(uploadedChunks)
          .then(() => {
            return fetch('http://localhost:5000/merge', {
              method: 'POST',
              mode: 'cors'
            });
          })
          .then(res => {
            console.log('🧩 병합 응답:', res.status);
          })
          .catch(err => {
            console.error('⚠️ 병합 실패:', err);
          });
      };
  
      recorder.start(1000);
      console.log('🔴 녹화 시작됨 (vp9/opus 또는 vp8/opus)');
      window.recorder = recorder;
    }
  
    if (video.readyState >= 1) {
      startRecording();
    } else {
      video.addEventListener('loadedmetadata', startRecording);
    }
})();
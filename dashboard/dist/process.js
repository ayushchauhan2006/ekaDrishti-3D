(() => {
  const originalInput = document.querySelector('#mission-files');
  const input = originalInput.cloneNode(true);
  originalInput.replaceWith(input);
  const originalButton = document.querySelector('#process-button');
  const button = originalButton.cloneNode(true);
  originalButton.replaceWith(button);
  const notice = document.querySelector('#upload-notice');
  const pipeline = document.querySelector('#pipeline');
  const statusBox = document.createElement('div');
  statusBox.className = 'job-status'; statusBox.hidden = true; statusBox.setAttribute('aria-live', 'polite');
  statusBox.innerHTML = '<span class="spinner"></span><div><strong></strong><small></small></div>';
  pipeline.insertAdjacentElement('afterend', statusBox);
  const stage = statusBox.querySelector('strong'); const log = statusBox.querySelector('small'); let pollTimer;
  function showStatus(data) {
    const active = data.status === 'running'; statusBox.hidden = !data.stage; stage.textContent = data.stage || '';
    log.textContent = Array.isArray(data.log) && data.log.length ? data.log.at(-1) : (data.message || '');
    button.disabled = active; button.textContent = active ? 'Processing locally…' : 'Process mission';
    if (data.status === 'complete') { notice.hidden = false; notice.textContent = '3D reconstruction ready. Review calibration status before taking real-world measurements.'; }
    if (data.status === 'failed') { notice.hidden = false; notice.textContent = `Processing stopped: ${data.message || 'Check the dashboard terminal.'}`; }
    if (!active && pollTimer) { clearInterval(pollTimer); pollTimer = undefined; }
  }
  async function checkStatus() { try { showStatus(await (await fetch('/api/status')).json()); } catch { /* Static preview has no job API. */ } }
  function selectedFiles() { const files = Array.from(input.files); return { video: files.find(file => file.name.toLowerCase().endsWith('.mp4') || file.name.toLowerCase().endsWith('.mov')), telemetry: files.find(file => file.name.toLowerCase().endsWith('.srt')) }; }
  input.addEventListener('change', () => {
    const { video, telemetry } = selectedFiles(); notice.hidden = false;
    notice.textContent = !video || !telemetry ? 'Choose the original DJI MP4 and its matching DJI SRT file.' : 'Mission selected: ' + video.name + ' + ' + telemetry.name + '. Geographic reconstruction is available.';
  });
  button.addEventListener('click', async () => {
    const { video, telemetry } = selectedFiles();
    if (!video || !telemetry) { notice.hidden = false; notice.textContent = 'Choose the original DJI MP4 and its matching DJI SRT before starting reconstruction.'; return; }
    const payload = new FormData(); payload.append('video', video); payload.append('telemetry', telemetry);
    button.disabled = true; button.textContent = 'Sending mission…';
    try { const response = await fetch('/api/process', { method: 'POST', body: payload }); const data = await response.json(); if (!response.ok) throw new Error(data.error || 'The local server rejected this mission.'); showStatus(data); pollTimer = setInterval(checkStatus, 2000); }
    catch (error) { notice.hidden = false; notice.textContent = `Could not start processing: ${error.message}. Run the dashboard using python3 dashboard/server.py.`; button.disabled = false; button.textContent = 'Process mission'; }
  });
  checkStatus();
})();

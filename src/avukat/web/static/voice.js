/**
 * Avukat AI — Sesli Asistan Client
 * Mikrofon capture (AudioWorklet) + WebSocket + PCM playback.
 */
(function () {
  "use strict";

  // --- DOM refs ---
  const btnMic = document.getElementById("btn-mic");
  const btnStop = document.getElementById("btn-stop");
  const statusEl = document.getElementById("voice-status");
  const statusDot = document.getElementById("status-dot");
  const transcriptEl = document.getElementById("transcript");
  const toolLogEl = document.getElementById("tool-log");

  // --- State ---
  let ws = null;
  let audioCtx = null;
  let mediaStream = null;
  let workletNode = null;
  let playbackCtx = null;
  let isRecording = false;
  let playbackQueue = [];
  let isPlaying = false;

  // --- Helpers ---
  function setStatus(text, color) {
    statusEl.textContent = text;
    statusDot.className = "status-dot " + (color || "gray");
  }

  function addTranscript(role, text) {
    const div = document.createElement("div");
    div.className = "transcript-line " + role;
    const label = role === "assistant" ? "AI" : "Sen";
    div.innerHTML = "<strong>" + label + ":</strong> " + escapeHtml(text);
    transcriptEl.appendChild(div);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
  }

  function addToolLog(name, detail) {
    const div = document.createElement("div");
    div.className = "tool-log-entry";
    div.innerHTML =
      '<span class="tool-name">' +
      escapeHtml(name) +
      "</span> " +
      '<span class="tool-detail">' +
      escapeHtml(detail) +
      "</span>";
    toolLogEl.appendChild(div);
    toolLogEl.scrollTop = toolLogEl.scrollHeight;
  }

  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  // --- Playback (PCM 24kHz mono) ---
  function initPlayback() {
    if (!playbackCtx) {
      playbackCtx = new AudioContext({ sampleRate: 24000 });
    }
  }

  function enqueueAudio(pcmBytes) {
    playbackQueue.push(pcmBytes);
    if (!isPlaying) {
      playNextChunk();
    }
  }

  function playNextChunk() {
    if (playbackQueue.length === 0) {
      isPlaying = false;
      return;
    }
    isPlaying = true;
    const raw = playbackQueue.shift();

    // PCM 16-bit LE -> Float32
    const int16 = new Int16Array(raw);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768.0;
    }

    const buffer = playbackCtx.createBuffer(1, float32.length, 24000);
    buffer.getChannelData(0).set(float32);

    const source = playbackCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(playbackCtx.destination);
    source.onended = playNextChunk;
    source.start();
  }

  // --- Microphone ---
  async function startMicrophone() {
    audioCtx = new AudioContext({ sampleRate: 48000 });

    // AudioWorklet yukle
    await audioCtx.audioWorklet.addModule("/static/audio-processor.js");

    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 48000,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });

    const source = audioCtx.createMediaStreamSource(mediaStream);
    workletNode = new AudioWorkletNode(audioCtx, "pcm-processor");

    // Worklet'ten gelen PCM verisini WebSocket'e gonder
    workletNode.port.onmessage = (event) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(event.data); // ArrayBuffer -> binary frame
      }
    };

    source.connect(workletNode);
    workletNode.connect(audioCtx.destination); // silence (worklet cikis uretmez)
  }

  function stopMicrophone() {
    if (workletNode) {
      workletNode.disconnect();
      workletNode = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
      mediaStream = null;
    }
    if (audioCtx) {
      audioCtx.close();
      audioCtx = null;
    }
  }

  // --- WebSocket ---
  function connectWS() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = proto + "//" + location.host + "/ws/voice";

    ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      setStatus("Baglandi, konusabilirsiniz", "green");
    };

    ws.onmessage = (event) => {
      // Binary = audio
      if (event.data instanceof ArrayBuffer) {
        initPlayback();
        enqueueAudio(event.data);
        return;
      }

      // Text = JSON event
      try {
        const data = JSON.parse(event.data);
        handleEvent(data);
      } catch (e) {
        console.warn("WS parse error:", e);
      }
    };

    ws.onclose = (event) => {
      setStatus("Baglanti kapandi", "gray");
      stopSession();
    };

    ws.onerror = (event) => {
      setStatus("Baglanti hatasi", "red");
      console.error("WS error:", event);
    };
  }

  function handleEvent(data) {
    switch (data.type) {
      case "status":
        if (data.state === "connected") {
          setStatus("Gemini bagli, konusun", "green");
        }
        break;

      case "transcript":
        addTranscript(data.role, data.text);
        break;

      case "tool_call":
        addToolLog(
          data.name,
          JSON.stringify(data.args || {}).substring(0, 100)
        );
        setStatus("Arastiriliyor: " + data.name, "yellow");
        break;

      case "tool_result":
        setStatus("Yanit hazirlaniyor...", "green");
        break;

      case "error":
        setStatus("Hata: " + (data.message || ""), "red");
        addTranscript("system", "Hata: " + (data.message || ""));
        break;

      case "pong":
        break;

      default:
        console.log("Unknown event:", data);
    }
  }

  // --- Session control ---
  async function startSession() {
    if (isRecording) return;
    isRecording = true;

    btnMic.disabled = true;
    btnStop.disabled = false;
    setStatus("Mikrofon aciliyor...", "yellow");

    try {
      await startMicrophone();
      connectWS();
    } catch (err) {
      setStatus("Mikrofon izni reddedildi", "red");
      isRecording = false;
      btnMic.disabled = false;
      btnStop.disabled = true;
      console.error("Start error:", err);
    }
  }

  function stopSession() {
    isRecording = false;
    btnMic.disabled = false;
    btnStop.disabled = true;

    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: "stop" }));
      } catch (e) {}
      ws.close();
    }
    ws = null;

    stopMicrophone();
    setStatus("Durduruldu", "gray");
  }

  // --- Ping (keep-alive) ---
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, 15000);

  // --- Event bindings ---
  btnMic.addEventListener("click", startSession);
  btnStop.addEventListener("click", stopSession);
})();

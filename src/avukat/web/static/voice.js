/**
 * Avukat AI — Sesli Asistan Client
 * Mikrofon capture (AudioWorklet) + WebSocket + PCM playback.
 *
 * Key fix: AudioContext MUST be created during user gesture (click)
 * to avoid autoplay policy blocking audio playback.
 */
(function () {
  "use strict";

  // --- DOM refs ---
  var btnMic = document.getElementById("btn-mic");
  var btnStop = document.getElementById("btn-stop");
  var statusEl = document.getElementById("voice-status");
  var statusDot = document.getElementById("status-dot");
  var transcriptEl = document.getElementById("transcript");
  var toolLogEl = document.getElementById("tool-log");
  var micRing = document.getElementById("mic-ring");

  // --- State ---
  var ws = null;
  var audioCtx = null;
  var mediaStream = null;
  var workletNode = null;
  var playbackCtx = null;
  var isRecording = false;
  var playbackQueue = [];
  var isPlaying = false;

  // --- Helpers ---
  function setStatus(text, color) {
    statusEl.textContent = text;
    statusDot.className = "status-dot " + (color || "gray");
  }

  function escapeHtml(str) {
    var d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  function addTranscript(role, text) {
    var div = document.createElement("div");
    div.className = "transcript-line " + role;
    var label = role === "assistant" ? "AI" : role === "user" ? "Sen" : "Sistem";
    div.innerHTML = "<strong>" + label + ":</strong> " + escapeHtml(text);
    transcriptEl.appendChild(div);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
  }

  function addThinking(text) {
    // Thinking text = Gemini'nin ic dusuncesi, kullaniciya gostermek opsiyonel
    // Kucuk/soluk goster
    var div = document.createElement("div");
    div.className = "transcript-line thinking";
    div.innerHTML = "<em>\uD83D\uDCAD " + escapeHtml(text.substring(0, 200)) + "</em>";
    transcriptEl.appendChild(div);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
  }

  function addToolLog(name, detail) {
    var div = document.createElement("div");
    div.className = "tool-log-entry";
    div.innerHTML =
      '<span class="tool-name">' + escapeHtml(name) + "</span> " +
      '<span class="tool-detail">' + escapeHtml(detail) + "</span>";
    toolLogEl.appendChild(div);
    toolLogEl.scrollTop = toolLogEl.scrollHeight;
  }

  // --- Playback (PCM 24kHz mono 16-bit LE) ---
  // CRITICAL: Must be called during user gesture to avoid autoplay block
  function ensurePlaybackCtx() {
    if (!playbackCtx) {
      try {
        playbackCtx = new AudioContext({ sampleRate: 24000 });
        console.log("[Voice] Playback AudioContext created, state:", playbackCtx.state);
      } catch (e) {
        console.error("[Voice] Failed to create playback context:", e);
        return;
      }
    }
    // Resume if suspended (autoplay policy)
    if (playbackCtx.state === "suspended") {
      playbackCtx.resume().then(function() {
        console.log("[Voice] Playback context resumed");
      });
    }
  }

  function enqueueAudio(pcmBytes) {
    if (!playbackCtx || playbackCtx.state !== "running") {
      ensurePlaybackCtx();
    }
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
    if (!playbackCtx || playbackCtx.state !== "running") {
      // Try again in 100ms
      setTimeout(playNextChunk, 100);
      return;
    }
    isPlaying = true;

    var raw = playbackQueue.shift();

    // PCM 16-bit LE -> Float32
    var int16 = new Int16Array(raw);
    var float32 = new Float32Array(int16.length);
    for (var i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768.0;
    }

    var buffer = playbackCtx.createBuffer(1, float32.length, 24000);
    buffer.getChannelData(0).set(float32);

    var source = playbackCtx.createBufferSource();
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

    var source = audioCtx.createMediaStreamSource(mediaStream);
    workletNode = new AudioWorkletNode(audioCtx, "pcm-processor");

    // Worklet'ten gelen PCM verisini WebSocket'e gonder
    workletNode.port.onmessage = function(event) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(event.data); // ArrayBuffer -> binary frame
      }
    };

    source.connect(workletNode);
    workletNode.connect(audioCtx.destination); // silence output
  }

  function stopMicrophone() {
    if (workletNode) {
      workletNode.disconnect();
      workletNode = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach(function(t) { t.stop(); });
      mediaStream = null;
    }
    if (audioCtx) {
      audioCtx.close();
      audioCtx = null;
    }
  }

  // --- WebSocket ---
  function connectWS() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    var url = proto + "//" + location.host + "/ws/voice";

    ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";

    ws.onopen = function() {
      setStatus("Sunucuya baglandi, Gemini baslatiliyor...", "yellow");
    };

    ws.onmessage = function(event) {
      // Binary = audio data from Gemini
      if (event.data instanceof ArrayBuffer) {
        if (event.data.byteLength > 0) {
          console.log("[Voice] Audio received:", event.data.byteLength, "bytes");
          enqueueAudio(event.data);
        }
        return;
      }

      // Text = JSON event
      try {
        var data = JSON.parse(event.data);
        handleEvent(data);
      } catch (e) {
        console.warn("[Voice] WS parse error:", e);
      }
    };

    ws.onclose = function() {
      setStatus("Baglanti kapandi", "gray");
      stopSession();
    };

    ws.onerror = function(event) {
      setStatus("Baglanti hatasi", "red");
      console.error("[Voice] WS error:", event);
    };
  }

  function handleEvent(data) {
    switch (data.type) {
      case "status":
        if (data.state === "connected") {
          setStatus("Baglandi — konusabilirsiniz", "green");
        }
        break;

      case "transcript":
        addTranscript(data.role, data.text);
        if (data.role === "assistant") {
          setStatus("AI konusuyor...", "green");
        }
        break;

      case "thinking":
        // Gemini'nin ic dusuncesi — kucuk goster
        addThinking(data.text);
        setStatus("Dusunuyor...", "yellow");
        break;

      case "turn_complete":
        setStatus("Dinliyor...", "green");
        break;

      case "tool_call":
        addToolLog(data.name, JSON.stringify(data.args || {}).substring(0, 120));
        setStatus("Arastiriliyor: " + data.name, "yellow");
        break;

      case "tool_result":
        setStatus("Yanit hazirlaniyor...", "green");
        break;

      case "error":
        setStatus("Hata: " + (data.message || "Bilinmeyen"), "red");
        addTranscript("system", "Hata: " + (data.message || ""));
        break;

      case "pong":
        break;

      default:
        console.log("[Voice] Unknown event:", data);
    }
  }

  // --- Session control ---
  async function startSession() {
    if (isRecording) return;
    isRecording = true;

    btnMic.disabled = true;
    btnStop.disabled = false;
    if (micRing) micRing.classList.add("active");
    setStatus("Mikrofon aciliyor...", "yellow");

    // CRITICAL: Create playback context during user click gesture
    // Otherwise browser autoplay policy will block audio
    ensurePlaybackCtx();

    try {
      await startMicrophone();
      connectWS();
    } catch (err) {
      setStatus("Mikrofon izni reddedildi", "red");
      isRecording = false;
      btnMic.disabled = false;
      btnStop.disabled = true;
      if (micRing) micRing.classList.remove("active");
      console.error("[Voice] Start error:", err);
    }
  }

  function stopSession() {
    isRecording = false;
    btnMic.disabled = false;
    btnStop.disabled = true;
    if (micRing) micRing.classList.remove("active");

    // Clear playback queue
    playbackQueue = [];
    isPlaying = false;

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
  setInterval(function() {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, 15000);

  // --- Event bindings ---
  btnMic.addEventListener("click", startSession);
  btnStop.addEventListener("click", stopSession);
})();

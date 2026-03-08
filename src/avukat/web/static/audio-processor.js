/**
 * AudioWorklet processor — mikrofon PCM 16-bit 16kHz capture.
 * Browser AudioContext (genellikle 48kHz) -> 16kHz downsample -> PCM16 LE bytes.
 */
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Float32Array(0);
    // Hedef: 16000 Hz
    this._targetRate = 16000;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const channelData = input[0]; // mono channel
    const srcRate = sampleRate; // AudioContext sample rate (e.g. 48000)

    // Downsample ratio
    const ratio = srcRate / this._targetRate;

    // Basit downsample (her ratio'ncu sample'i al)
    const outputLen = Math.floor(channelData.length / ratio);
    if (outputLen === 0) return true;

    const pcm16 = new Int16Array(outputLen);
    for (let i = 0; i < outputLen; i++) {
      const srcIdx = Math.floor(i * ratio);
      // Float32 [-1, 1] -> Int16 [-32768, 32767]
      let sample = channelData[srcIdx];
      sample = Math.max(-1, Math.min(1, sample));
      pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
    }

    // Ana thread'e gonder
    this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    return true;
  }
}

registerProcessor("pcm-processor", PCMProcessor);

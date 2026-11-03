/* Near-ultrasonic FSK. Keep the framing identical to app/audio_fsk.py. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.ZooFSK = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const FREQ_0 = 18000;
  const FREQ_1 = 19000;
  const BIT_SECONDS = 0.02;
  const PREAMBLE = [1, 1, 1, 1, 0, 0, 1, 0];
  const PAYLOAD_BYTES = 6;
  const AMPLITUDE = 0.5;

  function bytesToBits(bytes) {
    const bits = [];
    for (const byte of bytes) {
      for (let shift = 7; shift >= 0; shift -= 1) {
        bits.push((byte >> shift) & 1);
      }
    }
    return bits;
  }

  function bitsToBytes(bits) {
    const out = new Uint8Array(bits.length / 8);
    for (let i = 0; i < out.length; i += 1) {
      let value = 0;
      for (let bit = 0; bit < 8; bit += 1) {
        value = (value << 1) | (bits[i * 8 + bit] ? 1 : 0);
      }
      out[i] = value;
    }
    return out;
  }

  function encode(payload, sampleRate) {
    if (payload.length !== PAYLOAD_BYTES) {
      throw new Error("payload must be 6 bytes");
    }
    const bits = PREAMBLE.concat(bytesToBits(payload));
    const bitN = Math.round(BIT_SECONDS * sampleRate);
    const samples = new Float32Array(bits.length * bitN);
    let phase = 0;
    let cursor = 0;
    for (const bit of bits) {
      const freq = bit ? FREQ_1 : FREQ_0;
      const step = 2 * Math.PI * freq / sampleRate;
      for (let i = 0; i < bitN; i += 1) {
        samples[cursor] = AMPLITUDE * Math.sin(phase);
        phase += step;
        cursor += 1;
      }
    }
    return samples;
  }

  function goertzel(samples, start, count, freq, sampleRate) {
    if (count <= 0) return 0;
    const k = Math.round(freq * count / sampleRate);
    const w = 2 * Math.PI * k / count;
    const coeff = 2 * Math.cos(w);
    let s1 = 0;
    let s2 = 0;
    for (let i = 0; i < count; i += 1) {
      const s0 = samples[start + i] + coeff * s1 - s2;
      s2 = s1;
      s1 = s0;
    }
    return s1 * s1 + s2 * s2 - coeff * s1 * s2;
  }

  function bitPower(samples, start, count, sampleRate) {
    const power0 = goertzel(samples, start, count, FREQ_0, sampleRate);
    const power1 = goertzel(samples, start, count, FREQ_1, sampleRate);
    return { bit: power1 > power0 ? 1 : 0, tone: Math.max(power0, power1) };
  }

  function decode(samples, sampleRate) {
    const bitN = Math.round(BIT_SECONDS * sampleRate);
    if (bitN <= 0) return null;
    const totalBits = PREAMBLE.length + PAYLOAD_BYTES * 8;
    const window = bitN * totalBits;
    if (samples.length < window) return null;
    const hop = Math.max(1, Math.floor(bitN / 4));
    let bestStart = -1;
    let bestScore = -1;
    let bestPower = 0;
    for (let start = 0; start + window <= samples.length; start += hop) {
      let score = 0;
      let power = 0;
      for (let index = 0; index < PREAMBLE.length; index += 1) {
        const found = bitPower(samples, start + index * bitN, bitN, sampleRate);
        power += found.tone;
        if (found.bit === PREAMBLE[index]) score += 1;
      }
      if (score >= PREAMBLE.length - 1 && (score > bestScore || (score === bestScore && power > bestPower))) {
        bestScore = score;
        bestPower = power;
        bestStart = start;
      }
    }
    if (bestStart < 0 || bestPower / PREAMBLE.length < 1000) return null;
    const bits = [];
    const offset = PREAMBLE.length;
    for (let index = 0; index < PAYLOAD_BYTES * 8; index += 1) {
      const found = bitPower(samples, bestStart + (offset + index) * bitN, bitN, sampleRate);
      bits.push(found.bit);
    }
    return bitsToBytes(bits);
  }

  function hexToBytes(hex) {
    const out = new Uint8Array(hex.length / 2);
    for (let i = 0; i < out.length; i += 1) {
      out[i] = parseInt(hex.substr(i * 2, 2), 16);
    }
    return out;
  }

  function bytesToHex(bytes) {
    return Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  function base32(bytes) {
    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    let bits = "";
    for (const byte of bytes) bits += byte.toString(2).padStart(8, "0");
    let out = "";
    for (let i = 0; i < bits.length; i += 5) {
      out += alphabet[parseInt(bits.substr(i, 5).padEnd(5, "0"), 2)];
    }
    return out;
  }

  return {
    FREQ_0: FREQ_0,
    FREQ_1: FREQ_1,
    encode: encode,
    decode: decode,
    goertzel: goertzel,
    hexToBytes: hexToBytes,
    bytesToHex: bytesToHex,
    base32: base32,
  };
});

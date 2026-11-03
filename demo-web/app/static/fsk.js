/* FSK modem. Bands match app/audio_fsk.py. The HMAC payload is unchanged. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ZooFSK = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const PREAMBLE = [1, 1, 1, 1, 0, 0, 1, 0];
  const PAYLOAD_BYTES = 6;
  const AMPLITUDE = 0.5;
  const BANDS = {
    ultrasonic: { f0: 18000, f1: 19000, bitSeconds: 0.04, label: "18/19 kHz" },
    near: { f0: 17000, f1: 17600, bitSeconds: 0.04, label: "17.0/17.6 kHz" },
    audible: { f0: 4200, f1: 5600, bitSeconds: 0.05, label: "4.2/5.6 kHz" },
  };

  function bandOf(name) {
    return BANDS[name] || BANDS.ultrasonic;
  }

  function bytesToBits(bytes) {
    const bits = [];
    for (const byte of bytes) {
      for (let shift = 7; shift >= 0; shift -= 1) bits.push((byte >> shift) & 1);
    }
    return bits;
  }

  function bitsToBytes(bits) {
    const out = new Uint8Array(bits.length / 8);
    for (let i = 0; i < out.length; i += 1) {
      let value = 0;
      for (let bit = 0; bit < 8; bit += 1) value = (value << 1) | (bits[i * 8 + bit] ? 1 : 0);
      out[i] = value;
    }
    return out;
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

  function bitPower(samples, start, count, sampleRate, band) {
    const power0 = goertzel(samples, start, count, band.f0, sampleRate);
    const power1 = goertzel(samples, start, count, band.f1, sampleRate);
    const strong = Math.max(power0, power1);
    const weak = Math.min(power0, power1);
    return {
      bit: power1 > power0 ? 1 : 0,
      tone: strong,
      power0: power0,
      power1: power1,
      confident: strong > weak * 1.6 && strong > 40,
    };
  }

  function majorityBit(samples, start, count, sampleRate, band) {
    const third = Math.max(1, Math.floor(count / 3));
    const votes = [
      bitPower(samples, start, third, sampleRate, band),
      bitPower(samples, start + third, third, sampleRate, band),
      bitPower(samples, start + 2 * third, Math.max(1, count - 2 * third), sampleRate, band),
    ];
    const ones = votes.reduce((sum, vote) => sum + vote.bit, 0);
    const tone = votes.reduce((sum, vote) => sum + vote.tone, 0) / votes.length;
    return { bit: ones >= 2 ? 1 : 0, tone: tone, power0: votes[1].power0, power1: votes[1].power1 };
  }

  function encode(payload, sampleRate, bandName) {
    if (payload.length !== PAYLOAD_BYTES) throw new Error("payload must be 6 bytes");
    const band = bandName ? bandOf(bandName) : { f0: 18000, f1: 19000, bitSeconds: 0.02 };
    const frame = PREAMBLE.concat(bytesToBits(payload));
    const bits = frame.concat(frame);
    const bitN = Math.round(band.bitSeconds * sampleRate);
    const samples = new Float32Array(bits.length * bitN);
    let phase = 0;
    let cursor = 0;
    for (const bit of bits) {
      const freq = bit ? band.f1 : band.f0;
      const step = 2 * Math.PI * freq / sampleRate;
      for (let i = 0; i < bitN; i += 1) {
        samples[cursor] = AMPLITUDE * Math.sin(phase);
        phase += step;
        cursor += 1;
      }
    }
    return samples;
  }

  function decode(samples, sampleRate, bandName) {
    const found = inspect(samples, sampleRate, bandName);
    return found && found.bytes ? found.bytes : null;
  }

  function inspect(samples, sampleRate, bandName) {
    const band = bandName ? bandOf(bandName) : bandOf("ultrasonic");
    const bitN = Math.round(band.bitSeconds * sampleRate);
    const empty = { band: band, power0: 0, power1: 0, preamble: 0, bits: "", bytes: null };
    if (bitN <= 0) return empty;
    const mid = bitPower(samples, 0, Math.min(samples.length, bitN), sampleRate, band);
    empty.power0 = mid.power0;
    empty.power1 = mid.power1;
    const totalBits = PREAMBLE.length + PAYLOAD_BYTES * 8;
    const window = bitN * totalBits;
    if (samples.length < window) return empty;
    const hop = Math.max(1, Math.floor(bitN / 6));
    let bestStart = -1;
    let bestScore = -1;
    let bestPower = 0;
    for (let start = 0; start + window <= samples.length; start += hop) {
      let score = 0;
      let power = 0;
      for (let index = 0; index < PREAMBLE.length; index += 1) {
        const found = majorityBit(samples, start + index * bitN, bitN, sampleRate, band);
        power += found.tone;
        if (found.bit === PREAMBLE[index]) score += 1;
      }
      if (score >= PREAMBLE.length - 1 && (score > bestScore || (score === bestScore && power > bestPower))) {
        bestScore = score;
        bestPower = power;
        bestStart = start;
      }
    }
    empty.preamble = bestScore;
    if (bestStart < 0 || bestPower / PREAMBLE.length < 800) return empty;
    const bits = [];
    for (let index = 0; index < PAYLOAD_BYTES * 8; index += 1) {
      const found = majorityBit(samples, bestStart + (PREAMBLE.length + index) * bitN, bitN, sampleRate, band);
      bits.push(found.bit);
    }
    empty.bits = bits.join("");
    empty.bytes = bitsToBytes(bits);
    const center = bitPower(samples, bestStart, bitN, sampleRate, band);
    empty.power0 = center.power0;
    empty.power1 = center.power1;
    return empty;
  }

  function hexToBytes(hex) {
    const out = new Uint8Array(hex.length / 2);
    for (let i = 0; i < out.length; i += 1) out[i] = parseInt(hex.substr(i * 2, 2), 16);
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
    for (let i = 0; i < bits.length; i += 5) out += alphabet[parseInt(bits.substr(i, 5).padEnd(5, "0"), 2)];
    return out;
  }

  return {
    FREQ_0: 18000,
    FREQ_1: 19000,
    BANDS: BANDS,
    bandOf: bandOf,
    encode: encode,
    decode: decode,
    inspect: inspect,
    goertzel: goertzel,
    hexToBytes: hexToBytes,
    bytesToHex: bytesToHex,
    base32: base32,
  };
});

"""Near-ultrasonic FSK modem: 18 kHz = 0, 19 kHz = 1.

The browser plays and decodes the same framing (see app/static/fsk.js).
A 6-byte payload is one attendance token. Voice-band filtering is provided
so tests can show that a telephony-style lowpass removes the signal.
"""

from __future__ import annotations

import math
import struct
import wave

FREQ_0 = 18000.0
FREQ_1 = 19000.0
BIT_SECONDS = 0.02
PREAMBLE = (1, 1, 1, 1, 0, 0, 1, 0)
PAYLOAD_BYTES = 6
AMPLITUDE = 0.5


def bytes_to_bits(data: bytes) -> list[int]:
    bits: list[int] = []
    for byte in data:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)
    return bits


def bits_to_bytes(bits: list[int]) -> bytes:
    if len(bits) % 8 != 0:
        raise ValueError("bit length")
    out = bytearray()
    for start in range(0, len(bits), 8):
        value = 0
        for bit in bits[start : start + 8]:
            value = (value << 1) | (1 if bit else 0)
        out.append(value)
    return bytes(out)


def encode_pcm(
    payload: bytes,
    sample_rate: int = 48000,
    lead_seconds: float = 0.0,
    amplitude: float = AMPLITUDE,
) -> list[float]:
    if len(payload) != PAYLOAD_BYTES:
        raise ValueError(f"payload must be {PAYLOAD_BYTES} bytes")
    if sample_rate < 40000:
        raise ValueError("sample rate must be at least 40000 to carry 19 kHz")
    bits = list(PREAMBLE) + bytes_to_bits(payload)
    bit_n = int(round(BIT_SECONDS * sample_rate))
    samples = [0.0] * int(round(lead_seconds * sample_rate))
    phase = 0.0
    for bit in bits:
        freq = FREQ_1 if bit else FREQ_0
        step = 2.0 * math.pi * freq / sample_rate
        for _ in range(bit_n):
            samples.append(amplitude * math.sin(phase))
            phase += step
    return samples


def goertzel_power(samples: list[float], freq: float, sample_rate: int) -> float:
    count = len(samples)
    if count == 0:
        return 0.0
    k = round(freq * count / sample_rate)
    w = 2.0 * math.pi * k / count
    coeff = 2.0 * math.cos(w)
    s1 = 0.0
    s2 = 0.0
    for sample in samples:
        s0 = sample + coeff * s1 - s2
        s2 = s1
        s1 = s0
    return s1 * s1 + s2 * s2 - coeff * s1 * s2


def _bit_power(chunk: list[float], sample_rate: int) -> tuple[int, float]:
    power0 = goertzel_power(chunk, FREQ_0, sample_rate)
    power1 = goertzel_power(chunk, FREQ_1, sample_rate)
    bit = 1 if power1 > power0 else 0
    return bit, max(power0, power1)


def decode_pcm(samples: list[float], sample_rate: int = 48000) -> bytes | None:
    bit_n = int(round(BIT_SECONDS * sample_rate))
    if bit_n <= 0:
        return None
    total_bits = len(PREAMBLE) + PAYLOAD_BYTES * 8
    window = bit_n * total_bits
    if len(samples) < window:
        return None
    hop = max(1, bit_n // 4)
    best_start = None
    best_score = -1
    best_power = 0.0
    limit = len(samples) - window + 1
    for start in range(0, limit, hop):
        score = 0
        power = 0.0
        for index, expected in enumerate(PREAMBLE):
            chunk = samples[start + index * bit_n : start + (index + 1) * bit_n]
            bit, tone = _bit_power(chunk, sample_rate)
            power += tone
            if bit == expected:
                score += 1
        if score >= len(PREAMBLE) - 1 and (score > best_score or (score == best_score and power > best_power)):
            best_score = score
            best_power = power
            best_start = start
    # A real tone of amplitude 0.5 produces power on the order of 1e4–1e5.
    # Silence and a voice-band residue stay far below this.
    if best_start is None or best_power / len(PREAMBLE) < 1000.0:
        return None
    bits: list[int] = []
    offset = len(PREAMBLE)
    for index in range(PAYLOAD_BYTES * 8):
        begin = best_start + (offset + index) * bit_n
        chunk = samples[begin : begin + bit_n]
        bit, _tone = _bit_power(chunk, sample_rate)
        bits.append(bit)
    return bits_to_bytes(bits)


def voice_band(samples: list[float], sample_rate: int, cutoff: float = 3400.0, stages: int = 4) -> list[float]:
    """Cascade a Butterworth-style biquad lowpass. Simulates a voice codec cut."""
    filtered = list(samples)
    for _ in range(stages):
        filtered = _biquad_lowpass(filtered, sample_rate, cutoff)
    return filtered


def _biquad_lowpass(samples: list[float], sample_rate: int, cutoff: float) -> list[float]:
    omega = 2.0 * math.pi * cutoff / sample_rate
    cos_w = math.cos(omega)
    sin_w = math.sin(omega)
    q = 1.0 / math.sqrt(2.0)
    alpha = sin_w / (2.0 * q)
    b0 = (1.0 - cos_w) / 2.0
    b1 = 1.0 - cos_w
    b2 = (1.0 - cos_w) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w
    a2 = 1.0 - alpha
    b0 /= a0
    b1 /= a0
    b2 /= a0
    a1 /= a0
    a2 /= a0
    out: list[float] = []
    x1 = x2 = y1 = y2 = 0.0
    for sample in samples:
        y = b0 * sample + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        out.append(y)
        x2, x1 = x1, sample
        y2, y1 = y1, y
    return out


def add_noise(samples: list[float], amplitude: float, seed: int = 1) -> list[float]:
    # Deterministic LCG so tests do not depend on random module state.
    state = seed & 0xFFFFFFFF
    noisy = []
    for sample in samples:
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        unit = (state / 0xFFFFFFFF) * 2.0 - 1.0
        noisy.append(sample + amplitude * unit)
    return noisy


def write_wav(path: str, samples: list[float], sample_rate: int = 48000) -> None:
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for sample in samples:
            clipped = max(-1.0, min(1.0, sample))
            frames += struct.pack("<h", int(round(clipped * 32767)))
        handle.writeframes(frames)


def read_wav(path: str) -> tuple[list[float], int]:
    with wave.open(path, "rb") as handle:
        rate = handle.getframerate()
        count = handle.getnframes()
        raw = handle.readframes(count)
    pcm = struct.unpack("<" + "h" * (len(raw) // 2), raw)
    return [value / 32767.0 for value in pcm], rate


def spike_report(sample_rate: int = 48000) -> str:
    payload = bytes.fromhex("010203040506")
    clean = encode_pcm(payload, sample_rate)
    decoded = decode_pcm(clean, sample_rate)
    noisy = decode_pcm(add_noise(clean, 0.05, seed=7), sample_rate)
    filtered = decode_pcm(voice_band(clean, sample_rate), sample_rate)
    lines = [
        f"payload_hex={payload.hex()}",
        f"samples={len(clean)} seconds={len(clean) / sample_rate:.3f} rate={sample_rate}",
        f"clean_decode={None if decoded is None else decoded.hex()} match={decoded == payload}",
        f"noise_0.05_decode={None if noisy is None else noisy.hex()} match={noisy == payload}",
        f"voice_band_3400Hz_x4_decode={None if filtered is None else filtered.hex()} match={filtered == payload}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(spike_report())

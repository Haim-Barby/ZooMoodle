import os
import tempfile

from app.audio_fsk import BANDS, add_noise, decode_band, decode_pcm, encode_band, encode_pcm, read_wav, voice_band, write_wav
from app.crypto_tokens import b32encode


def test_clean_noise_and_voice_band():
    payload = bytes.fromhex("010203040506")
    clean = encode_pcm(payload, 48000)
    assert decode_pcm(clean, 48000) == payload
    assert decode_pcm(add_noise(clean, 0.05, seed=7), 48000) == payload
    assert decode_pcm(voice_band(clean, 48000), 48000) is None


def test_each_band_round_trips_at_phone_sample_rates():
    payload = bytes.fromhex("0a0b0c0d0e0f")
    for name in BANDS:
        for rate in (44100, 48000):
            samples = encode_band(payload, rate, name)
            assert decode_band(samples, rate, name) == payload
            assert decode_band(add_noise(samples, 0.02, seed=3), rate, name) == payload


def test_wav_round_trip_matches_the_on_screen_code():
    payload = bytes.fromhex("0a0b0c0d0e0f")
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "token.wav")
        write_wav(path, encode_pcm(payload, 48000), 48000)
        samples, rate = read_wav(path)
    decoded = decode_pcm(samples, rate)
    assert decoded == payload
    assert b32encode(decoded) == b32encode(payload)

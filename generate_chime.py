"""Generate a pleasant 2-tone notification chime WAV file."""
import struct, math, wave, os

SAMPLE_RATE = 44100
OUTPUT = os.path.join(os.path.dirname(__file__), "static", "audio", "chime.wav")

def generate_tone(freq, duration, volume=0.5, fade_in=0.01, fade_out=0.15):
    """Generate a sine-wave tone with smooth fade in/out."""
    samples = []
    n_samples = int(SAMPLE_RATE * duration)
    fade_in_samples = int(SAMPLE_RATE * fade_in)
    fade_out_samples = int(SAMPLE_RATE * fade_out)
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        # Base sine wave
        sample = math.sin(2 * math.pi * freq * t)
        # Add a soft harmonic for warmth
        sample += 0.3 * math.sin(2 * math.pi * freq * 2 * t)
        sample += 0.1 * math.sin(2 * math.pi * freq * 3 * t)
        # Envelope: fade in
        if i < fade_in_samples:
            sample *= i / fade_in_samples
        # Envelope: fade out (exponential decay for bell-like sound)
        decay = math.exp(-3.0 * t / duration)
        sample *= decay
        # Fade out at end
        if i > n_samples - fade_out_samples:
            remaining = (n_samples - i) / fade_out_samples
            sample *= remaining
        sample *= volume
        samples.append(sample)
    return samples

def mix(samples_list):
    """Mix multiple sample lists together."""
    max_len = max(len(s) for s in samples_list)
    mixed = [0.0] * max_len
    for samples in samples_list:
        for i, s in enumerate(samples):
            mixed[i] += s
    # Normalize
    peak = max(abs(s) for s in mixed)
    if peak > 0:
        mixed = [s / peak * 0.8 for s in mixed]
    return mixed

# Two-tone chime: a pleasant ascending interval (C6 → E6)
# Gives a friendly "ding-ding" notification feel
tone1 = generate_tone(1047, 0.25, volume=0.7)   # C6 - first ding
tone2_raw = generate_tone(1319, 0.35, volume=0.6)  # E6 - second ding (higher, longer tail)

# Offset the second tone by ~150ms
offset = int(SAMPLE_RATE * 0.15)
tone2 = [0.0] * offset + tone2_raw

mixed = mix([tone1, tone2])

# Write WAV
with wave.open(OUTPUT, 'w') as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)  # 16-bit
    wf.setframerate(SAMPLE_RATE)
    for sample in mixed:
        clamped = max(-1.0, min(1.0, sample))
        wf.writeframes(struct.pack('<h', int(clamped * 32767)))

print(f"[OK] Chime generated: {OUTPUT}")
print(f"   Duration: {len(mixed)/SAMPLE_RATE:.2f}s")
print(f"   Size: {os.path.getsize(OUTPUT)} bytes")

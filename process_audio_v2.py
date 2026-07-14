import os
import numpy as np
import soundfile as sf
from pedalboard import Pedalboard, Reverb, Compressor, Limiter, Gain, HighpassFilter, HighShelfFilter

def generate_tone(freq, duration, sr):
    t = np.linspace(0, duration, int(sr * duration), False)
    tone = np.sin(freq * t * 2 * np.pi)
    
    # Envelope (fast attack, exponential decay)
    attack_time = 0.05
    decay_time = duration - attack_time
    attack = np.linspace(0, 1, int(sr * attack_time))
    decay = np.exp(-np.linspace(0, 5, int(sr * decay_time)))
    envelope = np.concatenate([attack, decay])
    if len(envelope) < len(tone):
        envelope = np.pad(envelope, (0, len(tone) - len(envelope)), 'constant')
    elif len(envelope) > len(tone):
        envelope = envelope[:len(tone)]
    
    return tone * envelope

def generate_chime(sr, type='open'):
    # Notes: C5 and E5
    freqs = [659.25, 523.25] if type == 'close' else [523.25, 659.25]
    duration = 1.2
    note1 = generate_tone(freqs[0], duration, sr)
    note2 = generate_tone(freqs[1], duration, sr)
    
    # Overlap
    gap = int(sr * 0.5)
    total_len = gap + len(note2)
    chime = np.zeros(total_len)
    
    chime[:len(note1)] += note1
    chime[gap:gap+len(note2)] += note2
    
    # Add harmonics for a richer bell sound
    note1_h = generate_tone(freqs[0]*2, duration, sr) * 0.15
    note2_h = generate_tone(freqs[1]*2, duration, sr) * 0.15
    chime[:len(note1_h)] += note1_h
    chime[gap:gap+len(note2_h)] += note2_h
    
    # Add some chorus/detune effect artificially
    note1_d = generate_tone(freqs[0]*1.002, duration, sr) * 0.3
    note2_d = generate_tone(freqs[1]*1.002, duration, sr) * 0.3
    chime[:len(note1_d)] += note1_d
    chime[gap:gap+len(note2_d)] += note2_d
    
    # Normalize chime and apply some reverb to it so it fits the room
    chime = chime / np.max(np.abs(chime)) * 0.4
    
    board = Pedalboard([Reverb(room_size=0.6, wet_level=0.3, dry_level=0.8)])
    chime_stereo = np.stack([chime, chime])
    chime_effected = board(chime_stereo, sr)
    
    return np.mean(chime_effected, axis=0)

def process_audio(input_file, output_file):
    print(f"Loading {input_file}...")
    audio, sample_rate = sf.read(input_file)
    
    if len(audio.shape) == 1:
        audio = np.stack((audio, audio))
    elif audio.shape[1] == 2:
        audio = audio.T
        
    print("Applying voice effects...")
    # Gain staging to bring volume up significantly, since RMS was -34dB
    board = Pedalboard([
        Gain(gain_db=22.0),
        HighpassFilter(cutoff_frequency_hz=80.0),
        Compressor(threshold_db=-20.0, ratio=6.0, attack_ms=3.0, release_ms=100.0),
        HighShelfFilter(cutoff_frequency_hz=4000.0, gain_db=4.0),
        Reverb(room_size=0.2, damping=0.5, wet_level=0.1, dry_level=0.9, width=0.5),
        Limiter(threshold_db=-1.0)
    ])
    
    voice_processed = board(audio, sample_rate)
    voice_mono = np.mean(voice_processed, axis=0)
    
    # Fade edges of the voice slightly
    fade_len = int(sample_rate * 0.05)
    if len(voice_mono) > fade_len * 2:
        voice_mono[:fade_len] *= np.linspace(0, 1, fade_len)
        voice_mono[-fade_len:] *= np.linspace(1, 0, fade_len)
    
    print("Generating chimes...")
    chime_open = generate_chime(sample_rate, 'open')
    chime_close = generate_chime(sample_rate, 'close')
    
    print("Mixing final audio...")
    silence_short = np.zeros(int(sample_rate * 0.3))
    silence_long = np.zeros(int(sample_rate * 0.6))
    
    final_audio = np.concatenate([
        chime_open, 
        silence_short, 
        voice_mono, 
        silence_long, 
        chime_close
    ])
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    print(f"Saving to {output_file}...")
    sf.write(output_file, final_audio, sample_rate)
    print("Done!")

if __name__ == "__main__":
    input_wav = r"c:\Users\CarlosAlbertoAcevesC\Desktop\DEV SAO\Grabacion_Jocelyn.wav"
    output_wav = r"c:\Users\CarlosAlbertoAcevesC\Desktop\DEV SAO\static\audio\announcement_jocelyn.wav"
    process_audio(input_wav, output_wav)

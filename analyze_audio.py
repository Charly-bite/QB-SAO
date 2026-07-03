import os
import numpy as np
import soundfile as sf

def analyze_audio(file_path):
    print(f"Analyzing {file_path}...")
    audio, sr = sf.read(file_path)
    
    if len(audio.shape) > 1:
        # Convert to mono for analysis
        mono_audio = np.mean(audio, axis=1)
    else:
        mono_audio = audio
        
    duration = len(mono_audio) / sr
    print(f"Duration: {duration:.2f} seconds")
    print(f"Sample Rate: {sr} Hz")
    
    # Calculate RMS and Peak
    rms = np.sqrt(np.mean(mono_audio**2))
    rms_db = 20 * np.log10(rms + 1e-10)
    
    peak = np.max(np.abs(mono_audio))
    peak_db = 20 * np.log10(peak + 1e-10)
    
    print(f"RMS Level: {rms_db:.2f} dBFS")
    print(f"Peak Level: {peak_db:.2f} dBFS")
    
    # Crest Factor (Peak to RMS ratio)
    crest_factor = peak_db - rms_db
    print(f"Crest Factor: {crest_factor:.2f} dB")
    
    # Estimate Noise Floor (lowest 5% of energy frames)
    frame_length = int(sr * 0.05) # 50ms frames
    frames = [mono_audio[i:i+frame_length] for i in range(0, len(mono_audio), frame_length)]
    frame_energies = [np.mean(f**2) for f in frames if len(f) == frame_length]
    frame_energies.sort()
    
    # Lowest 5% of frames
    noise_floor_energy = np.mean(frame_energies[:max(1, len(frame_energies)//20)])
    noise_floor_db = 20 * np.log10(np.sqrt(noise_floor_energy) + 1e-10)
    print(f"Estimated Noise Floor: {noise_floor_db:.2f} dBFS")
    
    # SNR
    snr = rms_db - noise_floor_db
    print(f"Estimated SNR: {snr:.2f} dB")
    
    # Simple silence detection at start/end
    threshold = np.sqrt(noise_floor_energy) * 2
    above_threshold = np.where(np.abs(mono_audio) > threshold)[0]
    
    if len(above_threshold) > 0:
        start_silence = above_threshold[0] / sr
        end_silence = (len(mono_audio) - above_threshold[-1]) / sr
    else:
        start_silence = 0
        end_silence = 0
        
    print(f"Start Silence: {start_silence:.3f}s")
    print(f"End Silence: {end_silence:.3f}s")
    
if __name__ == '__main__':
    analyze_audio(r"c:\Users\CarlosAlbertoAcevesC\Desktop\DEV SAO\Grabacion_Jocelyn.wav")

import os
import numpy as np
import soundfile as sf
from pedalboard import Pedalboard, Reverb, Compressor, Limiter

def process_audio(input_file, output_file):
    # Load audio
    print(f"Loading {input_file}...")
    audio, sample_rate = sf.read(input_file)
    
    # Ensure it's 2D array if it's stereo, or convert mono to stereo if necessary
    # pedalboard works best with shape (channels, samples)
    if len(audio.shape) == 1:
        audio = audio.reshape((1, -1))
    else:
        audio = audio.T
    
    # Create a professional audio processing chain
    board = Pedalboard([
        # Compression to even out the voice dynamics
        Compressor(threshold_db=-20.0, ratio=3.0, attack_ms=5.0, release_ms=50.0),
        # Subtle reverb to add depth without washing out the voice
        Reverb(room_size=0.15, damping=0.5, wet_level=0.1, dry_level=0.9, width=0.5),
        # Limiter to catch peaks and normalize
        Limiter(threshold_db=-1.0)
    ])
    
    print("Applying effects...")
    # Apply effects
    effected = board(audio, sample_rate)
    
    # Convert back to shape (samples, channels)
    effected = effected.T
    
    # Save the result
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    print(f"Saving to {output_file}...")
    sf.write(output_file, effected, sample_rate)
    print("Done!")

if __name__ == "__main__":
    input_wav = r"c:\Users\CarlosAlbertoAcevesC\Desktop\DEV SAO\Grabacion_Jocelyn.wav"
    output_wav = r"c:\Users\CarlosAlbertoAcevesC\Desktop\DEV SAO\static\audio\announcement_jocelyn.wav"
    process_audio(input_wav, output_wav)

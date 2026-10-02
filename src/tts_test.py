import base64
import os
from pathlib import Path

from dotenv import load_dotenv
from speechify import Speechify

load_dotenv()

api_key = os.getenv("SPEECHIFY_API_KEY")

if not api_key:
    raise RuntimeError("SPEECHIFY_API_KEY not found.")

client = Speechify(token=api_key)

output_dir = Path("audio/test")
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / "speechify_test.mp3"

print("Generating test audio...")

response = client.audio.speech(
    input="Hello! This is our first automated test of the educational audio pipeline.",
    voice_id="geffen_32",
    model="simba-3.2",
    audio_format="mp3",
)

# Speechify returns the audio as Base64
audio_bytes = base64.b64decode(response.audio_data)

with open(output_file, "wb") as f:
    f.write(audio_bytes)

print(f"Success! Audio saved to: {output_file}")
print(f"Billable characters: {response.billable_characters_count}")
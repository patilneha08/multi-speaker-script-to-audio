import os
import json

from dotenv import load_dotenv
from speechify import Speechify


# Load API key
load_dotenv()

api_key = os.getenv("SPEECHIFY_API_KEY")

if not api_key:
    raise RuntimeError("SPEECHIFY_API_KEY not found.")

client = Speechify(token=api_key)

print("Fetching English Speechify voices...\n")

# Fetch voices
voices = list(
    client.voices.list(
        locale="en",
        model="simba-3.2",
    )
)

print(f"Found {len(voices)} voices.")

# Convert Speechify objects to normal Python dictionaries
voice_data = []

for voice in voices:
    if hasattr(voice, "model_dump"):
        voice_data.append(voice.model_dump())
    elif hasattr(voice, "dict"):
        voice_data.append(voice.dict())
    else:
        voice_data.append(vars(voice))


# Create config folder if necessary
os.makedirs("config", exist_ok=True)

output_file = "config/speechify_voices.json"

# Save catalog
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(
        voice_data,
        f,
        indent=2,
        ensure_ascii=False,
        default=str,
    )

print(f"Saved voice catalog to: {output_file}")
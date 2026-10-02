import os
import base64
from pathlib import Path

from dotenv import load_dotenv
from speechify import Speechify


load_dotenv()

api_key = os.getenv("SPEECHIFY_API_KEY")

if not api_key:
    raise RuntimeError("SPEECHIFY_API_KEY not found.")

client = Speechify(token=api_key)

# Initial audition set.
# We'll expand/change this after listening.
VOICES = {
    "jacob": "jacob",
    "archie": "archie",
    "edmund": "edmund_32",
    "jack": "jack",
    "marco": "marco",
    "byron": "byronagent",
}

TEST_TEXT = (
    "Wait, seriously? That's amazing! "
    "But how does your body actually know what to do?"
)

output_dir = Path("audio/auditions")
output_dir.mkdir(parents=True, exist_ok=True)

print(f"Generating {len(VOICES)} voice auditions...\n")

total_characters = 0

for name, voice_id in VOICES.items():

    output_file = output_dir / f"{name}.mp3"

    print(f"Generating {name} ({voice_id})...")

    try:
        response = client.audio.speech(
            input=TEST_TEXT,
            voice_id=voice_id,
            model="simba-3.2",
            audio_format="mp3",
        )

        audio_bytes = base64.b64decode(response.audio_data)

        with open(output_file, "wb") as f:
            f.write(audio_bytes)

        billable = response.billable_characters_count
        total_characters += billable

        print(f"  Saved: {output_file}")
        print(f"  Characters: {billable}")

    except Exception as e:
        print(f"  FAILED: {e}")

print("\nDone!")
print(f"Total billable characters: {total_characters}")
print(f"Auditions saved in: {output_dir}")
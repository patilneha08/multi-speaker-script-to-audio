import os
import sys
import json
import base64
import hashlib
from pathlib import Path

from dotenv import load_dotenv
from speechify import Speechify


VOICE_CONFIG = Path("config/voices.json")

MAX_LINES = None


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def make_signature(text, voice_id, model):
    """
    Unique fingerprint for the inputs that produced an audio clip.
    """
    value = f"{voice_id}|{model}|{text}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main(scene_file):
    load_dotenv()

    api_key = os.getenv("SPEECHIFY_API_KEY")

    if not api_key:
        raise RuntimeError("SPEECHIFY_API_KEY not found.")

    client = Speechify(token=api_key)

    scene = load_json(scene_file)
    config = load_json(VOICE_CONFIG)

    scene_id = scene["scene_id"]
    model = config.get("model", "simba-3.2")

    assignments = config.get(
        "scene_assignments", {}
    ).get(scene_id, {})

    if not assignments:
        raise RuntimeError(
            f"No voice assignments found for {scene_id}. "
            f"Run voice_assigner.py first."
        )

    output_dir = Path("audio") / scene_id
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_file = output_dir / "manifest.json"

    if manifest_file.exists():
        manifest = load_json(manifest_file)
    else:
        manifest = {}

    generated = 0
    skipped = 0
    processed = 0
    total_characters = 0

    print(f"\nTTS: {scene_id}")
    print("-" * 60)

    for event in scene.get("events", []):

        # Stage directions are intentionally non-spoken.
        if event.get("type") == "stage_direction":
            continue

        speaker = event.get("speaker")
        spoken_text = event.get("spoken_text", "").strip()

        if not speaker or not spoken_text:
            continue

        # MAX_LINES refers to spoken events processed,
        # whether generated or skipped.
        if MAX_LINES is not None and processed >= MAX_LINES:
            break

        processed += 1

        if speaker not in assignments:
            raise RuntimeError(
                f"No voice assigned to speaker '{speaker}'."
            )

        voice = assignments[speaker]
        voice_id = voice["voice_id"]

        event_id = event.get("event_id")

        if not event_id:
            raise RuntimeError(
                f"Event has no event_id: {event}"
            )   

        output_file = output_dir / f"{event_id}.mp3"

        signature = make_signature(
            spoken_text,
            voice_id,
            model
        )

        old_record = manifest.get(event_id)

        # Reuse the clip only if:
        # 1. MP3 exists
        # 2. Manifest knows about it
        # 3. Text/voice/model fingerprint is identical
        if (
            output_file.exists()
            and old_record
            and old_record.get("signature") == signature
        ):
            print(
                f"{event_id} | {speaker} -> "
                f"{voice['name']} | SKIP"
            )

            skipped += 1
            continue

        # Explain why we're generating.
        if output_file.exists():
            action = "REGENERATE"
        else:
            action = "GENERATE"

        print(
            f"{event_id} | {speaker} -> "
            f"{voice['name']} | {action}"
        )

        print(f"    {spoken_text}")

        try:
            response = client.audio.speech(
                input=spoken_text,
                voice_id=voice_id,
                model=model,
                audio_format="mp3",
            )

            audio_bytes = base64.b64decode(
                response.audio_data
            )

            with open(output_file, "wb") as f:
                f.write(audio_bytes)

            billable = getattr(
                response,
                "billable_characters_count",
                len(spoken_text)
            )

            total_characters += billable
            generated += 1

            # Update manifest only after successful generation.
            manifest[event_id] = {
                "speaker": speaker,
                "voice_name": voice["name"],
                "voice_id": voice_id,
                "model": model,
                "spoken_text": spoken_text,
                "signature": signature,
                "file": str(output_file)
            }

            # Save after every successful clip.
            # If generation later crashes, previous work is retained.
            save_json(manifest_file, manifest)

            print(f"    Saved -> {output_file}\n")

        except Exception as e:
            print(f"    FAILED -> {e}\n")

    print("-" * 60)
    print(f"Generated/regenerated: {generated}")
    print(f"Skipped unchanged:     {skipped}")
    print(f"Billable characters:   {total_characters}")
    print(f"Manifest:              {manifest_file}")


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print(
            "Usage: python3 src/tts.py "
            "json/scene_001.json"
        )
        sys.exit(1)

    main(sys.argv[1])
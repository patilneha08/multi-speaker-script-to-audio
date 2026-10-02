import sys
import json
from pathlib import Path

from pydub import AudioSegment


# ---------------------------------------------------------
# Timing configuration
# ---------------------------------------------------------

# Standard gap between spoken events
DEFAULT_GAP_MS = 400

# Slightly longer after narration before another speaker
NARRATION_GAP_MS = 500

# Tight gap when dialogue is being interrupted
INTERRUPTION_GAP_MS = 100


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_gap_ms(current_event, next_event):
    """
    Determine how much silence should appear after current_event
    before next_event begins.
    """

    interruption = current_event.get("interruption", {})

    # If the current line ends with --,
    # the next line should enter quickly.
    if interruption.get("ends_with_dash"):
        return INTERRUPTION_GAP_MS

    # If the next line begins with --,
    # it is probably continuing/interjecting quickly.
    next_interruption = next_event.get("interruption", {})

    if next_interruption.get("starts_with_dash"):
        return INTERRUPTION_GAP_MS

    # Narration gets a slightly more comfortable transition.
    if current_event.get("type") == "narration":
        return NARRATION_GAP_MS

    return DEFAULT_GAP_MS


def main(scene_file):
    scene = load_json(scene_file)

    scene_id = scene["scene_id"]

    audio_dir = Path("audio") / scene_id
    output_file = audio_dir / f"final_{scene_id}.mp3"

    if not audio_dir.exists():
        raise RuntimeError(
            f"Audio directory does not exist: {audio_dir}"
        )

    # -----------------------------------------------------
    # Collect spoken events only
    # -----------------------------------------------------

    spoken_events = []

    for event in scene.get("events", []):

        if event.get("type") == "stage_direction":
            continue

        spoken_text = event.get("spoken_text", "").strip()

        if not spoken_text:
            continue

        event_id = event.get("event_id")

        if not event_id:
            raise RuntimeError(
                f"Spoken event has no event_id: {event}"
            )

        spoken_events.append(event)

    if not spoken_events:
        raise RuntimeError(
            f"No spoken events found in {scene_id}."
        )

    # -----------------------------------------------------
    # Check that ALL required clips exist before assembling.
    # -----------------------------------------------------

    missing_files = []

    for event in spoken_events:

        event_id = event["event_id"]
        clip_file = audio_dir / f"{event_id}.mp3"

        if not clip_file.exists():
            missing_files.append(str(clip_file))

    if missing_files:
        print("\nCannot assemble scene.")
        print("Missing audio clips:\n")

        for file in missing_files:
            print(f"  - {file}")

        print(
            "\nGenerate the missing clips with tts.py first."
        )

        sys.exit(1)

    # -----------------------------------------------------
    # Assemble
    # -----------------------------------------------------

    print(f"\nAssembling {scene_id}")
    print("-" * 60)

    final_audio = AudioSegment.empty()

    for index, event in enumerate(spoken_events):

        event_id = event["event_id"]
        speaker = event.get("speaker", "Unknown")

        clip_file = audio_dir / f"{event_id}.mp3"

        print(
            f"{event_id} | {speaker} | "
            f"{clip_file.name}"
        )

        clip = AudioSegment.from_file(clip_file)

        final_audio += clip

        # Don't add silence after the final event.
        if index < len(spoken_events) - 1:

            next_event = spoken_events[index + 1]

            gap_ms = get_gap_ms(
                event,
                next_event
            )

            final_audio += AudioSegment.silent(
                duration=gap_ms
            )

    # -----------------------------------------------------
    # Export
    # -----------------------------------------------------

    final_audio.export(
        output_file,
        format="mp3",
        bitrate="192k"
    )

    duration_seconds = len(final_audio) / 1000

    print("-" * 60)
    print(f"Events assembled: {len(spoken_events)}")
    print(f"Duration: {duration_seconds:.1f} seconds")
    print(f"Final audio: {output_file}")


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print(
            "Usage: python3 src/assembler.py "
            "json/scene_001.json"
        )
        sys.exit(1)

    main(sys.argv[1])
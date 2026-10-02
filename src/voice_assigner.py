import json
import sys
from pathlib import Path


VOICE_CONFIG = Path("config/voices.json")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def choose_gender(character):
    """Ask once when a character has never been classified before."""

    while True:
        answer = input(
            f"Voice type for '{character}' "
            "[m=male / f=female / s=skip]: "
        ).strip().lower()

        if answer == "m":
            return "male"

        if answer == "f":
            return "female"

        if answer == "s":
            return "skip"

        print("Please enter m, f, or s.")


def used_voice_ids(scene_assignments):
    return {
        assignment["voice_id"]
        for assignment in scene_assignments.values()
        if isinstance(assignment, dict)
        and assignment.get("voice_id")
    }


def select_voice(pool, already_used):
    """
    Select the first available voice that has not already
    been used in this scene.
    """

    for voice in pool:
        if voice["voice_id"] not in already_used:
            return voice

    # If a scene has more characters than available voices,
    # reuse from the beginning of the pool.
    return pool[0]


def assign_voices(scene_file):
    scene_path = Path(scene_file)

    scene = load_json(scene_path)
    config = load_json(VOICE_CONFIG)

    scene_id = scene["scene_id"]
    characters = scene.get("characters", [])

    characters = [
    character["name"] if isinstance(character, dict) else character
    for character in characters
    ]
    config.setdefault("character_types", {})
    config.setdefault("scene_assignments", {})

    assignments = config["scene_assignments"].setdefault(
        scene_id, {}
    )

    narrator = config["narrator"]

    print(f"\nScene: {scene_id}")
    print("-" * 50)

    # Narrator is globally fixed.
    if "Narrator" in characters:
        assignments["Narrator"] = {
            "name": narrator["name"],
            "voice_id": narrator["voice_id"],
            "type": "narrator"
        }

        print(
            f"Narrator -> "
            f"{narrator['name']} ({narrator['voice_id']})"
        )

    for character in characters:

        if character == "Narrator":
            continue

        # Don't overwrite an existing assignment.
        if character in assignments:
            voice = assignments[character]

            print(
                f"{character} -> "
                f"{voice['name']} ({voice['voice_id']}) "
                "[existing]"
            )
            continue

        # Have we classified this character before?
        character_type = config["character_types"].get(character)

        if character_type is None:
            character_type = choose_gender(character)

            config["character_types"][character] = character_type

        if character_type == "skip":
            print(f"{character} -> skipped")
            continue

        pool = config["voice_pool"].get(character_type)

        if not pool:
            raise RuntimeError(
                f"No voices configured for '{character_type}'."
            )

        used = used_voice_ids(assignments)

        voice = select_voice(pool, used)

        assignments[character] = {
            "name": voice["name"],
            "voice_id": voice["voice_id"],
            "type": character_type
        }

        print(
            f"{character} -> "
            f"{voice['name']} ({voice['voice_id']})"
        )

    save_json(VOICE_CONFIG, config)

    print(f"\nAssignments saved to {VOICE_CONFIG}")


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print(
            "Usage: python3 src/voice_assigner.py "
            "json/scene_001.json"
        )
        sys.exit(1)

    assign_voices(sys.argv[1])
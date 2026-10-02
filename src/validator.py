from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


ALLOWED_EVENT_TYPES = {"dialogue", "narration", "stage_direction", "unparsed"}
SPOKEN_EVENT_TYPES = {"dialogue", "narration"}
DASHES = ("--", "–", "—")


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _case_variant_warnings(names: list[str]) -> list[str]:
    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(name.casefold(), []).append(name)

    warnings: list[str] = []
    for variants in groups.values():
        unique = list(dict.fromkeys(variants))
        if len(unique) > 1:
            warnings.append(
                "Possible character-name capitalization variants: "
                + ", ".join(f"'{name}'" for name in unique)
            )
    return warnings


def _similar_name_warnings(names: list[str]) -> list[str]:
    warnings: list[str] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if a.casefold() == b.casefold():
                continue
            if abs(len(a) - len(b)) > 2:
                continue
            score = SequenceMatcher(None, a.casefold(), b.casefold()).ratio()
            if score >= 0.85:
                warnings.append(
                    f"Possible duplicate/typo character names: '{a}' and '{b}'."
                )
    return warnings


def _expected_event_id(scene_id: str, number: int) -> str:
    return f"{scene_id}-{number:03d}"


def validate_scene(data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate parsed scene JSON before voice assignment / TTS.

    PASS   = no errors or warnings
    REVIEW = no blocking errors, but human review is recommended
    FAIL   = one or more blocking errors; do not send to TTS
    """
    errors: list[str] = []
    warnings: list[str] = []

    scene_id = data.get("scene_id")
    title = data.get("title")
    location = data.get("location")
    source_file = data.get("source_file")
    characters = data.get("characters")
    events = data.get("events")

    # ------------------------------------------------------------------
    # SCENE METADATA
    # ------------------------------------------------------------------
    if not _nonempty(scene_id):
        errors.append("Missing or empty scene_id.")
        scene_id = "scene"

    if not _nonempty(title):
        errors.append("Missing or empty title.")

    if not _nonempty(location):
        warnings.append("Missing or empty location.")

    if not _nonempty(source_file):
        warnings.append("Missing or empty source_file.")

    # ------------------------------------------------------------------
    # CHARACTERS
    # ------------------------------------------------------------------
    if not isinstance(characters, list):
        errors.append("characters must be a list.")
        characters = []

    character_names: list[str] = []
    for index, character in enumerate(characters):
        if not isinstance(character, dict):
            errors.append(f"characters[{index}] must be an object.")
            continue

        name = character.get("name")
        if not _nonempty(name):
            errors.append(f"characters[{index}] has a missing/empty name.")
            continue

        character_names.append(name)

    duplicate_character_names = [
        name for name, count in Counter(character_names).items() if count > 1
    ]
    for name in duplicate_character_names:
        errors.append(f"Duplicate character entry: '{name}'.")

    warnings.extend(_case_variant_warnings(character_names))
    warnings.extend(_similar_name_warnings(character_names))

    character_set = set(character_names)

    # ------------------------------------------------------------------
    # EVENTS
    # ------------------------------------------------------------------
    if not isinstance(events, list):
        errors.append("events must be a list.")
        events = []

    if not events:
        errors.append("No events found.")

    seen_ids: set[str] = set()
    numeric_event_number = 0
    spoken_count = 0
    stage_count = 0
    unparsed_count = 0

    for index, event in enumerate(events):
        label = f"events[{index}]"

        if not isinstance(event, dict):
            errors.append(f"{label} must be an object.")
            continue

        event_id = event.get("event_id")
        event_type = event.get("type")
        source = event.get("source")
        audio = event.get("audio")

        if not _nonempty(event_id):
            errors.append(f"{label} has a missing/empty event_id.")
            event_id = label
        elif event_id in seen_ids:
            errors.append(f"Duplicate event_id: '{event_id}'.")
        else:
            seen_ids.add(event_id)

        if event_type not in ALLOWED_EVENT_TYPES:
            errors.append(
                f"{event_id}: unknown event type {event_type!r}."
            )
            continue

        # Source traceability.
        if not isinstance(source, dict):
            errors.append(f"{event_id}: missing source object.")
        else:
            page = source.get("page")
            raw_text = source.get("raw_text")

            if not isinstance(page, int) or page < 1:
                errors.append(f"{event_id}: invalid/missing source.page.")

            if not _nonempty(raw_text):
                errors.append(f"{event_id}: missing/empty source.raw_text.")

        # Sequential IDs for normal (non-UNPARSED) events.
        if event_type != "unparsed":
            numeric_event_number += 1
            if _nonempty(scene_id) and _nonempty(event_id):
                expected = _expected_event_id(scene_id, numeric_event_number)
                if event_id != expected:
                    errors.append(
                        f"{event_id}: event IDs are not sequential; "
                        f"expected '{expected}'."
                    )

        # --------------------------------------------------------------
        # SPOKEN EVENTS
        # --------------------------------------------------------------
        if event_type in SPOKEN_EVENT_TYPES:
            spoken_count += 1

            speaker = event.get("speaker")
            text = event.get("text")
            spoken_text = event.get("spoken_text")
            delivery = event.get("delivery")
            interruption = event.get("interruption")

            if not _nonempty(speaker):
                errors.append(f"{event_id}: spoken event has no speaker.")
            elif speaker not in character_set:
                errors.append(
                    f"{event_id}: speaker '{speaker}' is not in characters."
                )

            if event_type == "narration" and _nonempty(speaker):
                if speaker.casefold() != "narrator":
                    warnings.append(
                        f"{event_id}: narration speaker is '{speaker}', "
                        "not 'Narrator'."
                    )

            if not _nonempty(text):
                errors.append(f"{event_id}: spoken event has empty text.")

            if not _nonempty(spoken_text):
                errors.append(f"{event_id}: spoken event has empty spoken_text.")

            if not isinstance(delivery, dict):
                errors.append(f"{event_id}: missing delivery metadata.")
            else:
                if "raw_cue" not in delivery:
                    errors.append(f"{event_id}: delivery.raw_cue is missing.")
                if not isinstance(delivery.get("off_screen"), bool):
                    errors.append(
                        f"{event_id}: delivery.off_screen must be boolean."
                    )
                inline = delivery.get("inline_cues")
                if not isinstance(inline, list):
                    errors.append(
                        f"{event_id}: delivery.inline_cues must be a list."
                    )

            if not isinstance(interruption, dict):
                errors.append(f"{event_id}: missing interruption metadata.")
            else:
                starts = interruption.get("starts_with_dash")
                ends = interruption.get("ends_with_dash")

                if not isinstance(starts, bool):
                    errors.append(
                        f"{event_id}: interruption.starts_with_dash "
                        "must be boolean."
                    )
                if not isinstance(ends, bool):
                    errors.append(
                        f"{event_id}: interruption.ends_with_dash "
                        "must be boolean."
                    )

                if _nonempty(text):
                    actual_start = text.lstrip().startswith(DASHES)
                    actual_end = text.rstrip().endswith(DASHES)

                    if isinstance(starts, bool) and starts != actual_start:
                        errors.append(
                            f"{event_id}: starts_with_dash does not match text."
                        )
                    if isinstance(ends, bool) and ends != actual_end:
                        errors.append(
                            f"{event_id}: ends_with_dash does not match text."
                        )

            if not isinstance(audio, dict):
                errors.append(f"{event_id}: missing audio metadata.")
            else:
                if audio.get("status") != "pending":
                    errors.append(
                        f"{event_id}: spoken event audio.status must be "
                        "'pending' before TTS."
                    )
                if "file" not in audio:
                    errors.append(f"{event_id}: audio.file is missing.")

        # --------------------------------------------------------------
        # STAGE DIRECTIONS
        # --------------------------------------------------------------
        elif event_type == "stage_direction":
            stage_count += 1

            if event.get("speaker") is not None:
                errors.append(
                    f"{event_id}: stage_direction speaker must be null."
                )

            if not _nonempty(event.get("text")):
                errors.append(f"{event_id}: stage_direction has empty text.")

            if not isinstance(audio, dict):
                errors.append(f"{event_id}: stage_direction missing audio.")
            else:
                if audio.get("status") != "skip":
                    errors.append(
                        f"{event_id}: stage_direction audio.status must be 'skip'."
                    )
                if audio.get("file") is not None:
                    warnings.append(
                        f"{event_id}: stage_direction has an audio file even "
                        "though it is marked skip."
                    )

        # --------------------------------------------------------------
        # UNPARSED
        # --------------------------------------------------------------
        elif event_type == "unparsed":
            unparsed_count += 1
            errors.append(
                f"{event_id}: unparsed content requires manual resolution."
            )

    # ------------------------------------------------------------------
    # CROSS-EVENT / TTS-SAFETY CHECKS
    # ------------------------------------------------------------------
    used_speakers = {
        event.get("speaker")
        for event in events
        if isinstance(event, dict)
        and event.get("type") in SPOKEN_EVENT_TYPES
        and _nonempty(event.get("speaker"))
    }

    for name in character_names:
        if name not in used_speakers:
            warnings.append(
                f"Character '{name}' is listed but has no spoken events."
            )

    # De-duplicate while preserving order.
    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))

    if errors:
        status = "fail"
        safe_for_tts = False
    elif warnings:
        status = "review"
        safe_for_tts = False
    else:
        status = "pass"
        safe_for_tts = True

    return {
        "status": status,
        "safe_for_tts": safe_for_tts,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "events": len(events),
            "spoken_events": spoken_count,
            "stage_directions": stage_count,
            "unparsed_events": unparsed_count,
            "characters": len(character_names),
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
    }


def validate_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    input_path = Path(input_path)

    with input_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    result = validate_scene(data)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return result


def print_result(filename: str, result: dict[str, Any]) -> None:
    summary = result["summary"]

    print(f"\n{filename}")
    print("-" * len(filename))
    print(f"STATUS: {result['status'].upper()}")
    print(f"SAFE FOR TTS: {'YES' if result['safe_for_tts'] else 'NO'}")
    print(
        f"Events: {summary['events']} | "
        f"Spoken: {summary['spoken_events']} | "
        f"Stage directions: {summary['stage_directions']} | "
        f"Characters: {summary['characters']}"
    )

    if result["errors"]:
        print("\nERRORS:")
        for error in result["errors"]:
            print(f"  - {error}")

    if result["warnings"]:
        print("\nWARNINGS:")
        for warning in result["warnings"]:
            print(f"  - {warning}")


def validate_folder(
    input_dir: str | Path,
    report_dir: str | Path | None = None,
) -> int:
    input_dir = Path(input_dir)
    json_files = sorted(input_dir.glob("*.json"))

    if not json_files:
        print(f"No JSON files found in: {input_dir}")
        return 1

    report_dir_path = Path(report_dir) if report_dir else None
    if report_dir_path:
        report_dir_path.mkdir(parents=True, exist_ok=True)

    overall_exit = 0

    for json_file in json_files:
        report_file = (
            report_dir_path / f"{json_file.stem}_validation.json"
            if report_dir_path
            else None
        )

        try:
            result = validate_file(json_file, report_file)
            print_result(json_file.name, result)

            if result["status"] == "fail":
                overall_exit = 2
            elif result["status"] == "review" and overall_exit == 0:
                overall_exit = 1

        except (json.JSONDecodeError, OSError) as exc:
            print(f"\n{json_file.name}\n{'-' * len(json_file.name)}")
            print(f"STATUS: FAIL")
            print(f"  - Could not validate file: {exc}")
            overall_exit = 2

    return overall_exit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate parsed scene JSON before voice assignment/TTS."
    )
    parser.add_argument(
        "input",
        help="Scene JSON file or directory containing scene JSON files.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        help=(
            "Optional validation report JSON file (single input) or "
            "report directory (directory input)."
        ),
    )
    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Input does not exist: {input_path}")
        return 2

    if input_path.is_dir():
        return validate_folder(input_path, args.output)

    output_path = Path(args.output) if args.output else None

    try:
        result = validate_file(input_path, output_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Could not validate {input_path}: {exc}")
        return 2

    print_result(input_path.name, result)

    if result["status"] == "fail":
        return 2
    if result["status"] == "review":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

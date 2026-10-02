from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pymupdf


LOCATION_RE = re.compile(r"^(?:INT\.|EXT\.|INT/EXT\.)\s+.+", re.IGNORECASE)
PAGE_RE = re.compile(r"^\d+\s*$")
SPEAKER_RE = re.compile(
    r"^(?P<speaker>[A-Za-z][A-Za-z0-9 _'’.-]*?)"
    r"(?:\s*\((?P<cue>[^)]*)\))?"
    r"\s*:\s*(?P<text>.*)$"
)
INLINE_CUE_RE = re.compile(r"\(([^()]+)\)")
OFF_SCREEN_TERMS = ("off-screen", "off screen", "from off-screen", "from off screen")


def normalize_spaces(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def normalize_name(name: str) -> str:
    # Preserve source spelling/capitalization; only normalize whitespace.
    return normalize_spaces(name)


def is_off_screen(cue: str | None) -> bool:
    if not cue:
        return False
    cue_lower = cue.lower()
    return any(term in cue_lower for term in OFF_SCREEN_TERMS)


def looks_like_character_name(name: str) -> bool:
    """Conservative filter for prefixes that could plausibly be speaker names."""
    name = normalize_spaces(name)
    if not name:
        return False

    words = name.split()
    if len(words) > 4:
        return False

    # Reject multiword all-lowercase prose such as "white blood cells".
    if len(words) > 1 and name == name.lower():
        return False

    return True


def discover_speakers(pages: list[list[str]]) -> set[str]:
    """
    Discover plausible speakers before the main parse so colons inside wrapped
    prose do not automatically create new speakers.
    """
    candidates: dict[str, int] = {}

    for lines in pages:
        for line in lines:
            match = SPEAKER_RE.match(line)
            if not match:
                continue

            speaker = normalize_name(match.group("speaker"))
            if not looks_like_character_name(speaker):
                continue

            candidates[speaker] = candidates.get(speaker, 0) + 1

    speakers: set[str] = set()

    for speaker, count in candidates.items():
        if speaker.casefold() == "narrator":
            speakers.add(speaker)
        elif speaker and speaker[0].isupper():
            speakers.add(speaker)
        elif count >= 2:
            speakers.add(speaker)

    return speakers


def extract_inline_cues(text: str) -> tuple[str, list[str]]:
    """
    Preserve original text but remove inline parenthetical delivery directions
    from spoken_text, e.g. "(sarcastic)" or "(sneezes)".
    """
    cues = INLINE_CUE_RE.findall(text)
    if not cues:
        return text, []

    spoken = INLINE_CUE_RE.sub("", text)
    spoken = normalize_spaces(spoken)
    spoken = re.sub(r"\s+([,.!?;:])", r"\1", spoken)

    return spoken, [normalize_spaces(cue) for cue in cues]


def extract_pages(pdf_path: Path) -> list[list[str]]:
    doc = pymupdf.open(pdf_path)
    pages: list[list[str]] = []

    try:
        for page in doc:
            lines: list[str] = []
            raw_text = page.get_text("text")

            for raw in raw_text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                if PAGE_RE.fullmatch(line):
                    continue
                lines.append(line)

            pages.append(lines)
    finally:
        doc.close()

    return pages


def looks_like_stage_direction(
    line: str,
    known_speakers: set[str] | None = None,
) -> bool:
    """
    Conservative detection for obvious screenplay/action directions.
    """
    line = normalize_spaces(line)
    if not line:
        return False

    if line.casefold() == "a beat.":
        return True

    if re.match(r"^As\s+(he|she|they)\b", line, re.IGNORECASE):
        return True

    action_verbs = (
        "arrives",
        "enters",
        "walks",
        "runs",
        "appears",
        "leaves",
        "exits",
        "moves",
        "picks",
        "takes",
        "looks",
        "turns",
        "starts",
        "stops",
        "sits",
        "stands",
        "shrugs",
        "faints",
        "points",
        "holds",
        "grabs",
        "puts",
        "raises",
        "lowers",
        "approaches",
        "backs",
        "steps",
        "knicks",
    )
    verbs = "|".join(action_verbs)

    # Named-subject action, e.g. "Crystal picks..." / "GRANDPA arrives..."
    if re.match(
        rf"^[A-Z][A-Za-z'’.-]*(?:\s+[A-Z][A-Za-z'’.-]*)?\s+(?:{verbs})\b",
        line,
        re.IGNORECASE,
    ):
        return True

    # Pronoun action, e.g. "She knicks..."
    if re.match(rf"^(He|She|They)\s+(?:{verbs})\b", line, re.IGNORECASE):
        return True

    # Known-character action/state sentence. This catches screenplay prose such
    # as "Nick is so freaked out ..." without treating arbitrary colon-bearing
    # prose as a speaker line. Source names are matched case-insensitively, but
    # are never corrected or normalized in the output.
    if known_speakers:
        for speaker in sorted(known_speakers, key=len, reverse=True):
            if speaker.casefold() == "narrator":
                continue
            escaped = re.escape(speaker)
            if re.match(
                rf"^{escaped}\s+(?:is|are|was|were|has|have|had|begins?|continues?|seems?|looks?|turns?|moves?|walks?|runs?|sits?|stands?|shrugs?|nods?|smiles?|laughs?|cries?|faints?|picks?|takes?|puts?|holds?|grabs?|points?|steps?|backs?|approaches?|leaves?|exits?|enters?|appears?|starts?|stops?)\b",
                line,
                re.IGNORECASE,
            ):
                return True

    return False


def find_case_variants(characters: list[dict[str, Any]]) -> list[str]:
    """Warn about source variants such as Sight / SIght without correcting them."""
    issues: list[str] = []
    groups: dict[str, list[str]] = {}

    for character in characters:
        name = character["name"]
        groups.setdefault(name.casefold(), []).append(name)

    for names in groups.values():
        unique_names = list(dict.fromkeys(names))
        if len(unique_names) > 1:
            issues.append(
                "Possible character-name capitalization variants: "
                + ", ".join(f"'{name}'" for name in unique_names)
            )

    return issues


def find_similar_speakers(characters: list[dict[str, Any]]) -> list[str]:
    """Warn about likely source typos such as Grandpa / Granda."""
    issues: list[str] = []
    names = [character["name"] for character in characters]

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a = names[i]
            b = names[j]

            if a.casefold() == b.casefold():
                continue
            if abs(len(a) - len(b)) > 2:
                continue

            similarity = SequenceMatcher(
                None, a.casefold(), b.casefold()
            ).ratio()

            if similarity >= 0.85:
                issues.append(
                    f"Possible duplicate/typo character names: '{a}' and '{b}'."
                )

    return issues


def validate_scene(
    events: list[dict[str, Any]],
    characters: list[dict[str, Any]],
    title: str | None,
    location: str | None,
) -> dict[str, Any]:
    """
    Lightweight parser-level validation. A dedicated validator.py can later
    perform deeper QA.
    """
    issues: list[str] = []
    speakers = {character["name"] for character in characters}
    ids = [event.get("event_id") for event in events]

    if not title:
        issues.append("Missing scene title.")
    if not location:
        issues.append("Missing scene location.")
    if len(ids) != len(set(ids)):
        issues.append("Duplicate event IDs detected.")

    unparsed_events = [
        event for event in events if event.get("type") == "unparsed"
    ]
    if unparsed_events:
        issues.append(f"{len(unparsed_events)} unparsed event(s) detected.")

    for event in events:
        if event.get("type") not in {"dialogue", "narration"}:
            continue

        event_id = event.get("event_id")
        speaker = event.get("speaker")
        text = event.get("text")

        if not speaker:
            issues.append(f"Missing speaker: {event_id}")
        if not text:
            issues.append(f"Empty dialogue: {event_id}")
        if (
            speaker
            and speaker not in speakers
            and speaker.casefold() != "narrator"
        ):
            issues.append(f"Unknown speaker: '{speaker}' in {event_id}.")

    issues.extend(find_case_variants(characters))
    issues.extend(find_similar_speakers(characters))

    return {
        "status": "pass" if not issues else "review",
        "issues": issues,
    }


def parse_pdf(
    pdf_path: str | Path,
    scene_id: str | None = None,
) -> dict[str, Any]:
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if scene_id is None:
        match = re.search(r"(\d{1,4})", pdf_path.stem)
        scene_id = (
            f"scene_{int(match.group(1)):03d}"
            if match
            else pdf_path.stem
        )

    pages = extract_pages(pdf_path)
    known_speakers = discover_speakers(pages)

    title: str | None = None
    location: str | None = None
    title_parts: list[str] = []
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    event_no = 0
    unparsed_no = 0
    header_complete = False

    def flush() -> None:
        nonlocal current, event_no

        if current is None:
            return

        original_text = normalize_spaces(current["text"])
        spoken_text, inline_cues = extract_inline_cues(original_text)

        current["text"] = original_text
        current["spoken_text"] = spoken_text.strip(" -–—")
        current["delivery"]["inline_cues"] = inline_cues
        current["interruption"] = {
            "starts_with_dash": original_text.lstrip().startswith(("--", "–", "—")),
            "ends_with_dash": original_text.rstrip().endswith(("--", "–", "—")),
        }

        event_no += 1
        current["event_id"] = f"{scene_id}-{event_no:03d}"
        events.append(current)
        current = None

    def add_stage_direction(text: str, page_number: int) -> None:
        nonlocal event_no

        event_no += 1
        clean_text = normalize_spaces(text)

        events.append(
            {
                "event_id": f"{scene_id}-{event_no:03d}",
                "source": {
                    "page": page_number,
                    "raw_text": clean_text,
                },
                "type": "stage_direction",
                "speaker": None,
                "text": clean_text,
                "audio": {
                    "status": "skip",
                    "file": None,
                },
            }
        )

    def add_unparsed(text: str, page_number: int) -> None:
        nonlocal unparsed_no

        unparsed_no += 1
        clean_text = normalize_spaces(text)

        events.append(
            {
                "event_id": f"{scene_id}-UNPARSED-{unparsed_no:03d}",
                "source": {
                    "page": page_number,
                    "raw_text": clean_text,
                },
                "type": "unparsed",
                "speaker": None,
                "text": clean_text,
            }
        )

    def is_known_speaker_line(line: str) -> bool:
        match = SPEAKER_RE.match(line)
        if not match:
            return False

        candidate = normalize_name(match.group("speaker"))
        return candidate in known_speakers

    for page_index, lines in enumerate(pages, start=1):
        i = 0

        while i < len(lines):
            line = lines[i]

            # ----------------------------------------------------------
            # HEADER / MULTILINE TITLE
            # ----------------------------------------------------------
            if not header_complete:
                if LOCATION_RE.fullmatch(line):
                    location = normalize_spaces(line)
                    title = normalize_spaces(" ".join(title_parts))
                    header_complete = True
                    i += 1
                    continue

                title_parts.append(line)
                i += 1
                continue

            # ----------------------------------------------------------
            # LOCATION APPEARING LATER
            # ----------------------------------------------------------
            if LOCATION_RE.fullmatch(line):
                flush()
                if location is None:
                    location = normalize_spaces(line)
                i += 1
                continue

            # ----------------------------------------------------------
            # SPEAKER LINE
            # ----------------------------------------------------------
            match = SPEAKER_RE.match(line)

            if match:
                candidate = normalize_name(match.group("speaker"))

                if candidate in known_speakers:
                    flush()

                    cue = match.group("cue")
                    dialogue_text = match.group("text").strip()

                    current = {
                        "source": {
                            "page": page_index,
                            "raw_text": line,
                        },
                        "type": (
                            "narration"
                            if candidate.casefold() == "narrator"
                            else "dialogue"
                        ),
                        "speaker": candidate,
                        "text": dialogue_text,
                        "delivery": {
                            "raw_cue": normalize_spaces(cue) if cue else None,
                            "off_screen": is_off_screen(cue),
                        },
                        "audio": {
                            "status": "pending",
                            "file": None,
                        },
                    }

                    i += 1
                    continue

            # ----------------------------------------------------------
            # STAGE DIRECTION
            # ----------------------------------------------------------
            # This check MUST occur before wrapped-dialogue handling.
            # Otherwise a line such as:
            #
            #   She knicks Nick's arm with the sharp edge of the toy plane.
            #
            # would incorrectly be appended to the preceding character's speech.
            if looks_like_stage_direction(line, known_speakers):
                flush()

                stage_text = line
                j = i + 1

                while j < len(lines):
                    next_line = lines[j]

                    if is_known_speaker_line(next_line):
                        break
                    if LOCATION_RE.fullmatch(next_line):
                        break
                    if looks_like_stage_direction(next_line, known_speakers):
                        break

                    stage_text += " " + next_line
                    j += 1

                add_stage_direction(stage_text, page_index)
                i = j
                continue

            # ----------------------------------------------------------
            # WRAPPED DIALOGUE / NARRATION
            # ----------------------------------------------------------
            # At this point the line is neither a known speaker line nor
            # a recognized stage direction, so it is safe to treat it as
            # a continuation of the current spoken event.
            if current is not None:
                current["text"] += " " + line
                current["source"]["raw_text"] += " " + line
                i += 1
                continue

            # ----------------------------------------------------------
            # STANDALONE PROSE
            # ----------------------------------------------------------
            # Outside dialogue, preserve standalone screenplay prose as a
            # non-spoken stage direction rather than feeding it to TTS.
            stage_text = line
            j = i + 1

            while j < len(lines):
                next_line = lines[j]

                if is_known_speaker_line(next_line):
                    break
                if LOCATION_RE.fullmatch(next_line):
                    break
                if looks_like_stage_direction(next_line, known_speakers):
                    break

                stage_text += " " + next_line
                j += 1

            add_stage_direction(stage_text, page_index)
            i = j

    flush()

    if title is None and title_parts:
        title = normalize_spaces(" ".join(title_parts))

    # Build character list from actual parsed spoken events.
    characters: list[dict[str, str]] = []
    seen: set[str] = set()
    narrator_name: str | None = None

    for event in events:
        speaker = event.get("speaker")
        if not speaker:
            continue

        if speaker.casefold() == "narrator":
            if narrator_name is None:
                narrator_name = speaker
            continue

        if speaker not in seen:
            seen.add(speaker)
            characters.append({"name": speaker})

    if narrator_name:
        characters.insert(0, {"name": narrator_name})

    validation = validate_scene(
        events=events,
        characters=characters,
        title=title,
        location=location,
    )

    return {
        "scene_id": scene_id,
        "title": title,
        "location": location,
        "source_file": pdf_path.name,
        "characters": characters,
        "events": events,
        "validation": validation,
    }


def parse_folder(
    input_dir: str | Path,
    output_dir: str | Path,
) -> None:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(input_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in: {input_dir}")
        return

    for pdf in pdf_files:
        match = re.search(r"(\d{1,4})", pdf.stem)
        scene_id = (
            f"scene_{int(match.group(1)):03d}"
            if match
            else pdf.stem
        )

        try:
            data = parse_pdf(pdf, scene_id)
            output_file = output_dir / f"{scene_id}.json"

            output_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            status = data["validation"]["status"]
            print(f"{pdf.name} -> {output_file.name}: {status}")

            for issue in data["validation"]["issues"]:
                print(f"  - {issue}")

        except Exception as exc:
            print(f"ERROR parsing {pdf.name}: {exc}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse screenplay-style PDF files into structured JSON for TTS."
    )
    parser.add_argument("input", help="Input PDF file or folder.")
    parser.add_argument("output", help="Output JSON file or folder.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if input_path.is_dir():
        parse_folder(input_path, output_path)
    else:
        if not input_path.exists():
            raise FileNotFoundError(
                f"Input PDF does not exist: {input_path}"
            )

        match = re.search(r"(\d{1,4})", input_path.stem)
        scene_id = (
            f"scene_{int(match.group(1)):03d}"
            if match
            else input_path.stem
        )

        data = parse_pdf(input_path, scene_id)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        status = data["validation"]["status"]
        print(f"{input_path.name} -> {output_path}: {status}")

        for issue in data["validation"]["issues"]:
            print(f"  - {issue}")

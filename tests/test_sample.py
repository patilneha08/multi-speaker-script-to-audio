import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from parser import parse_pdf

PDF = Path("/mnt/data/Copy of Taste Anatomy Script -- Petr Samoilov(1).pdf")


def test_sample():
    scene = parse_pdf(PDF, "scene_001")
    assert scene["validation"]["status"] == "pass"
    assert scene["location"] == "EXT. PARK"
    assert {c["name"] for c in scene["characters"]} == {"Narrator", "Victor", "Kendra", "Dawn"}
    assert scene["events"][0]["speaker"] == "Narrator"
    assert any(e["delivery"]["off_screen"] for e in scene["events"])
    confident = next(e for e in scene["events"] if e["speaker"] == "Victor" and e["delivery"]["raw_cue"] == "confident")
    assert confident["text"] == "A kind of sushi."
    long = next(e for e in scene["events"] if e["speaker"] == "Victor" and e["text"].startswith("Papillae are those bumps"))
    assert "depending on shape and where they are" in long["text"]
    assert len(scene["events"]) == 72

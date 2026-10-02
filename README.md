# Automated TTS Pipeline

## Pipeline
PDF scripts -> deterministic parser -> scene JSON -> validation -> scene voice assignment -> TTS API -> individual line clips -> scene assembly -> QA

## First milestone
Run the parser against one known-good sample PDF and manually inspect the resulting JSON. Do not connect the TTS provider until parser validation passes.

## Commands

```bash
python -m pip install -r requirements.txt
python src/parser.py "scripts/scene_001.pdf" "json/scene_001.json"
```

For a folder:

```bash
python src/parser.py scripts json
```

## Rules
- PDF remains the source of truth.
- Do not paraphrase dialogue.
- Preserve event order.
- Preserve parenthetical cues as `delivery.raw_cue`.
- Preserve interruptions (`--`) as metadata; do not speak the dash characters.
- Narrator voice is global; character voice assignments are scene-specific.
- Keep TTS provider voice IDs out of the parser output.

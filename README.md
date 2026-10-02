# Multi-Speaker Script-to-Audio Generator

An automated Python pipeline that converts multi-character dialogue scripts into structured, validated, multi-speaker audio using text-to-speech.

The system parses scripts, identifies speakers and dialogue, preserves delivery cues and interruptions, validates the extracted structure, assigns configurable voices to characters, generates individual speech clips through a TTS API, and assembles them into a complete audio scene.

## Overview

Producing multi-speaker audio from dialogue-heavy scripts involves more than simply sending text to a text-to-speech model. Scripts may contain narration, stage directions, speaker cues, interruptions, multiline dialogue, and character-specific delivery instructions.

This project automates that workflow as a reusable pipeline:

```text
PDF Script
    ↓
Script Parsing
    ↓
Structured Scene JSON
    ↓
Validation
    ↓
Voice Assignment
    ↓
Text-to-Speech Generation
    ↓
Individual Audio Clips
    ↓
Audio Assembly
    ↓
Final Multi-Speaker Audio
```

## Features

- **PDF script parsing**  
  Extracts structured dialogue and narration from screenplay-style PDF files.

- **Speaker detection**  
  Identifies characters and associates dialogue with the correct speaker.

- **Narration and stage-direction handling**  
  Separates spoken narration from non-spoken stage directions.

- **Delivery cue extraction**  
  Preserves cues such as `(sarcastic)`, `(confident)`, and `(off-screen)` as structured metadata.

- **Interruption handling**  
  Detects interrupted dialogue and preserves conversational timing information.

- **Source traceability**  
  Retains source-page and raw-text information for parsed events.

- **Automated validation**  
  Detects malformed events, unknown speakers, possible character-name inconsistencies, missing fields, and other issues before TTS generation.

- **Configurable voice casting**  
  Maps characters to voices while allowing a consistent narrator and reusable voice pools.

- **Incremental TTS generation**  
  Generates speech at the individual dialogue-line level rather than regenerating an entire scene.

- **Content-based caching**  
  Uses signatures to detect unchanged dialogue and avoid unnecessary TTS API calls.

- **Audio assembly**  
  Combines generated dialogue clips in script order with configurable pauses and interruption timing.

- **Restart-safe workflow**  
  Existing unchanged audio clips can be reused when generation is resumed.

## Tech Stack

- Python
- PyMuPDF
- Speechify API
- Pydub
- FFmpeg
- python-dotenv

## Project Structure

```text
multi-speaker-script-to-audio/
│
├── config/
│   └── speechify_voices.json
│
├── src/
│   ├── parser.py
│   ├── validator.py
│   ├── voice_assigner.py
│   ├── tts.py
│   ├── assembler.py
│   ├── audition_voices.py
│   ├── list_voices.py
│   └── tts_test.py
│
├── tests/
│   └── test_sample.py
│
├── requirements.txt
├── .gitignore
└── README.md
```

Runtime data such as source scripts, parsed scene JSON, generated audio, API credentials, and local voice assignments are intentionally excluded from version control.

## Pipeline

### 1. Script Parsing

`parser.py` converts a screenplay-style PDF into structured scene data.

Each spoken event can contain information such as:

```json
{
  "event_id": "scene_001-001",
  "type": "dialogue",
  "speaker": "Character A",
  "text": "Wait -- what happened?",
  "spoken_text": "Wait -- what happened?",
  "delivery": {
    "inline_cues": []
  }
}
```

Stage directions are represented separately and marked as non-spoken events.

### 2. Validation

`validator.py` performs structural and semantic checks before audio generation.

Validation includes checks for:

- duplicate or non-sequential event IDs
- missing speakers
- empty dialogue
- unknown event types
- possible character-name inconsistencies
- malformed delivery metadata
- missing source traceability
- invalid audio status

Scenes can be classified as:

```text
PASS
REVIEW
FAIL
```

This prevents malformed scene data from silently entering the TTS stage.

### 3. Voice Assignment

`voice_assigner.py` assigns TTS voices to characters using a configurable voice pool.

The configuration supports:

- a consistent narrator voice
- male/female voice pools
- persistent character assignments
- manual casting overrides

Local casting configuration is intentionally excluded from the public repository.

### 4. Text-to-Speech Generation

`tts.py` generates one audio file per spoken event.

Instead of regenerating an entire scene whenever something changes, each event is processed independently.

A manifest records information including:

```text
event
speaker
voice
model
spoken text
content signature
generated file
```

A hash derived from the text, voice, and model allows unchanged clips to be reused.

```text
Unchanged event → SKIP
Changed event   → REGENERATE
New event       → GENERATE
```

This reduces unnecessary API calls and makes the pipeline restart-safe.

### 5. Audio Assembly

`assembler.py` combines the generated clips in event order.

Different timing rules can be applied to:

- standard dialogue
- narration
- interruptions

The result is a single multi-speaker audio file for the scene.

## Setup

Clone the repository:

```bash
git clone https://github.com/patilneha08/multi-speaker-script-to-audio.git
cd multi-speaker-script-to-audio
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

FFmpeg is required by Pydub. On macOS:

```bash
brew install ffmpeg
```

## Environment Variables

Create a local `.env` file:

```text
SPEECHIFY_API_KEY=your_api_key_here
```

The `.env` file is excluded from version control.

## Running the Components

Parse a script:

```bash
python3 src/parser.py scripts/scene_001.pdf json/scene_001.json
```

Validate a scene:

```bash
python3 src/validator.py json/scene_001.json
```

Assign character voices:

```bash
python3 src/voice_assigner.py json/scene_001.json
```

Generate speech:

```bash
python3 src/tts.py json/scene_001.json
```

Assemble the generated clips:

```bash
python3 src/assembler.py json/scene_001.json
```

## Design Principles

### Preserve the source

The parser keeps the original dialogue separate from transformations required for speech generation. This allows the source script to remain traceable and auditable.

### Validate before generating

TTS calls can consume paid API resources. Structural problems are therefore detected before audio generation whenever possible.

### Generate at dialogue-line granularity

Every spoken event becomes an independent audio asset. A single incorrect line can therefore be regenerated without rebuilding the entire scene.

### Separate casting from parsing

Voice configuration is independent of script extraction. The same parsed scene can be recast without modifying the underlying scene representation.

### Make generation idempotent

Content signatures and manifests allow the pipeline to determine whether an audio clip already represents the current text, voice, and model configuration.

## Current Development

The core single-scene pipeline currently supports:

```text
PDF → Parse → Validate → Cast → TTS → Assemble
```

Planned extensions include:

- batch processing for multiple scripts
- pronunciation dictionaries for specialized vocabulary
- improved expressive speech controls
- automated QA reporting
- retry and rate-limit handling
- audio normalization
- automated tests for additional script formats
- end-to-end pipeline orchestration

## Privacy and Repository Safety

The repository intentionally excludes:

- source scripts
- extracted production dialogue
- generated audio
- API credentials
- private character casting configuration

Only the reusable pipeline implementation and non-sensitive configuration are version controlled.


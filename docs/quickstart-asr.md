# Optional ASR quickstart

These recipes produce local transcript JSON for the dependency-free toolkit. They are separate from the toolkit runtime: none of `faster-whisper`, NeMo, WhisperX, CUDA, or model weights is a package dependency of this repository. When running from this toolkit checkout, use the ignored `artifacts/` directory for generated JSON and Markdown. When running from the course repository, use its ignored `audio/` and `transcripts/` directories instead. Replace every placeholder path and token before running commands.

## 1. Normalize audio with ffmpeg

Use a locally available source file and keep the normalized audio outside Git, for example under a local `audio/` directory. In this toolkit checkout, `.wav` files are ignored by extension; the course repository additionally ignores its `audio/` directory:

```sh
mkdir -p audio
ffmpeg -i "/path/to/input-video-or-audio" \
  -vn -ac 1 -ar 16000 -c:a pcm_s16le \
  "audio/video-id-16k-mono.wav"
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force audio | Out-Null
ffmpeg -i "C:\path\to\input-video-or-audio" `
  -vn -ac 1 -ar 16000 -c:a pcm_s16le `
  "audio\video-id-16k-mono.wav"
```

The input must already be available locally. This command does not retrieve a video.

## 2. faster-whisper baseline

Create an isolated environment for the optional backend. `large-v3` is the conservative baseline; change `MODEL_NAME` to `large-v3-turbo` when that trade-off is appropriate for the hardware and accuracy target.

POSIX shell:

```sh
python3 -m venv .venv-faster-whisper
. .venv-faster-whisper/bin/activate
python -m pip install faster-whisper
```

PowerShell:

```powershell
py -m venv .venv-faster-whisper
. .venv-faster-whisper\Scripts\Activate.ps1
py -m pip install faster-whisper
```

Run this short transcription snippet from the toolkit checkout. It writes segment timestamps in the JSON shape accepted by `media_distill render`:

```sh
mkdir -p artifacts
python3 - <<'PY'
import json
from pathlib import Path
from faster_whisper import WhisperModel

INPUT_AUDIO = Path("audio/video-id-16k-mono.wav")
OUTPUT_JSON = Path("artifacts/video-id.json")
MODEL_NAME = "large-v3"  # or "large-v3-turbo"

model = WhisperModel(MODEL_NAME, device="cuda", compute_type="float16")
segments, info = model.transcribe(
    str(INPUT_AUDIO),
    language="it",
    vad_filter=True,
)
result = {
    "language": info.language,
    "segments": [
        {"start": segment.start, "end": segment.end, "text": segment.text.strip()}
        for segment in segments
    ],
}
OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(f"wrote {OUTPUT_JSON}")
PY
```

For a CPU-only machine, consult the current faster-whisper documentation and choose a compatible `device` and `compute_type`; do not assume the CUDA example is portable to every machine.

## 3. Optional Parakeet TDT v3 / NeMo path

Parakeet TDT v3 is GPU-oriented. Create a separate environment using the CUDA- and Python-compatible installation instructions in the [NeMo ASR documentation](https://docs.nvidia.com/nemo-framework/user-guide/latest/nemotoolkit/asr/intro.html) and the [Parakeet TDT v3 model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3). Do not add NeMo to the toolkit package.

After that environment is prepared, a minimal invocation is:

```sh
python3 - <<'PY'
import nemo.collections.asr as nemo_asr

model = nemo_asr.models.ASRModel.from_pretrained(
    model_name="nvidia/parakeet-tdt-0.6b-v3"
)
output = model.transcribe(
    ["audio/video-id-16k-mono.wav"],
    timestamps=True,
)
print(output[0])
PY
```

This is intentionally GPU-oriented and follows a version-sensitive NeMo API. Check the current model card and NeMo release notes if the invocation or timestamp object changes. Timestamps still do not provide speaker labels; add a separate diarization stage when required.

## 4. Optional WhisperX alignment and diarization

WhisperX is a pipeline, not a replacement ASR model. In its own optional environment, a basic Italian run is:

```sh
whisperx "/path/to/input-16k-mono.wav" \
  --language it \
  --model large-v3 \
  --output_dir "/path/to/whisperx-output"
```

Diarization generally needs access to the relevant gated pyannote models and a Hugging Face token. Use a placeholder supplied through the shell rather than writing a real token into a command history, file, or repository:

```sh
export HF_TOKEN="<HUGGING_FACE_TOKEN>"
whisperx "/path/to/input-16k-mono.wav" \
  --language it \
  --model large-v3 \
  --diarize \
  --hf_token "$HF_TOKEN" \
  --output_dir "/path/to/whisperx-diarized-output"
```

PowerShell equivalent:

```powershell
$env:HF_TOKEN = "<HUGGING_FACE_TOKEN>"
whisperx "C:\path\to\input-16k-mono.wav" `
  --language it `
  --model large-v3 `
  --diarize `
  --hf_token $env:HF_TOKEN `
  --output_dir "C:\path\to\whisperx-diarized-output"
```

Before diarization, accept the current pyannote model terms and check the [WhisperX documentation](https://github.com/m-bain/whisperX). The token is a local placeholder only.

## 5. Render the produced transcript

From the toolkit checkout, render a JSON file that contains a segment array or an object with a `segments` array:

```sh
python3 -m media_distill render \
  artifacts/video-id.json \
  --output artifacts/video-id.md
```

PowerShell:

```powershell
py -m media_distill render `
  artifacts\video-id.json `
  --output artifacts\video-id.md
```

The renderer does not fetch, enrich, or infer transcript content. Keep the input JSON, model details, timestamps, and verification status together in the downstream provenance note.

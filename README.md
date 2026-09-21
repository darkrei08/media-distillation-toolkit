# Media Distillation Toolkit

A dependency-free Python 3.11+ foundation for validating source manifests and turning already-available transcript JSON into deterministic Markdown. It does not download media or call AI providers.

## Prerequisites

- Python 3.11 or newer.
- Git, if you are working from a checkout.
- Optional ASR workflows may need `ffmpeg`, a GPU runtime, and their own isolated environment. Those tools are not toolkit runtime dependencies.

## Quickstart from a checkout

From the repository directory, the toolkit can run without installation:

```sh
python3 -m media_distill validate examples/playlist-manifest.json
python3 -m media_distill render examples/transcript.json --output artifacts/transcript.md
```

Create the ignored output directory first when needed:

```sh
mkdir -p artifacts
```

On PowerShell:

```powershell
New-Item -ItemType Directory -Force artifacts | Out-Null
py -m media_distill validate examples/playlist-manifest.json
py -m media_distill render examples/transcript.json --output artifacts/transcript.md
```

## Optional editable install

The runtime has no third-party dependencies. An editable install only adds the `micio-distill` console command.

POSIX shell:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
micio-distill validate examples/playlist-manifest.json
micio-distill render examples/transcript.json --output artifacts/transcript.md
```

PowerShell:

```powershell
py -m venv .venv
. .venv\Scripts\Activate.ps1
py -m pip install -e .
micio-distill validate examples/playlist-manifest.json
micio-distill render examples/transcript.json --output artifacts/transcript.md
```

If PowerShell blocks activation, use the checkout commands above or follow the local execution-policy rules for your machine; do not change a system policy just for this toolkit.

## Check the toolkit

Run the standard-library test suite, validate the example manifest, and render the example transcript:

```sh
python3 -m unittest discover -s tests -v
python3 -m media_distill validate examples/playlist-manifest.json
mkdir -p artifacts
python3 -m media_distill render examples/transcript.json --output artifacts/transcript.md
```

The equivalent installed-command checks are:

```sh
python -m unittest discover -s tests -v
micio-distill validate examples/playlist-manifest.json
micio-distill render examples/transcript.json --output artifacts/transcript.md
```

## Input formats

A manifest is an object with a valid HTTP(S) `source_url` and a non-empty `videos` array. Each video requires a unique `id`, a non-empty `title`, and a valid HTTP(S) `url`. A transcript is either a segment array or an object containing `segments`; each segment requires `text` and may contain `timestamp` or `start`, plus `speaker`.

For local ASR recipes and backend trade-offs, see [`docs/quickstart-asr.md`](docs/quickstart-asr.md) and [`docs/asr-backends.md`](docs/asr-backends.md). Those recipes use optional environments outside the toolkit package.

## Intended staged pipeline

1. **Official metadata**: record playlist and video metadata from an official feed or API, retaining source URLs and IDs.
2. **Captions when available**: prefer creator-provided or platform-provided captions and retain their provenance.
3. **Local fallback**: when permitted and available, use local `yt-dlp` and `ffmpeg`, then local Whisper transcription. Downloading and transcription are intentionally not implemented here.
4. **Optional adapters**: add explicit, opt-in Anthropic, OpenAI, or Ollama adapters later. Provider calls are not implemented here.
5. **Provenance**: attach source, retrieval time, tool/model, input hash, and timestamp ranges to every derived note.
6. **Caching**: cache immutable inputs and intermediate results by content hash; never commit private media or transcripts.
7. **Resumability**: write small checkpoints so a failed run can resume without repeating completed stages.
8. **Human verification**: mark claims as pending until a person checks the source and relevant timestamps.

The toolkit currently implements only manifest validation and Markdown rendering. There is no server to start yet, no automatic downloading, and no automatic provider or model calls.

## Development

The tests use only the Python standard library:

```sh
python3 -m unittest discover -s tests -v
```

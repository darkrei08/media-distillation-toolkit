# ASR backend comparison for Italian long-form audio

This is a practical shortlist, not a benchmark. Model support, language coverage, hardware requirements, and license terms can change. Read the current model card and project documentation before selecting a production backend. No exact Italian benchmark score is asserted here.

## Baseline and alternatives

| Option | What it is good at | Italian long-form fit | Timestamps and speakers | Main caveats |
| --- | --- | --- | --- | --- |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) with [Whisper large-v3](https://huggingface.co/openai/whisper-large-v3) or [Whisper large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) | Conservative local baseline with a mature Whisper ecosystem and CTranslate2 implementation | Strong default starting point when broad multilingual coverage and a straightforward local workflow matter | Segment timestamps are available; diarization is not part of the ASR model | Choose compute type and model size for the available CPU/GPU; check the current model and software terms |
| [NVIDIA Parakeet TDT v3 model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | Dedicated ASR candidate for European-language workloads, including Italian; the model card documents timestamp output | Strong candidate to test when GPU throughput and NeMo integration are acceptable | Timestamps are not speaker labels; TDT does not imply diarization | GPU/CUDA and version-compatible [NeMo ASR](https://docs.nvidia.com/nemo-framework/user-guide/latest/nemotoolkit/asr/intro.html) setup can be more involved; the model card states CC-BY-4.0, but verify the current card and any additional component terms |
| [WhisperX](https://github.com/m-bain/whisperX) | Pipeline around Whisper for alignment and optional diarization | Useful when word-level timing or a speaker-labelled deliverable matters more than a single ASR model | Adds word alignment and can add diarization through pyannote; it is not a new ASR model | Alignment models vary by language; diarization commonly requires a Hugging Face token, access to gated pyannote models, and acceptance of their terms |
| [FunASR](https://github.com/modelscope/FunASR), including [SenseVoiceSmall](https://huggingface.co/FunAudioLLM/SenseVoiceSmall) and Paraformer-family models | Model and pipeline collection with multiple speech tasks and deployment choices | Workload-dependent alternative; test the exact checkpoint on representative Italian audio rather than assuming every FunASR model supports Italian equally | Timestamp, VAD, and speaker capabilities depend on the selected pipeline and model | Language coverage, APIs, checkpoints, and licenses differ; review the exact model card. A Paraformer checkpoint is not automatically a multilingual Italian solution |
| [Qwen audio models](https://huggingface.co/Qwen/Qwen2-Audio-7B-Instruct) | General audio-language-model option for experiments or tasks beyond plain transcription | Workload-dependent; useful to investigate when instruction following or audio understanding is also required | Do not assume Whisper-like segment timestamps or diarization from an audio-language model | Larger runtime footprint, model-specific language behavior, and model terms; validate whether the exact checkpoint meets an ASR-only contract |
| [MOSS-Transcribe-Diarize](https://github.com/OpenMOSS/MOSS-Transcribe-Diarize) | Experimental long-form, multi-speaker transcription/diarization direction | Worth an evaluation for multi-speaker recordings when experimentation is acceptable | Aims at transcription plus speaker separation, subject to the current implementation and checkpoint | Experimental status and model/weight terms require careful review. Verify the current repository, model card, checkpoint provenance, and commercial/production rights before use |

## Practical recommendation

1. Start with faster-whisper and `large-v3` or `large-v3-turbo` as the comparison baseline.
2. Test Parakeet TDT v3 next when a CUDA/NeMo environment is available and European-language coverage with timestamps is attractive.
3. If speaker labels are required, use Parakeet plus a separate diarization model, or use WhisperX with its alignment and diarization components. **TDT does not mean diarization.** Speaker labels require a separate speaker-attribution step.
4. Evaluate FunASR, SenseVoice, Paraformer, Qwen-family, or MOSS options only against the actual workload: Italian accents, code-switching, overlapping speakers, long pauses, timestamps, and privacy constraints.
5. Record the exact checkpoint, software version, device, language setting, and license review in the transcript provenance.

## License and access checklist

- Read the exact model card for the checkpoint, not only the framework README.
- Confirm whether model weights, code, alignment models, and diarization models have compatible terms.
- For WhisperX diarization, follow the current [pyannote.audio documentation](https://github.com/pyannote/pyannote-audio) and its model access instructions; do not place a token in a repository or transcript.
- Treat external model links as references to re-check at installation time. This repository does not download models or call providers automatically.

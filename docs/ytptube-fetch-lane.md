# YTPTube fetch lane

Specification for adding YTPTube as the acquisition engine of this toolkit.

## Premise correction

This spec replaces an earlier assumption that the toolkit had no download capability. It does, in a limited form: `deploy/Dockerfile` already installs `yt-dlp==2025.02.19` into the runtime virtualenv, while `README.md` states the toolkit "does not download media or call AI providers". Both statements are true and they contradict each other in practice: the binary ships in the image and no code path uses it.

So the gap is not the ability to download. The gap is that there is no lane: no queue, no retry, no record of what was fetched, no handling of cookies, playlists, channels, or live streams, and no place where a downloaded artifact becomes part of a corpus. YTPTube supplies exactly that missing lane, and the existing in-image `yt-dlp` must stop being a second, undeclared fetch path once YTPTube exists.

## Problem statement

An operator can validate a source manifest and render transcript JSON into Markdown. They cannot acquire the media, the platform subtitles, or the auxiliary files that the transcript pipeline needs, because no component in this repository performs acquisition and the one that could is unused.

Trying to bolt acquisition onto the Python package would break its defining property: the runtime has no third-party dependencies, and the package is deliberately small enough to reason about. Pulling in a downloader, a queue, a scheduler, cookie handling, and a browser fallback would make the toolkit the monolith that this repository was built to avoid.

## Solution

YTPTube runs as a separate container, pinned and loopback-bound, and owns acquisition as an external engine. The toolkit talks to it over its HTTP API and keeps its own responsibilities: validating manifests, rendering transcripts, and deciding what belongs to the corpus.

There is exactly one acquisition engine. The in-image `yt-dlp` is removed from the runtime virtualenv so that no second path can exist, and every fetch goes through YTPTube where it is observable.

Provenance is split by field, not duplicated by record. Each fact has one writer. A reconciliation pass reads YTPTube's state and updates the manifest, but never writes queue state back.

## User stories

1. As an operator, I want to submit a list of URLs and have the media, subtitles, and metadata land in a known directory, so that the transcript pipeline has an input.
2. As an operator, I want a failed download to be visible and retryable without re-submitting the whole list, so that one bad URL does not stall a batch.
3. As an operator, I want to see progress and queue state in a UI, so that I do not have to read logs to know what is happening.
4. As an operator, I want to enqueue from the toolkit or from the YTPTube UI, so that I can work whichever way is convenient at the moment.
5. As an operator, I want an item enqueued in the UI to appear in the corpus manifest after reconciliation, so that two entry points do not create two truths.
6. As an operator, I want a download that YTPTube reports as failed to be marked stale in the manifest rather than silently dropped, so that I can see what is missing.
7. As an operator, I want a manifest entry to survive even when YTPTube's history has been pruned, so that pruning a queue never destroys corpus records.
8. As an operator, I want the media directory to be a normal filesystem path, so that I can back it up and inspect it without a database client.
9. As an operator, I want the platform's own subtitles preferred over transcription, so that I avoid running an ASR model when the text already exists.
10. As an operator, I want to know when a URL has no platform subtitles, so that the ASR decision is made on evidence instead of assumption.
11. As an operator, I want YTPTube reachable only on loopback, so that starting the stack does not expose an unauthenticated downloader to the network.
12. As an operator, I want authentication enabled on YTPTube with a key held in the environment, so that another local process cannot enqueue work under my identity.
13. As an operator, I want the image pinned to an exact release, so that an upstream change cannot alter behaviour between two runs of the same stack.
14. As an operator, I want the downloader's configuration and its downloaded files in separate directories, so that I can delete the queue state without deleting the corpus.
15. As a maintainer, I want the toolkit's runtime to stay free of third-party dependencies, so that its test suite remains fast and its behaviour remains predictable.
16. As a maintainer, I want one acquisition engine, so that a bug report about fetching has exactly one place to look.
17. As a maintainer, I want the manifest to remain the authoritative record of corpus membership, so that a queue database is never required to read the corpus.
18. As a maintainer, I want each fact to have exactly one writer, so that reconciliation is a comparison rather than a merge conflict.
19. As a maintainer, I want reconciliation to be idempotent, so that running it twice changes nothing the second time.
20. As a maintainer, I want reconciliation to be read-only against YTPTube, so that a bug in the toolkit cannot corrupt the queue.
21. As a maintainer, I want the fetch lane to be exercisable without a real network fetch, so that the suite stays hermetic.
22. As a maintainer, I want the YTPTube API surface the toolkit depends on to be recorded explicitly, so that an upstream API change is a known breakage rather than a surprise.
23. As a maintainer, I want the README's stated boundary to match the code, so that a reader is not misled in either direction.
24. As a maintainer, I want a documented path for cookie-protected and geo-restricted sources, so that the answer is not "edit the container".
25. As a security-conscious operator, I want no cookie, session token, or YTPTube API key committed, so that the repository stays publishable.
26. As a security-conscious operator, I want the downloader to run as a non-root user with a writable data directory and nothing else, so that its blast radius stays small.

## Implementation decisions

### Topology: an external engine, not absorbed code

YTPTube runs as its own container and is never imported, vendored, or wrapped as a Python dependency. This follows the same shape already used for parsing decisions: the engine is a separate process because it has a different runtime, a different release cadence, and a different licence surface. The toolkit keeps a thin client.

The existing `deploy/compose.yaml` gains a second service rather than being restructured. The current `media-distill` service keeps its build context, its loopback port, and its `/data` mount.

### One engine

The runtime image stops installing `yt-dlp`. Keeping it would leave two acquisition paths, one observable and one not, and the unobservable one would inevitably be used by whoever finds it first. The pinned version currently in `deploy/Dockerfile` is removed in the same change that adds YTPTube, so the repository never contains a state with two engines.

### Pinned image and isolation

The YTPTube image is pinned to the exact release `ghcr.io/arabcoders/ytptube:v2.7.6`, never `latest`. Its published port is bound to `127.0.0.1` only. Authentication stays enabled; `YTP_DISABLE_AUTH` is not used anywhere, including in examples. The API key lives in the environment and is never committed.

Two directories are mounted separately:

- a configuration and queue directory, holding YTPTube's SQLite database and its settings, disposable;
- a downloads directory, holding the acquired artifacts, part of the operator's data and never deleted by a queue reset.

### The field ownership rule

This is the rule that makes the operator's choice of reconciliation safe. Each fact has exactly one writer, and no field appears on both sides.

YTPTube owns, and the toolkit reads without ever writing:

- queue item identity and status;
- attempt count, error text, and the extractor version used for a given attempt;
- the output file path and byte size of a completed artifact;
- completion timestamps.

The toolkit manifest owns, and YTPTube never sees:

- corpus membership: whether an artifact belongs to the corpus at all;
- the stable record identity for a source URL;
- the declared collection or folder a record belongs to;
- the transcript path and its provenance;
- the accepted artifact checksum;
- the retention decision.

The toolkit may enqueue work through the YTPTube API. Enqueueing is an expression of intent, not a statement of fact, and it never writes status.

### Reconciliation

Reconciliation is a read-only pass over YTPTube's history that updates the manifest. It never deletes a manifest entry and never deletes a downloaded file.

| Observed | Manifest action |
| --- | --- |
| YTPTube item completed, no manifest record | Adopt: create the record, mark its origin as adopted, store the queue item id. |
| YTPTube item completed, manifest record exists | Update only the artifact facts YTPTube owns. Leave every manifest-owned field untouched. |
| YTPTube item failed or errored, manifest record exists | Mark the record stale with the reported reason. Keep the record and any existing artifact. |
| YTPTube item absent, manifest record exists | Mark the record unverified. Absence is not deletion, because queue history can be pruned. |
| Manifest record stale or unverified, then a later item completes | Clear the flag and record the new artifact facts. |

The pass is idempotent: a second run against unchanged state produces no diff.

### Subtitle policy

Platform subtitles are acquired whenever they exist, and the manifest records their presence or absence per record. This is the cheap path and it is preferred over transcription for every source that has them. The count of sources without platform subtitles is recorded, because that count is the only honest input to a decision about whether an ASR backend is worth operating.

### ASR stays out of scope

Transcription is not part of this lane. `docs/asr-backends.md` already owns the backend comparison and recommends faster-whisper `large-v3` as the baseline, with Parakeet and WhisperX as the next candidates. This spec neither reopens that comparison nor selects a backend. What it adds is the measurement that was missing: how much of the corpus actually lacks platform subtitles.

### API surface the toolkit depends on

Only these operations are used, and each is named here so an upstream change is a known breakage:

- submit one or more URLs for download;
- read queue and history state, in bulk and per item;
- inspect a single item's status and result;
- start, pause, cancel, or retry a queue item.

Everything else YTPTube offers is out of scope: presets, subscriptions, scheduled tasks, browser-console features, and its metadata formatters. The toolkit does not depend on them, and depending on them would tie the corpus to a UI product.

### Security posture

YTPTube is a downloader with a browser fallback and an admin UI. It is loopback-only, authenticated, and given exactly two writable directories. It receives no credentials for any other service. Cookies for protected sources, when used at all, are supplied through YTPTube's own configuration directory and are never committed or logged. The toolkit never forwards its own secrets to it.

### Documentation debt this closes

`README.md` currently states the toolkit does not download media. That becomes false the moment this lane exists, and it must be rewritten in the same change to say what the toolkit does itself and what it delegates to an external engine.

## Testing decisions

Tests exercise observable behaviour: a manifest produced from a given YTPTube history, a reconciliation pass that is idempotent, a client that refuses a malformed response, an enqueue that sends the expected request shape. They do not assert internal call counts or storage layout.

The toolkit's client for YTPTube is tested against a fake HTTP server, not a live container, so the suite stays hermetic and fast. The fake serves recorded response shapes, which is also how the dependency on the API surface above is pinned.

Compose-level verification is a configuration assertion plus one manual smoke run, because a real fetch depends on the network and on the source. The smoke run records the exact URL, the observed output path, and the queue state it produced; it does not become a test, because a network-dependent test is a flaky test.

The reconciliation pass needs three cases at minimum, and each asserts the full resulting manifest rather than a single field: adoption of an unknown completed item, staleness of a failed item, and non-deletion of an unverified item. A fourth case asserts idempotence by running the pass twice and comparing the manifests byte for byte.

Prior art in this repository: `tests/test_toolkit.py` for the manifest and render contracts, which assert the produced document rather than the implementation.

## Out of scope

- Selecting or operating an ASR backend. Owned by `docs/asr-backends.md`.
- Transcribing audio, diarizing speakers, or producing word-level alignment.
- Subscriptions, scheduled tasks, and any YTPTube feature beyond the API surface named above.
- A toolkit-side UI for the queue. YTPTube already has one.
- Cookie harvesting from a browser profile, and any credential storage beyond YTPTube's own config directory.
- Migrating an existing corpus into the new manifest shape. There is no existing corpus to migrate.
- Public or remote exposure of YTPTube. Loopback only, no reverse proxy, no tunnel.
- Replacing YTPTube with a toolkit-native downloader. That would recreate the monolith this design avoids.

## Further notes

The honest question this spec cannot answer is whether YTPTube is worth its footprint. It is a second container, a second SQLite database, a second UI, and a second thing to keep patched, on a 16 GB host that already runs several agent sessions. What justifies it is the operational surface that `yt-dlp` alone does not provide: a queue, retries, progress, and an API. If a future measurement shows that acquisitions are few and manual, the lighter alternative is a thin `yt-dlp` invocation inside the existing service, and this lane should be deleted rather than maintained out of inertia.

That alternative is not chosen now because the operator asked for the queue, and because deleting a service later is easier than discovering, after a corpus has grown, that fetches were never recorded.

## Subtitle conversion lane

YTPTube downloads platform subtitles when they exist, and those arrive as WebVTT or SRT, which is not the transcript JSON that `render_transcript` consumes. The `subtitles` subcommand bridges the gap: it parses either format into `{"segments": [{"start": ..., "text": ...}]}`, strips inline markup, collapses whitespace, and drops the rolling repetition YouTube auto-captions produce.

This lane does not transcribe. A video without platform subtitles still needs an external ASR engine, which this package does not ship. What it does is make that engine unnecessary for every source that already has subtitles.

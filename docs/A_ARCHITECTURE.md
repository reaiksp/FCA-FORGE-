# A implementation map

The product defaults to Chinese with an English language toggle. Both locales live in studio/static/app.js; browser localStorage persists the preference. Raw engine diagnostics remain in their original language.

## Ownership

A is implemented in this repository. B / Seed-VC remains unimplemented and assigned to a separate AI. Read SEED_VC_B_ARCHITECTURE_HANDOFF.md before integrating it.

## Runtime boundaries

- studio/app.py: loopback FastAPI, upload and model import/export, datasets and job APIs.
- studio/jobs.py: durable per-job JSON, single GPU queue, process-tree cancellation and stage caching. One server process only.
- studio/pipeline.py: preparation, training orchestration and song conversion/mixing. Neural inference is out of process.
- studio/engines.py: pinned upstream command construction and capability declarations. Add B alongside A here.
- studio/audio.py: FFmpeg decode, slice metrics, PCM processing, resampling and simple mixing.
- scripts/rvc_worker.py: neural converter with per-chunk context, crossfade and exact-length output.
- scripts/separator_worker.py: audio-separator stem naming and validation; optional dereverb returns an explicit dry stem.

## Persistence

Inputs are uploaded under UUID paths in data/uploads. Dataset clips retain source offsets and hashes. Human inclusion choices are snapshotted before training. Experiments use stable job-derived identifiers, allowing upstream G/D checkpoint recovery. Voices hold an inference model, optional index and provenance. Job artifacts are visible during long workflows once the corresponding stage has completed.

A stage marker is committed only after outputs validate. Retry uses the same immutable job request, verifies recorded hashes, and reruns missing or changed completed stages. It does not create a new training configuration. New training parameters require a new job.

## Scope limits

No real training or real-song evaluation is authorized for this implementation run. Synthetic tests and environment checks cannot establish voice similarity, Chinese diction quality, training convergence or optimum batch size. Model bundle import currently requires unzipping and importing the .pth/.index files; direct ZIP import is not implemented. Mix controls are gain plus a short multi-tap ambience, not a full DAW or mastering chain. The trained checkpoint is initially selected by newest modification time, not an automatic quality claim.

## B integration

Add a separate environment and worker, expose an engine selector, retain reference-audio identity in the voice manifest, and share uploads, datasets, jobs, artifacts and mixing. B must not silently replace an A voice or load GPL code into an assumed MIT-only distribution without reviewing the resulting package.

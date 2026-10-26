# Third-party notices

Cover Studio's original code is provided under the MIT license in LICENSE. Third-party components, model weights and user recordings retain their own licenses and conditions.

## RVC / Applio

- Repository: https://github.com/IAHispano/Applio
- Pinned commit: `97e2fdc356bd0fe4bc4604d942bd254b4e447299`
- License in that checkout: MIT, copyright (c) 2026 AI Hispano.
- The setup script downloads an unmodified checkout to `vendor/Applio/`. Its LICENSE, terms, acknowledgements and nested notices remain in that checkout. This repository does not redistribute that checkout or model binaries.
- RVC bases include VITS, ContentVec/HuBERT, RMVPE, HiFi-GAN and other upstream dependencies. Refer to their notices in Applio and model distribution pages; do not infer that every separately hosted weight has the same terms as wrapper code.
- Model distribution: https://huggingface.co/IAHispano/Applio. Base download revision and hashes are recorded in `configs/models.json`.

## Music source separation

- audio-separator: https://github.com/nomadkaraoke/python-audio-separator (MIT wrapper; dependencies and weights retain their own terms).
- Separation architectures and weights include BS-RoFormer and UVR models. Downloads are managed by audio-separator. Verify the individual weight provenance for redistribution.
- Source-separation research implementation: https://github.com/ZFTurbo/Music-Source-Separation-Training

## Runtime libraries

FastAPI, Uvicorn, NumPy, SciPy, SoundFile, PyTorch, torchaudio, torchvision and their dependencies are installed from package registries. Their distribution metadata contains their respective licenses. imageio-ffmpeg bundles an FFmpeg executable and associated license information; this repository installs that package rather than bundling the executable into its own source archive.

## Future B engine

Seed-VC (https://github.com/Plachtaa/seed-vc) is not included or installed by this implementation. Its upstream GPL-3.0 licensing must be addressed when B is integrated. Do not describe a future combined distribution as wholly MIT without reviewing what is incorporated and distributed.

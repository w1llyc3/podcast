# Windows automatic audio compression validation

Executed locally on 2026-10-22. No audio, full transcript, local notes or credentials are included in this repository.

## Actual media runs

- Full public Ep 6 audio: 537.379410 seconds, AAC stereo, 8,692,269 bytes. The new compression module produced mono MP3 at 48,000 bit/s and 24,000 Hz, 3,224,828 bytes (62.900% smaller). Full decode duration was 537.379417 seconds, difference 0.00000624 seconds. Source backup SHA256 was verified before replacing the episode-directory original.
- Separate 12.004717-second real speech excerpt: actual cached large-v3-turbo CPU/int8 transcription, TXT, raw checkpoints, one-page PDF, local notes, metadata and MP3 completed in an isolated local output directory. An injected first compression failure retried successfully: two compression attempts, exactly one model transcription call. MP3 fully decoded at 48,000 bit/s, 24,000 Hz, mono; duration 12.004708 seconds, 72,668 bytes. A repeated worker run skipped processing and preserved all completed artifact hashes.
- This excerpt run verifies the new worker integration; it is not a new full-episode ASR acceptance run. Prior full-episode transcription/PDF evidence remains in P0_VALIDATION.md.

Private receipts: D:/podcast/evidence/auto-compression-full-20261022/result.json and D:/podcast/evidence/auto-compression-e2e-20261022/result.json. They stay on the Windows machine.

## Regression checks

Nine unittest checks pass on the actual Windows environment, including real FFmpeg on generated test signals: mono delivery, distinct stereo retention, encoder failure retaining original, checked backup, staged-file/receipt recovery without re-encoding, compression retry reusing completed transcript, completed-item deduplication and legacy archive migration without changing text/PDF. Existing HTTP Range interruption, transcript checkpoint restart, exclusive worker lock and RSS baseline/dedup tests also pass. Injected failures intentionally appear in test logs. Dependency `pip check` passes.

The sandbox prevented temporary-directory and localhost test access; tests passed when rerun in the normal Windows environment. No production RSS baseline was reset. Compression validation establishes decodability, parameters and duration, not a claim of lossless audio or manual listening review. Independent speaker channels are retained by a conservative channel-similarity rule; speaker identification is not implemented.

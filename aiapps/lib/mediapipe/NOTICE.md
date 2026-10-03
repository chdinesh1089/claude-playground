# MediaPipe Tasks Vision (vendored)

- `vision_bundle.mjs`, `vision_wasm_internal.js`, `vision_wasm_internal.wasm`:
  `@mediapipe/tasks-vision` 1.0.1 from npm. Two changes: the source-map
  comment is removed, and the usage logger (class `Fh`, which POSTs task
  timings to `odml.pa.googleapis.com/v1/log`) starts in its error state, so
  it never sends anything.
- `face_landmarker.task`: the float16 v1 Face Landmarker model from
  `storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/`.

Copyright Google LLC. Licensed under the Apache License, Version 2.0:
https://www.apache.org/licenses/LICENSE-2.0

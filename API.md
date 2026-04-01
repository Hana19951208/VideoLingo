# IndexTTS API

This document describes the `indextts-api` service exposed by the Dockerized
IndexTTS deployment.

## Base URL

- Local Docker Compose: `http://127.0.0.1:8000`
- Health check: `GET /healthz`
- Synthesis: `POST /v1/tts`
- Batch synthesis: `POST /v1/tts/batch`

## Runtime Notes

- The service is designed for one long-lived process.
- Requests are serialized with an internal lock because the model keeps mutable
  cache state.
- The batch endpoint reduces repeated HTTP upload and prompt preprocessing, but
  it does not enable true multi-request GPU parallel inference.
- The container is configured for NVIDIA GPU inference. CPU-only startup is
  intentionally blocked by `--require_gpu`.
- Audio outputs are written to `/app/outputs` inside the container and then
  returned to the caller.
- The emotion analysis sub-model can be offloaded to CPU and loaded lazily to
  reduce GPU memory pressure.

## Startup

Build and start the API service:

```bash
docker compose build
docker compose up -d tts-api
```

Optional WebUI:

```bash
docker compose --profile webui up -d webui
```

## Health Check

### `GET /healthz`

Purpose:
- Verify the HTTP server is reachable
- Verify the model has finished loading

Response:

```json
{
  "status": "ok",
  "model_loaded": true
}
```

Status codes:
- `200`: server is ready

## Synthesis Endpoint

### `POST /v1/tts`

Purpose:
- Accept a speaker reference audio file
- Optionally accept emotion guidance
- Return a generated WAV file directly in the response body

Request format:
- `Content-Type: multipart/form-data`

Response:
- `Content-Type: audio/wav`
- `filename=tts.wav`

### Form Fields

#### Required

| Field | Type | Description |
| --- | --- | --- |
| `text` | string | Target text to synthesize. Must not be empty. |
| `spk_audio` | file | Speaker prompt audio file. Allowed suffixes: `.wav`, `.mp3`, `.flac`, `.ogg`, `.m4a`, `.aac`. |

#### Optional

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `emo_audio` | file | none | Emotion reference audio. If omitted, the speaker prompt is reused as the emotion prompt. |
| `emo_alpha` | float | `1.0` | Emotion blend strength. Must be in `[0.0, 1.0]`. |
| `emo_vector` | JSON string | none | JSON array with exactly 8 numbers. The order is `[happy, angry, sad, afraid, disgusted, melancholic, surprised, calm]`. |
| `use_emo_text` | bool | `false` | Whether to infer emotion vectors from `emo_text`. |
| `emo_text` | string | none | Text description of the desired emotion. If empty, the service falls back to `text`. |
| `use_random` | bool | `false` | Whether to use random sampling in emotion vector selection. |
| `max_text_tokens_per_segment` | int | `120` | Maximum token count per text segment. Must be in `[1, 512]`. |

### Validation Rules

- `text` must contain non-whitespace characters.
- `spk_audio` must have a supported extension.
- `emo_audio` must have a supported extension if provided.
- `emo_vector` must be a JSON array of 8 numeric values.
- `emo_alpha` must be within `[0.0, 1.0]`.
- `max_text_tokens_per_segment` must be within `[1, 512]`.

### Behavior

- If `use_emo_text=true`, the server derives emotion vectors from `emo_text`
  or from `text` when `emo_text` is omitted.
- If `emo_vector` is provided, it takes precedence over emotion audio guidance.
- If `emo_audio` is omitted, the speaker audio is reused as the emotion prompt.
- The API runs inference synchronously and returns only after the WAV file is
  ready.

## Batch Synthesis Endpoint

### `POST /v1/tts/batch`

Purpose:
- Accept one speaker reference audio file
- Accept multiple synthesis items in one request
- Return a zip package with `manifest.json` and multiple wav files

Request format:
- `Content-Type: multipart/form-data`

Response:
- `Content-Type: application/zip`
- `filename=tts_batch.zip`

### Form Fields

#### Required

| Field | Type | Description |
| --- | --- | --- |
| `items` | JSON string | A non-empty JSON array. Each item must contain `id` and `text`. |
| `spk_audio` | file | Shared speaker prompt audio file for the whole batch. |

#### Optional

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `emo_audio` | file | none | Shared emotion reference audio for the whole batch. |
| `emo_alpha` | float | `1.0` | Emotion blend strength for the whole batch. |
| `emo_vector` | JSON string | none | Shared 8-dimension emotion vector for the whole batch. |
| `use_random` | bool | `false` | Whether to use random sampling in emotion vector selection. |
| `max_text_tokens_per_segment` | int | `120` | Default max token count for items that do not set `max_text_tokens`. |

### Batch Item Fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | yes | Stable item identifier. Also used as the wav filename stem. |
| `text` | string | yes | Target text to synthesize. |
| `emotion` | string | no | Text emotion hint for this single item. |
| `max_text_tokens` | int | no | Item-level override for token segmentation length. |

### Batch Behavior

- The server processes the whole batch under one request lock.
- Items are synthesized one by one inside that lock to preserve cache safety.
- The main speedup comes from reusing the uploaded reference audio and reducing
  repeated request overhead.
- `manifest.json` contains one record per item with `status`, and failed items
  are reported explicitly instead of being silently dropped.

## Examples

### Minimal request

Use `curl.exe` on Windows PowerShell:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/v1/tts" `
  -F "text=你好，欢迎使用服务" `
  -F "spk_audio=@examples/voice_01.wav" `
  --output "out.wav"
```

### With emotion reference audio

```powershell
curl.exe -X POST "http://127.0.0.1:8000/v1/tts" `
  -F "text=今天很开心，终于完成了目标" `
  -F "spk_audio=@examples/voice_01.wav" `
  -F "emo_audio=@examples/emo_sad.wav" `
  -F "emo_alpha=0.6" `
  --output "out_emo_audio.wav"
```

### With emotion vector

```powershell
curl.exe -X POST "http://127.0.0.1:8000/v1/tts" `
  -F "text=太惊喜了，真的没想到" `
  -F "spk_audio=@examples/voice_10.wav" `
  -F "emo_vector=[0,0,0,0,0,0,0.7,0]" `
  --output "out_emo_vector.wav"
```

### With emotion text

```powershell
curl.exe -X POST "http://127.0.0.1:8000/v1/tts" `
  -F "text=请保持冷静，慢慢说明问题" `
  -F "spk_audio=@examples/voice_03.wav" `
  -F "use_emo_text=true" `
  -F "emo_text=语气平稳、克制、冷静" `
  -F "emo_alpha=0.5" `
  --output "out_emo_text.wav"
```

### Batch request

Use `curl.exe` on Windows PowerShell:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/v1/tts/batch" `
  -F "items=[{\"id\":\"seg-1\",\"text\":\"第一句\"},{\"id\":\"seg-2\",\"text\":\"第二句\",\"emotion\":\"冷静\"}]" `
  -F "spk_audio=@examples/voice_01.wav" `
  --output "out_batch.zip"
```

## Error Codes

| Code | Meaning |
| --- | --- |
| `400` | Invalid business input, for example empty `text`, invalid `emo_alpha`, or invalid `emo_vector`. |
| `422` | Invalid uploaded file, for example unsupported suffix or empty content. |
| `500` | Model loading failure or runtime inference failure. |

## Operational Guidance

- Keep the API service running as a background container while clients send
  requests.
- Do not run multiple Uvicorn workers for this service unless the model is made
  stateless. The current implementation is intentionally single-worker.
- The recommended Docker defaults are `--fp16 --emotion_device cpu --lazy_emotion_model`.
- If you need to expose this service publicly, add authentication and rate
  limiting in front of it.

# Media Provenance Lab

## Chosen Vertical

**Media provenance and evidence** is the working vertical assumption. The
supplied challenge brief requires choosing one provided vertical, but does not
identify the selected vertical/track. The stated deadline is **November 6,
2026**.

### Challenge submission constraints

- The repository must be public and smaller than 10 MB.
- Keep exactly one branch; this project uses `main`.
- A maximum of two attempts is allowed.
- Submit the complete code and this README, including the vertical, approach,
  logic, operation, and assumptions.
- Reviewers emphasize code quality, security, efficiency, testing,
  accessibility, and problem-statement alignment.

## Demo:

No hosted deployment is required for this prototype. Run it locally, click a
synthetic sample, watch the named modules progress, read the evidence tier and
rule, open a heatmap, download the offline HTML, and open the methodology
endpoint.

## Problem Statement

Images are often copied, recompressed, or edited, but a binary verdict hides uncertainty. This app presents reproducible signals and their limits in plain English.

## Approach and Logic

The pipeline validates file signatures and dimensions, reads non-sensitive provenance context including optional C2PA capability status, runs tiled ELA, tiled noise residual, and spatially validated ORB copy-move checks, then applies deterministic R1-R4 fusion rules. Missing optional detector weights produce `not_determined`, never a silent clean result.

## How the Solution Works

Uploads become asynchronous jobs. Each completed job stores a report with signals, heatmaps, limitations, and exportable HTML. The API and static UI share one origin.

## Architecture:

```text
Browser -> FastAPI routes -> async job -> Pillow/OpenCV analysis -> Report + PNG heatmaps
                                  |-> deterministic fusion -> JSON/API and offline HTML export
```

## Setup and Run:

Use Python 3.12, create a virtual environment, install `requirements-dev.txt`, then run:

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. The app works offline with no provider keys. To enable the local learned detector, keep `model_int8.onnx` in the project root and set `DETECTOR_LOCAL_PATH=model_int8.onnx` in `.env`; detector failures remain `not_determined`.

## Optional Render deployment:

Render configuration is included for future use, but deployment and production
measurements are not required for this prototype submission.

## Free Services and Keys:

| Service | Purpose | Required | Free-tier summary | Sign-up |
|---|---|---:|---|---|
| Render | Web hosting | Yes | Free web service with sleep and ephemeral filesystem | https://render.com |
| Gemini or Groq | Optional explanation prose | No | Provider free tier, subject to current provider terms | Provider websites |
| Hugging Face | Optional model download | No | Optional public model access | https://huggingface.co |

## API Reference:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Health and optional dependency status |
| GET | `/api/v1/samples` | Synthetic demo gallery |
| POST | `/api/v1/analyze` | Start an upload analysis |
| POST | `/api/v1/samples/{id}/analyze` | Start a real sample analysis |
| GET | `/api/v1/jobs/{id}` | Poll job progress |
| GET | `/api/v1/reports/{id}` | Read report JSON |
| GET | `/api/v1/reports/{id}/export` | Download offline HTML |
| GET | `/api/v1/methodology` | Rules and limitations |

## Evaluation Results:

The reproducible synthetic evaluation manifest and results are in
[eval/manifest.json](eval/manifest.json) and [eval/results.json](eval/results.json).
Regenerate them with `python scripts/generate_eval.py`. These are regression
measurements on original CC0-1.0 synthetic content, not real-world accuracy.

## Testing:

```powershell
pip install -r requirements-dev.txt
pytest --cov=app --cov-report=term-missing
python scripts/generate_eval.py
python scripts/check_secrets.py
python scripts/check_repo_size.py
```

CI runs the same test suite on every push. Coverage exclusions are not configured.

## Security and Privacy Notes

Uploads are capped and checked by magic bytes. Client filenames are ignored. Analysis requests have a bounded per-IP rate limit, request IDs are returned for support, and `CORS_ORIGINS` enables an explicit origin allowlist when needed. GPS coordinates are never returned, and the optional explainer receives only report JSON. Reports and jobs are stored in SQLite with restart recovery and cleanup hooks. The free-host filesystem remains ephemeral, so the data survives normal requests but not a Render restart or redeploy.

## Accessibility Notes

Controls have visible labels, progress uses `aria-live`, tier text does not rely on color, links open with `noopener noreferrer`, and the layout adapts to narrow screens.

## Assumptions

See [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md). The supplied challenge brief identifies the November 6, 2026 deadline and
submission constraints, but does not identify the selected vertical/track.

## Limitations:

Free Render cold starts can take up to a minute, local storage is ephemeral,
and reports can be lost on restart. C2PA inspection is optional and reports
`not checked` when its binding is unavailable. The learned detector has
checksum and failure handling but remains uncalibrated and excluded from
fusion tiers. Audio is not included, and MP4 aggregation is limited to
sampled frames.

## Future Work

The baseline includes SQLAlchemy-backed TTL persistence, verified ONNX
checksum handling and calibration tooling, OpenCV video frame aggregation
with strongest-frame display, optional C2PA inspection, known-item pHash/dHash
context, optional Gemini/Groq explanations with timeout/cache fallback, real
dataset evaluation and licensing metadata, and keyboard/360px regression
tests. Independent labeled evaluation data, licensed model provenance, and live
deployment are not required to demonstrate the offline prototype. They are
required only if claiming real-world accuracy, distributing the learned
detector, or publishing a hosted service.

## Licences and Credits:

Application code is available under the repository's chosen open-source licence. Pillow, NumPy, OpenCV, imagehash, piexif, FastAPI, and SQLAlchemy remain under their respective upstream licences. No third-party dataset or detector weights are bundled.

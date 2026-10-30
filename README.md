# Media Provenance Lab

## Chosen Vertical

**Media provenance and evidence** is the working vertical assumption because the challenge document supplied with this build did not include a named vertical. The exact challenge vertical and track should replace this sentence before submission.

## Live Demo:

Live deployment: **not deployed yet**. The first Render free-plan load can take up to a minute. Judge path: open the link, click a synthetic sample, watch the named modules progress, read the evidence tier and rule, open a heatmap, download the offline HTML, and open the methodology endpoint.

## Problem Statement

Images are often copied, recompressed, or edited, but a binary verdict hides uncertainty. This app presents reproducible signals and their limits in plain English.

## Approach and Logic

The pipeline validates file signatures and dimensions, reads non-sensitive provenance context, runs ELA, noise residual, and ORB copy-move checks, then applies deterministic R1-R4 fusion rules. Missing optional detector weights produce `not_determined`, never a silent clean result.

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

Open `http://127.0.0.1:8000`. The app works offline with no keys; the optional learned detector and explainer are not required.

## Deploy on Render:

Create a new Blueprint from this repository. `render.yaml` uses Render's native Python runtime, the free plan, `pip install -r requirements.txt`, and `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set optional secrets in the Render dashboard. Free services use ephemeral storage and may sleep after inactivity, so reports are not permanent.

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

No evaluation dataset has been supplied yet, so this repository reports no measured accuracy. It must not invent metrics; a future `eval/results.json` is the source of truth.

## Testing:

```powershell
pip install -r requirements-dev.txt
pytest --cov=app --cov-report=term-missing
```

CI runs the same test suite on every push. Coverage exclusions are not configured.

## Security and Privacy Notes

Uploads are capped and checked by magic bytes. Client filenames are ignored. GPS coordinates are never returned, and the optional explainer receives only report JSON. This initial build keeps short-lived reports in process memory; production deployment should add the specified TTL-backed persistence before public judging.

## Accessibility Notes

Controls have visible labels, progress uses `aria-live`, tier text does not rely on color, links open with `noopener noreferrer`, and the layout adapts to narrow screens.

## Assumptions

See [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md). The exact challenge document and its vertical/track were not included in the supplied materials.

## Limitations:

Free Render cold starts can take up to a minute, local storage is ephemeral, and reports can be lost on restart. C2PA is reported as not checked, the learned detector is not loaded without verified weights, audio is not included, and MP4 frame aggregation is limited in this first implementation.

## Future Work

Add SQLAlchemy-backed TTL persistence, verified ONNX weights and calibration, full OpenCV video frame aggregation, C2PA support when the Linux wheel is confirmed, evaluation data, and a live smoke test.

## Licences and Credits:

Application code is available under the repository's chosen open-source licence. Pillow, NumPy, OpenCV, imagehash, piexif, FastAPI, and SQLAlchemy remain under their respective upstream licences. No third-party dataset or detector weights are bundled.


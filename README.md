# Media Provenance Lab

Media Provenance Lab is an offline-first prototype for inspecting image and
video provenance signals. It does not claim that a file is definitively
“real” or “fake”. Instead, it combines several explainable signals and reports
an evidence tier, limitations, and supporting heatmaps.

For a detailed description of the application, its users, capabilities,
workflow, API surface, advantages, architecture, and limitations, see the
[Application and Digital Forensics Guide](docs/APPLICATION_GUIDE.md).

The prototype is suitable for local demonstration. A hosted deployment,
provider API key, external dataset, and learned detector are **not required**
to run the basic application.

## 1. What the application does

The application can:

- validate image and video file signatures and size limits;
- inspect dimensions, format, metadata, and optional C2PA provenance;
- calculate tiled Error Level Analysis (ELA);
- calculate tiled noise residual signals;
- check for spatially validated copy-move regions;
- compare against optional known-item references;
- sample video frames and summarize frame-level evidence;
- apply deterministic R1-R4 fusion rules;
- show evidence, limitations, and heatmaps in the browser;
- export a completed report as offline HTML;
- evaluate labeled images through a manifest;
- generate reproducible derived examples for evaluation.
- create offline investigation cases for JSON/JSONL, CSV, plain-text logs, and
  filesystem-metadata evidence;
- normalize imported records into a searchable investigation timeline;
- retain SHA-256 evidence hashes and verify a per-evidence tamper-evident
  chain-of-custody log;
- answer local investigation questions with citations back to timeline events.
- flag privilege, destructive, authentication-failure, and access activity
  with deterministic findings tied to source events;
- import Chromium-style browser history SQLite databases and application/access
  records;
- optionally enforce case ownership with `AUTHENTICATION_BACKEND=local_bearer`
  and `AUTH_TOKENS=username:token` pairs;
- anchor custody tips to a separately retained local file and detect changes
  during verification.

The investigation assistant is intentionally deterministic in the offline
mode: it retrieves matching imported events and returns their identifiers
instead of inventing an incident narrative. An external AI provider can be
added later only with an explicit privacy and deployment decision.

The optional ONNX learned detector is disabled unless a verified local model is
configured. If it is unavailable or fails, the result is reported as
`not_determined`; the application does not silently treat that as a clean
result.

## 2. Challenge submission information

- Deadline: **November 6, 2026**.
- The repository must be public and smaller than 10 MB.
- Keep exactly one branch: `main`.
- A maximum of two attempts is allowed.
- The submission should include the complete code and this README.
- Review areas include code quality, security, efficiency, testing,
  accessibility, and problem-statement alignment.

The selected challenge vertical should be named in the final submission
description. The working vertical for this project is **media provenance and
evidence**.

## 3. Requirements

### Required for the basic prototype

- Windows, macOS, or Linux;
- Python **3.12**;
- Git, if cloning the repository;
- approximately 2 GB of free disk space for Python packages and temporary
  files;
- a modern browser such as Chrome, Edge, or Firefox.

No API key, Render account, ONNX model, or external image dataset is required
for the basic demonstration.

### Optional components

| Component | Purpose | Required? |
|---|---|---:|
| `c2pa-python` | Read C2PA manifests when available | No |
| ONNX model | Add a learned detector signal | No |
| Gemini or Groq key | Generate optional explanation prose | No |
| Hugging Face token | Access a private/model-hosting workflow | No |
| Render | Host the application publicly | No |
| Real licensed dataset | Make general accuracy claims | No, prototype only |

## 4. Get the project

### Option A: clone with Git

Open PowerShell and run:

```powershell
cd "N:\"
git clone https://github.com/navadeepu1/Media-Provenance-Lab-Backend.git
cd "Media-Provenance-Lab-Backend"
```

Replace `N:\` with the folder where you want to keep the project.

### Option B: download a ZIP

1. Open the GitHub repository page.
2. Select **Code** and then **Download ZIP**.
3. Extract the ZIP using File Explorer.
4. Open PowerShell in the extracted folder.

The folder must contain `app`, `scripts`, `tests`, `requirements.txt`, and
`requirements-dev.txt`. Do not run commands from the parent folder.

## 5. Create the Python environment

From the repository root, create a virtual environment:

```powershell
py -3.12 -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, either use the Python executable directly as
shown below or run PowerShell with a user-scoped execution-policy change:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Install the runtime and development dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

The development requirements include the runtime packages, pytest, coverage,
ONNX inspection support, and process-memory tools used by the tests and smoke
checks.

## 6. Configure local settings

The application has safe defaults and works without an environment file. To
customize settings, copy the example:

```powershell
Copy-Item .env.example .env
```

For the basic prototype, leave provider keys empty and keep:

```text
AI_PROVIDER=none
DETECTOR_LOCAL_PATH=model_int8.onnx
```

The detector remains inactive unless `model_int8.onnx` exists and its checksum
matches the configured value. Do not download or commit an unknown model just
to remove this optional status.

Important default safety limits include:

- maximum image size: 10 MB;
- maximum video size: 25 MB;
- maximum decoded image pixels: 16 million;
- maximum image side: 5,000 pixels;
- analysis downscale side: 2,048 pixels.

Accepted large images are downscaled only for in-memory forensic processing.
Original dimensions and provenance checks are preserved.

## 7. Start the application

From the repository root, with the virtual environment active:

```powershell
python -m uvicorn app.main:app --reload
```

When the server starts, open:

```text
http://127.0.0.1:8000
```

To stop the server, return to PowerShell and press `Ctrl+C`.

If the `python` command is using the wrong interpreter, run the virtual
environment interpreter explicitly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## 8. Use the browser interface

1. Open `http://127.0.0.1:8000`.
2. Choose a built-in synthetic sample, or select an image/video file from your
   computer.
3. Start the analysis.
4. Wait for the asynchronous job to finish.
5. Review:
   - the evidence tier;
   - the deterministic rule that produced it;
   - individual ELA, noise, copy-move, provenance, and detector signals;
   - limitations and `not_determined` statuses;
   - heatmaps and strongest video frames, when available.
   - uncertainty level, determined signal/family counts, and analysis time.
6. Cancel a running analysis from the progress panel if it is no longer needed.
7. Open the report export to download an offline HTML copy.

The report is evidence-oriented. A strong signal is not proof of manipulation,
and an authentic image may contain compression or editing artifacts.

## 9. API endpoints

The browser uses the same-origin FastAPI API. The main endpoints are:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Check service and optional dependency status |
| `GET` | `/api/v1/samples` | List built-in synthetic samples |
| `POST` | `/api/v1/analyze` | Start an uploaded file analysis |
| `POST` | `/api/v1/samples/{id}/analyze` | Analyze a built-in sample |
| `GET` | `/api/v1/jobs/{id}` | Poll asynchronous job progress |
| `POST` | `/api/v1/jobs/{id}/cancel` | Request cancellation of a queued/running job |
| `GET` | `/api/v1/reports/{id}` | Read a completed JSON report |
| `GET` | `/api/v1/reports/{id}/export` | Download offline HTML |
| `GET` | `/api/v1/methodology` | Read rules and limitations |
| `GET` | `/api/v1/ready` | Check database, queue, and storage readiness |
| `GET` | `/api/v1/capabilities` | Report the configured status of advanced capabilities |
| `POST` | `/api/v1/reports/{id}/reviews` | Create a local human-review task |
| `POST` | `/api/v1/cases` | Create an offline investigation case |
| `GET` | `/api/v1/cases` | List local investigation cases |
| `POST` | `/api/v1/cases/{id}/evidence` | Import JSON, CSV, text-log, or filesystem-metadata evidence |
| `GET` | `/api/v1/cases/{id}/timeline` | Read normalized timeline events |
| `GET` | `/api/v1/cases/{id}/findings` | Read deterministic suspicious-activity findings |
| `POST` | `/api/v1/cases/{id}/assistant` | Ask an evidence-grounded local question |
| `GET` | `/api/v1/cases/{id}/custody/verify` | Verify the evidence custody hash chain |
| `POST` | `/api/v1/cases/{id}/custody/anchor` | Anchor current custody tips to the configured local anchor file |
| `PATCH` | `/api/v1/reviews/{id}` | Update a local human-review task |
| `DELETE` | `/api/v1/reports/{id}` | Request report deletion |

Quick health check from PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

The upload endpoint expects a multipart form field named `file`. For example,
using the `curl.exe` included with Windows:

```powershell
curl.exe -X POST `
  -F "file=@.\path\to\image.jpg" `
  http://127.0.0.1:8000/api/v1/analyze
```

The response contains a job ID. Poll the job endpoint until it is complete,
then request the report endpoint using the returned report ID.

Jobs have a durable deadline (`JOB_BUDGET_SECONDS`, 90 seconds by default).
Timeouts and cancellation requests are persisted in SQLite, survive a process
restart as explicit failures, and never produce a success-shaped report.
Each completed report includes `analysis_metrics.total_ms`; structured JSON
events are emitted for queueing, completion, rejection, cancellation, timeout,
recovery, and cleanup. The browser reports uncertainty separately from the
evidence tier because a tier is not a probability of authenticity.

## 10. Run the automated tests

With the virtual environment active:

```powershell
python -m pytest -q
```

Run tests with coverage:

```powershell
python -m pytest --cov=app --cov-report=term-missing
```

The test suite covers analysis, API behavior, safety limits, detector failure
handling, forensic fixtures, evaluation manifests, and generated categories.

Run the repository checks:

```powershell
python scripts/check_secrets.py
python scripts/check_repo_size.py
```

The GitHub Actions workflow runs the test suite, synthetic evaluation, secret
scan, and repository-size check on pushes and pull requests.

## 11. Run the synthetic evaluation

The built-in evaluation is a regression check using fixed-seed synthetic
content:

```powershell
python scripts/generate_eval.py
```

Results are written under `eval`. These results verify repeatability and
regressions; they are **not real-world accuracy measurements**.

## 12. Evaluate real images with a manifest

The real-data evaluator does not treat a folder name as truth. Every image
must have a manifest record containing a verified label and provenance
metadata.

Copy the example manifest:

```powershell
Copy-Item eval\real_manifest.example.json eval_data\manifest.json
```

Fill in the records and ensure the referenced files exist below `eval_data`.
Supported labels include:

- `authentic`
- `recompressed`
- `spliced`
- `copy_moved`
- `forwarded`
- `ai_generated`

Each record needs a label, expected detection value, source type, license,
source description, split, file path, modification history, and appropriate
source or consent information. Open-source records need a source URL, license,
attribution requirements, and download date. Personal records should use
`source_url: "not_applicable"` and a non-sensitive consent record.

Run:

```powershell
python scripts/evaluate_dataset.py
```

The output is `eval\real_results.json` and includes file hashes, dimensions,
format, confusion matrix, precision, recall, and per-class results. If labels
or required provenance fields are missing, the command refuses to produce
misleading metrics.

## 13. Create derived evaluation categories

If you have consented authentic images, the preparation script can create
recompressed, forwarded, spliced, and copy-moved examples:

```powershell
python scripts/prepare_eval_dataset.py `
  --source-type personal `
  --license private-consented `
  --source "captured by project contributor"
```

For an open-source image, use the actual source page and metadata:

```powershell
python scripts/prepare_eval_dataset.py `
  --source-type open_source `
  --license CC-BY-4.0 `
  --source "Creator name, original image" `
  --source-url "https://example.org/original-image" `
  --attribution-requirements "Credit creator and link the license." `
  --download-date 2026-11-02
```

All variants derived from one original must stay in the same split. Otherwise,
the evaluator can compare nearly identical files across training and test
groups and produce an inflated result.

The preparation script deliberately does not fabricate `ai_generated`
examples. Such files must be independently sourced and documented.

## 14. Calibrate forensic thresholds

Calibration is advisory and must use a reviewed, leakage-free validation
split containing authentic and edited examples:

```powershell
python scripts/calibrate_forensics.py
```

The output is `eval\forensic_calibration.json`. It proposes thresholds for
review; it does not change production thresholds automatically. Do not update
production thresholds based only on a small personal folder or derived
examples.

## 15. Optional detector and licensing requirements

The prototype does not require the learned detector. The detector should only
be distributed or enabled after its provenance is verified. Required evidence
includes:

1. original upstream repository or download page;
2. exact immutable commit, release, or model revision;
3. model author or organization;
4. model and dataset license;
5. permission to redistribute the model artifact;
6. download URL and SHA-256 checksum;
7. any required attribution or notice.

If this evidence is unavailable, leave the detector disabled. The
rule-based forensic pipeline remains usable.

## 16. Security, privacy, and data handling

- Do not commit `.env`, API keys, private consent details, or private images.
- Client filenames are not trusted as identifiers.
- Uploads are checked by file signature and bounded by size and dimension
  limits.
- Personal images should remain local and should not be pushed to GitHub.
- `eval_data` and generated real-evaluation outputs are ignored by Git.
- GPS coordinates are not returned in reports.
- Provider keys belong only in an untracked local `.env` or private deployment
  settings.
- Reports and jobs use local SQLite storage during development.

## 17. Troubleshooting

### `ModuleNotFoundError: No module named 'app'`

Confirm that PowerShell is in the repository root:

```powershell
Get-ChildItem app
```

Activate `.venv`, then run commands through `python -m`, for example:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

### `No module named ...` during installation

Upgrade pip and reinstall from the repository root:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

### `Could not read manifest`

Create `eval_data\manifest.json` from the example and verify that every
manifest path is relative to `eval_data`, for example
`authentic\photo_01.jpg`.

### Analysis is slow or stops on a large image

Use the current bounded configuration. Do not remove the byte, pixel, or side
limits. Accepted images are downscaled for analysis to control memory use.

### The learned detector is `not_determined`

This is expected when no verified ONNX model is configured. It is not a
failure of the core prototype.

## 18. Repository structure

```text
app\                         Application and analysis pipeline
app\static\                  Browser interface
tests\                       Automated tests
scripts\                     Evaluation, calibration, and maintenance tools
eval\                        Synthetic manifests and example real-data schema
eval_data\                   Local ignored evaluation images and manifest
docs\                        Methodology, limitations, data, and release notes
requirements.txt             Runtime dependencies
requirements-dev.txt         Runtime plus test/development dependencies
render.yaml                  Optional future Render configuration
```

## 19. Limitations and prototype status

The system provides explainable forensic signals, not legal or scientific
proof. C2PA support is optional, the learned detector is not enabled by
default, audio is not analyzed, and video analysis samples frames rather than
processing every frame continuously.

Independent licensed data, verified detector provenance, hosted deployment,
and manual assistive-technology testing are additional release-quality
activities. They are not required to demonstrate the offline prototype.

See:

- [docs/LIMITATIONS.md](docs/LIMITATIONS.md)
- [docs/METHODOLOGY.md](docs/METHODOLOGY.md)
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)
- [docs/REMAINING_DEVELOPMENT.md](docs/REMAINING_DEVELOPMENT.md)
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)
- [docs/MODEL_CARD.md](docs/MODEL_CARD.md)

## 20. Licences and credits

Application code is available under the repository's selected open-source
licence. Pillow, NumPy, OpenCV, imagehash, piexif, FastAPI, SQLAlchemy, and
other dependencies retain their respective upstream licences. No third-party
dataset or verified detector weights are bundled.

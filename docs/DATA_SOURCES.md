# Data Sources

No external dataset or detector weights are bundled in this initial scaffold. The optional Render, Gemini, Groq, and Hugging Face services must be checked against their current pricing and licence pages before a public submission. Never place a provider key in `.env.example`, source code, Git history, screenshots, or issue text; configure it only as a private Render environment variable or in an untracked local `.env`.

C2PA inspection uses the optional official `c2pa-python` binding when installed; the offline baseline reports capability as unavailable rather than guessing that a file has no provenance. Detector calibration requires a licensed held-out dataset and is not enabled without an explicit calibration file.

## Real-data evaluation

Real images are evaluated only through a manifest; a directory name is not
treated as ground truth. Copy `eval/real_manifest.example.json` to
`eval_data/manifest.json` and fill in every sample's `label`,
`expected_detection`, `source_type`, `license`, `source`, and `split` fields.
Use `expected_detection: false` for an authentic/reference item and `true` for
a verified edited item. Personal and open-source records are reported
separately.

Run:

```powershell
python scripts/evaluate_dataset.py
```

The command writes `eval/real_results.json`. It records hashes, dimensions,
formats, provenance fields, tiers, a confusion matrix, precision, recall, and
per-class results. It fails instead of producing metrics when the manifest is
missing required labels or provenance fields, and records invalid files as
errors without stopping the remaining samples.

Each manifest record must also include `source_url`, `license`,
`attribution_requirements`, `download_date`, and `modification_history`.
Open-source records require an HTTP(S) source URL and ISO date. Personal
records use `source_url: "not_applicable"` and must include a consent record;
do not record a person's name or other sensitive details in the repository.

Large-image policy: hard upload limits remain enabled for decompression safety.
Accepted images are downscaled only for forensic analysis according to
`ANALYSIS_MAX_SIDE`; original files are still used for validation and
provenance context.

## Creating derived categories

To create reproducible `recompressed`, `forwarded`, `spliced`, and
`copy_moved` examples from the authentic folder:

```powershell
python scripts/prepare_eval_dataset.py `
  --source-type personal `
  --license private-consented `
  --source "captured by project contributor"
```

For an open-source source, provide its actual page and download date:

```powershell
python scripts/prepare_eval_dataset.py `
  --source-type open_source `
  --license CC-BY-4.0 `
  --source "Creator name, original image" `
  --source-url "https://example.org/original-image" `
  --attribution-requirements "Credit creator and link the license." `
  --download-date 2026-11-02
```

The script creates the category directories and updates
`eval_data/manifest.json`. It deliberately leaves `ai_generated` empty:
AI-generated files must come from an independently documented source and must
not be fabricated by a preprocessing script.

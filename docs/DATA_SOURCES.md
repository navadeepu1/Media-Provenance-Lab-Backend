# Data Sources

No external dataset or detector weights are bundled in this initial scaffold. The optional Render, Gemini, Groq, and Hugging Face services must be checked against their current pricing and licence pages before a public submission. Never place a provider key in `.env.example`, source code, Git history, screenshots, or issue text; configure it only as a private Render environment variable or in an untracked local `.env`.

C2PA inspection uses the optional official `c2pa-python` binding when installed; the offline baseline reports capability as unavailable rather than guessing that a file has no provenance. Detector calibration requires a licensed held-out dataset and is not enabled without an explicit calibration file.

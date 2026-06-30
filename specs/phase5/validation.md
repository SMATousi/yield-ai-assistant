# Phase 5 — Hardening & Deployment: Validation

## Gate Criterion (from Roadmap)

> The system is reliable enough for MU Extension field use, with audit artifacts that allow agronomists to review AI outputs before trusting recommendations.

---

## Checklist

### Validation mode — offline unit tests

- [ ] `from src.app.validation import ValidationWriter, make_validation_writer` imports without error and without side effects.
- [ ] `make_validation_writer(validate=False)` returns `None`.
- [ ] `make_validation_writer(validate=True, root=<tmpdir>)` returns a `ValidationWriter` and creates the session directory.
- [ ] After `writer.write_turn(turn=1, ...)`:
  - `<session_dir>/001/query.txt` exists and contains the raw query string.
  - `<session_dir>/001/response.txt` exists and contains the response text.
  - `<session_dir>/001/conversation.json` is valid JSON and contains the `raw_messages` list.
  - `<session_dir>/001/recommendation.html` exists when `figures` dict contains `"generate_recommendation_plot"`.
  - `<session_dir>/001/doy_response.html` exists when `figures` dict contains `"generate_doy_response_plot"`.
  - `<session_dir>/index.html` exists and contains the query text from turn 1.
- [ ] `write_turn` with a non-serialisable value in `raw_messages` does not raise (the `default=str` fallback handles it).
- [ ] A second `write_turn(turn=2, ...)` appends a second row to `index.html` without losing turn 1's row.

### Validation mode — app integration

- [ ] `python src/app/app.py --validate` starts the app and prints a path under `./validation_runs/` to the sidebar.
- [ ] After submitting a query with `--validate` active, the session directory contains `001/query.txt` with the user's raw query (not the augmented version).
- [ ] `_handle_query` does not propagate `ValidationWriter` exceptions to the Gradio UI — a monkeypatched `write_turn` that raises still results in a normal chatbot response.
- [ ] `python src/app/app.py` (without `--validate`) runs normally; no `validation_runs/` directory is created.

### Spend tracking — offline unit tests

- [ ] `from src.app.spend import record_and_check` imports without error.
- [ ] `record_and_check(1000, 500, "anthropic/claude-sonnet-4-6", spend_file, 5.0)` returns `(cost_usd, False)` where `cost_usd > 0`.
- [ ] Calling `record_and_check` a second time on the same file accumulates the cost.
- [ ] When accumulated cost exceeds `daily_cap_usd`, the second return value is `True`.
- [ ] Local model strings (e.g. `"ollama/qwen2.5:14b"`) return `cost_usd == 0.0` and `over_cap == False`.

### Error handling

- [ ] Submitting an unrecognisable location string (e.g. `"xyz_notaplace_999"`) results in a chatbot message containing `"could not locate"`, not a traceback.
- [ ] Submitting a valid location with no data for the requested DOY/moisture results in a descriptive chatbot message, not an empty figure panel or crash.
- [ ] Setting `YIELD_LLM_TIMEOUT=1` and submitting a query against a slow model results in an `AgentError` shown in the chatbot within ~2 seconds.

### Operational logging

- [ ] Each completed query prints exactly one JSON line to stdout containing keys: `ts`, `query`, `site`, `plot_types`, `model`, `latency_s`.
- [ ] With `--validate`, the JSON line also contains `"validate": true` and `"validate_dir"`.
- [ ] `latency_s` is a float, not a string.

### Smoke script

- [ ] `python scripts/smoke_phase5.py` runs to completion and prints `"Phase 5 smoke OK."`.
- [ ] The smoke script creates `001/recommendation.html` and `index.html` in the temp directory.

### Dockerfile

- [ ] `docker build -t yield-ai .` completes without error.
- [ ] `docker run -p 7860:7860 -v $(pwd)/validation_runs:/validation_runs -e YIELD_VALIDATE_DIR=/validation_runs yield-ai python src/app/app.py --validate` starts the app and writes artifacts to the mounted volume.

### index.html review workflow

- [ ] Opening `<session_dir>/index.html` in a browser (via `file://`) shows a table with one row per completed turn.
- [ ] Each row's figure links open the corresponding `doy_response.html` or `recommendation.html` in a new tab.
- [ ] Figure link cells are visually distinct (greyed out or dashed) for turns where the figure was not generated.
- [ ] The index renders correctly with no internet connection (no CDN dependencies).

---

## How to Run Validation

```bash
# Offline unit tests
conda run -n yield-ai pytest tests/test_phase5.py -v

# Smoke test (no LLM, no network)
conda run -n yield-ai python scripts/smoke_phase5.py

# Launch in validation mode
conda run -n yield-ai python src/app/app.py --validate

# Launch with explicit output directory
YIELD_VALIDATE_DIR=/tmp/yield-review \
conda run -n yield-ai python src/app/app.py --validate

# Docker with mounted validation output
docker run -p 7860:7860 \
  -e YIELD_LLM_MODEL=anthropic/claude-sonnet-4-6 \
  -e ANTHROPIC_API_KEY=sk-... \
  -v "$(pwd)/data:/data" \
  -v "$(pwd)/validation_runs:/validation_runs" \
  -e YIELD_VALIDATE_DIR=/validation_runs \
  yield-ai python src/app/app.py --validate
```

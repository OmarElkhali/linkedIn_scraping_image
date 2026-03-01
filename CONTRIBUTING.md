# Contributing

Thanks for your interest in contributing to Alumni OSINT Recon Pipeline.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements-phase1.txt
pip install pytest
```

## Branch and PR flow

1. Fork repository
2. Create feature branch: `feat/<short-name>`
3. Add tests for behavior changes
4. Run checks locally
5. Open Pull Request to `main`

## Local validation

```bash
python -m py_compile core/alumni_osint_pipeline.py run_phase1_pipeline.py
pytest -q
```

## Commit style

Prefer conventional commits:
- `feat: ...`
- `fix: ...`
- `docs: ...`
- `chore: ...`

## Scope guardrails

- Keep Phase 1 focused on scraping/data collection.
- Do not commit secrets (`LI_AT`, personal tokens, private datasets).
- Respect legal/compliance constraints documented in README.

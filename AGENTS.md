# Agent Instructions

Read `docs/AI_NOTES.md` before making project-level changes.

## Core Rules

- Keep Fugle API access server-side.
- Never expose Fugle keys in frontend code.
- Never commit `backend/.env.local` or API keys.
- Preserve Gemini streaming behavior unless intentionally changing AI UX.
- Prefer Chinese user-facing error messages where the existing UI uses Chinese.
- Keep changes scoped and avoid unrelated refactors.

## Workflow

1. Inspect relevant files before editing.
2. Follow nearby frontend/backend patterns.
3. Make the smallest useful change.
4. Add or update tests when behavior changes.
5. Run targeted validation when possible.
6. Summarize changed files, tests run, and any deployment impact.

## Validation

For backend changes, prefer:

`cd backend && pytest`

For frontend changes, inspect `frontend/package.json`, then run the most relevant test or build command.

For deployment changes, inspect:

- `cloudbuild.yaml`
- `Dockerfile`
- `docs/AI_NOTES.md`

## Commit Messages

Use Conventional Commit style:

- `feat: ...`
- `fix: ...`
- `test: ...`
- `docs: ...`
- `ci: ...`
- `chore: ...`
- `refactor: ...`

Prefer clear messages like:

- `docs: add AI project notes`
- `ci: update Cloud Run deployment config`
- `fix: handle Fugle API errors`
- `test: add stock list coverage`

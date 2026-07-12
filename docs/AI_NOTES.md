# Stock Research AI Notes

## Project Shape
- Frontend is Vue 3 + Vite in `frontend/`.
- Backend is FastAPI in `backend/`.
- The app is deployed as one Docker image to Cloud Run.
- `cloudbuild.yaml` builds the Docker image, pushes it to Artifact Registry, then deploys Cloud Run.

## Deployment
- Cloud Build trigger: `stock-research-main`
- Trigger region: `asia-east1`
- GCP project: `stock-project-495908`
- GitHub repo: `carali527/stock-research`
- Trigger currently fires on any branch push via `branch: .*`.
- Consider changing trigger branch pattern to `^main$` if only main should deploy.
- Manual deploy:
  `gcloud builds submit --config cloudbuild.yaml`

## Secrets
- Never commit `backend/.env.local`.
- `FUGLE_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY`, and demo token settings belong in local env or Cloud Run env vars/secrets.
- Frontend should not directly hold Fugle secrets; Fugle calls should go through backend.

## Development
- Backend app entrypoint: `backend/main.py`.
- Backend tests are in `backend/tests/`.
- Frontend source is in `frontend/src/`.
- Frontend tests are colocated under `frontend/src/**/*.test.ts` and e2e under `frontend/e2e/`.

## Commands
- Backend tests:
  `cd backend && pytest`
- Frontend install:
  `cd frontend && npm install`
- Frontend build:
  `cd frontend && npm run build`
- Local backend:
  `cd backend && uvicorn main:app --reload`
- Local frontend:
  `cd frontend && npm run dev`

## Product Rules
- This is a Taiwan stock research app.
- Keep Fugle market data access server-side.
- Keep Gemini analysis streaming behavior stable unless intentionally changing AI UX.
- Prefer user-facing error messages in Chinese where the existing UI already uses Chinese.

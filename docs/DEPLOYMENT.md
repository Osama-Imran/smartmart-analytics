# Deployment guide

## Stage 1: GitHub + Streamlit Community Cloud (no separate database)

1. **Create the repo.** On github.com create a new **public** repository (e.g. `smartmart-analytics`). Streamlit Community Cloud deploys from GitHub, and public repos are the simple path on the free plan.
2. **Push the project** from the project folder:
   ```bash
   git init
   git add .
   git commit -m "SmartMart analytics: Stage 1"
   git branch -M main
   git remote add origin https://github.com/<your-username>/smartmart-analytics.git
   git push -u origin main
   ```
   `data/smartmart.db` is committed on purpose, so the deployed app needs no build step.
3. **Deploy.** Go to share.streamlit.io, sign in with GitHub, choose **Create app**, pick the repo, branch `main`, main file `app.py`, then **Deploy**.
4. **Verify the public URL.** Open the `*.streamlit.app` link in a private window and check: KPI cards load, filters change the numbers, the downloads work, and the "Data quality & export" tab shows the cleaning report.
5. **Check CI.** The Actions tab on GitHub should show the `CI` workflow passing.

Updating the app later: push to `main` and Streamlit redeploys automatically.

## Stage 2: move the data to Supabase Postgres

1. Create a free project at supabase.com and set a database password.
2. In the dashboard open **Connect** and copy the **pooler** connection string. Streamlit Cloud connects over IPv4, and Supabase's direct connection is IPv6 only, so use the pooler string.
3. Load the data from your laptop (the same cleaned CSVs and the same views):
   ```bash
   python -m pipeline.build_db --url "postgresql://postgres.<ref>:<password>@<host>:5432/postgres"
   ```
4. Test locally: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, fill in `DATABASE_URL`, run `streamlit run app.py`. The caption under the title should say "cloud PostgreSQL".
5. In Streamlit Community Cloud open **App settings > Secrets** and paste the same `DATABASE_URL = "..."` line. Never commit the real URL.
6. Remove the secret to fall back to the bundled SQLite file at any time.

A free Supabase project pauses after a week without activity (see FREE_TIER_LIMITS.md). If the app shows "A database query failed", open the Supabase dashboard and restore the project.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| "SQLite database not found" | `data/smartmart.db` was not committed. Run `python -m pipeline.run_all`, commit, push. |
| "Could not read the database" | Wrong or missing `DATABASE_URL`, or the cloud project is paused. |
| App shows a sleeping page | Streamlit sleeps idle apps. Click the wake-up button. |
| Package install fails on deploy | Check `requirements.txt` is in the repo root. |

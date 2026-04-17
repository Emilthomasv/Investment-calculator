# Investment Calculator

A Streamlit-based wealth dashboard for projecting investments, planned expenses, safety funds, and net future wealth over time.

## Features

- Project future value for fixed deposits, stocks, mutual funds, and step-up SIPs
- Add future one-time expenses by year
- Track emergency fund and insurance corpus
- View yearly snapshots and charts
- Support local single-user mode with `profiles.json`
- Support hosted multi-user mode with Google sign-in, guest access, and Supabase-backed private profiles

## Tech Stack

- Python
- Streamlit
- Pandas
- Matplotlib
- Supabase Postgres
- psycopg

## Project Files

- `Calculator.py` - main Streamlit app
- `profiles.json` - local profile storage and import seed
- `requirements.txt` - Python dependencies
- `sql/user_profiles.sql` - Supabase schema for hosted profile storage
- `.streamlit/secrets.toml.example` - example auth and database secrets

## Run Locally

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
streamlit run Calculator.py
```

4. Open the local URL shown in the terminal, usually:

```text
http://localhost:8501
```

If you do nothing else, the app runs in local single-user mode and stores profiles in `profiles.json`.

## Modes

### Local Mode

- No auth secrets and no `SUPABASE_DB_URL`
- Save, load, and delete profiles from `profiles.json`
- Best for personal/local use

### Hosted Cloud Mode

- Streamlit OIDC auth configured
- `SUPABASE_DB_URL` configured
- Guests can use the calculator but cannot save profiles
- Signed-in users can save, load, overwrite, and delete only their own profiles
- Signed-in users can import local seed profiles from `profiles.json`

## Streamlit Cloud Setup

### 1. Google OIDC

Configure your Google OAuth client so the redirect URI matches your deployed app:

```text
https://<your-app>.streamlit.app/oauth2callback
```

For local development, the example file uses:

```text
http://localhost:8501/oauth2callback
```

### 2. Supabase Database

Run the schema in:

```text
sql/user_profiles.sql
```

This creates the `public.user_profiles` table used by the app, enables Row-Level
Security, and revokes access from Supabase's browser-facing `anon` and
`authenticated` roles. The SQL targets the existing `public` schema, so it works
with Supabase roles that can create tables but cannot create schemas.

If you already deployed an earlier version of the app, rerun this SQL once or
restart the app with a `SUPABASE_DB_URL` user that can alter the table so the
existing table is hardened too.

### 3. Streamlit Secrets

Add secrets in Streamlit Community Cloud using `.streamlit/secrets.toml.example` as your template.

Required values:

- Streamlit `[auth]` settings
- Google provider credentials under `[auth.google]`
- `SUPABASE_DB_URL`

## How Profiles Work

### Local mode

- Profiles save to `profiles.json`

### Cloud mode

- Guests cannot save or load profiles
- Signed-in users only see profiles stored for their own login identity
- Saving with the same profile name overwrites only that user's version
- `Import local profiles` upserts the bundled `profiles.json` entries into the signed-in user's account
- Direct public access to `public.user_profiles` through the Supabase project URL is blocked by RLS

## Deployment

1. Push this project to GitHub.
2. Make sure `requirements.txt` is committed.
3. Add your Streamlit secrets in Community Cloud.
4. Deploy `Calculator.py` as the app entrypoint.

## Dependencies

- `streamlit==1.55.0`
- `pandas==2.3.3`
- `matplotlib==3.10.8`
- `psycopg[binary]>=3.2,<4`

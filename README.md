# Investment Calculator

A Streamlit-based personal wealth dashboard for projecting investments, planned expenses, safety funds, and net future wealth over time.

## Features

- Project future value for:
  - Fixed Deposits
  - Stocks
  - Mutual Funds
  - Step-up SIPs
- Add future one-time expenses by year
- Include emergency fund and insurance corpus
- View yearly wealth snapshots and charts
- Save, load, and delete named profiles

## Tech Stack

- Python
- Streamlit
- Pandas
- Matplotlib

## Project Files

- `Calculator.py` - main Streamlit app
- `profiles.json` - local profile storage
- `requirements.txt` - Python dependencies

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

## How Profiles Work

- Enter values in the dashboard.
- Type a profile name in `Profile name to save`.
- Click `Save profile` to store the current inputs.
- Select a saved profile from `Load saved profile` and click `Load profile`.
- Click `Delete profile` to remove a saved profile after confirmation.

Profiles are stored in `profiles.json` when running locally.

## Deployment

This app can be deployed easily on Streamlit Community Cloud.

### Deploy Steps

1. Push this project to GitHub.
2. Make sure `requirements.txt` is included in the repo.
3. In Streamlit Community Cloud, create a new app from the repo.
4. Set the main file path to:

```text
Calculator.py
```

## Important Note About Online Profile Storage

`profiles.json` is fine for local use, but it is not reliable persistent storage for a hosted app.

On Streamlit Cloud:

- the file is stored in the app's temporary filesystem
- it can be reset during redeploys or restarts
- all users share the same file
- saved profiles are not guaranteed to persist long term

For production-style hosting, move profile data to a persistent backend such as:

- Supabase
- Firebase
- Google Sheets
- PostgreSQL

## Dependencies

Current versions in `requirements.txt`:

- `streamlit==1.55.0`
- `pandas==2.3.3`
- `matplotlib==3.10.8`

## Future Improvements

- Persistent cloud profile storage
- Authentication per user
- Export reports to CSV or PDF
- Better mobile layout and styling


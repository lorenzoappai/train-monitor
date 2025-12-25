# Train Monitor

Automated monitoring system for Swiss (SBB) and Italian (Trenitalia) train departures. Tracks delays, platform changes, and effective departure times, logging them to a Google Sheet.

## Features
- **Multi-Provider Support**: Switch between Swiss (`swiss`) and Italian (`italy`) train providers.
- **Rich Data**: Captures planned vs. effective times, gate changes, and cancellation status.
- **Resilient**: Implements retry logic and error handling for API reliability.
- **Automated**: Designed to run via GitHub Actions on a schedule.

## Setup

### 1. Prerequisites
- Python 3.9+
- `pip`

### 2. Installation
```bash
pip install -r requirements.txt
```

### 3. Google Sheets Backend (Google Apps Script)
1. Create a new Google Sheet.
2. Extensions > Apps Script.
3. Paste the contents of `Code.gs`.
4. Deploy -> New Deployment -> Select "Web app".
   - Execute as: *Me*
   - Who has access: *Anyone* (required for GitHub Actions to POST data)
5. Copy the **Web App URL**.

## Usage

### Dry Run (Local Testing)
To verify the script locally without sending data to Google Sheets (Safe Mode):
```bash
# Defaults to Swiss provider searching for "Zurich HB"
python main.py
```
*The script will log fetched data to the console but warn that `DATA_ENDPOINT` is not set.*

To test the Italian provider locally:
```bash
# Windows (PowerShell)
$env:TRAIN_PROVIDER="italy"; $env:STATION_NAME="Roma Termini"; python main.py
```

### Production Run
Set the environment variables:
- `DATA_ENDPOINT`: The Web App URL from step 3.
- `TRAIN_PROVIDER`: `swiss` (default) or `italy`.
- `STATION_NAME`: Target station (e.g., "Bern", "Milano Centrale").

## GitHub Actions
The repository includes a workflow `.github/workflows/main.yml` that runs every 15 minutes.
**Secrets Required:**
- `DATA_ENDPOINT`

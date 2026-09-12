# PM Performance Dashboard

Streamlit dashboard for analysing the existing **StayPlease PM Task Report** Excel export.

## Main principle

The dashboard works with the current Excel structure.  
It does **not** require modification of the StayPlease source data.

## Features

- Executive PM KPI dashboard
- PM completion and backlog analysis
- Equipment group analysis
- Location analysis
- PM plan analysis
- Pass / Fail inspection snapshot
- Data quality checks
- Consolidation of PM task records from multiple Excel sheets
- CSV download of filtered data

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deployment

Push this project to GitHub, then deploy from Streamlit Community Cloud.

## Important data limitations

- Current report uses Create Date, not Scheduled/Due Date.
- True overdue status cannot be independently calculated from task-level data.
- Equipment grouping is automatically inferred from PM/Asset names.
- Blank Pass/Fail values are treated as Not Recorded.

# CME University Trading Challenge: morning pipeline

## Setup (once)
    python -m venv .venv
    source .venv/bin/activate      # Windows: .venv\Scripts\activate
    pip install -r requirements.txt

## Every morning
    python charts.py     # downloads prices, writes report.html, opens it

`python data.py` downloads prices only and prints a text summary.

## Files
- config.yaml: markets and dollar value per point (verify against CME contract specs)
- data.py: price downloader
- charts.py: visual report

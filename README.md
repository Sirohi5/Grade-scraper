# Grades Scraper

This script logs into the UniNow demo website, navigates to the grades overview, extracts the grade table, and saves the results as **JSON or CSV**. It also collects summary statistics (average grade, credits obtained, passed exams).

## Why Python + Selenium?
- Python is fast to develop and has great data tooling.

- Selenium reliably automates pages that render content via JavaScript and require button-driven flows (the demo uses an “Einfaches Login” button and dynamic navigation).

- Used explicit waits and robust selectors(German/English, <button>/<a>) so small UI changes don’t break the scraper.

## Project Structure

grade-scraper/
├── main.py
├── README.md
├── requirements.txt
├── .env # local credentials (not committed)
├── output/
│ ├── grades.csv # CSV output (if run with --format csv)
│ ├── grades.json # JSON output (if run without flag or with --format json)
│ └── (debug *.png/html on failures)
└── venv/ # local virtualenv (excluded from submission)


# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run script (default JSON)
python main.py

# Run script with CSV output
python main.py --format csv

# Scraping Luigi Mangione GiveSendGo
A Python scraper for collecting and updating donation data from the Luigi Mangione Defense Fund on GiveSendGo. The script gathers donor names, amounts, comments, and timestamps, and can be run periodically for incremental updates. Data last scraped on October 21, 2025 at 10:00 PM EST.

# Overview
This tool collects donation information from any GiveSendGo campaign page. It runs in two modes: initial full scrape to get all historical data, and incremental updates to only fetch new donations on subsequent runs.

## Features
- Dual Scraping Modes: Full initial scrape or incremental updates
- Checkpoint System: Resume interrupted sessions without data loss
- Cloudflare Handling: Bypasses anti-bot protection with retry logic
- Duplicate Removal: Automatically filters out duplicate donations
- Process Management: Prevents chromedriver conflicts

## Usage
1. Set your campaign name in the campaign variable
2. Run the script - it automatically detects whether to do full scrape or incremental update
3. Outputs to donations_data folder with:
 - Individual page JSON files
 - Combined CSV file (all_donations.csv)
 - Checkpoint file for resuming

# Attribution
[Appelson](https://github.com/appelson/Scraping_GiveSendGo/)

# Quick Start
```bash
pip install undetected-chromedriver beautifulsoup4 pandas psutil
python scrape_donations.py

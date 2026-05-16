# 🤖 Job Aggregation Agent

An automated job aggregation agent that scrapes job listings from multiple platforms, deduplicates them using fuzzy matching, stores results in CSV files, and sends Slack notifications.

## 🎯 Features

- **Multi-platform scraping**: Naukri.com (India), RemoteOK.com (remote jobs), WellFound.com (startup jobs)
- **Smart deduplication**: Fuzzy matching on job title + company name (85% similarity threshold)
- **CSV storage**: Monthly CSV files with changelog tracking
- **Slack notifications**: Rich formatted summaries after each run
- **Anti-bot measures**: Polite delays, rotating User-Agents, session rotation, proxy support
- **GitHub Actions on-demand**: Run manually via Actions tab whenever you want
- **Configurable**: Job titles, keywords, rate limits, and more via settings.json

## 📋 Requirements

- Python 3.8+
- Pip packages (see `requirements.txt`)
- GitHub repository (for Actions automation)
- Slack webhook URL (optional, for notifications)

## 🚀 Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/raktimneog08-ops/JOB-AGENT.git
cd JOB-AGENT
pip install -r requirements.txt
```

### 2. Configure Settings

Edit `config/settings.json` to customize your search:

```json
{
    "job_titles": ["Senior Frontend Developer", "React Developer", "Full Stack Engineer"],
    "keywords_filter": ["React", "TypeScript", "Node.js"],
    "keywords_priority": ["React", "TypeScript"],
    "max_results_per_platform": 50,
    "polite_delay_min_seconds": 3,
    "polite_delay_max_seconds": 6,
    "dedup_similarity_threshold": 85
}
```

### 3. Run Locally

```bash
# Test run (no Slack notification)
python main.py

# Run with Slack notification
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/xxx/yyy/zzz"
python main.py
```

### 4. Set Up GitHub Actions (run on-demand)

1. Push the code to your GitHub repository
2. Add the Slack webhook as a repository secret:
   - Go to Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `SLACK_WEBHOOK_URL`
   - Value: Your Slack Incoming Webhook URL
3. Go to the **Actions** tab → **Run Job Agent** → **Run workflow** → click the green button
4. That's it! The agent runs immediately and CSV results are available as downloadable artifacts

## 📁 Project Structure

```
job-agent/
├── .github/workflows/
│   └── daily_run.yml          # GitHub Actions workflow
├── config/
│   └── settings.json          # Configuration file
├── scrapers/
│   ├── base_scraper.py        # Base class with common functionality
│   ├── naukri_scraper.py      # Naukri.com scraper
│   ├── remoteok_scraper.py    # RemoteOK.com scraper
│   └── wellfound_scraper.py   # WellFound.com scraper
├── core/
│   ├── job_processor.py       # Deduplication engine
│   ├── storage.py             # CSV read/write operations
│   └── notifier.py            # Slack notification sender
├── utils/
│   ├── logger.py              # Structured logging
│   ├── user_agents.py         # User-Agent rotation
│   └── proxy_rotator.py       # Proxy rotation
├── data/                      # Generated CSV files
├── main.py                    # Entry point
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## 📊 Output Format

CSV files are named `{Month_Year}_Job_Listings.csv` (e.g., `May_2026_Job_Listings.csv`) with columns:

| Column | Description |
|--------|-------------|
| Job Title | Position title |
| Company Name | Employer name |
| Location | Remote/On-site/Hybrid |
| Job URL | Direct link to listing |
| Posted Date | When the job was posted |
| Salary Range | Compensation (if available) |
| Source Platform | Naukri/RemoteOK/WellFound |
| Description Snippet | First 200 characters |
| Date Scraped | When we scraped it |
| Status | New/Applied/Interviewing/Rejected/Offer |
| Run ID | Unique run identifier |

## 🛠️ Configuration Options

### Settings (`config/settings.json`)

| Parameter | Description | Default |
|-----------|-------------|---------|
| `job_titles` | List of job titles to search | See file |
| `keywords_filter` | Words to match in job titles | See file |
| `keywords_priority` | High-priority keywords for scoring | See file |
| `max_results_per_platform` | Max results per platform per run | 50 |
| `polite_delay_min_seconds` | Minimum delay between requests | 3 |
| `polite_delay_max_seconds` | Maximum delay between requests | 6 |
| `dedup_similarity_threshold` | Fuzzy match threshold (0-100) | 85 |
| `csv_output_dir` | Directory for CSV files | "data" |
| `slack_webhook_url_env` | Environment variable for webhook | "SLACK_WEBHOOK_URL" |

## 🔄 GitHub Actions Workflow (Manual Only)

The workflow (`daily_run.yml`) is **triggered manually only** — no automatic schedule:

1. Go to **Actions** tab → **Run Job Agent** → **Run workflow**
2. Installs dependencies
3. Executes the job agent
4. Uploads CSV files as build artifacts (30-day retention)
5. Download results from the run's **Artifacts** section

## ⚠️ Known Limitations

- **Naukri.com**: May block requests due to anti-bot measures. The scraper uses polite delays and session rotation as mitigation. For production use, consider adding ScraperAPI/BrightData.
- **WellFound.com**: Full job descriptions require login. The scraper extracts what's available from the public API.
 - **CAPTCHA / JS rendering**: Some platforms use bot protection (DataDome, Cloudflare, CAPTCHA). This project includes Playwright fallbacks and two options:
     - **Automated solving**: Configure a CAPTCHA solver service (2captcha) via `CAPTCHA_PROVIDER` and `CAPTCHA_API_KEY` environment variables. Solving may cost money and isn't guaranteed for custom challenge flows.
     - **Manual solve**: Set `WELLFOUND_MANUAL_SOLVE=1` to open a headed browser when a challenge is detected. Solve the challenge manually, then press Enter in the terminal to continue the run.
- **Free proxies**: The proxy rotator fetches free proxies which may be unreliable. Use with caution.

## 📝 Status Management

You can update job statuses manually in the CSV file:
- **New**: Freshly scraped, not yet actioned
- **Applied**: You've submitted an application
- **Interviewing**: In the interview process
- **Rejected**: Application was not successful
- **Offer**: Received an offer

## 🤝 Contributing

Feel free to fork, submit PRs, or open issues for improvements.

## 📄 License

MIT
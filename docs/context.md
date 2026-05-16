Great question! Here's exactly how to test everything and start getting job listings:

---

## 1️⃣ First, test locally (recommended to verify it works)

Open **PowerShell** or **Command Prompt** in the `D:\job-agent` folder and run:

```bash
python main.py
```

You'll see live output like this:
```
2026-05-16 15:30:00 | INFO     | 🚀 Job Aggregation Agent Starting
2026-05-16 15:30:00 | INFO     | PHASE 1: Scraping job listings
2026-05-16 15:30:03 | INFO     |   ✓ 'Senior Frontend Developer': 25 results from RemoteOK
2026-05-16 15:30:07 | INFO     |   ✓ 'React Developer': 18 results from RemoteOK
...
2026-05-16 15:32:00 | INFO     | 📊 RUN SUMMARY
2026-05-16 15:32:00 | INFO     |   Duration: 2m 15s
2026-05-16 15:32:00 | INFO     |   CSV file: data\May_2026_Job_Listings.csv
```

After it finishes, check the CSV file:

```bash
# Open the CSV in Notepad or Excel
notepad data\May_2026_Job_Listings.csv
```

Or open it in Excel by double-clicking the file in the `data/` folder.

---

## 2️⃣ Get the job listings

All jobs are stored in **`data/May_2026_Job_Listings.csv`** (filename changes each month). Open it in Excel and you'll see columns:

| Job Title | Company | Location | Job URL | Posted Date | Salary Range | Source Platform | Status |
|-----------|---------|----------|---------|-------------|-------------|----------------|--------|
| Senior React Developer | Google | Remote | https://... | 2 days ago | $150k-$200k | RemoteOK | New |
| ... | ... | ... | ... | ... | ... | ... | ... |

You can update the **Status** column manually (New → Applied → Interviewing → Rejected → Offer).

---

## 3️⃣ Automated daily runs via GitHub Actions

Once you've tested locally, the daily schedule will run automatically. To **manually trigger** it right now:

1. Go to https://github.com/raktimneog08-ops/JOB-AGENT
2. Click the **Actions** tab
3. Click **Daily Job Agent Run** in the left sidebar
4. Click the **Run workflow** button (right side)
5. Select **master** branch and click **Run workflow**

You'll see the run in progress. After it completes (~3-5 minutes):
- ✅ **Slack notification** will post to `#all-job-agents`
- ✅ **CSV file** will be committed to the repo
- ✅ **Build artifacts** will be available for download (click on the run → Artifacts section)

### How to know it's working:
| Signal | What to check |
|--------|---------------|
| ✅ Local run succeeds | `python main.py` completes with no errors |
| ✅ CSV created | `data/May_2026_Job_Listings.csv` has data |
| ✅ GitHub Actions passes | Green checkmark in Actions tab |
| ✅ Slack notification | Message appears in `#all-job-agents` |
| ✅ CSV auto-committed | New commit appears in repo with "Auto-update job listings" message |

---

## 4️⃣ Customize job titles

If you want to search for different roles, edit `config/settings.json`:

```json
{
    "job_titles": ["React Developer", "Full Stack Engineer", "Frontend Engineer"],
    "keywords_priority": ["React", "TypeScript"],
    "max_results_per_platform": 50
}
```

Save the file, push to GitHub, and the next run will use your new settings!

---

**Bottom line**: Run `python main.py` locally first. If it works, the GitHub Actions schedule will handle automatic daily runs from tomorrow at 11:30 AM IST. 🚀
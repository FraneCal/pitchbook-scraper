## 📦 Install Requirements

Before running the scraper, make sure to install the required dependencies:

```bash
cd pitchbook_scraper
pip install -r requirements.txt
```

---

## 🚀 Starting the Scraper

```bash
# Navigate to the scraper directory
cd pitchbook_scraper

# Start the scraper in the background using nohup
# Output is redirected to monitor.log, and the process ID is saved
nohup ./run_scraper.sh monitor > monitor.log 2>&1 &
echo $! > nohup_runner.pid
```

---

## 🛑 Stopping the Scraper

```bash
# If the PID file exists, kill the process and remove the PID file
if [ -f pitchbook_scraper/nohup_runner.pid ]; then
    kill $(cat pitchbook_scraper/nohup_runner.pid) 2>/dev/null
    rm pitchbook_scraper/nohup_runner.pid
fi

# Kill any remaining scraper-related processes
pkill -f run_scraper.sh
pkill -f scraper.py
```

---

## ▶️ Running Additional Scripts

```bash
# Run the low-rated companies visitor script in the background
nohup python3 visit_low_rated_companies.py > monitor.log 2>&1 &

# Run a RAM usage monitor in the background
nohup ./monitor_and_stop.sh monitor > ram_monitor.log 2>&1 &
```


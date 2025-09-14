#!/bin/bash

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRAPER_SCRIPT="$SCRIPT_DIR/scraper.py"
VENV_PATH="$SCRIPT_DIR/.venv"
LOG_FILE="$SCRIPT_DIR/scraper.log"
URL_LIST_FILE="$SCRIPT_DIR/url_list.json"
SCRAPED_LINKS_FILE="$SCRIPT_DIR/scraped_links.json"
PID_FILE="$SCRIPT_DIR/scraper.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to log messages
log_message() {
    echo -e "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Function to check if scraper is running
is_scraper_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0  # Running
        else
            rm -f "$PID_FILE"
        fi
    fi
    return 1  # Not running
}

# Function to count total URLs
count_total_urls() {
    if [ -f "$URL_LIST_FILE" ]; then
        python3 -c "import json; print(len(json.load(open('$URL_LIST_FILE'))))" 2>/dev/null || echo "0"
    else
        echo "0"
    fi
}

# Function to count scraped URLs
count_scraped_urls() {
    if [ -f "$SCRAPED_LINKS_FILE" ]; then
        python3 -c "import json; print(len(json.load(open('$SCRAPED_LINKS_FILE'))))" 2>/dev/null || echo "0"
    else
        echo "0"
    fi
}

# Function to check if scraping is complete
is_scraping_complete() {
    local total=$(count_total_urls)
    local scraped=$(count_scraped_urls)
    
    if [ "$total" -gt 0 ] && [ "$scraped" -ge "$total" ]; then
        return 0  # Complete
    else
        return 1  # Not complete
    fi
}

# Function to start scraper
start_scraper() {
    log_message "${GREEN}Starting scraper...${NC}"
    
    # Activate virtual environment
    if [ -d "$VENV_PATH" ]; then
        source "$VENV_PATH/bin/activate"
        log_message "Virtual environment activated"
    else
        log_message "${RED}Virtual environment not found at $VENV_PATH${NC}"
        return 1
    fi
    
    # Check if required files exist
    if [ ! -f "$SCRAPER_SCRIPT" ]; then
        log_message "${RED}Scraper script not found: $SCRAPER_SCRIPT${NC}"
        return 1
    fi
    
    if [ ! -f "$URL_LIST_FILE" ]; then
        log_message "${RED}URL list file not found: $URL_LIST_FILE${NC}"
        return 1
    fi
    
    # Start scraper in background
    nohup python3 "$SCRAPER_SCRIPT" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    
    log_message "Scraper started with PID: $pid"
    return 0
}

# Function to stop scraper
stop_scraper() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            log_message "${YELLOW}Stopping scraper (PID: $pid)...${NC}"
            kill "$pid"
            sleep 2
            if ps -p "$pid" > /dev/null 2>&1; then
                log_message "${YELLOW}Force killing scraper...${NC}"
                kill -9 "$pid"
            fi
        fi
        rm -f "$PID_FILE"
    fi
}

# Function to show status
show_status() {
    local total=$(count_total_urls)
    local scraped=$(count_scraped_urls)
    local remaining=$((total - scraped))
    
    if is_scraper_running; then
        local pid=$(cat "$PID_FILE")
        echo -e "${GREEN}✓${NC} Running (PID: $pid) | URLs: $scraped/$total | Remaining: $remaining"
    else
        echo -e "${RED}✗${NC} Not running | URLs: $scraped/$total | Remaining: $remaining"
    fi
}

# Main monitoring loop
main() {
    echo "Scraper Monitor Started"
    echo "======================"
    
    # Handle signals
    trap 'echo -e "\n${YELLOW}Stopping scraper...${NC}"; stop_scraper; exit 0' INT TERM
    
    while true; do
        show_status
        
        # Check if scraping is complete
        if is_scraping_complete; then
            echo -e "\n${GREEN}✓ All URLs scraped! Stopping monitor.${NC}"
            stop_scraper
            break
        fi
        
        # Check if scraper is running
        if ! is_scraper_running; then
            echo -e "\n${YELLOW}Starting scraper...${NC}"
            if start_scraper; then
                echo -e "${GREEN}✓ Started${NC}"
            else
                echo -e "${RED}✗ Failed to start${NC}"
                sleep 60
            fi
        fi
        
        # Wait before next check
        sleep 30
    done
    
    echo "Monitor stopped"
}

# Handle command line arguments
case "${1:-monitor}" in
    "start")
        if is_scraper_running; then
            log_message "${YELLOW}Scraper is already running${NC}"
        else
            start_scraper
        fi
        ;;
    "stop")
        stop_scraper
        log_message "Scraper stopped"
        ;;
    "status")
        show_status
        ;;
    "monitor")
        main
        ;;
    *)
        echo "Usage: $0 {start|stop|status|monitor}"
        echo "  start   - Start the scraper"
        echo "  stop    - Stop the scraper"
        echo "  status  - Show current status"
        echo "  monitor - Run monitoring loop (default)"
        exit 1
        ;;
esac 
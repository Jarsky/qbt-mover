# qbt-mover Python Script

import os
import json
import subprocess
import time
from datetime import datetime

# Load configuration from a separate file
import configparser

config = configparser.ConfigParser()
config.read('/app/config/config.ini')

# Configuration Variables
LOG_FILE = config.get('settings', 'log_file')
REMOTE_HOST = config.get('settings', 'remote_host')
SLEEP_DURATION = config.getint('settings', 'sleep_duration')
COUNT_MAX = config.getint('settings', 'count_max')
LOG_LINE_TAIL = config.getint('settings', 'log_line_tail')
STATES = json.loads(config.get('settings', 'states'))
JSON_FILENAME = config.get('settings', 'json_filename')
PAUSED_TORRENTS_FILE = config.get('settings', 'paused_torrents_file', fallback='paused_torrents.json')

# Path to the qbt config file (ludviglundgren/qbittorrent-cli)
QBT_CONFIG = os.path.expanduser("~/.config/qbt/.qbt.toml")

# Utility Functions
SCRIPT_NAME = "qbt-mover"
SCRIPT_VERSION = "1.3.0"

def date_format():
    return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

def log_message(level, message):
    prefix = f"{SCRIPT_NAME} {SCRIPT_VERSION}"
    log_line = f"{date_format()} {prefix} {level} {message}"
    with open(LOG_FILE, 'a') as log:
        log.write(log_line + "\n")
    print(log_line, flush=True)

def check_log_file():
    if not os.access(LOG_FILE, os.W_OK):
        log_message("[ERROR]", f"{LOG_FILE} is not writable.")
        exit(1)

def check_jq():
    if subprocess.call("command -v jq", shell=True) != 0:
        log_message("[ERROR]", "jq is not installed. Please install jq.")
        exit(1)

def check_settings():
    check_log_file()
    check_jq()

def save_paused_torrents(paused_torrents):
    """Save the list of paused torrents with their original states to a JSON file"""
    with open(PAUSED_TORRENTS_FILE, 'w') as f:
        json.dump(paused_torrents, f, indent=2)
    log_message("[INFO]", f"Saved {len(paused_torrents)} paused torrents with original states to {PAUSED_TORRENTS_FILE}")

def load_paused_torrents():
    """Load the list of paused torrents with their original states from JSON file"""
    if not os.path.exists(PAUSED_TORRENTS_FILE):
        return []
    try:
        with open(PAUSED_TORRENTS_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        log_message("[WARN]", f"Could not load {PAUSED_TORRENTS_FILE}, returning empty list")
        return []

def clear_paused_torrents_file():
    """Remove the paused torrents tracking file"""
    if os.path.exists(PAUSED_TORRENTS_FILE):
        os.remove(PAUSED_TORRENTS_FILE)
        log_message("[INFO]", f"Removed {PAUSED_TORRENTS_FILE}")

def get_torrent_state(hash_value):
    """Get the current state of a specific torrent"""
    try:
        # Export current torrent list
        result = subprocess.run([
            "qbt", "torrent", "list",
            "--output", "json",
            "--config", QBT_CONFIG
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            log_message("[ERROR]", f"qbt torrent list failed: {result.stderr.decode().strip()}")
            return 'unknown'
        torrents = json.loads(result.stdout.decode())
        for torrent in torrents:
            if torrent.get('hash') == hash_value:
                return torrent.get('state', 'unknown')
        return 'unknown'
    except Exception as e:
        log_message("[ERROR]", f"Error getting torrent state for {hash_value[:5]}: {str(e)}")
        return 'unknown'

def summarize_torrents(torrents):
    from collections import Counter
    state_counts = Counter(t.get('state', 'unknown') for t in torrents)
    summary = ", ".join(f"{count} {state}" for state, count in sorted(state_counts.items(), key=lambda x: x[0]))
    return summary, state_counts

def check_ssh_connection():
    """Check if SSH connection to UnRAID host is possible."""
    try:
        result = subprocess.run(["ssh", REMOTE_HOST, "echo connected"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        if result.returncode == 0 and b"connected" in result.stdout:
            return True
        else:
            log_message("[ERROR]", f"Failed to connect to UnRAID via SSH: {result.stderr.decode().strip()}")
            return False
    except Exception as e:
        log_message("[ERROR]", f"SSH connection check failed: {str(e)}")
        return False

# Main Functions

def pause_torrents():
    """Pause torrents with specific states and track their original states"""
    check_settings()
    if not check_ssh_connection():
        log_message("[ERROR]", "Skipping mover start due to SSH connection failure.")
        return
    log_message("[INFO]", f"Starting pause operation.")
    # Get all torrents as JSON
    result = subprocess.run([
        "qbt", "torrent", "list",
        "--output", "json",
        "--config", QBT_CONFIG
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        log_message("[ERROR]", f"qbt torrent list failed: {result.stderr.decode().strip()}")
        return
    try:
        torrents = json.loads(result.stdout.decode())
    except Exception as e:
        log_message("[ERROR]", f"Failed to parse qbt torrent list output: {str(e)}")
        return
    summary, _ = summarize_torrents(torrents)
    log_message("[INFO]", f"Torrent status summary before pausing: {summary}")
    paused_torrents = []
    status_paused = {}
    hashes_to_pause = []
    for torrent in torrents:
        if torrent.get('state') in STATES:
            state = torrent.get('state')
            torrent_info = {
                'hash': torrent.get('hash'),
                'name': torrent.get('name'),
                'original_state': state,
                'paused_at': datetime.now().isoformat(),
                'size': torrent.get('size', 0),
                'progress': torrent.get('progress', 0)
            }
            paused_torrents.append(torrent_info)
            status_paused[state] = status_paused.get(state, 0) + 1
            hashes_to_pause.append(torrent['hash'])
    # Pause all relevant torrents in one call
    if hashes_to_pause:
        subprocess.run([
            "qbt", "torrent", "pause",
            "--hashes", ",".join(hashes_to_pause),
            "--config", QBT_CONFIG
        ])
        for torrent in paused_torrents:
            log_message("[INFO]", f"Torrent Paused: {torrent['name']} :: Hash: {torrent['hash'][:5]} :: Original State: {torrent['original_state']}")
        save_paused_torrents(paused_torrents)
        summary_paused = ", ".join(f"{count} {state}" for state, count in status_paused.items())
        log_message("[INFO]", f"Paused {len(paused_torrents)} torrents: {summary_paused}")
    else:
        log_message("[INFO]", "No torrents needed to be paused.")
    # Start the mover at the end of pause (in background)
    log_message("[INFO]", "Invoking mover function for UnRAID (starting mover via SSH in background)...")
    mover_start = subprocess.run(f"ssh {REMOTE_HOST} 'nohup mover start >/dev/null 2>&1 &'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if mover_start.returncode == 0:
        log_message("[INFO]", "Mover started in background on UnRAID.")
    else:
        log_message("[ERROR]", f"Failed to start mover: {mover_start.stderr.decode().strip()}")

def resume_paused_torrents():
    """Resume torrents to their original states"""
    check_settings()
    log_message("[INFO]", f"Starting resume operation.")
    paused_torrents = load_paused_torrents()
    if not paused_torrents:
        log_message("[INFO]", "No paused torrents found to resume")
        return
    status_resumed = {}
    hashes_to_resume = []
    for torrent in paused_torrents:
        state = torrent.get('original_state', 'unknown')
        status_resumed[state] = status_resumed.get(state, 0) + 1
        hashes_to_resume.append(torrent['hash'])
    log_message("[INFO]", f"Will attempt to resume {len(paused_torrents)} torrents: {', '.join(f'{count} {state}' for state, count in status_resumed.items())}")
    if hashes_to_resume:
        subprocess.run([
            "qbt", "torrent", "resume",
            "--hashes", ",".join(hashes_to_resume),
            "--config", QBT_CONFIG
        ])
        resumed_count = 0
        for torrent in paused_torrents:
            original_state = torrent.get('original_state', 'unknown')
            current_state = get_torrent_state(torrent['hash'])
            log_message("[INFO]", f"Torrent Resumed: {torrent['name']} :: Hash: {torrent['hash'][:5]} :: Original State: {original_state} :: Current State: {current_state}")
            if current_state == original_state:
                log_message("[INFO]", f"✓ Successfully restored {torrent['name']} to {original_state}")
            else:
                log_message("[WARN]", f"⚠ {torrent['name']} state mismatch: expected {original_state}, got {current_state}")
            resumed_count += 1
        log_message("[INFO]", f"Successfully resumed {resumed_count} out of {len(paused_torrents)} torrents")
        clear_paused_torrents_file()
    else:
        log_message("[INFO]", "No torrents to resume.")

def force_resume():
    log_message("[INFO]", "Using targeted resume instead of force-resume ALL")
    resume_paused_torrents()

def force_resume_mover():
    check_settings()
    if not check_ssh_connection():
        log_message("[ERROR]", "Skipping mover status check and resume due to SSH connection failure.")
        return
    log_message("[INFO]", "Checking if mover is running on UnRAID...")
    result = subprocess.run(["ssh", REMOTE_HOST, "pgrep -f /usr/local/sbin/mover"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    is_running = bool(result.stdout.strip())
    if not is_running:
        log_message("[INFO]", "Mover has stopped running. Resuming paused torrents to original states.")
        resume_paused_torrents()
    else:
        log_message("[INFO]", "Mover is still running. Will check again on next scheduled run.")

def setup_cron():
    cron_entry = f"*/10 * * * * python3 /app/qbt-mover.py -force-resume\n"
    with open("/etc/crontabs/root", "w") as cron_file:
        cron_file.write(cron_entry)
    subprocess.run(["crond", "-f", "-l", "2"])

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        log_message("[WARN]", "No command provided.")
        exit(1)
    command = sys.argv[1]
    if command == "-force-resume":
        force_resume()
    elif command == "-force-resume-mover":
        force_resume_mover()
    elif command == "-pause":
        pause_torrents()
    elif command == "-resume":
        resume_paused_torrents()
    elif command == "-setup-cron":
        setup_cron()
    else:
        log_message("[ERROR]", "Invalid command.")

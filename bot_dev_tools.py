#!/usr/bin/env python3
"""
Development Tools for Discord Bot
Utility functions to help with bot development and testing
"""

import os
import psutil
import time
import signal

def kill_existing_bots():
    """Kill any existing bot processes to prevent conflicts."""
    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and 'main.py' in ' '.join(proc.info['cmdline']):
                if proc.info['pid'] != os.getpid():  # Don't kill ourselves
                    proc.terminate()
                    killed_count += 1
                    time.sleep(0.5)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if killed_count > 0:
        print(f"Terminated {killed_count} existing bot process(es)")
        time.sleep(2)  # Give time for cleanup
    
    return killed_count

def check_bot_status():
    """Check if the bot is currently running."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and 'main.py' in ' '.join(proc.info['cmdline']):
                return True, proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False, None

def restart_bot_dev():
    """Development-friendly bot restart."""
    print("🔄 Development restart initiated...")
    
    # Kill existing processes
    killed = kill_existing_bots()
    
    # Check if process is really gone
    running, pid = check_bot_status()
    if running:
        print(f"Warning: Bot still running (PID: {pid})")
        return False
    
    print("✅ Ready for restart - use 'python main.py' to start")
    return True

if __name__ == "__main__":
    restart_bot_dev()
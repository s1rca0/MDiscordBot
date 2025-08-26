#!/usr/bin/env python3
"""
Development Restart Script
Quick restart tool for Discord bot development
"""

import subprocess
import sys
import time

def restart_bot():
    """Restart the Discord bot for development."""
    print("🔄 Restarting Discord bot...")
    
    try:
        # Kill any existing bot processes
        subprocess.run(["pkill", "-f", "main.py"], capture_output=True)
        time.sleep(1)
        
        # Start the bot again
        print("🚀 Starting bot...")
        subprocess.Popen([sys.executable, "main.py"])
        print("✅ Bot restarted successfully!")
        
    except Exception as e:
        print(f"❌ Error restarting bot: {e}")

if __name__ == "__main__":
    restart_bot()
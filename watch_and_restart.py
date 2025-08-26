#!/usr/bin/env python3
"""
File Watcher for Discord Bot Development
Automatically restarts the bot when code files change
"""

import os
import sys
import time
import subprocess
import signal
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class BotRestartHandler(FileSystemEventHandler):
    """Handle file changes and restart the bot."""
    
    def __init__(self):
        self.bot_process = None
        self.restart_delay = 2  # seconds to wait before restart
        self.last_restart = 0
        
    def start_bot(self):
        """Start the Discord bot process."""
        if self.bot_process:
            self.stop_bot()
            
        try:
            print("🚀 Starting Discord bot...")
            self.bot_process = subprocess.Popen(
                [sys.executable, "main.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            print(f"✅ Bot started with PID: {self.bot_process.pid}")
            
        except Exception as e:
            print(f"❌ Failed to start bot: {e}")
            
    def stop_bot(self):
        """Stop the Discord bot process."""
        if self.bot_process and self.bot_process.poll() is None:
            print("🛑 Stopping bot...")
            self.bot_process.terminate()
            try:
                self.bot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.bot_process.kill()
            print("✅ Bot stopped")
            
    def restart_bot(self):
        """Restart the bot with delay to avoid rapid restarts."""
        current_time = time.time()
        if current_time - self.last_restart < self.restart_delay:
            return  # Too soon, skip restart
            
        self.last_restart = current_time
        print("\n🔄 Code change detected, restarting bot...")
        self.stop_bot()
        time.sleep(1)  # Brief pause
        self.start_bot()
        
    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return
            
        # Only restart for Python files in the bot project
        if event.src_path.endswith(('.py')):
            # Ignore temporary files and logs
            if any(ignore in event.src_path for ignore in ['__pycache__', '.pyc', 'bot.log', '.tmp']):
                return
                
            print(f"📝 File changed: {os.path.basename(event.src_path)}")
            self.restart_bot()

def main():
    """Main function to start the file watcher."""
    print("🔍 Starting development file watcher...")
    print("📁 Monitoring Python files for changes...")
    print("⌨️  Press Ctrl+C to stop\n")
    
    handler = BotRestartHandler()
    observer = Observer()
    
    # Watch current directory and subdirectories
    observer.schedule(handler, ".", recursive=True)
    
    try:
        observer.start()
        handler.start_bot()  # Start bot initially
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping file watcher...")
        handler.stop_bot()
        observer.stop()
        
    observer.join()
    print("✅ File watcher stopped")

if __name__ == "__main__":
    main()
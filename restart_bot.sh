#!/bin/bash
# Quick restart script for Discord bot development

echo "🔄 Restarting Discord bot..."

# Kill existing bot processes
pkill -f "main.py" 2>/dev/null
sleep 1

# Start the bot
echo "🚀 Starting bot..."
python main.py &

echo "✅ Bot restarted! Check the console for status."
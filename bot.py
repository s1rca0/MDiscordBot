# cogs/void_pulse_cog.py
import os
import discord
from discord.ext import commands, tasks

from cogs.utils.morpheus_voice import speak

class VoidPulseCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = int(os.getenv("VOID_BROADCAST_CHANNEL", "0"))
        self.ai_prompt = os.getenv("VOID_BROADCAST_PROMPT", "").strip()
        self._pulse_task = self._maybe_pulse.start()

    @tasks.loop(minutes=60)
    async def _maybe_pulse(self):
        if not self.channel_id:
            return
        ch = self.bot.get_channel(self.channel_id)
        if not ch:
            return
        # Send message with optional AI prompt
        if self.ai_prompt:
            # Use AI to generate message
            from cogs.utils.morpheus_voice import ai_generate
            msg_text = await ai_generate(self.ai_prompt, tone=os.getenv("VOID_BROADCAST_AI_TONE", "cryptic"))
        else:
            msg_text = speak("[signal] The Void hums tonight. Those who listen may hear the door unlatch.")
        await ch.send(msg_text)

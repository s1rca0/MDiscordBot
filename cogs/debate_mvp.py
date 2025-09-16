import re, discord
from discord import app_commands
from discord.ext import commands
from config_store import get_debate, set_debate_flag, get_channel
from config import DEFAULT_BRAND_NICK

PATTERNS = {
    "ad_hominem": [r"\bidiot\b", r"\bmoron\b", r"\bclown\b", r"\bpersonal attack\b"],
    "straw_man":  [r"\bso you're saying\b", r"\bso you admit\b", r"\bthat's not what i said\b"],
    "tone_spike": [r"!!!", r"ALL CAPS(?![a-z])", r"\bfreaking\b", r"\bdumb\b"]
}
COMPILED = {k: [re.compile(x, re.I) for x in v] for k, v in PATTERNS.items()}

def _classify(text: str) -> list[str]:
    hits = []
    for label, regs in COMPILED.items():
        if any(r.search(text or "") for r in regs):
            hits.append(label)
    return hits

class DebateMVP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="debate", description="Debate tools")

    @group.command(name="terms", description="Enable/disable debate terms.")
    @app_commands.choices(state=[app_commands.Choice(name="on", value="on"), app_commands.Choice(name="off", value="off")])
    async def terms(self, interaction: discord.Interaction, state: app_commands.Choice[str]):
        on = state.value == "on"
        set_debate_flag(interaction.guild_id, "terms_on", on)
        await interaction.response.send_message(f"Debate terms **{'ON' if on else 'OFF'}**.", ephemeral=True)

    @group.command(name="coach", description="Enable/disable gentle coaching nudges.")
    @app_commands.choices(state=[app_commands.Choice(name="on", value="on"), app_commands.Choice(name="off", value="off")])
    async def coach(self, interaction: discord.Interaction, state: app_commands.Choice[str]):
        on = state.value == "on"
        set_debate_flag(interaction.guild_id, "coach_on", on)
        await interaction.response.send_message(f"Coach **{'ON' if on else 'OFF'}**.", ephemeral=True)

    @group.command(name="start", description="Announce debate start in the assigned channel.")
    async def start(self, interaction: discord.Interaction, topic: str):
        chan_id = get_channel(interaction.guild_id, "open_chat", None) or interaction.channel_id
        chan = interaction.guild.get_channel(chan_id) or interaction.channel
        flags = get_debate(interaction.guild_id)
        brand = interaction.guild.name or DEFAULT_BRAND_NICK
        await chan.send(embed=discord.Embed(
            title=f"🗣️ Debate Started — {brand}",
            description=f"**Topic:** {topic}\n\nTerms: **{flags['terms_on']}** · Coach: **{flags['coach_on']}**",
            color=discord.Color.blurple()
        ))
        await interaction.response.send_message(f"Debate announced in {chan.mention}.", ephemeral=True)

    @group.command(name="end", description="End debate (manual).")
    async def end(self, interaction: discord.Interaction):
        chan_id = get_channel(interaction.guild_id, "open_chat", None) or interaction.channel_id
        chan = interaction.guild.get_channel(chan_id) or interaction.channel
        await chan.send("✅ Debate ended. Thanks for keeping it constructive.")
        await interaction.response.send_message("Ended.", ephemeral=True)

    @commands.Cog.listener("on_message")
    async def debate_coach(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        flags = get_debate(message.guild.id)
        if not flags.get("terms_on") and not flags.get("coach_on"):
            return

        labels = _classify(message.content)
        if not labels:
            return

        try:
            await message.add_reaction("🧭")
        except discord.Forbidden:
            pass

        if flags.get("coach_on"):
            tips = {
                "ad_hominem": "Aim at the **argument**, not the person. Try: “Your claim is wrong because…”",
                "straw_man":  "Steelman first: restate your opponent’s point **fairly**, then respond.",
                "tone_spike": "Heat rises—clarify rather than intensify. One claim at a time."
            }
            hit_lines = [f"• **{l.replace('_',' ')}** — {tips[l]}" for l in labels if l in tips]
            if hit_lines:
                try:
                    await message.reply("Coach note:\n" + "\n".join(hit_lines), mention_author=False, suppress_embeds=True)
                except discord.Forbidden:
                    pass
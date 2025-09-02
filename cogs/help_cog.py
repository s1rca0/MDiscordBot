# cogs/help_cog.py
import discord
from discord.ext import commands
from discord import app_commands

from config import BotConfig
cfg = BotConfig()

# You already have a trust helper in layer_cog; we’ll repeat a light version here
def _role_ids(member: discord.Member) -> set[int]:
    return {r.id for r in member.roles}

def _trusted_ids() -> set[int]:
    ids = set()
    for v in getattr(cfg, "TRUST_ROLE_IDS", []):
        ids.add(int(v))
    for v in getattr(cfg, "YT_VERIFIED_ROLE_IDS", []):
        ids.add(int(v))
    if getattr(cfg, "YT_VERIFIED_ROLE_ID", 0):
        ids.add(int(cfg.YT_VERIFIED_ROLE_ID))
    return {i for i in ids if i > 0}

def is_trusted(member: discord.Member) -> bool:
    return bool(_role_ids(member) & _trusted_ids())

def is_staff(member: discord.Member) -> bool:
    # treat “M.O.R.P.H.E.U.S.” / admin or any role with Manage Guild as staff
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    # OPTIONAL: add a STAFF_ROLE_ID env and check it here if you make one
    return False

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show commands tailored to your access layer.")
    async def help(self, inter: discord.Interaction):
        if inter.guild is None or not isinstance(inter.user, discord.Member):
            await inter.response.send_message("Use this in a server for a layered help overview.", ephemeral=True)
            return

        member: discord.Member = inter.user
        # Layer selection
        layer = "MAINFRAME"
        if is_staff(member):
            layer = "STAFF"
        elif is_trusted(member):
            layer = "CONSTRUCT"

        emb = discord.Embed(
            title="Morpheus — Layered Help",
            color=discord.Color.green()
        )
        emb.set_footer(text=f"Requested by {member}", icon_url=member.display_avatar.url if member.display_avatar else None)

        # MAINFRAME (public) — minimal & safe
        if layer == "MAINFRAME":
            emb.add_field(
                name="Essentials",
                value="\n".join([
                    "• `/ask <prompt>` — Ask Morpheus anything",
                    "• `/faq` — Top questions",
                    "• Check **#welcome** and **#rules** to get started",
                ]),
                inline=False
            )
            emb.add_field(
                name="Want deeper access?",
                value="Earn **YT-Verified** or **Trusted** to unlock *The Construct* tools.",
                inline=False
            )

        # CONSTRUCT (trusted / YT-Verified)
        if layer in {"CONSTRUCT", "STAFF"}:
            emb.add_field(
                name="Creator Tools (The Construct)",
                value="\n".join([
                    "• `/hackin` — Send a Morpheus transmission (DM or channel)",
                    "• `/yt_overview` — YouTube performance snapshot",
                    "• `/yt_new` — Recent uploads",
                    "• `/presence now|cycle` — Status tuning",
                    "• `/void status` — Void signal/engagement status",
                ]),
                inline=False
            )

        # STAFF
        if layer == "STAFF":
            emb.add_field(
                name="Ops / Staff",
                value="\n".join([
                    "• `/roles set_member_role` — Configure the default member role",
                    "• `/trust_addrole` & `/trust_list` — Manage trusted roles",
                    "• `/modscan` — Recommend trial moderators (privacy-safe)",
                    "• `/tickets setup` — Ticket home (if you enable tickets)",
                    "• `/yt_announce test` — Test the new-video announcer",
                    "• `/memory export` — Export mission memory snapshot",
                    "• `/health` — Bot diagnostics",
                ]),
                inline=False
            )
            emb.add_field(
                name="Transparency",
                value="Use `/ethics audit` for privacy/ethics one-pager.",
                inline=False
            )

        await inter.response.send_message(embed=emb, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
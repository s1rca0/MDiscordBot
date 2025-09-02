# faq_cog.py
import os
import json
from typing import Optional, Dict

import discord
from discord.ext import commands
from discord import app_commands

from config import BotConfig
from ai_provider import ai_reply

cfg = BotConfig()

DATA_DIR = "data"
FAQ_PATH = os.path.join(DATA_DIR, "faq.json")

# --------- Storage helpers ----------
def _load_faq() -> Dict[str, str]:
    try:
        with open(FAQ_PATH, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                # normalize keys to strings
                return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}

def _save_faq(data: Dict[str, str]) -> None:
    os.makedirs(os.path.dirname(FAQ_PATH), exist_ok=True)
    with open(FAQ_PATH, "w") as f:
        json.dump(data, f, indent=2)

# --------- Placeholder helpers ----------
def _guess_channel_mention(guild: Optional[discord.Guild], *name_candidates: str) -> str:
    if not guild:
        return "#channel"
    for ch in guild.text_channels:
        low = ch.name.lower()
        if any(cand in low for cand in name_candidates):
            return f"<#{ch.id}>"
    if guild.system_channel:
        return f"<#{guild.system_channel.id}>"
    return "#channel"

def _format_template(text: str, guild: Optional[discord.Guild], me: Optional[discord.ClientUser]) -> str:
    server_name = guild.name if guild else "this server"
    member_count = guild.member_count if guild else 0
    rules = _guess_channel_mention(guild, "rules", "guidelines")
    announcements = _guess_channel_mention(guild, "announcements", "news")
    owner_name = (guild.owner.display_name if guild and guild.owner else "the owner")
    bot_name = me.name if me else "the bot"

    return (
        text.replace("{server}", server_name)
            .replace("{member_count}", str(member_count))
            .replace("{rules}", rules)
            .replace("{announcements}", announcements)
            .replace("{owner}", owner_name)
            .replace("{me}", bot_name)
    )

def _faq_lookup_local(q: str, guild: Optional[discord.Guild], me: Optional[discord.ClientUser], store: Dict[str, str]) -> Optional[str]:
    ql = (q or "").lower().strip()
    if not ql:
        return None
    if ql in store:
        return _format_template(store[ql], guild, me)
    # simple keyword containment: any token in the key found in the query
    for k, v in store.items():
        if any(tok in ql for tok in str(k).lower().split()):
            return _format_template(v, guild, me)
    return None

def _is_owner(user: discord.abc.User) -> bool:
    return bool(cfg.OWNER_USER_ID) and str(user.id) == cfg.OWNER_USER_ID

# --------- Confirm UI ----------
class ConfirmDeleteView(discord.ui.View):
    def __init__(self, requester_id: int, *, timeout: float = 45.0):
        super().__init__(timeout=timeout)
        self.requester_id = requester_id
        self.confirmed: Optional[bool] = None

    async def _gate(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("This confirmation isn’t for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._gate(interaction):
            return
        self.confirmed = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="🗑️ Confirmed. Deleting…", view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._gate(interaction):
            return
        self.confirmed = False
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❎ Cancelled. Nothing was deleted.", view=self)
        self.stop()

# --------- The Cog ----------
class FAQCog(commands.Cog, name="FAQ"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._faq: Dict[str, str] = _load_faq()

    # ------- Basic API -------
    def _save(self):
        _save_faq(self._faq)

    # ------- Slash Commands -------
    @commands.Cog.listener()
    async def on_ready(self):
        # Log to console when loaded
        try:
            print(f"[FAQCog] Loaded with {len(self._faq)} entries.")
        except Exception:
            pass

    @app_commands.command(name="faq", description="Ask the server FAQ")
    @app_commands.describe(question="Your question (e.g., rules, schedule)")
    async def faq_cmd(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer(ephemeral=True)
        # Try local FAQ
        ans = _faq_lookup_local(question, interaction.guild, self.bot.user, self._faq)
        if ans:
            await interaction.followup.send(f"**Answer:** {ans}", ephemeral=True)
            return
        # AI fallback (very brief)
        prompt = (
            f"FAQ question: {question}. "
            "If you know the likely answer for a Discord YouTube community server, reply briefly (<=4 lines). "
            "If unsure, say you’re not certain and suggest asking mods."
        )
        try:
            reply = await ai_reply(cfg.GREETER_PROMPT, [{"role": "user", "content": prompt}],
                                   max_new_tokens=160, temperature=0.4)
        except Exception:
            reply = "I’m not certain—ask a moderator or check #rules / #announcements."
        if not reply or not reply.strip():
            reply = "I’m here—try asking me again."
        await interaction.followup.send(reply[:min(cfg.MAX_MESSAGE_LENGTH, 1900)], ephemeral=True)

    @app_commands.command(name="setfaq", description="Add or update an FAQ (admin)")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(question="Key/topic", answer="Short answer (supports {server}, {rules}, etc.)")
    async def setfaq(self, interaction: discord.Interaction, question: str, answer: str):
        key = question.lower().strip()
        if not key:
            await interaction.response.send_message("Question key cannot be empty.", ephemeral=True)
            return
        self._faq[key] = answer
        try:
            self._save()
        except Exception:
            pass
        await interaction.response.send_message(f"Saved FAQ: **{question}**", ephemeral=True)

    @app_commands.command(name="faq_list", description="List saved FAQ entries (optional filter)")
    @app_commands.describe(filter="Optional text to filter FAQ keys/answers")
    async def faq_list(self, interaction: discord.Interaction, filter: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        if not self._faq:
            await interaction.followup.send("No FAQ entries yet. Use `/setfaq` or `/faq_seed`.", ephemeral=True)
            return

        flt = (filter or "").strip().lower()
        items = []
        for k, v in self._faq.items():
            k2 = str(k)
            v2 = str(v)
            if flt and (flt not in k2.lower() and flt not in v2.lower()):
                continue
            preview = v2.strip().splitlines()[0][:80]
            items.append(f"• **{k2}** — {preview}{'…' if len(v2) > len(preview) else ''}")

        if not items:
            await interaction.followup.send(f"No FAQ entries match `{filter}`.", ephemeral=True)
            return

        # paginate to stay under ~1900 chars per message
        chunks, buf = [], ""
        for line in items:
            if len(buf) + len(line) + 1 > 1800:
                chunks.append(buf)
                buf = ""
            buf += line + "\n"
        if buf:
            chunks.append(buf)

        for i, chunk in enumerate(chunks, start=1):
            header = f"**FAQ entries ({len(items)} result(s)) — page {i}/{len(chunks)}**\n"
            await interaction.followup.send(header + chunk, ephemeral=True)

    @app_commands.command(name="faq_delete", description="Delete an FAQ entry (admin, with confirmation)")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(question="The FAQ key/topic to delete")
    async def faq_delete(self, interaction: discord.Interaction, question: str):
        key = question.lower().strip()
        if key not in self._faq:
            await interaction.response.send_message(
                f"No FAQ entry found for **{question}**.",
                ephemeral=True
            )
            return

        preview = str(self._faq[key]).strip()
        if len(preview) > 180:
            preview = preview[:177] + "…"

        view = ConfirmDeleteView(requester_id=interaction.user.id, timeout=45)
        await interaction.response.send_message(
            content=(f"Delete FAQ for **{question}**?\n"
                     f"**Current answer preview:**\n> {preview}\n\n"
                     "Please confirm within 45s."),
            view=view,
            ephemeral=True
        )

        await view.wait()

        if view.confirmed is None:
            try:
                await interaction.followup.send("⌛ Timed out. Nothing was deleted.", ephemeral=True)
            except Exception:
                pass
            return

        if view.confirmed is False:
            return

        self._faq.pop(key, None)
        try:
            self._save()
        except Exception:
            pass

        try:
            await interaction.followup.send(f"🗑️ Deleted FAQ entry for **{question}**.", ephemeral=True)
        except Exception:
            pass

    @app_commands.command(name="faq_reload", description="(Owner) Reload FAQ from disk")
    async def faq_reload(self, interaction: discord.Interaction):
        if not _is_owner(interaction.user):
            await interaction.response.send_message("Only the owner can use this.", ephemeral=True)
            return
        self._faq = _load_faq()
        await interaction.response.send_message("✅ FAQ reloaded.", ephemeral=True)

    @app_commands.command(name="faq_seed", description="(Owner) Seed FAQ with useful defaults")
    async def faq_seed(self, interaction: discord.Interaction):
        if not _is_owner(interaction.user):
            await interaction.response.send_message("Only the owner can use this.", ephemeral=True)
            return
        defaults = {
            "rules": "Please read {rules}. Be kind, no spam.",
            "announcements": "News and updates are posted in {announcements}.",
            "server name": "Welcome to {server}! We have {member_count} members.",
            "help": "Try /faq (e.g., /faq rules) or mention {me}. If unsure, ask a mod.",
            "upload schedule": "New videos every Tue/Thu 5pm PT."
        }
        self._faq.update(defaults)
        try:
            self._save()
        except Exception:
            pass
        await interaction.response.send_message("✅ Seeded default FAQ entries.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(FAQCog(bot))
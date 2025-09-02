# cogs/persona_cog.py
import os
import discord
from discord.ext import commands
from discord import app_commands

class Persona:
    @staticmethod
    def _parse_role_ids(csv: str) -> list[int]:
        return [int(x.strip()) for x in (csv or "").split(",") if x.strip().isdigit()]

    @staticmethod
    def resolve_layer(member: discord.Member, owner_user_id: int,
                      trusted_csv: str, construct_csv: str) -> str:
        """Return the layer this member belongs to."""
        if member is None:
            return "Mainframe"

        # Owner = always HAVN
        if owner_user_id and int(member.id) == int(owner_user_id):
            return "HAVN"

        role_ids = {r.id for r in getattr(member, "roles", [])}

        # HAVN trust roles
        trusted_ids = set(Persona._parse_role_ids(trusted_csv))
        if role_ids & trusted_ids:
            return "HAVN"

        # Construct roles
        construct_ids = set(Persona._parse_role_ids(construct_csv))
        if role_ids & construct_ids:
            return "Construct"

        return "Mainframe"

    @staticmethod
    def build_system_prompt(
        *,
        public_prompt: str,
        backstage_prompt: str,
        mission_prompt: str,
        morpheus_style_hint: str,
        member: discord.Member,
        owner_user_id: int,
        trusted_csv: str,
        construct_csv: str,
    ) -> str:
        """Return a system prompt based on which layer the member is in."""
        layer = Persona.resolve_layer(member, owner_user_id, trusted_csv, construct_csv)

        base = morpheus_style_hint.strip() + "\n\n" + public_prompt.strip()
        if layer == "Construct":
            return base + "\n\n" + "***Construct Context:***\n" + backstage_prompt.strip()
        elif layer == "HAVN":
            return (
                base + "\n\n"
                + "***Construct Context:***\n" + backstage_prompt.strip() + "\n\n"
                + "***HAVN Context:***\n" + mission_prompt.strip()
            )
        return base  # Mainframe only

class PersonaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Secrets (CSV of role IDs)
        self.owner_user_id = int(os.getenv("OWNER_USER_ID", "0") or 0)
        self.trusted_csv = os.getenv("TRUST_ROLE_IDS", "")
        self.construct_csv = os.getenv("CONSTRUCT_ROLE_IDS", "")

        # Prompts (from env/secrets)
        self.public_prompt = os.getenv("PUBLIC_PROMPT", "You are Morpheus, guide for all.")
        self.backstage_prompt = os.getenv("BACKSTAGE_PROMPT", "Deeper lore and context for inner circle.")
        self.mission_prompt = os.getenv("MISSION_PROMPT", "Mission secrets reserved for HAVN.")
        self.morpheus_style_hint = os.getenv("MORPHEUS_STYLE_HINT", "Speak with wisdom and mystery.")

    @app_commands.command(name="mylayer", description="Find out which layer you currently belong to.")
    async def mylayer(self, interaction: discord.Interaction):
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        layer = Persona.resolve_layer(member, self.owner_user_id, self.trusted_csv, self.construct_csv)

        if interaction.user.id == self.owner_user_id:
            # Owner sees full debug
            desc = (
                f"**You are in:** {layer}\n\n"
                f"**Public Prompt:** {self.public_prompt[:120]}...\n"
                f"**Backstage Prompt:** {self.backstage_prompt[:120]}...\n"
                f"**Mission Prompt:** {self.mission_prompt[:120]}..."
            )
        else:
            desc = f"You are currently in the **{layer}** layer."

        embed = discord.Embed(
            title="🔮 Your Layer",
            description=desc,
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PersonaCog(bot))
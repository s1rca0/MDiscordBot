"""
Basic Commands Cog
Contains basic bot commands like hello, help, ping, etc.
"""

import discord
from discord.ext import commands
import time
import platform
import psutil
import logging

class BasicCommands(commands.Cog):
    """Basic command implementations."""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        
    @commands.command(name='hello', aliases=['hi', 'hey'])
    async def hello(self, ctx):
        """Say hello to the user."""
        embed = discord.Embed(
            title="👋 Hello!",
            description=f"Hello {ctx.author.mention}! Nice to meet you!",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)
        
    @commands.command(name='ping')
    async def ping(self, ctx):
        """Check bot latency."""
        start_time = time.time()
        message = await ctx.send("🏓 Pinging...")
        end_time = time.time()
        
        latency = round(self.bot.latency * 1000, 2)
        response_time = round((end_time - start_time) * 1000, 2)
        
        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.blue()
        )
        embed.add_field(name="API Latency", value=f"{latency}ms", inline=True)
        embed.add_field(name="Response Time", value=f"{response_time}ms", inline=True)
        
        await message.edit(content="", embed=embed)
        
    @commands.command(name='info', aliases=['about', 'botinfo'])
    async def info(self, ctx):
        """Display bot information."""
        embed = discord.Embed(
            title="🤖 Bot Information",
            description="A simple Discord bot built with discord.py",
            color=discord.Color.blue()
        )
        
        # Bot stats
        embed.add_field(name="Guilds", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="Users", value=len(self.bot.users), inline=True)
        embed.add_field(name="Commands", value=len(self.bot.commands), inline=True)
        
        # System info
        embed.add_field(name="Python Version", value=platform.python_version(), inline=True)
        embed.add_field(name="Discord.py Version", value=discord.__version__, inline=True)
        embed.add_field(name="Platform", value=platform.system(), inline=True)
        
        # Memory usage
        memory_usage = psutil.virtual_memory().percent
        embed.add_field(name="Memory Usage", value=f"{memory_usage}%", inline=True)
        
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        
        await ctx.send(embed=embed)
        
    @commands.command(name='help')
    async def help_command(self, ctx, *, command_name=None):
        """Display help information."""
        if command_name:
            # Help for specific command
            command = self.bot.get_command(command_name.lower())
            if command:
                embed = discord.Embed(
                    title=f"Help: {command.name}",
                    description=command.help or "No description available.",
                    color=discord.Color.blue()
                )
                
                if command.aliases:
                    embed.add_field(name="Aliases", value=", ".join(command.aliases), inline=False)
                    
                embed.add_field(name="Usage", value=f"`{ctx.prefix}{command.name} {command.signature}`", inline=False)
            else:
                embed = discord.Embed(
                    title="❌ Command Not Found",
                    description=f"Command `{command_name}` not found.",
                    color=discord.Color.red()
                )
        else:
            # General help
            embed = discord.Embed(
                title="🤖 Bot Commands",
                description=f"Here are all available commands. Use `{ctx.prefix}help <command>` for detailed help.",
                color=discord.Color.blue()
            )
            
            # Group commands by cog
            for cog_name, cog in self.bot.cogs.items():
                commands_list = [cmd.name for cmd in cog.get_commands() if not cmd.hidden]
                if commands_list:
                    embed.add_field(
                        name=cog_name.replace('Commands', ''),
                        value=f"`{f'`, `'.join(commands_list)}`",
                        inline=False
                    )
            
            # Add commands not in cogs
            no_cog_commands = [cmd.name for cmd in self.bot.commands if cmd.cog is None and not cmd.hidden]
            if no_cog_commands:
                embed.add_field(
                    name="Other",
                    value=f"`{f'`, `'.join(no_cog_commands)}`",
                    inline=False
                )
        
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)
        
    @commands.command(name='say', aliases=['echo'])
    @commands.has_permissions(manage_messages=True)
    async def say(self, ctx, *, message):
        """Make the bot say something. (Requires Manage Messages permission)"""
        # Delete the original command message
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
            
        await ctx.send(message)
        
    @commands.command(name='clear', aliases=['purge'])
    @commands.has_permissions(manage_messages=True)
    async def clear_messages(self, ctx, amount: int = 5):
        """Clear messages from the channel. (Requires Manage Messages permission)"""
        if amount < 1 or amount > 100:
            await ctx.send("❌ Amount must be between 1 and 100.")
            return
            
        try:
            deleted = await ctx.channel.purge(limit=amount + 1)  # +1 to include the command message
            
            embed = discord.Embed(
                title="🧹 Messages Cleared",
                description=f"Successfully deleted {len(deleted) - 1} messages.",
                color=discord.Color.green()
            )
            
            # Send confirmation and delete it after 5 seconds
            confirmation = await ctx.send(embed=embed)
            await confirmation.delete(delay=5)
            
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to delete messages: {e}")
            
    @say.error
    @clear_messages.error
    async def permission_error_handler(self, ctx, error):
        """Handle permission errors for commands that require special permissions."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
            
    @clear_messages.error
    async def clear_error_handler(self, ctx, error):
        """Handle errors specific to the clear command."""
        if isinstance(error, commands.BadArgument):
            await ctx.send("❌ Please provide a valid number of messages to clear.")

async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(BasicCommands(bot))

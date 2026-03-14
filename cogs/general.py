import discord
from discord import app_commands
from discord.ext import commands

from services.localization import HELP_MESSAGES, PING_MESSAGES, get_ui_language


class GeneralCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="\ubd07 \uc751\ub2f5 \ud655\uc778")
    async def ping(self, interaction: discord.Interaction) -> None:
        language = get_ui_language(interaction.locale)
        await interaction.response.send_message(PING_MESSAGES[language])

    @app_commands.command(name="help", description="\uba85\ub839\uc5b4 \uc548\ub0b4")
    async def help_command(self, interaction: discord.Interaction) -> None:
        language = get_ui_language(interaction.locale)
        await interaction.response.send_message(HELP_MESSAGES[language], ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GeneralCog(bot))

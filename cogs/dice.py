import random

import discord
from discord import app_commands
from discord.ext import commands


class DiceCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dice", description="주사위를 굴립니다")
    async def dice(self, interaction: discord.Interaction) -> None:
        result = random.randint(1, 6)
        await interaction.response.send_message(
            f"🎲 {interaction.user.mention}의 주사위 결과: **{result}**"
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DiceCog(bot))

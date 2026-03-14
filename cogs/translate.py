import asyncio

import discord
from deep_translator import GoogleTranslator
from discord import app_commands
from discord.ext import commands


class TranslateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.translator = GoogleTranslator(source="en", target="ko")

    async def translate_text(self, text: str) -> str:
        return await asyncio.to_thread(self.translator.translate, text)

    @app_commands.command(name="translate", description="영어 문장을 한국어로 번역")
    @app_commands.rename(text="영문")
    @app_commands.describe(text="한국어로 번역할 영어 문장")
    async def translate(
        self,
        interaction: discord.Interaction,
        text: app_commands.Range[str, 1, 1500],
    ) -> None:
        content = text.strip()
        if not content:
            await interaction.response.send_message(
                "번역할 문장을 비워둘 수 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)

        try:
            translated_text = await self.translate_text(content)
        except Exception as error:
            await interaction.followup.send(
                f"번역 중 오류가 발생했습니다: {error}",
                ephemeral=True,
            )
            return

        if not translated_text:
            await interaction.followup.send(
                "번역 결과를 가져오지 못했습니다. 다시 시도해 주세요.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="번역 결과",
            color=discord.Color.blue(),
        )
        embed.add_field(name="원문", value=content[:1024], inline=False)
        embed.add_field(name="한국어", value=translated_text[:1024], inline=False)
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TranslateCog(bot))

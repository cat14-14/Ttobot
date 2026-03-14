from __future__ import annotations

import re
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands


DURATION_PATTERN = re.compile(r"(\d+)([smhd])", re.IGNORECASE)
UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 60 * 60 * 24,
}
MAX_TIMEOUT_DURATION = timedelta(days=28)


class TimeoutCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def can_timeout(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False

        member = interaction.user
        if not isinstance(member, discord.Member):
            return False

        return member.guild_permissions.moderate_members

    def get_bot_member(self, guild: discord.Guild) -> discord.Member | None:
        if self.bot.user is None:
            return None

        return guild.get_member(self.bot.user.id)

    def can_act_on_target(
        self,
        actor: discord.Member,
        target: discord.Member,
    ) -> bool:
        if actor.guild.owner_id == actor.id:
            return target.id != actor.id

        if target.id == actor.id or target.id == actor.guild.owner_id:
            return False

        return actor.top_role > target.top_role

    def bot_can_act_on_target(self, target: discord.Member) -> bool:
        bot_member = self.get_bot_member(target.guild)
        if bot_member is None:
            return False

        if target.id == bot_member.id or target.id == target.guild.owner_id:
            return False

        return bot_member.top_role > target.top_role

    def bot_has_timeout_permission(self, guild: discord.Guild) -> bool:
        bot_member = self.get_bot_member(guild)
        if bot_member is None:
            return False

        return bot_member.guild_permissions.moderate_members

    def parse_duration(self, value: str) -> timedelta | None:
        normalized = value.replace(" ", "").lower()
        if not normalized:
            return None

        total_seconds = 0
        position = 0
        for match in DURATION_PATTERN.finditer(normalized):
            if match.start() != position:
                return None

            amount = int(match.group(1))
            unit = match.group(2).lower()
            total_seconds += amount * UNIT_SECONDS[unit]
            position = match.end()

        if position != len(normalized) or total_seconds <= 0:
            return None

        duration = timedelta(seconds=total_seconds)
        if duration > MAX_TIMEOUT_DURATION:
            return None

        return duration

    def format_duration(self, duration: timedelta) -> str:
        total_seconds = int(duration.total_seconds())
        units = (
            ("일", 60 * 60 * 24),
            ("시간", 60 * 60),
            ("분", 60),
            ("초", 1),
        )

        parts: list[str] = []
        remaining = total_seconds
        for label, size in units:
            if remaining < size:
                continue

            amount, remaining = divmod(remaining, size)
            parts.append(f"{amount}{label}")

        return " ".join(parts)

    @app_commands.command(name="timeout", description="일정 시간 채팅 금지")
    @app_commands.rename(member="유저", duration="시간", reason="이유")
    @app_commands.describe(
        member="타임아웃할 서버 멤버",
        duration="예: 10m, 1h, 1h30m, 2d",
        reason="타임아웃 사유",
    )
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not self.can_timeout(interaction):
            await interaction.response.send_message(
                "타임아웃은 타임아웃 권한이 있는 사람만 할 수 있습니다.",
                ephemeral=True,
            )
            return

        moderator = interaction.user
        if not isinstance(moderator, discord.Member):
            await interaction.response.send_message(
                "서버 멤버 정보를 확인할 수 없습니다.",
                ephemeral=True,
            )
            return

        if member.bot:
            await interaction.response.send_message(
                "봇 계정에는 타임아웃을 적용할 수 없습니다.",
                ephemeral=True,
            )
            return

        if not self.can_act_on_target(moderator, member):
            await interaction.response.send_message(
                "자신보다 높거나 같은 역할의 멤버에게는 타임아웃을 적용할 수 없습니다.",
                ephemeral=True,
            )
            return

        parsed_duration = self.parse_duration(duration)
        if parsed_duration is None:
            await interaction.response.send_message(
                "시간 형식이 올바르지 않습니다. `10m`, `1h`, `1h30m`, `2d`처럼 입력해 주세요. 최대 28일까지 가능합니다.",
                ephemeral=True,
            )
            return

        if not self.bot_has_timeout_permission(interaction.guild):
            await interaction.response.send_message(
                "봇에 타임아웃 권한이 없습니다.",
                ephemeral=True,
            )
            return

        if not self.bot_can_act_on_target(member):
            await interaction.response.send_message(
                "봇 역할이 대상보다 낮아 타임아웃을 적용할 수 없습니다.",
                ephemeral=True,
            )
            return

        until = discord.utils.utcnow() + parsed_duration
        try:
            await member.timeout(
                parsed_duration,
                reason=f"{reason} | by {moderator} ({moderator.id})",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "타임아웃을 적용하지 못했습니다. 봇 권한을 확인해 주세요.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as error:
            await interaction.response.send_message(
                f"타임아웃 적용 중 오류가 발생했습니다: {error}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            (
                f"{member.mention}에게 타임아웃을 적용했습니다.\n"
                f"기간: {self.format_duration(parsed_duration)}\n"
                f"해제 시각: {discord.utils.format_dt(until, style='F')}\n"
                f"사유: {reason}"
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TimeoutCog(bot))

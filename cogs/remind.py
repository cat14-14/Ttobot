from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.remind_store import ReminderEntry

if TYPE_CHECKING:
    from bot import CoraxBot


DURATION_PATTERN = re.compile(r"(\d+)([smhd])", re.IGNORECASE)
UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 60 * 60 * 24,
}
MAX_REMINDER_DURATION = timedelta(days=365)


class RemindCog(commands.Cog):
    def __init__(self, bot: "CoraxBot"):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self.reminder_loop.is_running():
            self.reminder_loop.start()

    def cog_unload(self) -> None:
        self.reminder_loop.cancel()

    def get_local_now(self) -> datetime:
        return datetime.now().astimezone()

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
        if duration > MAX_REMINDER_DURATION:
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

    async def resolve_user(self, user_id: int) -> discord.User | None:
        user = self.bot.get_user(user_id)
        if user is not None:
            return user

        try:
            return await self.bot.fetch_user(user_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return None

    @tasks.loop(seconds=30)
    async def reminder_loop(self) -> None:
        now = self.get_local_now()
        due_entries = self.bot.remind_store.get_due_entries(now)

        for entry in due_entries:
            user = await self.resolve_user(entry.user_id)
            if user is None:
                self.bot.remind_store.remove_reminder(entry.reminder_id)
                continue

            due_at = entry.due_at_datetime()
            try:
                await user.send(
                    (
                        "⏰ 리마인더\n"
                        f"{entry.content}\n"
                        f"예약 시각: {discord.utils.format_dt(due_at, style='F')}"
                    )
                )
            except discord.Forbidden:
                self.bot.remind_store.remove_reminder(entry.reminder_id)
                continue
            except discord.NotFound:
                self.bot.remind_store.remove_reminder(entry.reminder_id)
                continue
            except discord.HTTPException as error:
                print(
                    "DM 리마인더 전송 실패: "
                    f"{entry.reminder_id} user_id={entry.user_id} error={error}"
                )
                continue

            self.bot.remind_store.remove_reminder(entry.reminder_id)

    @reminder_loop.before_loop
    async def before_reminder_loop(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="remind", description="지정 시간이 지나면 DM 리마인더 전송")
    @app_commands.rename(duration_text="시간", content="내용")
    @app_commands.describe(
        duration_text="예: 30m, 1h, 1d",
        content="DM으로 받을 리마인더 내용",
    )
    async def remind(
        self,
        interaction: discord.Interaction,
        duration_text: str,
        content: str,
    ) -> None:
        if interaction.guild is None or interaction.guild_id is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        content = content.strip()
        if not content:
            await interaction.response.send_message(
                "리마인더 내용을 비워둘 수 없습니다.",
                ephemeral=True,
            )
            return

        duration = self.parse_duration(duration_text)
        if duration is None:
            await interaction.response.send_message(
                "시간 형식이 올바르지 않습니다. `30m`, `1h`, `1d`처럼 입력해 주세요. 최대 365일까지 가능합니다.",
                ephemeral=True,
            )
            return

        due_at = self.get_local_now() + duration
        self.bot.remind_store.add_reminder(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            content=content,
            due_at=due_at,
            created_at=self.get_local_now(),
        )

        await interaction.response.send_message(
            (
                "DM 리마인더를 등록했습니다.\n"
                f"내용: {content}\n"
                f"알림 시각: {discord.utils.format_dt(due_at, style='F')}"
            ),
            ephemeral=True,
        )


async def setup(bot: "CoraxBot") -> None:
    await bot.add_cog(RemindCog(bot))

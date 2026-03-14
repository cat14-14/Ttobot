from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.schedule_store import ScheduleEntry

if TYPE_CHECKING:
    from bot import CoraxBot


SCHEDULE_CHANNEL = discord.TextChannel | discord.Thread
DATE_PATTERN = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})$")
TIME_PATTERN = re.compile(r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})$")


class ScheduleCog(commands.Cog):
    def __init__(self, bot: "CoraxBot"):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self.reminder_loop.is_running():
            self.reminder_loop.start()

    def cog_unload(self) -> None:
        self.reminder_loop.cancel()

    def get_target_channel(
        self,
        interaction: discord.Interaction,
    ) -> SCHEDULE_CHANNEL | None:
        channel = interaction.channel
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel

        return None

    def bot_can_send(self, channel: SCHEDULE_CHANNEL) -> bool:
        if self.bot.user is None:
            return False

        member = channel.guild.get_member(self.bot.user.id)
        if member is None:
            return False

        permissions = channel.permissions_for(member)
        return permissions.send_messages and permissions.read_message_history

    def get_local_now(self) -> datetime:
        return datetime.now().astimezone()

    def parse_due_datetime(
        self,
        date_text: str,
        time_text: str,
    ) -> tuple[datetime | None, str | None]:
        date_match = DATE_PATTERN.fullmatch(date_text.strip())
        if date_match is None:
            return None, "날짜 형식이 올바르지 않습니다. `2026-03-14`처럼 입력해 주세요."

        time_match = TIME_PATTERN.fullmatch(time_text.strip())
        if time_match is None:
            return None, "시간 형식이 올바르지 않습니다. `20:00`처럼 입력해 주세요."

        year = int(date_match.group("year"))
        month = int(date_match.group("month"))
        day = int(date_match.group("day"))
        hour = int(time_match.group("hour"))
        minute = int(time_match.group("minute"))

        if hour > 23 or minute > 59:
            return None, "시간 형식이 올바르지 않습니다. `20:00`처럼 입력해 주세요."

        try:
            now = self.get_local_now()
            due_at = now.replace(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
        except ValueError:
            return None, "날짜 형식이 올바르지 않습니다. 실제 존재하는 날짜를 입력해 주세요."

        if due_at <= now:
            return None, "이미 지난 날짜 또는 시간입니다."

        return due_at, None

    async def resolve_channel(
        self,
        entry: ScheduleEntry,
    ) -> SCHEDULE_CHANNEL | None:
        channel = self.bot.get_channel(entry.channel_id)
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel

        try:
            fetched_channel = await self.bot.fetch_channel(entry.channel_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return None

        if isinstance(fetched_channel, (discord.TextChannel, discord.Thread)):
            return fetched_channel

        return None

    @tasks.loop(seconds=30)
    async def reminder_loop(self) -> None:
        now = self.get_local_now()
        due_entries = self.bot.schedule_store.get_due_entries(now)

        for entry in due_entries:
            channel = await self.resolve_channel(entry)
            if channel is None:
                self.bot.schedule_store.remove_schedule(entry.schedule_id)
                continue

            if not self.bot_can_send(channel):
                self.bot.schedule_store.remove_schedule(entry.schedule_id)
                continue

            due_at = entry.due_at_datetime()
            try:
                await channel.send(
                    (
                        f"⏰ <@{entry.user_id}> 일정 알림\n"
                        f"**{entry.title}**\n"
                        f"{entry.content}\n"
                        f"예정 시각: {discord.utils.format_dt(due_at, style='F')}"
                    )
                )
            except discord.Forbidden:
                self.bot.schedule_store.remove_schedule(entry.schedule_id)
                continue
            except discord.NotFound:
                self.bot.schedule_store.remove_schedule(entry.schedule_id)
                continue
            except discord.HTTPException as error:
                print(
                    "일정 알림 전송 실패: "
                    f"{entry.schedule_id} channel_id={entry.channel_id} error={error}"
                )
                continue

            self.bot.schedule_store.remove_schedule(entry.schedule_id)

    @reminder_loop.before_loop
    async def before_reminder_loop(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="schedule", description="간단 일정 알림 등록")
    @app_commands.rename(title="제목", content="내용", date_text="날짜", time_text="시간")
    @app_commands.describe(
        title="알림 제목",
        content="일정 내용",
        date_text="날짜 형식 예: 2026-03-14",
        time_text="24시간 형식 예: 20:00",
    )
    async def schedule(
        self,
        interaction: discord.Interaction,
        title: str,
        content: str,
        date_text: str,
        time_text: str,
    ) -> None:
        if interaction.guild is None or interaction.guild_id is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        channel = self.get_target_channel(interaction)
        if channel is None:
            await interaction.response.send_message(
                "이 채널에서는 일정 알림을 등록할 수 없습니다.",
                ephemeral=True,
            )
            return

        if not self.bot_can_send(channel):
            await interaction.response.send_message(
                "봇에 메시지 전송 및 채팅 기록 보기 권한이 필요합니다.",
                ephemeral=True,
            )
            return

        title = title.strip()
        if not title:
            await interaction.response.send_message(
                "일정 제목을 비워둘 수 없습니다.",
                ephemeral=True,
            )
            return

        content = content.strip()
        if not content:
            await interaction.response.send_message(
                "일정 내용을 비워둘 수 없습니다.",
                ephemeral=True,
            )
            return

        due_at, error_message = self.parse_due_datetime(date_text, time_text)
        if due_at is None:
            await interaction.response.send_message(
                error_message or "일정 날짜/시간을 확인해 주세요.",
                ephemeral=True,
            )
            return

        self.bot.schedule_store.add_schedule(
            guild_id=interaction.guild_id,
            channel_id=channel.id,
            user_id=interaction.user.id,
            title=title,
            content=content,
            due_at=due_at,
            created_at=self.get_local_now(),
        )

        await interaction.response.send_message(
            (
                f"일정을 등록했습니다.\n"
                f"제목: {title}\n"
                f"내용: {content}\n"
                f"알림 시각: {discord.utils.format_dt(due_at, style='F')}\n"
                f"알림 채널: {channel.mention}"
            ),
            ephemeral=True,
        )


async def setup(bot: "CoraxBot") -> None:
    await bot.add_cog(ScheduleCog(bot))

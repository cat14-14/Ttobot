from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from services.warn_store import WarningRecord

if TYPE_CHECKING:
    from bot import CoraxBot


WARNING_TIMEOUTS: dict[int, timedelta] = {
    3: timedelta(hours=1),
    5: timedelta(hours=5),
}
KICK_THRESHOLD = 10
SANCTION_THRESHOLDS = (KICK_THRESHOLD, 5, 3)


class WarnCog(commands.Cog):
    def __init__(self, bot: "CoraxBot"):
        self.bot = bot

    def can_warn(self, interaction: discord.Interaction) -> bool:
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

    def get_pending_threshold(self, record: WarningRecord) -> int | None:
        for threshold in SANCTION_THRESHOLDS:
            if (
                record.warning_count >= threshold
                and threshold not in record.triggered_thresholds
            ):
                return threshold

        return None

    def bot_has_timeout_permission(self, guild: discord.Guild) -> bool:
        bot_member = self.get_bot_member(guild)
        if bot_member is None:
            return False

        return bot_member.guild_permissions.moderate_members

    def bot_has_kick_permission(self, guild: discord.Guild) -> bool:
        bot_member = self.get_bot_member(guild)
        if bot_member is None:
            return False

        return bot_member.guild_permissions.kick_members

    async def apply_sanction(
        self,
        member: discord.Member,
        warning_count: int,
        threshold: int,
    ) -> str:
        reason = f"경고 누적 {warning_count}회 자동 제재"

        if threshold == KICK_THRESHOLD:
            if not self.bot_has_kick_permission(member.guild):
                return "자동 킥을 실행하려면 봇에 멤버 추방 권한이 필요합니다."

            if not self.bot_can_act_on_target(member):
                return "자동 킥을 실행할 수 있도록 봇 역할을 대상보다 위로 올려야 합니다."

            await member.kick(reason=reason)
            return "자동 제재가 적용되었습니다: 킥"

        duration = WARNING_TIMEOUTS[threshold]
        if not self.bot_has_timeout_permission(member.guild):
            return "자동 타임아웃을 실행하려면 봇에 타임아웃 권한이 필요합니다."

        if not self.bot_can_act_on_target(member):
            return "자동 타임아웃을 실행할 수 있도록 봇 역할을 대상보다 위로 올려야 합니다."

        await member.timeout(duration, reason=reason)
        hours = int(duration.total_seconds() // 3600)
        return f"자동 제재가 적용되었습니다: {hours}시간 타임아웃"

    def build_warning_history(self, member: discord.Member, record: WarningRecord) -> str:
        if not record.entries:
            return f"{member.mention}의 경고 기록이 없습니다."

        recent_entries = record.entries[-5:]
        lines = [
            f"{member.mention}의 누적 경고: {record.warning_count}회",
            "",
            "최근 경고 기록",
        ]

        for entry in reversed(recent_entries):
            timestamp = self.format_timestamp(entry.created_at)
            lines.append(
                f"{entry.warning_number}. {timestamp} | 관리자 <@{entry.moderator_id}> | {entry.reason}"
            )

        return "\n".join(lines)

    def format_timestamp(self, iso_timestamp: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_timestamp)
        except ValueError:
            return iso_timestamp

        return discord.utils.format_dt(dt, style="f")

    @app_commands.command(name="warn", description="유저에게 경고를 부여하고 자동 제재를 적용")
    @app_commands.rename(member="유저", reason="이유")
    @app_commands.describe(
        member="경고를 부여할 서버 멤버",
        reason="경고 사유",
    )
    @app_commands.default_permissions(moderate_members=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        if interaction.guild is None or interaction.guild_id is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not self.can_warn(interaction):
            await interaction.response.send_message(
                "경고 부여는 타임아웃 권한이 있는 사람만 할 수 있습니다.",
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
                "봇 계정에는 경고를 부여할 수 없습니다.",
                ephemeral=True,
            )
            return

        if not self.can_act_on_target(moderator, member):
            await interaction.response.send_message(
                "자신보다 높거나 같은 역할의 멤버에게는 경고를 부여할 수 없습니다.",
                ephemeral=True,
            )
            return

        record, _ = self.bot.warn_store.add_warning(
            guild_id=interaction.guild_id,
            user_id=member.id,
            moderator_id=moderator.id,
            reason=reason,
        )

        sanction_message = "자동 제재 없음"
        pending_threshold = self.get_pending_threshold(record)
        if pending_threshold is not None:
            try:
                sanction_message = await self.apply_sanction(
                    member=member,
                    warning_count=record.warning_count,
                    threshold=pending_threshold,
                )
                if sanction_message.startswith("자동 제재가 적용되었습니다"):
                    record = self.bot.warn_store.mark_threshold_triggered(
                        guild_id=interaction.guild_id,
                        user_id=member.id,
                        threshold=pending_threshold,
                    )
            except discord.Forbidden:
                sanction_message = "자동 제재를 적용하지 못했습니다. 봇 권한을 확인해 주세요."
            except discord.HTTPException as error:
                sanction_message = f"자동 제재 적용 중 오류가 발생했습니다: {error}"

        await interaction.response.send_message(
            (
                f"{member.mention}에게 경고를 부여했습니다.\n"
                f"사유: {reason}\n"
                f"누적 경고: {record.warning_count}회\n"
                f"{sanction_message}"
            ),
            ephemeral=True,
        )

    @app_commands.command(name="warnings", description="유저의 경고 기록 확인")
    @app_commands.rename(member="유저")
    @app_commands.describe(member="경고 기록을 확인할 서버 멤버")
    @app_commands.default_permissions(moderate_members=True)
    async def warnings(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if interaction.guild is None or interaction.guild_id is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not self.can_warn(interaction):
            await interaction.response.send_message(
                "경고 기록은 타임아웃 권한이 있는 사람만 확인할 수 있습니다.",
                ephemeral=True,
            )
            return

        record = self.bot.warn_store.get_record(interaction.guild_id, member.id)
        await interaction.response.send_message(
            self.build_warning_history(member, record),
            ephemeral=True,
        )


async def setup(bot: "CoraxBot") -> None:
    await bot.add_cog(WarnCog(bot))

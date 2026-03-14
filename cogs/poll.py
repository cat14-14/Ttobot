from __future__ import annotations

from datetime import UTC, datetime, time as dt_time, timedelta, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from services.poll_store import PollRecord

if TYPE_CHECKING:
    from bot import CoraxBot


PollChannel = discord.TextChannel | discord.Thread
KST = timezone(timedelta(hours=9), name="KST")


def is_admin(user: discord.abc.User) -> bool:
    return isinstance(user, discord.Member) and user.guild_permissions.administrator


def can_end_poll(user: discord.abc.User, poll: PollRecord) -> bool:
    return user.id == poll.author_id or is_admin(user)


class PollView(discord.ui.View):
    def __init__(self, bot: "CoraxBot", message_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.message_id = message_id

    def get_poll(self) -> PollRecord | None:
        return self.bot.poll_store.get_poll(self.message_id)

    def close_if_expired(self, poll: PollRecord) -> PollRecord:
        if poll.is_ended:
            return poll

        end_at = poll.end_at_datetime()
        if end_at is None or end_at > datetime.now(UTC):
            return poll

        updated_poll = self.bot.poll_store.close_poll(
            message_id=self.message_id,
            ended_by=None,
        )
        return updated_poll or poll

    def refresh_buttons(self, poll: PollRecord) -> None:
        self.vote_yes.label = f"👍 {poll.yes_label} {poll.yes_votes}"
        self.vote_no.label = f"👎 {poll.no_label} {poll.no_votes}"
        self.details.label = f"현황 보기 {poll.total_votes}"
        self.vote_yes.disabled = poll.is_ended
        self.vote_no.disabled = poll.is_ended
        self.end_poll.disabled = poll.is_ended
        self.end_poll.label = "투표 종료됨" if poll.is_ended else "투표 종료"

    async def sync_message(
        self,
        interaction: discord.Interaction,
        poll: PollRecord,
    ) -> None:
        self.refresh_buttons(poll)
        await interaction.response.edit_message(
            embed=PollCog.build_poll_embed(poll),
            view=self,
        )

    async def handle_vote(
        self,
        interaction: discord.Interaction,
        choice: str,
    ) -> None:
        poll = self.get_poll()
        if poll is None:
            await interaction.response.send_message(
                "이 투표를 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        poll = self.close_if_expired(poll)
        if poll.is_ended:
            self.refresh_buttons(poll)
            await interaction.response.edit_message(
                embed=PollCog.build_poll_embed(poll),
                view=self,
            )
            await interaction.followup.send("이미 종료된 투표입니다.", ephemeral=True)
            return

        updated_poll, action = self.bot.poll_store.update_vote(
            message_id=self.message_id,
            user_id=interaction.user.id,
            choice=choice,
        )
        if updated_poll is None:
            await interaction.response.send_message(
                "이 투표를 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        await self.sync_message(interaction, updated_poll)

        if action == "closed":
            message = "이미 종료된 투표입니다."
        elif action == "removed":
            message = "기존 투표를 취소했습니다."
        elif action == "changed":
            message = "투표를 변경했습니다."
        else:
            message = "투표를 등록했습니다."

        await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(
        label="👍 찬성 0",
        style=discord.ButtonStyle.success,
        custom_id="poll:vote_yes",
    )
    async def vote_yes(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self.handle_vote(interaction, "yes")

    @discord.ui.button(
        label="👎 반대 0",
        style=discord.ButtonStyle.danger,
        custom_id="poll:vote_no",
    )
    async def vote_no(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self.handle_vote(interaction, "no")

    @discord.ui.button(
        label="현황 보기 0",
        style=discord.ButtonStyle.secondary,
        custom_id="poll:details",
    )
    async def details(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        poll = self.get_poll()
        if poll is None:
            await interaction.response.send_message(
                "이 투표를 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        poll = self.close_if_expired(poll)
        self.refresh_buttons(poll)
        try:
            await interaction.message.edit(
                embed=PollCog.build_poll_embed(poll),
                view=self,
            )
        except (AttributeError, discord.HTTPException):
            pass

        details_embed = PollCog.build_details_embed(
            poll=poll,
            guild=interaction.guild,
            viewer=interaction.user,
        )
        await interaction.response.send_message(embed=details_embed, ephemeral=True)

    @discord.ui.button(
        label="투표 종료",
        style=discord.ButtonStyle.primary,
        custom_id="poll:end",
    )
    async def end_poll(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        poll = self.get_poll()
        if poll is None:
            await interaction.response.send_message(
                "이 투표를 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        poll = self.close_if_expired(poll)
        if poll.is_ended:
            self.refresh_buttons(poll)
            await interaction.response.edit_message(
                embed=PollCog.build_poll_embed(poll),
                view=self,
            )
            await interaction.followup.send("이미 종료된 투표입니다.", ephemeral=True)
            return

        if not can_end_poll(interaction.user, poll):
            await interaction.response.send_message(
                "투표 종료는 개설자 또는 관리자만 할 수 있습니다.",
                ephemeral=True,
            )
            return

        updated_poll = self.bot.poll_store.close_poll(
            message_id=self.message_id,
            ended_by=interaction.user.id,
        )
        if updated_poll is None:
            await interaction.response.send_message(
                "이 투표를 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        await self.sync_message(interaction, updated_poll)
        await interaction.followup.send("투표를 종료했습니다.", ephemeral=True)


class PollCog(commands.Cog):
    def __init__(self, bot: "CoraxBot"):
        self.bot = bot
        self._registered_views: dict[int, PollView] = {}

    async def cog_load(self) -> None:
        self.register_existing_polls()
        if not self.poll_expiry_task.is_running():
            self.poll_expiry_task.start()

    def cog_unload(self) -> None:
        if self.poll_expiry_task.is_running():
            self.poll_expiry_task.cancel()

    def register_existing_polls(self) -> None:
        for poll in self.bot.poll_store.list_polls():
            self.get_or_register_view(poll)

    def get_or_register_view(self, poll: PollRecord) -> PollView:
        view = self._registered_views.get(poll.message_id)
        if view is not None:
            view.refresh_buttons(poll)
            return view

        view = PollView(self.bot, poll.message_id)
        view.refresh_buttons(poll)
        self.bot.add_view(view, message_id=poll.message_id)
        self._registered_views[poll.message_id] = view
        return view

    def get_target_channel(
        self,
        interaction: discord.Interaction,
    ) -> PollChannel | None:
        channel = interaction.channel
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel

        return None

    def bot_can_create_poll(self, channel: PollChannel) -> bool:
        if self.bot.user is None:
            return False

        member = channel.guild.get_member(self.bot.user.id)
        if member is None:
            return False

        permissions = channel.permissions_for(member)
        return (
            permissions.send_messages
            and permissions.embed_links
            and permissions.read_message_history
        )

    @staticmethod
    def format_percentage(votes: int, total_votes: int) -> str:
        if total_votes == 0:
            return "0%"

        return f"{round((votes / total_votes) * 100)}%"

    @staticmethod
    def build_bar(votes: int, total_votes: int, filled_emoji: str) -> str:
        ratio = 0 if total_votes == 0 else votes / total_votes
        filled = round(ratio * 8)
        empty = 8 - filled
        return f"{filled_emoji * filled}{'▫️' * empty}"

    @staticmethod
    def format_timestamp(value: datetime | None) -> str:
        if value is None:
            return "없음"

        timestamp = int(value.astimezone(UTC).timestamp())
        return f"<t:{timestamp}:F> (<t:{timestamp}:R>)"

    @staticmethod
    def build_poll_embed(poll: PollRecord) -> discord.Embed:
        total_votes = poll.total_votes
        visibility = "공개 투표" if poll.is_public else "비공개 투표"
        status = "종료됨" if poll.is_ended else "진행 중"

        if poll.is_ended:
            end_info = PollCog.format_timestamp(poll.ended_at_datetime())
        else:
            end_info = PollCog.format_timestamp(poll.end_at_datetime())

        embed = discord.Embed(
            title="투표",
            description=poll.question,
            color=discord.Color.dark_grey() if poll.is_ended else discord.Color.gold(),
            timestamp=poll.created_at_datetime(),
        )
        embed.add_field(
            name=f"👍 {poll.yes_label}",
            value=(
                f"{PollCog.build_bar(poll.yes_votes, total_votes, '🟩')}\n"
                f"{poll.yes_votes}표 ({PollCog.format_percentage(poll.yes_votes, total_votes)})"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"👎 {poll.no_label}",
            value=(
                f"{PollCog.build_bar(poll.no_votes, total_votes, '🟥')}\n"
                f"{poll.no_votes}표 ({PollCog.format_percentage(poll.no_votes, total_votes)})"
            ),
            inline=False,
        )
        embed.add_field(
            name="정보",
            value=(
                f"총 참여자: **{total_votes}명**\n"
                f"설정: **{visibility}**\n"
                f"상태: **{status}**\n"
                f"종료 시각: **{end_info}**\n"
                f"개설자: <@{poll.author_id}>"
            ),
            inline=False,
        )
        footer_text = (
            "종료된 투표입니다."
            if poll.is_ended
            else "같은 버튼을 다시 누르면 투표가 취소됩니다."
        )
        embed.set_footer(text=footer_text)
        return embed

    @staticmethod
    def build_member_list(
        user_ids: list[int],
        *,
        guild: discord.Guild | None,
    ) -> str:
        if not user_ids:
            return "없음"

        mentions = []
        for user_id in user_ids:
            member = guild.get_member(user_id) if guild else None
            if member is not None:
                mentions.append(member.mention)
            else:
                mentions.append(f"<@{user_id}>")

        text = "\n".join(mentions)
        if len(text) <= 1024:
            return text

        shortened = []
        length = 0
        for mention in mentions:
            if length + len(mention) + 1 > 1000:
                break
            shortened.append(mention)
            length += len(mention) + 1

        remaining = len(mentions) - len(shortened)
        return "\n".join(shortened) + f"\n... 외 {remaining}명"

    @staticmethod
    def build_details_embed(
        *,
        poll: PollRecord,
        guild: discord.Guild | None,
        viewer: discord.abc.User,
    ) -> discord.Embed:
        embed = discord.Embed(
            title="투표 현황",
            description=poll.question,
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="참여 인원",
            value=f"{poll.total_votes}명",
            inline=False,
        )
        embed.add_field(
            name="상태",
            value="종료됨" if poll.is_ended else "진행 중",
            inline=False,
        )

        can_view_voters = (
            poll.is_public or is_admin(viewer) or viewer.id == poll.author_id
        )
        if not can_view_voters:
            embed.add_field(
                name="상세 정보",
                value=(
                    "이 투표는 비공개입니다.\n"
                    "관리자와 개설자만 누가 어디에 투표했는지 볼 수 있습니다."
                ),
                inline=False,
            )
            embed.add_field(
                name=f"👍 {poll.yes_label}",
                value=f"{poll.yes_votes}표",
                inline=True,
            )
            embed.add_field(
                name=f"👎 {poll.no_label}",
                value=f"{poll.no_votes}표",
                inline=True,
            )
            return embed

        yes_voters = [
            user_id for user_id, choice in poll.votes.items() if choice == "yes"
        ]
        no_voters = [
            user_id for user_id, choice in poll.votes.items() if choice == "no"
        ]
        embed.add_field(
            name=f"👍 {poll.yes_label} ({len(yes_voters)}명)",
            value=PollCog.build_member_list(yes_voters, guild=guild),
            inline=False,
        )
        embed.add_field(
            name=f"👎 {poll.no_label} ({len(no_voters)}명)",
            value=PollCog.build_member_list(no_voters, guild=guild),
            inline=False,
        )
        return embed

    @staticmethod
    def parse_end_datetime(
        *,
        end_date: str | None,
        end_time: str | None,
        no_end_time: bool,
    ) -> tuple[str, str | None]:
        if no_end_time:
            if end_date or end_time:
                return "", "종료없음을 선택한 경우 종료날짜와 종료시간은 비워 두어야 합니다."
            return "", None

        if not end_date and not end_time:
            return "", None

        if not end_date or not end_time:
            return "", "종료날짜와 종료시간은 함께 입력해야 합니다."

        try:
            parsed_date = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            return "", "종료날짜는 YYYY-MM-DD 형식으로 입력해 주세요."

        try:
            parsed_time = datetime.strptime(end_time.strip(), "%H:%M").time()
        except ValueError:
            return "", "종료시간은 HH:MM 24시간 형식으로 입력해 주세요."

        end_datetime_kst = datetime.combine(
            parsed_date,
            dt_time(parsed_time.hour, parsed_time.minute, tzinfo=KST),
        )
        now_kst = datetime.now(KST)
        if end_datetime_kst <= now_kst:
            return "", "종료 시각은 현재보다 미래여야 합니다."

        return end_datetime_kst.astimezone(UTC).isoformat(), None

    async def refresh_poll_message(self, poll: PollRecord) -> None:
        channel = self.bot.get_channel(poll.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(poll.channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        try:
            message = await channel.fetch_message(poll.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        view = self.get_or_register_view(poll)
        try:
            await message.edit(
                embed=self.build_poll_embed(poll),
                view=view,
            )
        except discord.HTTPException:
            return

    async def close_expired_polls(self) -> None:
        now = datetime.now(UTC)
        for poll in self.bot.poll_store.list_polls():
            if poll.is_ended:
                continue

            end_at = poll.end_at_datetime()
            if end_at is None or end_at > now:
                continue

            updated_poll = self.bot.poll_store.close_poll(
                message_id=poll.message_id,
                ended_by=None,
            )
            if updated_poll is None:
                continue

            await self.refresh_poll_message(updated_poll)

    async def refresh_all_polls(self) -> None:
        for poll in self.bot.poll_store.list_polls():
            await self.refresh_poll_message(poll)

    @tasks.loop(seconds=30)
    async def poll_expiry_task(self) -> None:
        await self.close_expired_polls()

    @poll_expiry_task.before_loop
    async def before_poll_expiry_task(self) -> None:
        await self.bot.wait_until_ready()
        await self.refresh_all_polls()
        await self.close_expired_polls()

    @app_commands.command(name="poll", description="버튼형 찬반 투표 생성")
    @app_commands.rename(
        question="질문",
        yes_label="찬성",
        no_label="반대",
        is_public="공개",
        end_date="종료날짜",
        end_time="종료시간",
        no_end_time="종료없음",
    )
    @app_commands.describe(
        question="투표 질문",
        yes_label="찬성 선택지 문구, 비우면 '찬성'",
        no_label="반대 선택지 문구, 비우면 '반대'",
        is_public="누가 어디에 투표했는지 모두에게 공개할지 여부",
        end_date="종료 날짜 (YYYY-MM-DD)",
        end_time="종료 시간 (HH:MM, 24시간 형식)",
        no_end_time="종료 시간을 두지 않을지 여부",
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        yes_label: str | None = None,
        no_label: str | None = None,
        is_public: bool = False,
        end_date: str | None = None,
        end_time: str | None = None,
        no_end_time: bool = False,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        channel = self.get_target_channel(interaction)
        if channel is None:
            await interaction.response.send_message(
                "이 채널에서는 투표 메시지를 생성할 수 없습니다.",
                ephemeral=True,
            )
            return

        if not self.bot_can_create_poll(channel):
            await interaction.response.send_message(
                "봇에 메시지 전송, 임베드 링크, 채팅 기록 보기 권한이 필요합니다.",
                ephemeral=True,
            )
            return

        question = question.strip()
        yes_text = (yes_label or "찬성").strip()
        no_text = (no_label or "반대").strip()
        end_at, end_error = self.parse_end_datetime(
            end_date=end_date,
            end_time=end_time,
            no_end_time=no_end_time,
        )

        if end_error:
            await interaction.response.send_message(end_error, ephemeral=True)
            return

        if not question:
            await interaction.response.send_message(
                "투표 질문을 비워둘 수 없습니다.",
                ephemeral=True,
            )
            return

        if not yes_text or not no_text:
            await interaction.response.send_message(
                "찬성/반대 문구를 비워둘 수 없습니다.",
                ephemeral=True,
            )
            return

        placeholder = discord.Embed(
            title="투표 생성 중",
            description=question,
            color=discord.Color.gold(),
        )

        try:
            poll_message = await channel.send(embed=placeholder)
        except discord.Forbidden:
            await interaction.response.send_message(
                "투표 메시지를 생성하지 못했습니다. 봇 권한을 확인해 주세요.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as error:
            await interaction.response.send_message(
                f"투표 생성 중 오류가 발생했습니다: {error}",
                ephemeral=True,
            )
            return

        poll = self.bot.poll_store.add_poll(
            message_id=poll_message.id,
            guild_id=interaction.guild_id,
            channel_id=channel.id,
            author_id=interaction.user.id,
            question=question,
            yes_label=yes_text,
            no_label=no_text,
            is_public=is_public,
            end_at=end_at,
        )

        view = self.get_or_register_view(poll)

        try:
            await poll_message.edit(
                embed=self.build_poll_embed(poll),
                view=view,
            )
        except discord.HTTPException as error:
            self.bot.poll_store.remove_poll(poll.message_id)
            await interaction.response.send_message(
                f"투표 메시지 구성 중 오류가 발생했습니다: {error}",
                ephemeral=True,
            )
            return

        visibility = "공개" if is_public else "비공개"
        deadline = "없음" if not poll.end_at else self.format_timestamp(poll.end_at_datetime())
        await interaction.response.send_message(
            f"투표를 생성했습니다: {poll_message.jump_url}\n"
            f"설정: {visibility} 투표\n"
            f"종료 시각: {deadline}",
            ephemeral=True,
        )


async def setup(bot: "CoraxBot") -> None:
    await bot.add_cog(PollCog(bot))

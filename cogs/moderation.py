from __future__ import annotations

import asyncio
import time

import discord
from discord import app_commands
from discord.ext import commands


ModerationChannel = discord.TextChannel | discord.Thread


def build_clear_prompt(amount: int | None) -> str:
    if amount is None:
        return (
            "⚠️ 이 채널의 삭제 가능한 메시지를 전부 삭제하시겠습니까?\n"
            "오래된 메시지도 포함되며 시간이 걸릴 수 있습니다.\n"
            "본인에게만 보이는 메시지는 삭제되지 않습니다."
        )

    return f"⚠️ 최근 {amount}개의 메시지를 삭제하시겠습니까?"


def build_clear_timeout_message(amount: int | None) -> str:
    if amount is None:
        return "전체 메시지 삭제 확인 시간이 만료되었습니다."

    return "메시지 삭제 확인 시간이 만료되었습니다."


def build_clear_cancel_message(amount: int | None) -> str:
    if amount is None:
        return "전체 메시지 삭제를 취소했습니다."

    return "메시지 삭제를 취소했습니다."


def build_clear_success_message(amount: int | None, deleted_count: int) -> str:
    if deleted_count == 0:
        if amount is None:
            return "🧹 이 채널에서 삭제할 수 있는 메시지가 없었습니다."

        return "🧹 최근 삭제할 수 있는 메시지가 없었습니다."

    if amount is None:
        return (
            f"🧹 이 채널에서 삭제 가능한 메시지 {deleted_count}개를 모두 삭제했습니다."
        )

    return f"🧹 최근 {deleted_count}개의 메시지를 삭제했습니다."


def build_clear_reason(
    interaction: discord.Interaction,
    amount: int | None,
) -> str:
    command_name = "/clear_all" if amount is None else "/clear"
    return f"{command_name} by {interaction.user} ({interaction.user.id})"


async def delete_message_batch(
    channel: ModerationChannel,
    messages: list[discord.Message],
    *,
    use_bulk: bool,
    reason: str,
) -> int:
    if not messages:
        return 0

    if use_bulk and len(messages) >= 2:
        try:
            await channel.delete_messages(messages, reason=reason)
            return len(messages)
        except discord.NotFound:
            pass

    deleted_count = 0
    for message in messages:
        try:
            await message.delete()
            deleted_count += 1
        except discord.NotFound as error:
            if error.code == 10008:
                continue
            raise

    return deleted_count


async def delete_all_messages(
    channel: ModerationChannel,
    *,
    reason: str,
) -> int:
    deleted_count = 0
    pending_messages: list[discord.Message] = []
    use_bulk = True
    minimum_time = (
        int((time.time() - 14 * 24 * 60 * 60) * 1000.0 - 1420070400000) << 22
    )

    async for message in channel.history(limit=None):
        if not message.type.is_deletable():
            continue

        if use_bulk and message.id < minimum_time:
            deleted_count += await delete_message_batch(
                channel,
                pending_messages,
                use_bulk=True,
                reason=reason,
            )
            pending_messages.clear()
            use_bulk = False

        pending_messages.append(message)
        if len(pending_messages) < 100:
            continue

        deleted_count += await delete_message_batch(
            channel,
            pending_messages,
            use_bulk=use_bulk,
            reason=reason,
        )
        pending_messages.clear()
        if use_bulk:
            await asyncio.sleep(1)

    deleted_count += await delete_message_batch(
        channel,
        pending_messages,
        use_bulk=use_bulk,
        reason=reason,
    )
    return deleted_count


async def delete_requested_messages(
    channel: ModerationChannel,
    *,
    amount: int | None,
    reason: str,
) -> int:
    if amount is None:
        return await delete_all_messages(channel, reason=reason)

    deleted_messages = await channel.purge(limit=amount, reason=reason)
    return len(deleted_messages)


class ClearConfirmView(discord.ui.View):
    def __init__(
        self,
        channel: ModerationChannel,
        requester_id: int,
        amount: int | None,
    ) -> None:
        super().__init__(timeout=30)
        self.channel = channel
        self.requester_id = requester_id
        self.amount = amount
        self.message: discord.InteractionMessage | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True

        await interaction.response.send_message(
            "이 확인 버튼은 명령어를 실행한 사용자만 누를 수 있습니다.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        if self.message is None:
            return

        try:
            await self.message.edit(
                content=build_clear_timeout_message(self.amount),
                view=None,
            )
        except (discord.HTTPException, discord.NotFound):
            pass

    @discord.ui.button(label="확인", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "서버 멤버 정보를 확인할 수 없습니다.",
                ephemeral=True,
            )
            return

        if not member.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "메시지 관리 권한이 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            deleted_count = await delete_requested_messages(
                self.channel,
                amount=self.amount,
                reason=build_clear_reason(interaction, self.amount),
            )
        except discord.Forbidden:
            await interaction.edit_original_response(
                content="메시지를 삭제할 권한이 없어 작업을 완료하지 못했습니다.",
                view=None,
            )
            self.stop()
            return
        except discord.HTTPException as error:
            await interaction.edit_original_response(
                content=f"메시지 삭제 중 오류가 발생했습니다: {error}",
                view=None,
            )
            self.stop()
            return

        await interaction.edit_original_response(
            content=build_clear_success_message(self.amount, deleted_count),
            view=None,
        )
        self.stop()

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            content=build_clear_cancel_message(self.amount),
            view=None,
        )
        self.stop()


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def can_manage_messages(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False

        member = interaction.user
        if not isinstance(member, discord.Member):
            return False

        return member.guild_permissions.manage_messages

    def get_target_channel(
        self,
        interaction: discord.Interaction,
    ) -> ModerationChannel | None:
        channel = interaction.channel
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel

        return None

    def bot_can_manage_messages(self, channel: ModerationChannel) -> bool:
        if self.bot.user is None:
            return False

        member = channel.guild.get_member(self.bot.user.id)
        if member is None:
            return False

        permissions = channel.permissions_for(member)
        return permissions.manage_messages and permissions.read_message_history

    async def ensure_clear_available(
        self,
        interaction: discord.Interaction,
    ) -> ModerationChannel | None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return None

        if not self.can_manage_messages(interaction):
            await interaction.response.send_message(
                "메시지 삭제는 메시지 관리 권한이 있는 사람만 할 수 있습니다.",
                ephemeral=True,
            )
            return None

        channel = self.get_target_channel(interaction)
        if channel is None:
            await interaction.response.send_message(
                "이 채널에서는 메시지 삭제 기능을 사용할 수 없습니다.",
                ephemeral=True,
            )
            return None

        if not self.bot_can_manage_messages(channel):
            await interaction.response.send_message(
                "봇에 메시지 관리 또는 채팅 기록 보기 권한이 없습니다.",
                ephemeral=True,
            )
            return None

        return channel

    async def send_clear_prompt(
        self,
        interaction: discord.Interaction,
        *,
        amount: int | None,
    ) -> None:
        channel = await self.ensure_clear_available(interaction)
        if channel is None:
            return

        view = ClearConfirmView(
            channel=channel,
            requester_id=interaction.user.id,
            amount=amount,
        )
        await interaction.response.send_message(
            build_clear_prompt(amount),
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()

    @app_commands.command(name="clear", description="최근 메시지 삭제")
    @app_commands.rename(amount="개수")
    @app_commands.describe(amount="삭제할 최근 메시지 수 (1~100)")
    @app_commands.default_permissions(manage_messages=True)
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
    ) -> None:
        await self.send_clear_prompt(interaction, amount=amount)

    @app_commands.command(
        name="clear_all",
        description="이 채널의 오래된 메시지를 포함해 전부 삭제",
    )
    @app_commands.default_permissions(manage_messages=True)
    async def clear_all(self, interaction: discord.Interaction) -> None:
        await self.send_clear_prompt(interaction, amount=None)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(bot))

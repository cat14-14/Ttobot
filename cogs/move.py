from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from bot import CoraxBot


MoveSourceChannel = discord.TextChannel | discord.Thread
MoveDestinationChannel = discord.TextChannel | discord.Thread
MAX_MOVE_SELECTION_MESSAGES = 25

MOVE_ACTION_PATTERN = re.compile(r"(?:옮겨|이동|move)", re.IGNORECASE)
HERE_PATTERN = re.compile(r"(?:여기로|이 채널로|현재 채널로)", re.IGNORECASE)
USER_MENTION_PATTERN = re.compile(r"<@!?(\d+)>")
CHANNEL_MENTION_PATTERN = re.compile(r"<#(\d+)>")


@dataclass(frozen=True)
class ParsedMoveRequest:
    destination_channel_id: int
    count: int
    author_id: int | None
    needs_source_channel_selection: bool


@dataclass(frozen=True)
class MoveResult:
    moved_count: int
    copied_only_count: int
    failed_count: int


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text

    return f"{text[: limit - 1].rstrip()}…"


def build_move_prompt(destination: MoveDestinationChannel, count: int) -> str:
    noun = "이 메시지" if count == 1 else f"최근 메시지 {count}개"
    return f"⚠️ {noun}를 {destination.mention}(으)로 이동하시겠습니까?"


def build_move_cancel_message() -> str:
    return "메시지 이동을 취소했습니다."


def build_move_timeout_message() -> str:
    return "메시지 이동 확인 시간이 만료되었습니다."


def message_preview(message: discord.Message, limit: int = 60) -> str:
    content = message.content.strip() or "(텍스트 없이 첨부만 있음)"
    content = re.sub(r"\s+", " ", content)
    return truncate_text(content, limit)


def build_move_selection_notice(
    destination: MoveDestinationChannel,
    messages: list[discord.Message],
    selected_message_ids: set[int],
    *,
    capped: bool,
) -> str:
    source_channel = messages[0].channel if messages else None
    lines = [
        "이동할 메시지를 선택해 주세요.",
        f"대상 채널: {destination.mention}",
    ]
    if isinstance(source_channel, (discord.TextChannel, discord.Thread)):
        lines.append(f"원본 채널: {source_channel.mention}")
    lines.append(f"선택됨: {len(selected_message_ids)}개 / 후보 {len(messages)}개")
    lines.append("아래 선택 메뉴에서 하나 이상 고른 뒤 `선택한 메시지 이동`을 누르세요.")
    if capped:
        lines.append(
            f"Discord 선택 메뉴 제한으로 최근 {MAX_MOVE_SELECTION_MESSAGES}개만 표시합니다."
        )
    lines.append("")

    for index, message in enumerate(messages, start=1):
        marker = "☑️" if message.id in selected_message_ids else "⬜"
        author_name = truncate_text(
            getattr(message.author, "display_name", str(message.author)),
            20,
        )
        lines.append(f"{marker} {index}. {author_name}: {message_preview(message)}")

    return truncate_text("\n".join(lines), 1900)


def build_move_option_label(index: int, message: discord.Message) -> str:
    author_name = truncate_text(
        getattr(message.author, "display_name", str(message.author)),
        35,
    )
    return truncate_text(f"{index}. {author_name}", 100)


def build_move_option_description(message: discord.Message) -> str:
    return truncate_text(message_preview(message, 95), 100)


def build_move_result_message(
    destination: MoveDestinationChannel,
    result: MoveResult,
) -> str:
    parts = [f"📦 {destination.mention}(으)로 메시지 {result.moved_count}개를 이동했습니다."]
    if result.copied_only_count:
        parts.append(
            f"원본 삭제에 실패해 복사만 된 메시지 {result.copied_only_count}개가 있습니다."
        )
    if result.failed_count:
        parts.append(f"이동에 실패한 메시지 {result.failed_count}개가 있습니다.")

    return "\n".join(parts)


def build_move_reason(
    interaction: discord.Interaction,
    source_label: str,
) -> str:
    return f"{source_label} by {interaction.user} ({interaction.user.id})"


def requester_can_move_messages(interaction: discord.Interaction) -> bool:
    return (
        interaction.guild is not None
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.manage_messages
    )


def get_bot_member(
    bot: commands.Bot,
    guild: discord.Guild,
) -> discord.Member | None:
    if bot.user is None:
        return None

    return guild.get_member(bot.user.id)


def bot_can_read_and_delete(
    bot: commands.Bot,
    channel: MoveSourceChannel,
) -> bool:
    member = get_bot_member(bot, channel.guild)
    if member is None:
        return False

    permissions = channel.permissions_for(member)
    return (
        permissions.view_channel
        and permissions.read_message_history
        and permissions.manage_messages
    )


def bot_can_post_moved_messages(
    bot: commands.Bot,
    channel: MoveDestinationChannel,
) -> bool:
    member = get_bot_member(bot, channel.guild)
    if member is None:
        return False

    permissions = channel.permissions_for(member)
    can_send = permissions.send_messages or getattr(
        permissions,
        "send_messages_in_threads",
        False,
    )
    return (
        permissions.view_channel
        and can_send
        and permissions.embed_links
        and permissions.attach_files
    )


async def collect_recent_movable_messages(
    channel: MoveSourceChannel,
    count: int,
    *,
    author_id: int | None = None,
) -> list[discord.Message]:
    messages: list[discord.Message] = []
    async for message in channel.history(limit=None):
        if not message.type.is_deletable():
            continue

        if author_id is not None and message.author.id != author_id:
            continue

        messages.append(message)
        if len(messages) >= count:
            break

    messages.reverse()
    return messages


async def collect_move_candidates(
    channel: MoveSourceChannel,
    count: int,
    *,
    author_id: int | None = None,
) -> tuple[list[discord.Message], bool]:
    capped = count > MAX_MOVE_SELECTION_MESSAGES
    messages = await collect_recent_movable_messages(
        channel,
        min(count, MAX_MOVE_SELECTION_MESSAGES),
        author_id=author_id,
    )
    return messages, capped


def build_moved_message_embed(
    message: discord.Message,
    source_channel: MoveSourceChannel,
) -> discord.Embed:
    description = truncate_text(message.content or "*텍스트 없이 첨부만 있는 메시지입니다.*", 4000)
    embed = discord.Embed(
        description=description,
        color=discord.Color.blurple(),
        timestamp=message.created_at,
    )
    embed.set_author(
        name=str(message.author),
        icon_url=message.author.display_avatar.url,
    )
    embed.add_field(name="원본 채널", value=source_channel.mention, inline=True)
    embed.add_field(name="작성자", value=message.author.mention, inline=True)

    if message.attachments:
        attachment_names = ", ".join(
            truncate_text(attachment.filename, 80) for attachment in message.attachments
        )
        embed.add_field(name="첨부 파일", value=truncate_text(attachment_names, 1024), inline=False)

    if message.reference and isinstance(message.reference.resolved, discord.Message):
        replied_message = message.reference.resolved
        reply_preview = truncate_text(
            replied_message.content or "(내용 없음)",
            180,
        )
        embed.add_field(
            name="답장 대상",
            value=f"{replied_message.author.mention}: {reply_preview}",
            inline=False,
        )

    embed.set_footer(text=f"원본 메시지 ID: {message.id}")
    return embed


async def copy_message_to_channel(
    message: discord.Message,
    destination: MoveDestinationChannel,
    source_channel: MoveSourceChannel,
) -> None:
    files = [await attachment.to_file() for attachment in message.attachments]
    await destination.send(
        embed=build_moved_message_embed(message, source_channel),
        files=files,
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def move_messages(
    messages: list[discord.Message],
    *,
    destination: MoveDestinationChannel,
) -> MoveResult:
    moved_count = 0
    copied_only_count = 0
    failed_count = 0

    for message in messages:
        source_channel = message.channel
        if not isinstance(source_channel, (discord.TextChannel, discord.Thread)):
            failed_count += 1
            continue

        if not message.type.is_deletable():
            failed_count += 1
            continue

        try:
            await copy_message_to_channel(message, destination, source_channel)
        except (discord.Forbidden, discord.HTTPException):
            failed_count += 1
            continue

        try:
            await message.delete()
            moved_count += 1
        except discord.NotFound:
            moved_count += 1
        except (discord.Forbidden, discord.HTTPException):
            copied_only_count += 1

    return MoveResult(
        moved_count=moved_count,
        copied_only_count=copied_only_count,
        failed_count=failed_count,
    )


def prompt_looks_like_move_request(prompt: str) -> bool:
    has_destination_hint = (
        HERE_PATTERN.search(prompt) is not None
        or USER_MENTION_PATTERN.search(prompt) is not None
        or CHANNEL_MENTION_PATTERN.search(prompt) is not None
        or "#" in prompt
    )
    return bool(MOVE_ACTION_PATTERN.search(prompt) and has_destination_hint)


def parse_move_count(prompt: str) -> int:
    match = re.search(r"(\d+)\s*개", prompt)
    if match is None:
        return 1

    try:
        count = int(match.group(1))
    except ValueError:
        return 1

    return max(1, min(count, MAX_MOVE_SELECTION_MESSAGES))


def find_destination_channel_by_text(
    guild: discord.Guild,
    prompt: str,
) -> MoveDestinationChannel | None:
    normalized = prompt.casefold()
    candidates = [
        channel
        for channel in guild.channels
        if isinstance(channel, (discord.TextChannel, discord.Thread))
        and f"#{channel.name}".casefold() in normalized
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda channel: len(channel.name), reverse=True)
    return candidates[0]


def resolve_destination_channel_from_prompt(
    guild: discord.Guild,
    current_channel: discord.abc.MessageableChannel | None,
    prompt: str,
) -> tuple[MoveDestinationChannel | None, str | None]:
    channel_getter = getattr(guild, "get_channel_or_thread", guild.get_channel)
    mentioned_channel_ids = [
        int(match.group(1)) for match in CHANNEL_MENTION_PATTERN.finditer(prompt)
    ]
    unique_channel_ids = list(dict.fromkeys(mentioned_channel_ids))
    if len(unique_channel_ids) > 1:
        return None, "대상 채널은 하나만 지정해 주세요."

    if unique_channel_ids:
        channel = channel_getter(unique_channel_ids[0])
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel, None
        return None, "대상 채널을 찾지 못했습니다."

    if HERE_PATTERN.search(prompt):
        if isinstance(current_channel, (discord.TextChannel, discord.Thread)):
            return current_channel, None
        return None, "현재 채널로 이동은 텍스트 채널이나 스레드에서만 사용할 수 있습니다."

    channel = find_destination_channel_by_text(guild, prompt)
    if channel is not None:
        return channel, None

    return None, "대상 채널을 찾지 못했습니다. 채널 멘션이나 `#채널명`으로 써 주세요."


def parse_move_request(
    interaction: discord.Interaction,
    prompt: str,
) -> tuple[bool, ParsedMoveRequest | None, str | None]:
    guild = interaction.guild
    if guild is None:
        return False, None, None

    if not prompt_looks_like_move_request(prompt):
        return False, None, None

    destination, destination_error = resolve_destination_channel_from_prompt(
        guild,
        interaction.channel,
        prompt,
    )
    if destination_error is not None or destination is None:
        return True, None, destination_error or "대상 채널을 찾지 못했습니다."

    author_ids = [int(match.group(1)) for match in USER_MENTION_PATTERN.finditer(prompt)]
    author_id = author_ids[0] if author_ids else None
    if len(dict.fromkeys(author_ids)) > 1:
        return True, None, "유저 지정 이동은 한 명만 멘션해 주세요."

    needs_source_channel_selection = bool(author_id is not None and HERE_PATTERN.search(prompt))
    return True, ParsedMoveRequest(
        destination_channel_id=destination.id,
        count=parse_move_count(prompt),
        author_id=author_id,
        needs_source_channel_selection=needs_source_channel_selection,
    ), None


async def send_move_selection(
    interaction: discord.Interaction,
    *,
    cog: "MoveCog",
    destination: MoveDestinationChannel,
    messages: list[discord.Message],
    source_label: str,
    capped: bool,
) -> None:
    view = MoveMessageSelectionView(
        cog=cog,
        requester_id=interaction.user.id,
        destination=destination,
        messages=messages,
        source_label=source_label,
        capped=capped,
    )
    if interaction.response.is_done():
        message = await interaction.edit_original_response(
            content=view.build_content(),
            view=view,
        )
    else:
        await interaction.response.send_message(
            view.build_content(),
            view=view,
            ephemeral=True,
        )
        message = await interaction.original_response()

    view.message = message


class MoveMessageSelect(discord.ui.Select):
    def __init__(self, parent_view: "MoveMessageSelectionView") -> None:
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label=build_move_option_label(index, message),
                description=build_move_option_description(message),
                value=str(message.id),
                default=message.id in parent_view.selected_message_ids,
            )
            for index, message in enumerate(parent_view.messages, start=1)
        ]
        super().__init__(
            placeholder="이동할 메시지를 하나 이상 선택하세요",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.parent_view.requester_id:
            await interaction.response.send_message(
                "이 선택 메뉴는 명령어를 실행한 사용자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        self.parent_view.selected_message_ids = {int(value) for value in self.values}
        for option in self.options:
            option.default = int(option.value) in self.parent_view.selected_message_ids
        self.parent_view.confirm.disabled = not self.parent_view.selected_message_ids
        await interaction.response.edit_message(
            content=self.parent_view.build_content(),
            view=self.parent_view,
        )


class MoveMessageSelectionView(discord.ui.View):
    def __init__(
        self,
        cog: "MoveCog",
        requester_id: int,
        destination: MoveDestinationChannel,
        messages: list[discord.Message],
        source_label: str,
        *,
        capped: bool,
    ) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.requester_id = requester_id
        self.destination = destination
        self.messages = messages
        self.source_label = source_label
        self.capped = capped
        self.selected_message_ids: set[int] = set()
        self.message: discord.InteractionMessage | None = None
        self.add_item(MoveMessageSelect(self))
        self.confirm.disabled = True

    def build_content(self) -> str:
        return build_move_selection_notice(
            self.destination,
            self.messages,
            self.selected_message_ids,
            capped=self.capped,
        )

    def get_selected_messages(self) -> list[discord.Message]:
        selected_ids = self.selected_message_ids
        return [message for message in self.messages if message.id in selected_ids]

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
            await self.message.edit(content=build_move_timeout_message(), view=None)
        except (discord.HTTPException, discord.NotFound):
            pass

    @discord.ui.button(label="선택한 메시지 이동", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        selected_messages = self.get_selected_messages()
        if not selected_messages:
            await interaction.response.send_message(
                "먼저 이동할 메시지를 선택해 주세요.",
                ephemeral=True,
            )
            return

        validation_error = self.cog.validate_move_request(
            interaction,
            source_channel=selected_messages[0].channel,
            destination=self.destination,
        )
        if validation_error is not None:
            await interaction.response.send_message(validation_error, ephemeral=True)
            return

        await interaction.response.defer()

        result = await move_messages(
            selected_messages,
            destination=self.destination,
        )
        await interaction.edit_original_response(
            content=build_move_result_message(self.destination, result),
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
            content=build_move_cancel_message(),
            view=None,
        )
        self.stop()


class MoveConfirmView(discord.ui.View):
    def __init__(
        self,
        cog: "MoveCog",
        requester_id: int,
        destination: MoveDestinationChannel,
        messages: list[discord.Message],
        source_label: str,
    ) -> None:
        super().__init__(timeout=30)
        self.cog = cog
        self.requester_id = requester_id
        self.destination = destination
        self.messages = messages
        self.source_label = source_label
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
            await self.message.edit(content=build_move_timeout_message(), view=None)
        except (discord.HTTPException, discord.NotFound):
            pass

    @discord.ui.button(label="확인", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        validation_error = self.cog.validate_move_request(
            interaction,
            source_channel=self.messages[0].channel if self.messages else None,
            destination=self.destination,
        )
        if validation_error is not None:
            await interaction.response.send_message(validation_error, ephemeral=True)
            return

        await interaction.response.defer()

        result = await move_messages(
            self.messages,
            destination=self.destination,
        )
        await interaction.edit_original_response(
            content=build_move_result_message(self.destination, result),
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
            content=build_move_cancel_message(),
            view=None,
        )
        self.stop()


class MoveChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, parent_view: "MoveSelectView") -> None:
        super().__init__(
            placeholder="이동할 대상 채널을 선택하세요",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=1,
            max_values=1,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.parent_view.requester_id:
            await interaction.response.send_message(
                "이 선택 메뉴는 명령어를 실행한 사용자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        selected_channel = self.values[0]
        if not isinstance(selected_channel, discord.TextChannel):
            await interaction.response.send_message(
                "텍스트 채널만 선택할 수 있습니다.",
                ephemeral=True,
            )
            return

        self.parent_view.destination = selected_channel
        self.parent_view.confirm.disabled = False
        await interaction.response.edit_message(
            content=self.parent_view.build_content(),
            view=self.parent_view,
        )


class MoveSelectView(discord.ui.View):
    def __init__(
        self,
        cog: "MoveCog",
        requester_id: int,
        message_to_move: discord.Message,
        source_label: str,
    ) -> None:
        super().__init__(timeout=30)
        self.cog = cog
        self.requester_id = requester_id
        self.message_to_move = message_to_move
        self.source_label = source_label
        self.destination: MoveDestinationChannel | None = None
        self.message: discord.InteractionMessage | None = None
        self.add_item(MoveChannelSelect(self))
        self.confirm.disabled = True

    def build_content(self) -> str:
        if self.destination is None:
            return "이 메시지를 이동할 대상 채널을 선택해 주세요."

        return build_move_prompt(self.destination, 1)

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
            await self.message.edit(content=build_move_timeout_message(), view=None)
        except (discord.HTTPException, discord.NotFound):
            pass

    @discord.ui.button(label="확인", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if self.destination is None:
            await interaction.response.send_message(
                "먼저 대상 채널을 선택해 주세요.",
                ephemeral=True,
            )
            return

        validation_error = self.cog.validate_move_request(
            interaction,
            source_channel=self.message_to_move.channel,
            destination=self.destination,
        )
        if validation_error is not None:
            await interaction.response.send_message(validation_error, ephemeral=True)
            return

        await interaction.response.defer()

        result = await move_messages(
            [self.message_to_move],
            destination=self.destination,
        )
        await interaction.edit_original_response(
            content=build_move_result_message(self.destination, result),
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
            content=build_move_cancel_message(),
            view=None,
        )
        self.stop()


class MoveSourceChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, parent_view: "MoveSourceSelectView") -> None:
        super().__init__(
            placeholder="메시지를 가져올 원본 채널을 선택하세요",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=1,
            max_values=1,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.parent_view.requester_id:
            await interaction.response.send_message(
                "이 선택 메뉴는 명령어를 실행한 사용자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        selected_channel = self.values[0]
        if not isinstance(selected_channel, discord.TextChannel):
            await interaction.response.send_message(
                "텍스트 채널만 선택할 수 있습니다.",
                ephemeral=True,
            )
            return

        self.parent_view.source_channel = selected_channel
        self.parent_view.confirm.disabled = False
        await interaction.response.edit_message(
            content=self.parent_view.build_content(),
            view=self.parent_view,
        )


class MoveSourceSelectView(discord.ui.View):
    def __init__(
        self,
        cog: "MoveCog",
        requester_id: int,
        destination: MoveDestinationChannel,
        author_id: int,
        count: int,
        source_label: str,
    ) -> None:
        super().__init__(timeout=30)
        self.cog = cog
        self.requester_id = requester_id
        self.destination = destination
        self.author_id = author_id
        self.count = count
        self.source_label = source_label
        self.source_channel: discord.TextChannel | None = None
        self.message: discord.InteractionMessage | None = None
        self.add_item(MoveSourceChannelSelect(self))
        self.confirm.disabled = True

    def build_content(self) -> str:
        if self.source_channel is None:
            return (
                "가져올 원본 채널을 선택해 주세요.\n"
                "선택한 유저의 최근 메시지를 현재 채널로 이동합니다."
            )

        return (
            f"⚠️ {self.source_channel.mention}에서 선택한 유저의 최근 메시지 "
            f"{self.count}개를 {self.destination.mention}(으)로 이동하시겠습니까?"
        )

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
            await self.message.edit(content=build_move_timeout_message(), view=None)
        except (discord.HTTPException, discord.NotFound):
            pass

    @discord.ui.button(label="확인", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if self.source_channel is None:
            await interaction.response.send_message(
                "먼저 원본 채널을 선택해 주세요.",
                ephemeral=True,
            )
            return

        validation_error = self.cog.validate_move_request(
            interaction,
            source_channel=self.source_channel,
            destination=self.destination,
        )
        if validation_error is not None:
            await interaction.response.send_message(validation_error, ephemeral=True)
            return

        await interaction.response.defer()

        messages, capped = await collect_move_candidates(
            self.source_channel,
            self.count,
            author_id=self.author_id,
        )
        if not messages:
            await interaction.edit_original_response(
                content="선택한 채널에서 이동할 메시지를 찾지 못했습니다.",
                view=None,
            )
            return

        await send_move_selection(
            interaction,
            cog=self.cog,
            destination=self.destination,
            messages=messages,
            source_label=self.source_label,
            capped=capped,
        )
        self.stop()

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            content=build_move_cancel_message(),
            view=None,
        )
        self.stop()


class MoveCog(commands.Cog):
    def __init__(self, bot: "CoraxBot") -> None:
        self.bot = bot
        self.move_message_context_menu = app_commands.ContextMenu(
            name="메시지 이동",
            callback=self.move_message_context,
        )
        self.move_message_context_menu.default_permissions = discord.Permissions(
            manage_messages=True
        )

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.move_message_context_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.move_message_context_menu.name,
            type=self.move_message_context_menu.type,
        )

    def validate_move_request(
        self,
        interaction: discord.Interaction,
        *,
        source_channel: discord.abc.MessageableChannel | None,
        destination: MoveDestinationChannel,
    ) -> str | None:
        if interaction.guild is None:
            return "이 기능은 서버에서만 사용할 수 있습니다."

        if not requester_can_move_messages(interaction):
            return "메시지 이동은 메시지 관리 권한이 있는 사람만 할 수 있습니다."

        if not isinstance(source_channel, (discord.TextChannel, discord.Thread)):
            return "이 채널에서는 메시지를 이동할 수 없습니다."

        if source_channel.guild.id != destination.guild.id:
            return "같은 서버 안의 채널로만 이동할 수 있습니다."

        if source_channel.id == destination.id:
            return "같은 채널로는 이동할 수 없습니다."

        if not bot_can_read_and_delete(self.bot, source_channel):
            return "봇에 원본 채널의 메시지 보기/삭제 권한이 없습니다."

        if not bot_can_post_moved_messages(self.bot, destination):
            return "봇에 대상 채널의 메시지 전송, 임베드, 파일 첨부 권한이 없습니다."

        return None

    async def dispatch_move_request(
        self,
        interaction: discord.Interaction,
        request: ParsedMoveRequest,
        *,
        source_label: str,
    ) -> None:
        guild = interaction.guild
        channel_getter = (
            getattr(guild, "get_channel_or_thread", guild.get_channel)
            if guild is not None
            else None
        )
        destination_channel = (
            channel_getter(request.destination_channel_id)
            if channel_getter is not None
            else None
        )
        if not isinstance(destination_channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "대상 채널을 찾지 못했습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        if request.needs_source_channel_selection:
            if request.author_id is None:
                await interaction.edit_original_response(
                    content="이동할 유저를 찾지 못했습니다.",
                    view=None,
                )
                return

            view = MoveSourceSelectView(
                cog=self,
                requester_id=interaction.user.id,
                destination=destination_channel,
                author_id=request.author_id,
                count=request.count,
                source_label=source_label,
            )
            message = await interaction.edit_original_response(
                content=view.build_content(),
                view=view,
            )
            view.message = message
            return

        validation_error = self.validate_move_request(
            interaction,
            source_channel=interaction.channel,
            destination=destination_channel,
        )
        if validation_error is not None:
            await interaction.edit_original_response(content=validation_error, view=None)
            return

        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            await interaction.edit_original_response(
                content="이 채널에서는 메시지를 이동할 수 없습니다.",
                view=None,
            )
            return

        messages, capped = await collect_move_candidates(
            interaction.channel,
            request.count,
            author_id=request.author_id,
        )
        if not messages:
            await interaction.edit_original_response(
                content="이동할 메시지를 찾지 못했습니다.",
                view=None,
            )
            return

        await send_move_selection(
            interaction,
            cog=self,
            destination=destination_channel,
            messages=messages,
            source_label=source_label,
            capped=capped,
        )

    @app_commands.command(name="move", description="현재 채널의 최근 메시지 여러 개 이동")
    @app_commands.rename(destination="대상채널", count="개수")
    @app_commands.describe(
        destination="메시지를 옮길 대상 채널",
        count="선택 후보로 불러올 최근 메시지 개수 (1~25)",
    )
    @app_commands.default_permissions(manage_messages=True)
    async def move(
        self,
        interaction: discord.Interaction,
        destination: discord.TextChannel,
        count: app_commands.Range[int, 1, MAX_MOVE_SELECTION_MESSAGES],
    ) -> None:
        if interaction.channel is None:
            await interaction.response.send_message(
                "현재 채널 정보를 확인할 수 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        validation_error = self.validate_move_request(
            interaction,
            source_channel=interaction.channel,
            destination=destination,
        )
        if validation_error is not None:
            await interaction.edit_original_response(content=validation_error, view=None)
            return

        source_channel = interaction.channel
        if not isinstance(source_channel, (discord.TextChannel, discord.Thread)):
            await interaction.edit_original_response(
                content="이 채널에서는 메시지를 이동할 수 없습니다.",
                view=None,
            )
            return

        messages, capped = await collect_move_candidates(source_channel, count)
        if not messages:
            await interaction.edit_original_response(
                content="이동할 최근 메시지가 없습니다.",
                view=None,
            )
            return

        await send_move_selection(
            interaction,
            cog=self,
            destination=destination,
            messages=messages,
            source_label="/move",
            capped=capped,
        )

    async def move_message_context(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "이 기능은 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not requester_can_move_messages(interaction):
            await interaction.response.send_message(
                "메시지 이동은 메시지 관리 권한이 있는 사람만 할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "이 메시지는 이동할 수 없습니다.",
                ephemeral=True,
            )
            return

        if not bot_can_read_and_delete(self.bot, message.channel):
            await interaction.response.send_message(
                "봇에 원본 채널의 메시지 보기/삭제 권한이 없습니다.",
                ephemeral=True,
            )
            return

        if not message.type.is_deletable():
            await interaction.response.send_message(
                "이 유형의 메시지는 이동할 수 없습니다.",
                ephemeral=True,
            )
            return

        view = MoveSelectView(
            cog=self,
            requester_id=interaction.user.id,
            message_to_move=message,
            source_label="message_context",
        )
        await interaction.response.send_message(
            view.build_content(),
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()


async def setup(bot: "CoraxBot") -> None:
    await bot.add_cog(MoveCog(bot))

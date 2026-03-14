from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from cogs.moderation import (
    ClearConfirmView,
    ModerationChannel,
    build_clear_prompt,
)
from cogs.move import parse_move_request
from cogs.roles import (
    parse_nickname_change_request,
    parse_role_grant_request,
    send_nickname_confirmation,
    send_role_grant_confirmation,
)
from services.gemini_client import (
    CommandPlan,
    GeminiConfigurationError,
    GeminiError,
)

if TYPE_CHECKING:
    from bot import CoraxBot
    from cogs.move import MoveCog


CORAX_SYSTEM_PROMPT = """
You are 또봇 (Ttobot), a Discord bot assistant for a Korean-speaking community.
Answer in Korean unless the user explicitly asks for another language.
Be concise, practical, and accurate.
If the user asks about code, explain likely causes and fixes clearly.
Do not claim to have performed actions unless the bot actually executed them.
""".strip()


COMMAND_SYSTEM_PROMPT = """
You convert Korean natural-language admin requests into a safe execution plan.
Supported internal actions:
- clear: delete recent messages in the current channel when the user gives a concrete count from 1 to 100
- clear_all: delete all deletable messages in the current channel, including old messages, when the user clearly says all/everything/전부/전체

Rules:
- Use status="execute" with action="clear" only when the user clearly wants recent-message deletion and gives a concrete count from 1 to 100.
- Use status="execute" with action="clear_all" only when the user clearly wants every deletable message in the channel removed.
- If the user wants deletion but does not specify a clear count and does not clearly say all, use status="clarify", action="clear", amount=0.
- If the request is unrelated, unsupported, or unsafe, use status="reject" and action="unsupported".
- Never infer a count when the user did not provide one.
- The message must be a short Korean sentence for the user.
""".strip()


def member_can_manage_messages(user: discord.abc.User) -> bool:
    return isinstance(user, discord.Member) and user.guild_permissions.manage_messages


def bot_can_manage_messages(
    bot: commands.Bot,
    channel: ModerationChannel,
) -> bool:
    if bot.user is None:
        return False

    member = channel.guild.get_member(bot.user.id)
    if member is None:
        return False

    permissions = channel.permissions_for(member)
    return permissions.manage_messages and permissions.read_message_history


async def send_clear_confirmation(
    interaction: discord.Interaction,
    channel: ModerationChannel,
    requester_id: int,
    amount: int | None,
) -> None:
    view = ClearConfirmView(
        channel=channel,
        requester_id=requester_id,
        amount=amount,
    )

    if interaction.response.is_done():
        message = await interaction.followup.send(
            content=build_clear_prompt(amount),
            view=view,
            ephemeral=True,
            wait=True,
        )
    else:
        await interaction.response.send_message(
            build_clear_prompt(amount),
            view=view,
            ephemeral=True,
        )
        message = await interaction.original_response()

    view.message = message


class ClearAmountModal(discord.ui.Modal, title="삭제 개수 입력"):
    amount = discord.ui.TextInput(
        label="삭제할 메시지 개수",
        placeholder="1~100",
        min_length=1,
        max_length=3,
    )

    def __init__(
        self,
        bot: "CoraxBot",
        channel: ModerationChannel,
        requester_id: int,
        prompt_message: discord.InteractionMessage | None,
    ) -> None:
        super().__init__()
        self.bot = bot
        self.channel = channel
        self.requester_id = requester_id
        self.prompt_message = prompt_message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "이 입력 창은 명령어를 실행한 사용자만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not member_can_manage_messages(interaction.user):
            await interaction.response.send_message(
                "메시지 관리 권한이 없습니다.",
                ephemeral=True,
            )
            return

        if not bot_can_manage_messages(self.bot, self.channel):
            await interaction.response.send_message(
                "봇에 메시지 관리 또는 채팅 기록 보기 권한이 없습니다.",
                ephemeral=True,
            )
            return

        try:
            amount = int(self.amount.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "숫자만 입력해 주세요.",
                ephemeral=True,
            )
            return

        if amount < 1 or amount > 100:
            await interaction.response.send_message(
                "삭제할 메시지 수는 1개에서 100개 사이여야 합니다.",
                ephemeral=True,
            )
            return

        if self.prompt_message is not None:
            try:
                await self.prompt_message.edit(
                    content="삭제 개수 입력이 완료되었습니다.",
                    view=None,
                )
            except (discord.HTTPException, discord.NotFound):
                pass

        await send_clear_confirmation(
            interaction=interaction,
            channel=self.channel,
            requester_id=self.requester_id,
            amount=amount,
        )


class ClearAmountView(discord.ui.View):
    def __init__(
        self,
        bot: "CoraxBot",
        channel: ModerationChannel,
        requester_id: int,
    ) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.channel = channel
        self.requester_id = requester_id
        self.message: discord.InteractionMessage | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True

        await interaction.response.send_message(
            "이 선택 버튼은 명령어를 실행한 사용자만 누를 수 있습니다.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        if self.message is None:
            return

        try:
            await self.message.edit(
                content="삭제 개수 선택 시간이 만료되었습니다.",
                view=None,
            )
        except (discord.HTTPException, discord.NotFound):
            pass

    async def close_prompt(self, content: str) -> None:
        if self.message is None:
            return

        try:
            await self.message.edit(content=content, view=None)
        except (discord.HTTPException, discord.NotFound):
            pass

    async def handle_quick_amount(
        self,
        interaction: discord.Interaction,
        amount: int,
    ) -> None:
        if not member_can_manage_messages(interaction.user):
            await interaction.response.send_message(
                "메시지 관리 권한이 없습니다.",
                ephemeral=True,
            )
            return

        if not bot_can_manage_messages(self.bot, self.channel):
            await interaction.response.send_message(
                "봇에 메시지 관리 또는 채팅 기록 보기 권한이 없습니다.",
                ephemeral=True,
            )
            return

        await self.close_prompt("삭제 개수 선택이 완료되었습니다.")
        self.stop()
        await send_clear_confirmation(
            interaction=interaction,
            channel=self.channel,
            requester_id=self.requester_id,
            amount=amount,
        )

    @discord.ui.button(label="10개", style=discord.ButtonStyle.secondary)
    async def ten(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self.handle_quick_amount(interaction, 10)

    @discord.ui.button(label="20개", style=discord.ButtonStyle.secondary)
    async def twenty(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self.handle_quick_amount(interaction, 20)

    @discord.ui.button(label="50개", style=discord.ButtonStyle.secondary)
    async def fifty(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self.handle_quick_amount(interaction, 50)

    @discord.ui.button(label="직접 입력", style=discord.ButtonStyle.primary)
    async def custom(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            ClearAmountModal(
                bot=self.bot,
                channel=self.channel,
                requester_id=self.requester_id,
                prompt_message=self.message,
            )
        )

    @discord.ui.button(label="취소", style=discord.ButtonStyle.danger)
    async def cancel(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            content="메시지 삭제 요청을 취소했습니다.",
            view=None,
        )
        self.stop()


class AICog(commands.Cog):
    def __init__(self, bot: "CoraxBot"):
        self.bot = bot

    def get_target_channel(
        self,
        interaction: discord.Interaction,
    ) -> ModerationChannel | None:
        channel = interaction.channel
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel

        return None

    def can_manage_messages(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None and member_can_manage_messages(
            interaction.user
        )

    def bot_can_manage_messages(self, channel: ModerationChannel) -> bool:
        return bot_can_manage_messages(self.bot, channel)

    def chunk_text(self, text: str, chunk_size: int = 1800) -> list[str]:
        if len(text) <= chunk_size:
            return [text]

        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= chunk_size:
                chunks.append(remaining)
                break

            split_at = remaining.rfind("\n", 0, chunk_size)
            if split_at <= 0:
                split_at = chunk_size

            chunks.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()

        return chunks

    def ensure_gemini(self) -> None:
        if not self.bot.gemini_service.is_configured:
            raise GeminiConfigurationError("GEMINI_API_KEY가 설정되지 않았습니다.")

    def get_move_cog(self) -> "MoveCog | None":
        move_cog = self.bot.get_cog("MoveCog")
        if move_cog is None:
            return None

        return move_cog  # type: ignore[return-value]

    @app_commands.command(name="ttobot", description="또봇 AI에게 질문")
    @app_commands.rename(prompt="질문")
    @app_commands.describe(prompt="또봇 AI에게 보낼 질문")
    async def ttobot(
        self,
        interaction: discord.Interaction,
        prompt: app_commands.Range[str, 1, 2000],
    ) -> None:
        question = prompt.strip()
        if not question:
            await interaction.response.send_message(
                "질문을 비워둘 수 없습니다.",
                ephemeral=True,
            )
            return

        role_handled, role_request, role_error = parse_role_grant_request(
            self.bot,
            interaction,
            question,
        )
        if role_handled:
            if role_error is not None or role_request is None:
                await interaction.response.send_message(
                    role_error or "역할 부여 요청을 처리하지 못했습니다.",
                    ephemeral=True,
                )
                return

            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message(
                    "이 명령어는 서버에서만 사용할 수 있습니다.",
                    ephemeral=True,
                )
                return

            target_member = guild.get_member(role_request.target_member_id)
            role = (
                guild.get_role(role_request.existing_role_id)
                if role_request.existing_role_id is not None
                else None
            )
            if target_member is None:
                await interaction.response.send_message(
                    "대상 유저를 찾지 못했습니다.",
                    ephemeral=True,
                )
                return

            await send_role_grant_confirmation(
                interaction,
                self.bot,
                target_member,
                role_request.role_name,
                existing_role=role,
                source_label="/ttobot",
            )
            return

        move_handled, move_request, move_error = parse_move_request(
            interaction,
            question,
        )
        if move_handled:
            if move_error is not None or move_request is None:
                await interaction.response.send_message(
                    move_error or "메시지 이동 요청을 처리하지 못했습니다.",
                    ephemeral=True,
                )
                return

            move_cog = self.get_move_cog()
            if move_cog is None:
                await interaction.response.send_message(
                    "메시지 이동 기능을 사용할 수 없습니다.",
                    ephemeral=True,
                )
                return

            await move_cog.dispatch_move_request(
                interaction,
                move_request,
                source_label="/ttobot",
            )
            return

        nickname_handled, nickname_request, nickname_error = parse_nickname_change_request(
            self.bot,
            interaction,
            question,
        )
        if nickname_handled:
            if nickname_error is not None or nickname_request is None:
                await interaction.response.send_message(
                    nickname_error or "별명 변경 요청을 처리하지 못했습니다.",
                    ephemeral=True,
                )
                return

            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message(
                    "이 명령어는 서버에서만 사용할 수 있습니다.",
                    ephemeral=True,
                )
                return

            target_member = guild.get_member(nickname_request.target_member_id)
            if target_member is None:
                await interaction.response.send_message(
                    "대상 유저를 찾지 못했습니다.",
                    ephemeral=True,
                )
                return

            await send_nickname_confirmation(
                interaction,
                self.bot,
                target_member,
                nickname_request.nickname,
                source_label="/ttobot",
            )
            return

        await interaction.response.defer(thinking=True)

        try:
            self.ensure_gemini()
            answer = await self.bot.gemini_service.generate_text(
                prompt=question,
                system_instruction=CORAX_SYSTEM_PROMPT,
                temperature=0.7,
                max_output_tokens=1200,
            )
        except GeminiConfigurationError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except GeminiError as error:
            await interaction.followup.send(
                f"또봇 AI 응답 중 오류가 발생했습니다: {error}",
                ephemeral=True,
            )
            return

        chunks = self.chunk_text(answer)
        for chunk in chunks:
            await interaction.followup.send(chunk)

    @app_commands.command(name="command", description="자연어를 내부 관리 명령으로 해석")
    @app_commands.rename(prompt="요청")
    @app_commands.describe(prompt="예: 최근 메시지 20개 삭제해줘")
    @app_commands.default_permissions(manage_messages=True)
    async def command(
        self,
        interaction: discord.Interaction,
        prompt: app_commands.Range[str, 1, 1000],
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not self.can_manage_messages(interaction):
            await interaction.response.send_message(
                "이 AI 관리 명령은 메시지 관리 권한이 있는 사람만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        channel = self.get_target_channel(interaction)
        if channel is None:
            await interaction.response.send_message(
                "이 채널에서는 AI 관리 명령을 사용할 수 없습니다.",
                ephemeral=True,
            )
            return

        if not self.bot_can_manage_messages(channel):
            await interaction.response.send_message(
                "봇에 메시지 관리 또는 채팅 기록 보기 권한이 없습니다.",
                ephemeral=True,
            )
            return

        move_handled, move_request, move_error = parse_move_request(
            interaction,
            prompt.strip(),
        )
        if move_handled:
            if move_error is not None or move_request is None:
                await interaction.response.send_message(
                    move_error or "메시지 이동 요청을 처리하지 못했습니다.",
                    ephemeral=True,
                )
                return

            move_cog = self.get_move_cog()
            if move_cog is None:
                await interaction.response.send_message(
                    "메시지 이동 기능을 사용할 수 없습니다.",
                    ephemeral=True,
                )
                return

            await move_cog.dispatch_move_request(
                interaction,
                move_request,
                source_label="/command",
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            self.ensure_gemini()
            plan = await self.bot.gemini_service.plan_command(
                prompt=prompt.strip(),
                system_instruction=COMMAND_SYSTEM_PROMPT,
            )
        except GeminiConfigurationError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except GeminiError as error:
            await interaction.followup.send(
                f"AI 명령 해석 중 오류가 발생했습니다: {error}",
                ephemeral=True,
            )
            return

        await self.dispatch_plan(interaction, channel, plan)

    async def dispatch_plan(
        self,
        interaction: discord.Interaction,
        channel: ModerationChannel,
        plan: CommandPlan,
    ) -> None:
        if plan.status == "execute" and plan.action == "clear":
            if plan.amount < 1 or plan.amount > 100:
                await interaction.followup.send(
                    "삭제할 메시지 수는 1개에서 100개 사이여야 합니다.",
                    ephemeral=True,
                )
                return

            await send_clear_confirmation(
                interaction=interaction,
                channel=channel,
                requester_id=interaction.user.id,
                amount=plan.amount,
            )
            return

        if plan.status == "execute" and plan.action == "clear_all":
            await send_clear_confirmation(
                interaction=interaction,
                channel=channel,
                requester_id=interaction.user.id,
                amount=None,
            )
            return

        if plan.status == "clarify" and plan.action == "clear":
            view = ClearAmountView(
                bot=self.bot,
                channel=channel,
                requester_id=interaction.user.id,
            )
            message = await interaction.followup.send(
                content=plan.message,
                view=view,
                ephemeral=True,
                wait=True,
            )
            view.message = message
            return

        await interaction.followup.send(plan.message, ephemeral=True)


async def setup(bot: "CoraxBot") -> None:
    await bot.add_cog(AICog(bot))

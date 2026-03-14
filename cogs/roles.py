from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from bot import CoraxBot


USER_MENTION_PATTERN = re.compile(r"<@!?(\d+)>")
ROLE_MENTION_PATTERN = re.compile(r"<@&(\d+)>")
ROLE_ACTION_PATTERN = re.compile(
    r"(?:역할|role).{0,12}(?:부여|추가|달아|붙여|줘|주세요|assign|grant|add)",
    re.IGNORECASE,
)
NICKNAME_ACTION_PATTERN = re.compile(
    r"(?:별명|닉네임|nickname|nick).{0,12}(?:변경|설정|바꿔|수정|해줘|주세요|change|set)",
    re.IGNORECASE,
)
ROLE_NAME_PATTERNS = (
    re.compile(
        r"<@!?\d+>\s*(?:한테|에게|에)?\s*[\"'`“”‘’]?(?P<name>.+?)[\"'`“”‘’]?\s*역할(?:을|를)?\s*(?:부여|추가|달아|붙여|줘|주세요)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:역할|role)\s*[\"'`“”‘’]?(?P<name>.+?)[\"'`“”‘’]?\s*(?:부여|추가|달아|붙여|줘|주세요|assign|grant|add)",
        re.IGNORECASE,
    ),
)
NICKNAME_PATTERNS = (
    re.compile(
        r"<@!?\d+>\s*(?:한테|에게|의)?\s*(?:별명|닉네임)\s*[\"'`“”‘’]?(?P<name>.+?)[\"'`“”‘’]?\s*(?:으로|로)?\s*(?:변경|설정|바꿔|수정|해줘|해주세요|주세요)",
        re.IGNORECASE,
    ),
    re.compile(
        r"<@!?\d+>\s*(?:한테|에게|에)?\s*[\"'`“”‘’]?(?P<name>.+?)[\"'`“”‘’]?\s*(?:으로|로)\s*(?:별명|닉네임)\s*(?:변경|설정|바꿔|수정|해줘|해주세요|주세요)",
        re.IGNORECASE,
    ),
)
LEADING_DIGIT_PATTERN = re.compile(r"^\s*(\d)")


@dataclass(frozen=True)
class RoleGrantRequest:
    target_member_id: int
    role_name: str
    existing_role_id: int | None
    will_create_role: bool


@dataclass(frozen=True)
class NicknameChangeRequest:
    target_member_id: int
    nickname: str


STUDENT_GRADE_ROLE_NAMES = {
    "3학년": "3학년",
    "2학년": "2학년",
    "1학년": "1학년",
}


def member_is_admin(user: discord.abc.User) -> bool:
    return isinstance(user, discord.Member) and user.guild_permissions.administrator


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_wrapping_quotes(value: str) -> str:
    text = value.strip()
    quote_pairs = [
        ('"', '"'),
        ("'", "'"),
        ("`", "`"),
        ("“", "”"),
        ("‘", "’"),
    ]
    for left, right in quote_pairs:
        if text.startswith(left) and text.endswith(right) and len(text) >= 2:
            return text[len(left) : -len(right)].strip()

    return text


def resolve_target_member(
    guild: discord.Guild,
    prompt: str,
) -> tuple[discord.Member | None, str | None]:
    mentioned_ids = [
        int(match.group(1)) for match in USER_MENTION_PATTERN.finditer(prompt)
    ]
    unique_ids = list(dict.fromkeys(mentioned_ids))
    if not unique_ids:
        return None, "대상 유저를 멘션해 주세요."

    if len(unique_ids) > 1:
        return None, "대상 유저는 한 명만 멘션해 주세요."

    member = guild.get_member(unique_ids[0])
    if member is None:
        return None, "멘션한 유저를 서버에서 찾지 못했습니다."

    return member, None


def find_role_by_name(guild: discord.Guild, role_name: str) -> discord.Role | None:
    normalized = role_name.casefold()
    for role in guild.roles:
        if role.name.casefold() == normalized:
            return role

    return None


def parse_role_name_from_prompt(prompt: str) -> str | None:
    mention_match = ROLE_MENTION_PATTERN.search(prompt)
    if mention_match:
        return mention_match.group(0)

    for pattern in ROLE_NAME_PATTERNS:
        match = pattern.search(prompt)
        if match is None:
            continue

        name = strip_wrapping_quotes(normalize_text(match.group("name")))
        if name:
            return name

    return None


def parse_nickname_from_prompt(prompt: str) -> str | None:
    for pattern in NICKNAME_PATTERNS:
        match = pattern.search(prompt)
        if match is None:
            continue

        nickname = strip_wrapping_quotes(normalize_text(match.group("name")))
        if nickname:
            return nickname

    return None


def resolve_role_request(
    guild: discord.Guild,
    role_input: str,
) -> tuple[discord.Role | None, str, bool, str | None]:
    mention_match = ROLE_MENTION_PATTERN.fullmatch(role_input.strip())
    if mention_match:
        role = guild.get_role(int(mention_match.group(1)))
        if role is None:
            return None, "", False, "멘션한 역할을 서버에서 찾지 못했습니다."
        return role, role.name, False, None

    role_name = strip_wrapping_quotes(normalize_text(role_input))
    if not role_name:
        return None, "", False, "부여할 역할명을 비워둘 수 없습니다."

    if len(role_name) > 100:
        return None, "", False, "역할명은 100자 이하로 입력해 주세요."

    if role_name.casefold() == "@everyone":
        return None, "", False, "@everyone 역할은 만들거나 부여할 수 없습니다."

    existing_role = find_role_by_name(guild, role_name)
    if existing_role is not None:
        return existing_role, existing_role.name, False, None

    return None, role_name, True, None


def validate_role_management_permissions(
    bot: "CoraxBot",
    requester: discord.Member,
) -> str | None:
    if not requester.guild_permissions.administrator:
        return "역할 관리는 관리자만 할 수 있습니다."

    bot_user = bot.user
    if bot_user is None:
        return "봇 정보를 확인할 수 없습니다."

    bot_member = requester.guild.get_member(bot_user.id)
    if bot_member is None:
        return "봇 멤버 정보를 확인할 수 없습니다."

    if not bot_member.guild_permissions.manage_roles:
        return "봇에 역할 관리 권한이 없습니다."

    return None


def validate_role_target(
    bot: "CoraxBot",
    requester: discord.Member,
    target_member: discord.Member,
) -> str | None:
    guild = requester.guild
    bot_user = bot.user
    if bot_user is None:
        return "봇 정보를 확인할 수 없습니다."

    bot_member = guild.get_member(bot_user.id)
    if bot_member is None:
        return "봇 멤버 정보를 확인할 수 없습니다."

    if guild.owner_id == target_member.id:
        return "서버 소유자에게는 역할을 부여할 수 없습니다."

    if target_member.id != bot_member.id and target_member.top_role >= bot_member.top_role:
        return "봇보다 높거나 같은 역할을 가진 유저에게는 역할을 부여할 수 없습니다."

    if requester.id != guild.owner_id and target_member.id != requester.id:
        if target_member.top_role >= requester.top_role:
            return "자신보다 높거나 같은 역할을 가진 유저에게는 역할을 부여할 수 없습니다."

    return None


def validate_existing_role_assignment(
    bot: "CoraxBot",
    requester: discord.Member,
    target_member: discord.Member,
    role: discord.Role,
) -> str | None:
    permission_error = validate_role_management_permissions(bot, requester)
    if permission_error is not None:
        return permission_error

    target_error = validate_role_target(bot, requester, target_member)
    if target_error is not None:
        return target_error

    if role.is_default():
        return "@everyone 역할은 부여할 수 없습니다."

    if role.managed:
        return "봇 또는 연동 서비스가 관리하는 역할은 부여할 수 없습니다."

    if requester.id != requester.guild.owner_id and role >= requester.top_role:
        return "자신보다 높거나 같은 역할은 부여할 수 없습니다."

    if not role.is_assignable():
        return "봇 역할이 대상 역할보다 높지 않아 그 역할을 부여할 수 없습니다."

    return None


def build_role_grant_prompt(
    target_member: discord.Member,
    role_name: str,
    *,
    will_create_role: bool,
    role: discord.Role | None,
) -> str:
    role_text = role.mention if role is not None else f"`{role_name}`"
    if will_create_role:
        return (
            f"⚠️ {target_member.mention}에게 {role_text} 역할을 새로 만들고 부여하시겠습니까?"
        )

    return f"⚠️ {target_member.mention}에게 {role_text} 역할을 부여하시겠습니까?"


def build_role_grant_success(
    target_member: discord.Member,
    role: discord.Role,
    *,
    created_role: bool,
) -> str:
    if created_role:
        return f"✅ {role.mention} 역할을 생성하고 {target_member.mention}에게 부여했습니다."

    return f"✅ {target_member.mention}에게 {role.mention} 역할을 부여했습니다."


def build_role_grant_reason(
    interaction: discord.Interaction,
    source_label: str,
) -> str:
    return f"{source_label} by {interaction.user} ({interaction.user.id})"


def prompt_looks_like_role_grant(prompt: str) -> bool:
    return bool(USER_MENTION_PATTERN.search(prompt) and ROLE_ACTION_PATTERN.search(prompt))


def parse_role_grant_request(
    bot: "CoraxBot",
    interaction: discord.Interaction,
    prompt: str,
) -> tuple[bool, RoleGrantRequest | None, str | None]:
    guild = interaction.guild
    requester = interaction.user
    if guild is None or not isinstance(requester, discord.Member):
        return False, None, None

    if not prompt_looks_like_role_grant(prompt):
        return False, None, None

    target_member, member_error = resolve_target_member(guild, prompt)
    if member_error is not None or target_member is None:
        return True, None, member_error or "대상 유저를 찾지 못했습니다."

    role_input = parse_role_name_from_prompt(prompt)
    if role_input is None:
        return True, None, "부여할 역할명을 찾지 못했습니다. `@유저 한테 VIP 역할 부여해줘`처럼 써 주세요."

    role, role_name, will_create_role, role_error = resolve_role_request(guild, role_input)
    if role_error is not None:
        return True, None, role_error

    permission_error = validate_role_management_permissions(bot, requester)
    if permission_error is not None:
        return True, None, permission_error

    target_error = validate_role_target(bot, requester, target_member)
    if target_error is not None:
        return True, None, target_error

    if role is not None:
        validation_error = validate_existing_role_assignment(
            bot,
            requester,
            target_member,
            role,
        )
        if validation_error is not None:
            return True, None, validation_error

    return True, RoleGrantRequest(
        target_member_id=target_member.id,
        role_name=role_name,
        existing_role_id=role.id if role is not None else None,
        will_create_role=will_create_role,
    ), None


def build_nickname_prompt(target_member: discord.Member, nickname: str) -> str:
    return f"⚠️ {target_member.mention}의 별명을 `{nickname}`(으)로 변경하시겠습니까?"


def build_nickname_success(target_member: discord.Member, nickname: str) -> str:
    return f"✅ {target_member.mention}의 별명을 `{nickname}`(으)로 변경했습니다."


def build_nickname_reason(
    interaction: discord.Interaction,
    source_label: str,
) -> str:
    return f"{source_label} by {interaction.user} ({interaction.user.id})"


def prompt_looks_like_nickname_change(prompt: str) -> bool:
    return bool(
        USER_MENTION_PATTERN.search(prompt) and NICKNAME_ACTION_PATTERN.search(prompt)
    )


def validate_nickname_change(
    bot: "CoraxBot",
    requester: discord.Member,
    target_member: discord.Member,
    nickname: str,
) -> str | None:
    if not requester.guild_permissions.administrator:
        return "별명 변경은 관리자만 할 수 있습니다."

    if not nickname:
        return "별명을 비워둘 수 없습니다."

    if len(nickname) > 32:
        return "별명은 32자 이하로 입력해 주세요."

    bot_user = bot.user
    if bot_user is None:
        return "봇 정보를 확인할 수 없습니다."

    bot_member = requester.guild.get_member(bot_user.id)
    if bot_member is None:
        return "봇 멤버 정보를 확인할 수 없습니다."

    if not bot_member.guild_permissions.manage_nicknames:
        return "봇에 별명 관리 권한이 없습니다."

    if requester.guild.owner_id == target_member.id:
        return "서버 소유자의 별명은 변경할 수 없습니다."

    if target_member.id != bot_member.id and target_member.top_role >= bot_member.top_role:
        return "봇보다 높거나 같은 역할을 가진 유저의 별명은 변경할 수 없습니다."

    if requester.id != requester.guild.owner_id and target_member.id != requester.id:
        if target_member.top_role >= requester.top_role:
            return "자신보다 높거나 같은 역할을 가진 유저의 별명은 변경할 수 없습니다."

    return None


def parse_nickname_change_request(
    bot: "CoraxBot",
    interaction: discord.Interaction,
    prompt: str,
) -> tuple[bool, NicknameChangeRequest | None, str | None]:
    guild = interaction.guild
    requester = interaction.user
    if guild is None or not isinstance(requester, discord.Member):
        return False, None, None

    if not prompt_looks_like_nickname_change(prompt):
        return False, None, None

    target_member, member_error = resolve_target_member(guild, prompt)
    if member_error is not None or target_member is None:
        return True, None, member_error or "대상 유저를 찾지 못했습니다."

    nickname = parse_nickname_from_prompt(prompt)
    if nickname is None:
        return True, None, "새 별명을 찾지 못했습니다. `@유저 별명 철수로 바꿔줘`처럼 써 주세요."

    validation_error = validate_nickname_change(
        bot,
        requester,
        target_member,
        nickname,
    )
    if validation_error is not None:
        return True, None, validation_error

    return True, NicknameChangeRequest(
        target_member_id=target_member.id,
        nickname=nickname,
    ), None


class RoleGrantConfirmView(discord.ui.View):
    def __init__(
        self,
        bot: "CoraxBot",
        requester_id: int,
        target_member_id: int,
        role_name: str,
        existing_role_id: int | None,
        source_label: str,
    ) -> None:
        super().__init__(timeout=30)
        self.bot = bot
        self.requester_id = requester_id
        self.target_member_id = target_member_id
        self.role_name = role_name
        self.existing_role_id = existing_role_id
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
            await self.message.edit(
                content="역할 부여 확인 시간이 만료되었습니다.",
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
        guild = interaction.guild
        requester = interaction.user
        if guild is None or not isinstance(requester, discord.Member):
            await interaction.response.send_message(
                "서버 정보를 확인할 수 없습니다.",
                ephemeral=True,
            )
            return

        target_member = guild.get_member(self.target_member_id)
        if target_member is None:
            await interaction.response.send_message(
                "대상 유저를 더 이상 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        role = guild.get_role(self.existing_role_id) if self.existing_role_id else None
        if role is None:
            role = find_role_by_name(guild, self.role_name)

        if role is not None:
            validation_error = validate_existing_role_assignment(
                self.bot,
                requester,
                target_member,
                role,
            )
            if validation_error is not None:
                await interaction.response.send_message(
                    validation_error,
                    ephemeral=True,
                )
                return

            if role in target_member.roles:
                await interaction.response.edit_message(
                    content=f"{target_member.mention}에게는 이미 {role.mention} 역할이 있습니다.",
                    view=None,
                )
                self.stop()
                return

        else:
            permission_error = validate_role_management_permissions(self.bot, requester)
            if permission_error is not None:
                await interaction.response.send_message(
                    permission_error,
                    ephemeral=True,
                )
                return

            target_error = validate_role_target(self.bot, requester, target_member)
            if target_error is not None:
                await interaction.response.send_message(
                    target_error,
                    ephemeral=True,
                )
                return

        await interaction.response.defer()

        created_role = False
        if role is None:
            try:
                role = await guild.create_role(
                    name=self.role_name,
                    reason=build_role_grant_reason(interaction, self.source_label),
                )
                created_role = True
            except discord.Forbidden:
                await interaction.edit_original_response(
                    content="역할을 생성할 권한이 없어 작업을 완료하지 못했습니다.",
                    view=None,
                )
                self.stop()
                return
            except discord.HTTPException as error:
                await interaction.edit_original_response(
                    content=f"역할 생성 중 오류가 발생했습니다: {error}",
                    view=None,
                )
                self.stop()
                return

        try:
            await target_member.add_roles(
                role,
                reason=build_role_grant_reason(interaction, self.source_label),
            )
        except discord.Forbidden:
            await interaction.edit_original_response(
                content="역할을 부여할 권한이 없어 작업을 완료하지 못했습니다.",
                view=None,
            )
            self.stop()
            return
        except discord.HTTPException as error:
            await interaction.edit_original_response(
                content=f"역할 부여 중 오류가 발생했습니다: {error}",
                view=None,
            )
            self.stop()
            return

        await interaction.edit_original_response(
            content=build_role_grant_success(
                target_member,
                role,
                created_role=created_role,
            ),
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
            content="역할 부여를 취소했습니다.",
            view=None,
        )
        self.stop()


class NicknameConfirmView(discord.ui.View):
    def __init__(
        self,
        bot: "CoraxBot",
        requester_id: int,
        target_member_id: int,
        nickname: str,
        source_label: str,
    ) -> None:
        super().__init__(timeout=30)
        self.bot = bot
        self.requester_id = requester_id
        self.target_member_id = target_member_id
        self.nickname = nickname
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
            await self.message.edit(
                content="별명 변경 확인 시간이 만료되었습니다.",
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
        guild = interaction.guild
        requester = interaction.user
        if guild is None or not isinstance(requester, discord.Member):
            await interaction.response.send_message(
                "서버 정보를 확인할 수 없습니다.",
                ephemeral=True,
            )
            return

        target_member = guild.get_member(self.target_member_id)
        if target_member is None:
            await interaction.response.send_message(
                "대상 유저를 더 이상 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        validation_error = validate_nickname_change(
            self.bot,
            requester,
            target_member,
            self.nickname,
        )
        if validation_error is not None:
            await interaction.response.send_message(
                validation_error,
                ephemeral=True,
            )
            return

        if target_member.nick == self.nickname:
            await interaction.response.edit_message(
                content=f"{target_member.mention}의 별명이 이미 `{self.nickname}`입니다.",
                view=None,
            )
            self.stop()
            return

        await interaction.response.defer()

        try:
            await target_member.edit(
                nick=self.nickname,
                reason=build_nickname_reason(interaction, self.source_label),
            )
        except discord.Forbidden:
            await interaction.edit_original_response(
                content="별명을 변경할 권한이 없어 작업을 완료하지 못했습니다.",
                view=None,
            )
            self.stop()
            return
        except discord.HTTPException as error:
            await interaction.edit_original_response(
                content=f"별명 변경 중 오류가 발생했습니다: {error}",
                view=None,
            )
            self.stop()
            return

        await interaction.edit_original_response(
            content=build_nickname_success(target_member, self.nickname),
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
            content="별명 변경을 취소했습니다.",
            view=None,
        )
        self.stop()


async def send_role_grant_confirmation(
    interaction: discord.Interaction,
    bot: "CoraxBot",
    target_member: discord.Member,
    role_name: str,
    *,
    existing_role: discord.Role | None,
    source_label: str,
) -> None:
    view = RoleGrantConfirmView(
        bot=bot,
        requester_id=interaction.user.id,
        target_member_id=target_member.id,
        role_name=role_name,
        existing_role_id=existing_role.id if existing_role is not None else None,
        source_label=source_label,
    )
    content = build_role_grant_prompt(
        target_member,
        role_name,
        will_create_role=existing_role is None,
        role=existing_role,
    )
    if interaction.response.is_done():
        message = await interaction.followup.send(
            content=content,
            view=view,
            ephemeral=True,
            wait=True,
        )
    else:
        await interaction.response.send_message(
            content,
            view=view,
            ephemeral=True,
        )
        message = await interaction.original_response()

    view.message = message


async def send_nickname_confirmation(
    interaction: discord.Interaction,
    bot: "CoraxBot",
    target_member: discord.Member,
    nickname: str,
    *,
    source_label: str,
) -> None:
    view = NicknameConfirmView(
        bot=bot,
        requester_id=interaction.user.id,
        target_member_id=target_member.id,
        nickname=nickname,
        source_label=source_label,
    )
    if interaction.response.is_done():
        message = await interaction.followup.send(
            content=build_nickname_prompt(target_member, nickname),
            view=view,
            ephemeral=True,
            wait=True,
        )
    else:
        await interaction.response.send_message(
            build_nickname_prompt(target_member, nickname),
            view=view,
            ephemeral=True,
        )
        message = await interaction.original_response()

    view.message = message


def extract_student_prefix(member: discord.Member) -> str | None:
    match = LEADING_DIGIT_PATTERN.match(member.display_name)
    if match is None:
        return None

    return match.group(1)


def validate_student_grade_role(
    requester: discord.Member,
    role: discord.Role,
) -> str | None:
    if role.is_default():
        return "@everyone 역할은 학생 역할로 사용할 수 없습니다."

    if role.managed:
        return "봇 또는 연동 서비스가 관리하는 역할은 학생 역할로 사용할 수 없습니다."

    if requester.id != requester.guild.owner_id and role >= requester.top_role:
        return "자신보다 높거나 같은 역할은 학생 역할로 사용할 수 없습니다."

    if not role.is_assignable():
        return "봇 역할이 학생 역할보다 높지 않아 작업을 진행할 수 없습니다."

    return None


async def ensure_student_grade_role(
    guild: discord.Guild,
    requester: discord.Member,
    role_name: str,
    *,
    source_label: str,
) -> tuple[discord.Role | None, str | None]:
    role = find_role_by_name(guild, role_name)
    if role is not None:
        validation_error = validate_student_grade_role(requester, role)
        if validation_error is not None:
            return None, f"`{role_name}` 역할 설정 오류: {validation_error}"
        return role, None

    try:
        created_role = await guild.create_role(
            name=role_name,
            reason=f"{source_label} by {requester} ({requester.id})",
        )
    except discord.Forbidden:
        return None, f"`{role_name}` 역할을 생성할 권한이 없습니다."
    except discord.HTTPException as error:
        return None, f"`{role_name}` 역할 생성 중 오류가 발생했습니다: {error}"

    return created_role, None


async def sync_student_grade_roles(
    bot: "CoraxBot",
    requester: discord.Member,
    *,
    third_grade_prefix: int,
    second_grade_prefix: int,
    first_grade_prefix: int,
    admin_role: discord.Role,
    source_label: str,
) -> tuple[str, bool]:
    guild = requester.guild
    permission_error = validate_role_management_permissions(bot, requester)
    if permission_error is not None:
        return permission_error, False

    bot_user = bot.user
    if bot_user is None:
        return "봇 정보를 확인할 수 없습니다.", False

    bot_member = guild.get_member(bot_user.id)
    if bot_member is None:
        return "봇 멤버 정보를 확인할 수 없습니다.", False

    grade_roles: dict[str, discord.Role] = {}
    for role_name in STUDENT_GRADE_ROLE_NAMES:
        role, role_error = await ensure_student_grade_role(
            guild,
            requester,
            role_name,
            source_label=source_label,
        )
        if role_error is not None or role is None:
            return role_error or "학생 역할을 준비하지 못했습니다.", False
        grade_roles[role_name] = role

    prefix_map = {
        str(third_grade_prefix): grade_roles["3학년"],
        str(second_grade_prefix): grade_roles["2학년"],
        str(first_grade_prefix): grade_roles["1학년"],
    }
    managed_roles = tuple(grade_roles.values())
    summary = {
        "updated": 0,
        "unchanged": 0,
        "skipped_admin": 0,
        "skipped_unmatched": 0,
        "skipped_unmanageable": 0,
        "failed": 0,
    }
    error_samples: list[str] = []

    for member in guild.members:
        if member.bot:
            continue

        if member.guild_permissions.administrator or admin_role in member.roles:
            summary["skipped_admin"] += 1
            continue

        leading_digit = extract_student_prefix(member)
        target_role = prefix_map.get(leading_digit or "")
        if target_role is None:
            summary["skipped_unmatched"] += 1
            continue

        target_error = validate_role_target(bot, requester, member)
        if target_error is not None:
            summary["skipped_unmanageable"] += 1
            if len(error_samples) < 5:
                error_samples.append(f"{member.display_name}: {target_error}")
            continue

        roles_to_remove = [
            role for role in managed_roles if role != target_role and role in member.roles
        ]
        needs_add = target_role not in member.roles
        if not needs_add and not roles_to_remove:
            summary["unchanged"] += 1
            continue

        try:
            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove,
                    reason=f"{source_label} by {requester} ({requester.id})",
                )
            if needs_add:
                await member.add_roles(
                    target_role,
                    reason=f"{source_label} by {requester} ({requester.id})",
                )
            summary["updated"] += 1
        except discord.Forbidden:
            summary["failed"] += 1
            if len(error_samples) < 5:
                error_samples.append(
                    f"{member.display_name}: 역할을 변경할 권한이 없습니다."
                )
        except discord.HTTPException as error:
            summary["failed"] += 1
            if len(error_samples) < 5:
                error_samples.append(f"{member.display_name}: {error}")

    lines = [
        "✅ 학생 역할 동기화를 완료했습니다.",
        f"3학년 시작 숫자: `{third_grade_prefix}` -> {grade_roles['3학년'].mention}",
        f"2학년 시작 숫자: `{second_grade_prefix}` -> {grade_roles['2학년'].mention}",
        f"1학년 시작 숫자: `{first_grade_prefix}` -> {grade_roles['1학년'].mention}",
        f"관리자 제외 역할: {admin_role.mention}",
        "처리 대상: 전체 학생",
        "",
        f"변경됨: {summary['updated']}명",
        f"이미 정상: {summary['unchanged']}명",
        f"관리자 제외: {summary['skipped_admin']}명",
        f"숫자 불일치/없음: {summary['skipped_unmatched']}명",
        f"권한상 제외: {summary['skipped_unmanageable']}명",
        f"실패: {summary['failed']}명",
    ]
    if error_samples:
        lines.extend(["", "오류 예시:", *error_samples])

    return "\n".join(lines), True


class RolesCog(commands.Cog):
    def __init__(self, bot: "CoraxBot"):
        self.bot = bot

    @app_commands.command(name="role_add", description="관리자 전용 역할 생성 및 부여")
    @app_commands.rename(member="유저", role_name="역할명")
    @app_commands.describe(
        member="역할을 부여할 유저",
        role_name="기존 역할명 또는 새로 만들 역할명",
    )
    @app_commands.default_permissions(administrator=True)
    async def role_add(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role_name: app_commands.Range[str, 1, 100],
    ) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        role, resolved_name, _, role_error = resolve_role_request(
            interaction.guild,
            role_name,
        )
        if role_error is not None:
            await interaction.response.send_message(role_error, ephemeral=True)
            return

        if role is not None:
            validation_error = validate_existing_role_assignment(
                self.bot,
                interaction.user,
                member,
                role,
            )
        else:
            permission_error = validate_role_management_permissions(
                self.bot,
                interaction.user,
            )
            target_error = validate_role_target(self.bot, interaction.user, member)
            validation_error = permission_error or target_error

        if validation_error is not None:
            await interaction.response.send_message(
                validation_error,
                ephemeral=True,
            )
            return

        await send_role_grant_confirmation(
            interaction,
            self.bot,
            member,
            resolved_name,
            existing_role=role,
            source_label="/role_add",
        )

    @app_commands.command(name="student", description="이름 앞 숫자 기준으로 학년 역할 일괄 부여")
    @app_commands.rename(
        third_grade_prefix="3",
        second_grade_prefix="2",
        first_grade_prefix="1",
        admin_role="관리자",
    )
    @app_commands.describe(
        third_grade_prefix="3학년으로 볼 이름 시작 숫자",
        second_grade_prefix="2학년으로 볼 이름 시작 숫자",
        first_grade_prefix="1학년으로 볼 이름 시작 숫자",
        admin_role="학생 역할 부여에서 제외할 관리자 역할",
    )
    @app_commands.default_permissions(administrator=True)
    async def student(
        self,
        interaction: discord.Interaction,
        third_grade_prefix: app_commands.Range[int, 0, 9],
        second_grade_prefix: app_commands.Range[int, 0, 9],
        first_grade_prefix: app_commands.Range[int, 0, 9],
        admin_role: discord.Role,
    ) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        prefixes = {
            third_grade_prefix,
            second_grade_prefix,
            first_grade_prefix,
        }
        if len(prefixes) < 3:
            await interaction.response.send_message(
                "3학년, 2학년, 1학년 시작 숫자는 서로 다르게 입력해 주세요.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        result_message, _ = await sync_student_grade_roles(
            self.bot,
            interaction.user,
            third_grade_prefix=third_grade_prefix,
            second_grade_prefix=second_grade_prefix,
            first_grade_prefix=first_grade_prefix,
            admin_role=admin_role,
            source_label="/student",
        )
        await interaction.followup.send(result_message, ephemeral=True)

    @app_commands.command(name="nickname", description="관리자 전용 별명 변경")
    @app_commands.rename(member="유저", nickname="별명")
    @app_commands.describe(
        member="별명을 바꿀 유저",
        nickname="새 별명",
    )
    @app_commands.default_permissions(administrator=True)
    async def nickname(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        nickname: app_commands.Range[str, 1, 32],
    ) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        nickname_text = strip_wrapping_quotes(normalize_text(nickname))
        validation_error = validate_nickname_change(
            self.bot,
            interaction.user,
            member,
            nickname_text,
        )
        if validation_error is not None:
            await interaction.response.send_message(
                validation_error,
                ephemeral=True,
            )
            return

        await send_nickname_confirmation(
            interaction,
            self.bot,
            member,
            nickname_text,
            source_label="/nickname",
        )


async def setup(bot: "CoraxBot") -> None:
    await bot.add_cog(RolesCog(bot))

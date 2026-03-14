from __future__ import annotations

import html
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode, urlparse

import aiohttp
import discord
from aiohttp import web
from discord import app_commands
from discord.ext import commands
from google.auth.transport.requests import Request
from google.oauth2 import id_token as google_id_token

from services.school_auth_store import SchoolAuthGuildConfig

if TYPE_CHECKING:
    from bot import CoraxBot


AUTH_CATEGORY_NAME = "학교 인증"
AUTH_CHANNEL_NAME = "학교-인증"
UNVERIFIED_ROLE_NAME = "학교미인증"
VERIFIED_ROLE_NAME = "학교인증완료"
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class PendingSchoolAuthSession:
    state: str
    guild_id: int
    user_id: int
    created_at: float
    expires_at: float


class SchoolAuthLinkView(discord.ui.View):
    def __init__(self, auth_url: str):
        super().__init__(timeout=300)
        self.add_item(
            discord.ui.Button(
                label="Google 계정으로 인증하기",
                style=discord.ButtonStyle.link,
                url=auth_url,
            )
        )


class SchoolAuthLaunchView(discord.ui.View):
    def __init__(self, cog: "SchoolAuthCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="학교 계정 인증 시작",
        style=discord.ButtonStyle.primary,
        custom_id="school_auth:start",
    )
    async def start_auth(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self.cog.send_auth_link(interaction)


class SchoolAuthCog(commands.Cog):
    def __init__(self, bot: "CoraxBot"):
        self.bot = bot
        self.pending_sessions: dict[str, PendingSchoolAuthSession] = {}
        self.web_runner: web.AppRunner | None = None
        self.web_site: web.TCPSite | None = None
        self.panel_view = SchoolAuthLaunchView(self)
        self.callback_path = self._resolve_callback_path()

    @property
    def is_google_configured(self) -> bool:
        return bool(
            self.bot.google_client_id
            and self.bot.google_client_secret
            and self.bot.google_redirect_uri
        )

    def _resolve_callback_path(self) -> str:
        redirect_uri = self.bot.google_redirect_uri
        if not redirect_uri:
            return "/school-auth/callback"

        path = urlparse(redirect_uri).path
        return path or "/school-auth/callback"

    async def start_web_server(self) -> None:
        if not getattr(self.bot, "enable_school_auth_web_server", True):
            return

        if not self.is_google_configured:
            print("학교 인증 웹 서버를 시작하지 않았습니다. Google OAuth 설정이 없습니다.")
            return

        if self.web_runner is not None:
            return

        app = web.Application()
        app.router.add_get("/", self.handle_root)
        app.router.add_get("/healthz", self.handle_healthz)
        app.router.add_get(self.callback_path, self.handle_google_callback)
        self.web_runner = web.AppRunner(app)
        await self.web_runner.setup()
        self.web_site = web.TCPSite(
            self.web_runner,
            self.bot.school_auth_bind_host,
            self.bot.school_auth_bind_port,
        )
        await self.web_site.start()
        print(
            "학교 인증 웹 서버 시작: "
            f"http://{self.bot.school_auth_bind_host}:{self.bot.school_auth_bind_port}"
        )

    async def stop_web_server(self) -> None:
        if self.web_runner is None:
            return

        await self.web_runner.cleanup()
        self.web_runner = None
        self.web_site = None

    def get_config(self, guild_id: int) -> SchoolAuthGuildConfig | None:
        return self.bot.school_auth_config_store.get_config(guild_id)

    def get_verified_role(
        self,
        guild: discord.Guild,
        config: SchoolAuthGuildConfig,
    ) -> discord.Role | None:
        return guild.get_role(config.verified_role_id)

    def get_unverified_role(
        self,
        guild: discord.Guild,
        config: SchoolAuthGuildConfig,
    ) -> discord.Role | None:
        return guild.get_role(config.unverified_role_id)

    def get_bypass_role(
        self,
        guild: discord.Guild,
        config: SchoolAuthGuildConfig,
    ) -> discord.Role | None:
        if config.bypass_role_id is None:
            return None

        return guild.get_role(config.bypass_role_id)

    def member_is_bypass(
        self,
        member: discord.Member,
        config: SchoolAuthGuildConfig,
    ) -> bool:
        if member.guild_permissions.administrator:
            return True

        bypass_role = self.get_bypass_role(member.guild, config)
        return bypass_role is not None and bypass_role in member.roles

    def cleanup_pending_sessions(self) -> None:
        now = time.time()
        expired_states = [
            state
            for state, pending in self.pending_sessions.items()
            if pending.expires_at <= now
        ]
        for state in expired_states:
            self.pending_sessions.pop(state, None)

    def create_pending_session(self, guild_id: int, user_id: int) -> PendingSchoolAuthSession:
        self.cleanup_pending_sessions()
        state = secrets.token_urlsafe(32)
        now = time.time()
        session = PendingSchoolAuthSession(
            state=state,
            guild_id=guild_id,
            user_id=user_id,
            created_at=now,
            expires_at=now + 600,
        )
        self.pending_sessions[state] = session
        return session

    def pop_pending_session(self, state: str | None) -> PendingSchoolAuthSession | None:
        self.cleanup_pending_sessions()
        if state is None:
            return None

        return self.pending_sessions.pop(state, None)

    def build_google_auth_url(self, config: SchoolAuthGuildConfig, state: str) -> str:
        params = {
            "client_id": self.bot.google_client_id or "",
            "redirect_uri": self.bot.google_redirect_uri or "",
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
            "hd": config.domain,
        }
        return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"

    async def exchange_google_code(self, code: str) -> dict[str, object]:
        data = {
            "code": code,
            "client_id": self.bot.google_client_id or "",
            "client_secret": self.bot.google_client_secret or "",
            "redirect_uri": self.bot.google_redirect_uri or "",
            "grant_type": "authorization_code",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(GOOGLE_TOKEN_ENDPOINT, data=data) as response:
                payload = await response.json(content_type=None)
                if response.status >= 400:
                    message = payload.get("error_description") or payload.get("error") or str(
                        payload
                    )
                    raise ValueError(f"Google 토큰 교환 실패: {message}")
                if not isinstance(payload, dict):
                    raise ValueError("Google 토큰 응답 형식이 올바르지 않습니다.")
                return payload

    def verify_google_id_token(self, id_token: str) -> dict[str, object]:
        try:
            payload = google_id_token.verify_oauth2_token(
                id_token,
                Request(),
                self.bot.google_client_id,
            )
        except Exception as error:
            raise ValueError(f"Google ID 토큰 검증 실패: {error}") from error

        if not isinstance(payload, dict):
            raise ValueError("Google ID 토큰 payload 형식이 올바르지 않습니다.")

        return payload

    def validate_google_identity(
        self,
        *,
        payload: dict[str, object],
        expected_domain: str,
    ) -> tuple[str, str]:
        issuer = str(payload.get("iss", ""))
        audience = str(payload.get("aud", ""))
        email = str(payload.get("email", "")).strip().casefold()
        hd = str(payload.get("hd", "")).strip().casefold()
        google_sub = str(payload.get("sub", "")).strip()
        email_verified = payload.get("email_verified")
        expires_at = int(payload.get("exp", 0))
        now = int(time.time())

        if issuer not in {"https://accounts.google.com", "accounts.google.com"}:
            raise ValueError("Google 발급 토큰이 아닙니다.")

        if audience != (self.bot.google_client_id or ""):
            raise ValueError("이 앱용 Google 토큰이 아닙니다.")

        if expires_at <= now:
            raise ValueError("만료된 Google 토큰입니다.")

        if not google_sub:
            raise ValueError("Google 계정 식별 정보를 읽지 못했습니다.")

        if email_verified is not True:
            raise ValueError("확인된 Google 이메일만 사용할 수 있습니다.")

        if hd != expected_domain:
            raise ValueError(f"{expected_domain} 학교 계정으로 로그인해야 합니다.")

        if not email.endswith(f"@{expected_domain}"):
            raise ValueError(f"{expected_domain} 메일 주소만 사용할 수 있습니다.")

        return google_sub, email

    def render_page(self, title: str, description: str, *, success: bool) -> web.Response:
        escaped_title = html.escape(title)
        escaped_description = html.escape(description)
        color = "#177245" if success else "#9b1c1c"
        body = f"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    body {{
      margin: 0;
      font-family: "Noto Sans KR", "Malgun Gothic", sans-serif;
      background: linear-gradient(135deg, #f6f2e8, #dce7f2);
      color: #1c1c1c;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    main {{
      width: min(560px, 100%);
      background: rgba(255, 255, 255, 0.94);
      border: 2px solid {color};
      border-radius: 20px;
      padding: 28px 24px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.12);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 28px;
    }}
    p {{
      margin: 0;
      line-height: 1.65;
      font-size: 16px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{escaped_title}</h1>
    <p>{escaped_description}</p>
  </main>
</body>
</html>
"""
        return web.Response(text=body, content_type="text/html")

    async def handle_root(self, _: web.Request) -> web.Response:
        return self.render_page(
            "또봇 학교 인증 서버",
            "이 주소는 학교 계정 인증 콜백 처리용입니다.",
            success=True,
        )

    async def handle_healthz(self, _: web.Request) -> web.Response:
        return web.Response(text="ok", content_type="text/plain")

    async def finish_verification(
        self,
        *,
        guild_id: int,
        user_id: int,
        google_sub: str,
        email: str,
    ) -> None:
        config = self.get_config(guild_id)
        if config is None:
            raise ValueError("서버 학교 인증 설정을 찾지 못했습니다.")

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise ValueError("서버 정보를 확인할 수 없습니다.")

        try:
            member = guild.get_member(user_id) or await guild.fetch_member(user_id)
        except discord.HTTPException as error:
            raise ValueError(f"디스코드 멤버를 찾지 못했습니다: {error}") from error

        verified_role = self.get_verified_role(guild, config)
        unverified_role = self.get_unverified_role(guild, config)
        if verified_role is None or unverified_role is None:
            raise ValueError("학교 인증 역할 설정이 올바르지 않습니다.")

        try:
            await member.add_roles(
                verified_role,
                reason=f"school_auth verified: {email}",
            )
            if unverified_role in member.roles:
                await member.remove_roles(
                    unverified_role,
                    reason=f"school_auth verified: {email}",
                )
        except discord.Forbidden as error:
            raise ValueError("봇에 인증 역할을 변경할 권한이 없습니다.") from error
        except discord.HTTPException as error:
            raise ValueError(f"디스코드 역할 변경 중 오류가 발생했습니다: {error}") from error

        self.bot.school_verification_store.set_record(
            guild_id=guild_id,
            user_id=user_id,
            google_sub=google_sub,
            email=email,
        )

    async def handle_google_callback(self, request: web.Request) -> web.Response:
        if not self.is_google_configured:
            return self.render_page(
                "학교 인증 불가",
                "Google OAuth 설정이 없어 인증을 처리할 수 없습니다.",
                success=False,
            )

        error = request.query.get("error")
        if error:
            return self.render_page(
                "학교 인증 취소됨",
                f"Google 로그인에서 오류가 발생했습니다: {error}",
                success=False,
            )

        pending = self.pop_pending_session(request.query.get("state"))
        if pending is None:
            return self.render_page(
                "학교 인증 실패",
                "인증 링크가 만료되었거나 잘못되었습니다. 디스코드에서 다시 인증 버튼을 눌러 주세요.",
                success=False,
            )

        code = request.query.get("code")
        if not code:
            return self.render_page(
                "학교 인증 실패",
                "Google 인증 코드를 받지 못했습니다. 다시 시도해 주세요.",
                success=False,
            )

        config = self.get_config(pending.guild_id)
        if config is None:
            return self.render_page(
                "학교 인증 실패",
                "서버 학교 인증 설정을 찾지 못했습니다. 관리자에게 문의해 주세요.",
                success=False,
            )

        try:
            token_payload = await self.exchange_google_code(code)
            id_token = str(token_payload.get("id_token", "")).strip()
            if not id_token:
                raise ValueError("Google ID 토큰을 받지 못했습니다.")

            decoded_payload = self.verify_google_id_token(id_token)
            google_sub, email = self.validate_google_identity(
                payload=decoded_payload,
                expected_domain=config.domain,
            )
            await self.finish_verification(
                guild_id=pending.guild_id,
                user_id=pending.user_id,
                google_sub=google_sub,
                email=email,
            )
        except ValueError as error:
            return self.render_page(
                "학교 인증 실패",
                str(error),
                success=False,
            )
        except Exception as error:
            return self.render_page(
                "학교 인증 실패",
                f"처리 중 예상하지 못한 오류가 발생했습니다: {error}",
                success=False,
            )

        return self.render_page(
            "학교 인증 완료",
            "인증이 완료되었습니다. 디스코드로 돌아가면 다른 채널을 볼 수 있습니다.",
            success=True,
        )

    def build_auth_panel_embed(self, domain: str) -> discord.Embed:
        return discord.Embed(
            title="학교 계정 인증",
            description=(
                "이 서버는 학교 Google 계정 인증 후에만 다른 채널을 볼 수 있습니다.\n"
                f"`@{domain}` 계정으로 로그인해 인증을 완료해 주세요."
            ),
            color=discord.Color.blue(),
        ).add_field(
            name="진행 방법",
            value=(
                "1. 아래 버튼을 누릅니다.\n"
                "2. 브라우저에서 학교 Google 계정으로 로그인합니다.\n"
                "3. 인증 완료 후 디스코드로 돌아옵니다."
            ),
            inline=False,
        )

    async def send_auth_link(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None or interaction.guild_id is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        config = self.get_config(interaction.guild_id)
        if config is None:
            await interaction.response.send_message(
                "이 서버는 아직 학교 인증이 설정되지 않았습니다.",
                ephemeral=True,
            )
            return

        if not self.is_google_configured:
            await interaction.response.send_message(
                "Google OAuth 설정이 없어 인증 링크를 만들 수 없습니다.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "멤버 정보를 확인할 수 없습니다.",
                ephemeral=True,
            )
            return

        verified_role = self.get_verified_role(guild, config)
        if verified_role is not None and verified_role in interaction.user.roles:
            await interaction.response.send_message(
                "이미 학교 인증이 완료되어 있습니다.",
                ephemeral=True,
            )
            return

        session = self.create_pending_session(interaction.guild_id, interaction.user.id)
        auth_url = self.build_google_auth_url(config, session.state)
        await interaction.response.send_message(
            (
                f"`@{config.domain}` 학교 Google 계정으로 로그인해 주세요.\n"
                "아래 버튼을 누르면 브라우저에서 인증을 진행할 수 있습니다."
            ),
            view=SchoolAuthLinkView(auth_url),
            ephemeral=True,
        )

    async def ensure_role(
        self,
        guild: discord.Guild,
        role_id: int | None,
        fallback_name: str,
        *,
        reason: str,
    ) -> discord.Role:
        role = guild.get_role(role_id) if role_id else None
        if role is not None:
            return role

        existing = discord.utils.get(guild.roles, name=fallback_name)
        if existing is not None:
            return existing

        return await guild.create_role(name=fallback_name, reason=reason)

    async def ensure_auth_spaces(
        self,
        guild: discord.Guild,
        config: SchoolAuthGuildConfig | None,
        *,
        reason: str,
    ) -> tuple[discord.CategoryChannel, discord.TextChannel]:
        category = guild.get_channel(config.auth_category_id) if config else None
        if not isinstance(category, discord.CategoryChannel):
            category = discord.utils.get(guild.categories, name=AUTH_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(AUTH_CATEGORY_NAME, reason=reason)

        channel = guild.get_channel(config.auth_channel_id) if config else None
        if not isinstance(channel, discord.TextChannel):
            channel = discord.utils.get(guild.text_channels, name=AUTH_CHANNEL_NAME)
            if channel is not None and channel.category_id != category.id:
                channel = None
        if channel is None:
            channel = await guild.create_text_channel(
                AUTH_CHANNEL_NAME,
                category=category,
                reason=reason,
            )

        if channel.category_id != category.id:
            await channel.edit(category=category, reason=reason)

        return category, channel

    async def configure_auth_space_permissions(
        self,
        guild: discord.Guild,
        *,
        category: discord.CategoryChannel,
        channel: discord.TextChannel,
        unverified_role: discord.Role,
        verified_role: discord.Role,
        bypass_role: discord.Role | None,
        reason: str,
    ) -> None:
        category_overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            unverified_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            verified_role: discord.PermissionOverwrite(view_channel=False),
        }
        if bypass_role is not None:
            category_overwrites[bypass_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )

        await category.edit(overwrites=category_overwrites, reason=reason)
        await channel.edit(
            topic="학교 계정 인증 전용 채널입니다.",
            sync_permissions=True,
            reason=reason,
        )

    async def lock_other_channels(
        self,
        guild: discord.Guild,
        *,
        config: SchoolAuthGuildConfig,
        unverified_role: discord.Role,
        reason: str,
    ) -> tuple[int, int]:
        updated = 0
        failed = 0
        for channel in guild.channels:
            if channel.id == config.auth_category_id or channel.id == config.auth_channel_id:
                continue
            if getattr(channel, "category_id", None) == config.auth_category_id:
                continue

            try:
                await channel.set_permissions(
                    unverified_role,
                    view_channel=False,
                    reason=reason,
                )
                updated += 1
            except discord.HTTPException:
                failed += 1

        return updated, failed

    async def sync_member_access(
        self,
        guild: discord.Guild,
        *,
        config: SchoolAuthGuildConfig,
        reason: str,
    ) -> dict[str, int]:
        unverified_role = self.get_unverified_role(guild, config)
        verified_role = self.get_verified_role(guild, config)
        if unverified_role is None or verified_role is None:
            raise ValueError("학교 인증 역할을 찾지 못했습니다.")

        summary = {
            "verified_assigned": 0,
            "unverified_assigned": 0,
            "bypass_skipped": 0,
            "bots_skipped": 0,
            "failed": 0,
        }

        for member in guild.members:
            if member.bot:
                summary["bots_skipped"] += 1
                continue

            if self.member_is_bypass(member, config):
                summary["bypass_skipped"] += 1
                try:
                    if unverified_role in member.roles:
                        await member.remove_roles(unverified_role, reason=reason)
                except discord.HTTPException:
                    summary["failed"] += 1
                continue

            verified_record = self.bot.school_verification_store.get_record(
                guild.id,
                member.id,
            )
            if verified_record is not None:
                roles_to_add = []
                roles_to_remove = []
                if verified_role not in member.roles:
                    roles_to_add.append(verified_role)
                if unverified_role in member.roles:
                    roles_to_remove.append(unverified_role)
                try:
                    if roles_to_add:
                        await member.add_roles(*roles_to_add, reason=reason)
                        summary["verified_assigned"] += 1
                    if roles_to_remove:
                        await member.remove_roles(*roles_to_remove, reason=reason)
                except discord.HTTPException:
                    summary["failed"] += 1
                continue

            roles_to_add = []
            roles_to_remove = []
            if unverified_role not in member.roles:
                roles_to_add.append(unverified_role)
            if verified_role in member.roles:
                roles_to_remove.append(verified_role)
            try:
                if roles_to_add:
                    await member.add_roles(*roles_to_add, reason=reason)
                    summary["unverified_assigned"] += 1
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason=reason)
            except discord.HTTPException:
                summary["failed"] += 1

        return summary

    async def post_or_update_auth_panel(
        self,
        channel: discord.TextChannel,
        config: SchoolAuthGuildConfig,
    ) -> int:
        embed = self.build_auth_panel_embed(config.domain)
        if config.panel_message_id is not None:
            try:
                message = await channel.fetch_message(config.panel_message_id)
                await message.edit(embed=embed, view=self.panel_view)
                return message.id
            except (discord.HTTPException, discord.NotFound):
                pass

        message = await channel.send(embed=embed, view=self.panel_view)
        return message.id

    async def configure_guild_school_auth(
        self,
        guild: discord.Guild,
        requester: discord.Member,
        *,
        domain: str,
        bypass_role: discord.Role | None,
    ) -> tuple[SchoolAuthGuildConfig, dict[str, int], int, int]:
        bot_user = self.bot.user
        if bot_user is None:
            raise ValueError("봇 정보를 확인할 수 없습니다.")

        bot_member = guild.get_member(bot_user.id)
        if bot_member is None:
            raise ValueError("봇 멤버 정보를 확인할 수 없습니다.")

        if not bot_member.guild_permissions.manage_roles:
            raise ValueError("봇에 역할 관리 권한이 없습니다.")

        if not bot_member.guild_permissions.manage_channels:
            raise ValueError("봇에 채널 관리 권한이 없습니다.")

        reason = f"/school_auth_setup by {requester} ({requester.id})"
        current = self.get_config(guild.id)
        unverified_role = await self.ensure_role(
            guild,
            current.unverified_role_id if current else None,
            UNVERIFIED_ROLE_NAME,
            reason=reason,
        )
        verified_role = await self.ensure_role(
            guild,
            current.verified_role_id if current else None,
            VERIFIED_ROLE_NAME,
            reason=reason,
        )
        category, channel = await self.ensure_auth_spaces(guild, current, reason=reason)

        config = SchoolAuthGuildConfig(
            guild_id=guild.id,
            domain=domain,
            auth_category_id=category.id,
            auth_channel_id=channel.id,
            unverified_role_id=unverified_role.id,
            verified_role_id=verified_role.id,
            bypass_role_id=bypass_role.id if bypass_role is not None else None,
            panel_message_id=current.panel_message_id if current else None,
        )

        await self.configure_auth_space_permissions(
            guild,
            category=category,
            channel=channel,
            unverified_role=unverified_role,
            verified_role=verified_role,
            bypass_role=bypass_role,
            reason=reason,
        )
        self.bot.school_auth_config_store.set_config(config)

        updated_channels, failed_channels = await self.lock_other_channels(
            guild,
            config=config,
            unverified_role=unverified_role,
            reason=reason,
        )
        member_summary = await self.sync_member_access(
            guild,
            config=config,
            reason=reason,
        )
        panel_message_id = await self.post_or_update_auth_panel(channel, config)
        self.bot.school_auth_config_store.update_panel_message_id(guild.id, panel_message_id)
        final_config = self.get_config(guild.id)
        if final_config is None:
            raise ValueError("학교 인증 설정 저장에 실패했습니다.")

        return final_config, member_summary, updated_channels, failed_channels

    def normalize_domain(self, domain: str) -> str:
        normalized = domain.strip().casefold()
        if normalized.startswith("@"):
            normalized = normalized[1:]
        return normalized

    def build_setup_summary(
        self,
        config: SchoolAuthGuildConfig,
        member_summary: dict[str, int],
        updated_channels: int,
        failed_channels: int,
    ) -> str:
        lines = [
            "✅ 학교 인증 잠금 설정을 완료했습니다.",
            f"학교 도메인: `@{config.domain}`",
            f"인증 채널 ID: `{config.auth_channel_id}`",
            f"미인증 역할 ID: `{config.unverified_role_id}`",
            f"인증완료 역할 ID: `{config.verified_role_id}`",
            f"잠금 적용 채널 수: {updated_channels}",
            f"잠금 실패 채널 수: {failed_channels}",
            "",
            f"기존 인증 완료 역할 부여: {member_summary['verified_assigned']}명",
            f"미인증 역할 부여: {member_summary['unverified_assigned']}명",
            f"관리자/예외 역할 제외: {member_summary['bypass_skipped']}명",
            f"봇 제외: {member_summary['bots_skipped']}명",
            f"역할 변경 실패: {member_summary['failed']}명",
        ]
        return "\n".join(lines)

    @app_commands.command(name="school_auth", description="학교 Google 계정 인증 링크 발급")
    async def school_auth(self, interaction: discord.Interaction) -> None:
        await self.send_auth_link(interaction)

    @app_commands.command(
        name="school_auth_setup",
        description="학교 Google 계정 인증 잠금 채널과 역할을 설정",
    )
    @app_commands.rename(domain="도메인", bypass_role="관리자")
    @app_commands.describe(
        domain="허용할 학교 메일 도메인 예: bssm.hs.kr",
        bypass_role="학교 인증을 건너뛸 관리자/운영진 역할",
    )
    @app_commands.default_permissions(administrator=True)
    async def school_auth_setup(
        self,
        interaction: discord.Interaction,
        domain: app_commands.Range[str, 3, 255],
        bypass_role: discord.Role | None = None,
    ) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not self.is_google_configured:
            await interaction.response.send_message(
                "Google OAuth 설정이 없어 학교 인증 기능을 설정할 수 없습니다.",
                ephemeral=True,
            )
            return

        normalized_domain = self.normalize_domain(domain)
        if "." not in normalized_domain or " " in normalized_domain:
            await interaction.response.send_message(
                "학교 도메인은 `bssm.hs.kr`처럼 입력해 주세요.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            config, member_summary, updated_channels, failed_channels = await self.configure_guild_school_auth(
                interaction.guild,
                interaction.user,
                domain=normalized_domain,
                bypass_role=bypass_role,
            )
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except discord.HTTPException as error:
            await interaction.followup.send(
                f"학교 인증 설정 중 Discord 오류가 발생했습니다: {error}",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            self.build_setup_summary(
                config,
                member_summary,
                updated_channels,
                failed_channels,
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="school_auth_sync",
        description="학교 인증 채널 잠금과 미인증 역할 상태를 다시 동기화",
    )
    @app_commands.default_permissions(administrator=True)
    async def school_auth_sync(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        current = self.get_config(interaction.guild.id)
        if current is None:
            await interaction.response.send_message(
                "이 서버는 아직 학교 인증 설정이 없습니다. `/학교인증설정`을 먼저 실행해 주세요.",
                ephemeral=True,
            )
            return

        bypass_role = self.get_bypass_role(interaction.guild, current)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            config, member_summary, updated_channels, failed_channels = await self.configure_guild_school_auth(
                interaction.guild,
                interaction.user,
                domain=current.domain,
                bypass_role=bypass_role,
            )
        except ValueError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        except discord.HTTPException as error:
            await interaction.followup.send(
                f"학교 인증 동기화 중 Discord 오류가 발생했습니다: {error}",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            self.build_setup_summary(
                config,
                member_summary,
                updated_channels,
                failed_channels,
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="school_auth_status",
        description="현재 학교 인증 완료 여부를 확인",
    )
    async def school_auth_status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        config = self.get_config(interaction.guild.id)
        if config is None:
            await interaction.response.send_message(
                "이 서버는 아직 학교 인증 설정이 없습니다.",
                ephemeral=True,
            )
            return

        verified_role = self.get_verified_role(interaction.guild, config)
        record = self.bot.school_verification_store.get_record(
            interaction.guild.id,
            interaction.user.id,
        )
        if verified_role is not None and verified_role in interaction.user.roles and record:
            await interaction.response.send_message(
                (
                    "✅ 학교 인증 완료 상태입니다.\n"
                    f"인증 메일: `{record.email}`\n"
                    f"인증 시각: `{record.verified_at}`"
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "아직 학교 인증이 완료되지 않았습니다. 인증 채널의 버튼을 눌러 진행해 주세요.",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        config = self.get_config(member.guild.id)
        if config is None:
            return

        if self.member_is_bypass(member, config):
            return

        unverified_role = self.get_unverified_role(member.guild, config)
        verified_role = self.get_verified_role(member.guild, config)
        if unverified_role is None or verified_role is None:
            return

        record = self.bot.school_verification_store.get_record(member.guild.id, member.id)
        try:
            if record is not None:
                if verified_role not in member.roles:
                    await member.add_roles(
                        verified_role,
                        reason="school_auth returning verified member",
                    )
                if unverified_role in member.roles:
                    await member.remove_roles(
                        unverified_role,
                        reason="school_auth returning verified member",
                    )
                return

            if unverified_role not in member.roles:
                await member.add_roles(
                    unverified_role,
                    reason="school_auth new member",
                )
        except discord.HTTPException:
            return

    @commands.Cog.listener()
    async def on_guild_channel_create(
        self,
        channel: discord.abc.GuildChannel,
    ) -> None:
        guild = channel.guild
        config = self.get_config(guild.id)
        if config is None:
            return

        unverified_role = self.get_unverified_role(guild, config)
        if unverified_role is None:
            return

        try:
            if channel.id == config.auth_channel_id or getattr(
                channel,
                "category_id",
                None,
            ) == config.auth_category_id:
                return

            await channel.set_permissions(
                unverified_role,
                view_channel=False,
                reason="school_auth auto-lock new channel",
            )
        except discord.HTTPException:
            return


async def setup(bot: "CoraxBot") -> None:
    cog = SchoolAuthCog(bot)
    await bot.add_cog(cog)
    bot.add_view(cog.panel_view)
    await cog.start_web_server()

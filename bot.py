from pathlib import Path

import discord
from discord.ext import commands

from services.announce_config import AnnounceChannelStore
from services.bamboo_config import BambooChannelStore
from services.gemini_client import GeminiService
from services.localization import CoraxTranslator
from services.poll_store import PollStore
from services.remind_store import RemindStore
from services.schedule_store import ScheduleStore
from services.school_auth_store import SchoolAuthConfigStore, SchoolVerificationStore
from services.warn_store import WarnStore


class CoraxBot(commands.Bot):
    def __init__(
        self,
        base_dir: Path,
        sync_guild_id: str | None,
        sync_commands_on_startup: bool,
        gemini_api_key: str | None,
        gemini_model: str | None,
        google_client_id: str | None,
        google_client_secret: str | None,
        google_redirect_uri: str | None,
        school_auth_bind_host: str | None,
        school_auth_bind_port: int | None,
        enable_school_auth_web_server: bool = True,
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(command_prefix="!", intents=intents)
        self.base_dir = base_dir
        self.sync_guild_id = sync_guild_id
        self.sync_commands_on_startup = sync_commands_on_startup
        self.announce_store = AnnounceChannelStore(base_dir / "announce_channels.json")
        self.bamboo_store = BambooChannelStore(base_dir / "bamboo_channels.json")
        self.gemini_service = GeminiService(
            api_key=gemini_api_key,
            model=gemini_model or "gemini-2.5-flash-lite",
        )
        self.poll_store = PollStore(base_dir / "poll_records.json")
        self.remind_store = RemindStore(base_dir / "remind_records.json")
        self.schedule_store = ScheduleStore(base_dir / "schedule_records.json")
        self.warn_store = WarnStore(base_dir / "warn_records.json")
        self.school_auth_config_store = SchoolAuthConfigStore(
            base_dir / "school_auth_configs.json"
        )
        self.school_verification_store = SchoolVerificationStore(
            base_dir / "school_verifications.json"
        )
        self.google_client_id = google_client_id
        self.google_client_secret = google_client_secret
        self.google_redirect_uri = google_redirect_uri
        self.school_auth_bind_host = school_auth_bind_host or "127.0.0.1"
        self.school_auth_bind_port = school_auth_bind_port or 8080
        self.enable_school_auth_web_server = enable_school_auth_web_server
        self._commands_synced = False

    def get_sync_guild(self) -> discord.Object | None:
        if not self.sync_guild_id:
            return None

        try:
            return discord.Object(id=int(self.sync_guild_id))
        except ValueError:
            print("DISCORD_GUILD_ID 값이 올바르지 않습니다. 접속한 서버들에 동기화합니다.")
            return None

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.ai")
        await self.load_extension("cogs.bamboo")
        await self.load_extension("cogs.dice")
        await self.load_extension("cogs.general")
        await self.load_extension("cogs.school_auth")
        await self.load_extension("cogs.announce")
        await self.load_extension("cogs.moderation")
        await self.load_extension("cogs.move")
        await self.load_extension("cogs.poll")
        await self.load_extension("cogs.remind")
        await self.load_extension("cogs.roles")
        await self.load_extension("cogs.schedule")
        await self.load_extension("cogs.timeout")
        await self.load_extension("cogs.translate")
        await self.load_extension("cogs.warn")
        await self.tree.set_translator(CoraxTranslator())

    async def clear_global_application_commands(self) -> None:
        global_commands = list(self.tree.get_commands())
        if not global_commands:
            return

        self.tree.clear_commands(guild=None)
        try:
            await self.tree.sync()
            print("전역 슬래시 명령어 정리 완료")
        finally:
            for command in global_commands:
                self.tree.add_command(command)

    async def sync_guild_application_commands(
        self,
        guild: discord.abc.Snowflake,
    ) -> None:
        self.tree.clear_commands(guild=guild)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        print(
            "서버 슬래시 명령어 동기화 완료: "
            f"{len(synced)}개 (guild_id={guild.id})"
        )

    async def sync_application_commands(self) -> None:
        await self.clear_global_application_commands()

        sync_guild = self.get_sync_guild()
        if sync_guild is not None:
            await self.sync_guild_application_commands(sync_guild)
            return

        for guild in self.guilds:
            await self.sync_guild_application_commands(guild)

    async def on_ready(self) -> None:
        print(f"로그인 완료: {self.user}")

        if self._commands_synced:
            return

        if not self.sync_commands_on_startup:
            print("슬래시 명령어 자동 동기화 건너뜀")
            self._commands_synced = True
            return

        try:
            await self.sync_application_commands()
            self._commands_synced = True
        except Exception as error:
            print(f"명령어 동기화 실패: {error}")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        if not self.sync_commands_on_startup:
            return

        sync_guild = self.get_sync_guild()
        if sync_guild is not None and guild.id != sync_guild.id:
            return

        try:
            await self.sync_guild_application_commands(guild)
        except Exception as error:
            print(f"새 서버 명령어 동기화 실패 (guild_id={guild.id}): {error}")

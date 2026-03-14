import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from bot import CoraxBot
from services.discord_token import validate_discord_token


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="또봇 슬래시 명령어를 수동으로 동기화합니다.",
    )
    parser.add_argument(
        "--guild",
        action="append",
        dest="guild_ids",
        help="동기화할 서버 ID. 여러 번 지정할 수 있습니다.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="봇이 들어가 있는 모든 서버에 동기화합니다.",
    )
    return parser.parse_args()


class CommandSyncBot(CoraxBot):
    def __init__(
        self,
        *,
        target_guild_ids: list[int] | None,
        sync_all_guilds: bool,
        **kwargs,
    ) -> None:
        super().__init__(sync_commands_on_startup=False, **kwargs)
        self.target_guild_ids = target_guild_ids
        self.sync_all_guilds = sync_all_guilds

    async def on_ready(self) -> None:
        print(f"로그인 완료: {self.user}")

        await self.clear_global_application_commands()

        if self.sync_all_guilds:
            guilds = list(self.guilds)
        else:
            target_ids = set(self.target_guild_ids or [])
            guilds = [guild for guild in self.guilds if guild.id in target_ids]

        if not guilds:
            print("동기화할 서버가 없습니다.")
            await self.close()
            return

        for guild in guilds:
            try:
                await self.sync_guild_application_commands(guild)
            except Exception as error:
                print(f"동기화 실패 (guild_id={guild.id}, name={guild.name}): {error}")

        await self.close()


async def main() -> None:
    args = parse_args()

    if not args.all and not args.guild_ids:
        raise SystemExit("`--all` 또는 `--guild 서버ID` 중 하나는 지정해야 합니다.")

    base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir / ".env")

    token = validate_discord_token(
        os.getenv("DISCORD_BOT_TOKEN") or os.getenv("DISCORD_TOKEN")
    )
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL")

    guild_ids: list[int] | None = None
    if args.guild_ids:
        try:
            guild_ids = [int(guild_id) for guild_id in args.guild_ids]
        except ValueError as error:
            raise SystemExit(f"서버 ID는 숫자여야 합니다: {error}") from error

    bot = CommandSyncBot(
        base_dir=base_dir,
        sync_guild_id=None,
        target_guild_ids=guild_ids,
        sync_all_guilds=args.all,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
    )
    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())

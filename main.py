import os
import socket
import time
from pathlib import Path

import aiohttp
import discord
from dotenv import load_dotenv

from bot import CoraxBot
from services.discord_token import validate_discord_token
from services.instance_lock import InstanceLock, InstanceLockError

load_dotenv()


def get_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def load_token() -> str:
    try:
        return validate_discord_token(
            os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")
        )
    except ValueError as error:
        raise SystemExit(f"Discord 토큰 설정 오류: {error}") from error


TOKEN = load_token()
SYNC_GUILD_ID = os.getenv("DISCORD_GUILD_ID")
SYNC_COMMANDS_ON_STARTUP = get_bool_env("SYNC_COMMANDS_ON_STARTUP")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
BASE_DIR = Path(__file__).resolve().parent


def create_bot() -> CoraxBot:
    return CoraxBot(
        base_dir=BASE_DIR,
        sync_guild_id=SYNC_GUILD_ID,
        sync_commands_on_startup=SYNC_COMMANDS_ON_STARTUP,
        gemini_api_key=GEMINI_API_KEY,
        gemini_model=GEMINI_MODEL,
    )


lock = InstanceLock(BASE_DIR / ".corax.lock")
try:
    lock.acquire()
except InstanceLockError as error:
    raise SystemExit(str(error)) from error

try:
    while True:
        bot = create_bot()
        try:
            bot.run(TOKEN)
            break
        except discord.LoginFailure as error:
            raise SystemExit(
                "Discord 봇 토큰이 잘못됐거나 이미 폐기됐습니다. "
                "Render 환경변수 `DISCORD_BOT_TOKEN` 또는 `DISCORD_TOKEN`에 "
                "Discord Developer Portal에서 다시 발급한 Bot Token 본문만 넣고 재배포해 주세요."
            ) from error
        except (
            aiohttp.ClientConnectorError,
            aiohttp.ClientConnectorDNSError,
            socket.gaierror,
        ) as error:
            print(f"Discord 연결 실패: {error}")
            print("인터넷 또는 DNS 문제입니다. 5초 뒤에 다시 연결합니다.")
            time.sleep(5)
finally:
    lock.release()

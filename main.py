import os
import socket
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

from bot import CoraxBot
from services.discord_token import validate_discord_token
from services.instance_lock import InstanceLock, InstanceLockError

load_dotenv()

TOKEN = validate_discord_token(
    os.getenv("DISCORD_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")
)
SYNC_GUILD_ID = os.getenv("DISCORD_GUILD_ID")
SYNC_COMMANDS_ON_STARTUP = os.getenv("SYNC_COMMANDS_ON_STARTUP", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
RENDER_PORT = os.getenv("PORT")
SCHOOL_AUTH_BIND_HOST = os.getenv(
    "SCHOOL_AUTH_BIND_HOST",
    "0.0.0.0" if RENDER_PORT else "127.0.0.1",
)
SCHOOL_AUTH_BIND_PORT = int(os.getenv("SCHOOL_AUTH_BIND_PORT") or RENDER_PORT or "8080")
BASE_DIR = Path(__file__).resolve().parent

def create_bot() -> CoraxBot:
    return CoraxBot(
        base_dir=BASE_DIR,
        sync_guild_id=SYNC_GUILD_ID,
        sync_commands_on_startup=SYNC_COMMANDS_ON_STARTUP,
        gemini_api_key=GEMINI_API_KEY,
        gemini_model=GEMINI_MODEL,
        google_client_id=GOOGLE_CLIENT_ID,
        google_client_secret=GOOGLE_CLIENT_SECRET,
        google_redirect_uri=GOOGLE_REDIRECT_URI,
        school_auth_bind_host=SCHOOL_AUTH_BIND_HOST,
        school_auth_bind_port=SCHOOL_AUTH_BIND_PORT,
        enable_school_auth_web_server=True,
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
        except (
            aiohttp.ClientConnectorError,
            aiohttp.ClientConnectorDNSError,
            socket.gaierror,
        ) as error:
            print(f"Discord 연결 실패: {error}")
            print("인터넷 또는 DNS 문제입니다. 5초 뒤 다시 연결합니다.")
            time.sleep(5)
finally:
    lock.release()

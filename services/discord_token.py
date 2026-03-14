from __future__ import annotations


def validate_discord_token(token: str | None) -> str:
    if token is None:
        raise ValueError(
            "DISCORD_TOKEN 또는 DISCORD_BOT_TOKEN이 .env 파일에 없습니다."
        )

    normalized = token.strip()
    if not normalized:
        raise ValueError("DISCORD_TOKEN이 비어 있습니다.")

    if normalized.startswith("Bot "):
        raise ValueError("DISCORD_TOKEN에는 `Bot ` 접두사 없이 봇 토큰 원문만 넣어야 합니다.")

    if normalized.count(".") != 2:
        raise ValueError(
            "DISCORD_TOKEN 형식이 올바르지 않습니다. Discord 봇 토큰 전체 값을 그대로 넣어야 합니다."
        )

    return normalized

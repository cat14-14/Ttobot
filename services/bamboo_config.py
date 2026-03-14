import json
from pathlib import Path


class BambooChannelStore:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.channels = self._load()

    def _load(self) -> dict[str, int]:
        if not self.file_path.exists():
            return {}

        try:
            raw_data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        if not isinstance(raw_data, dict):
            return {}

        channels: dict[str, int] = {}
        for guild_id, channel_id in raw_data.items():
            try:
                channels[str(guild_id)] = int(channel_id)
            except (TypeError, ValueError):
                continue

        return channels

    def _save(self) -> None:
        self.file_path.write_text(
            json.dumps(self.channels, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_channel_id(self, guild_id: int) -> int | None:
        return self.channels.get(str(guild_id))

    def set_channel(self, guild_id: int, channel_id: int) -> None:
        self.channels[str(guild_id)] = channel_id
        self._save()

    def clear_channel(self, guild_id: int) -> bool:
        removed = self.channels.pop(str(guild_id), None)
        if removed is None:
            return False

        self._save()
        return True

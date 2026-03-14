from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class ReminderEntry:
    reminder_id: str
    user_id: int
    guild_id: int
    channel_id: int
    content: str
    due_at: str
    created_at: str

    def due_at_datetime(self) -> datetime:
        return datetime.fromisoformat(self.due_at)


class RemindStore:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.entries = self._load()

    def _load(self) -> list[dict[str, object]]:
        if not self.file_path.exists():
            return []

        try:
            raw_data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

        if not isinstance(raw_data, list):
            return []

        normalized_entries: list[dict[str, object]] = []
        for raw_entry in raw_data:
            if isinstance(raw_entry, dict):
                normalized_entries.append(raw_entry)

        return normalized_entries

    def _save(self) -> None:
        self.file_path.write_text(
            json.dumps(self.entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _parse_entry(self, raw_entry: object) -> ReminderEntry | None:
        if not isinstance(raw_entry, dict):
            return None

        try:
            reminder_id = str(raw_entry["reminder_id"])
            user_id = int(raw_entry["user_id"])
            guild_id = int(raw_entry["guild_id"])
            channel_id = int(raw_entry["channel_id"])
            content = str(raw_entry["content"])
            due_at = str(raw_entry["due_at"])
            created_at = str(raw_entry["created_at"])
        except (KeyError, TypeError, ValueError):
            return None

        try:
            datetime.fromisoformat(due_at)
            datetime.fromisoformat(created_at)
        except ValueError:
            return None

        return ReminderEntry(
            reminder_id=reminder_id,
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
            content=content,
            due_at=due_at,
            created_at=created_at,
        )

    def list_entries(self) -> list[ReminderEntry]:
        parsed_entries = [
            entry
            for raw_entry in self.entries
            if (entry := self._parse_entry(raw_entry)) is not None
        ]
        return sorted(parsed_entries, key=lambda entry: entry.due_at_datetime())

    def add_reminder(
        self,
        user_id: int,
        guild_id: int,
        channel_id: int,
        content: str,
        due_at: datetime,
        created_at: datetime,
    ) -> ReminderEntry:
        entry = ReminderEntry(
            reminder_id=uuid4().hex,
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
            content=content,
            due_at=due_at.isoformat(),
            created_at=created_at.isoformat(),
        )
        self.entries.append(
            {
                "reminder_id": entry.reminder_id,
                "user_id": entry.user_id,
                "guild_id": entry.guild_id,
                "channel_id": entry.channel_id,
                "content": entry.content,
                "due_at": entry.due_at,
                "created_at": entry.created_at,
            }
        )
        self._save()
        return entry

    def remove_reminder(self, reminder_id: str) -> bool:
        original_count = len(self.entries)
        self.entries = [
            raw_entry
            for raw_entry in self.entries
            if str(raw_entry.get("reminder_id")) != reminder_id
        ]
        if len(self.entries) == original_count:
            return False

        self._save()
        return True

    def get_due_entries(self, now: datetime) -> list[ReminderEntry]:
        return [
            entry
            for entry in self.list_entries()
            if entry.due_at_datetime() <= now
        ]

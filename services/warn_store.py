from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class WarningEntry:
    warning_number: int
    moderator_id: int
    reason: str
    created_at: str


@dataclass(frozen=True)
class WarningRecord:
    entries: list[WarningEntry] = field(default_factory=list)
    triggered_thresholds: set[int] = field(default_factory=set)

    @property
    def warning_count(self) -> int:
        return len(self.entries)


class WarnStore:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.records = self._load()

    def _load(self) -> dict[str, dict[str, dict[str, object]]]:
        if not self.file_path.exists():
            return {}

        try:
            raw_data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        if not isinstance(raw_data, dict):
            return {}

        records: dict[str, dict[str, dict[str, object]]] = {}
        for guild_id, guild_data in raw_data.items():
            if not isinstance(guild_data, dict):
                continue

            normalized_guild: dict[str, dict[str, object]] = {}
            for user_id, user_data in guild_data.items():
                if isinstance(user_data, dict):
                    normalized_guild[str(user_id)] = user_data

            if normalized_guild:
                records[str(guild_id)] = normalized_guild

        return records

    def _save(self) -> None:
        self.file_path.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _empty_record(self) -> WarningRecord:
        return WarningRecord()

    def _parse_record(self, raw_record: object) -> WarningRecord:
        if not isinstance(raw_record, dict):
            return self._empty_record()

        entries_raw = raw_record.get("entries", [])
        entries: list[WarningEntry] = []
        if isinstance(entries_raw, list):
            for fallback_number, raw_entry in enumerate(entries_raw, start=1):
                if not isinstance(raw_entry, dict):
                    continue

                try:
                    warning_number = int(
                        raw_entry.get("warning_number", fallback_number)
                    )
                    moderator_id = int(raw_entry["moderator_id"])
                    reason = str(raw_entry["reason"])
                    created_at = str(raw_entry["created_at"])
                except (KeyError, TypeError, ValueError):
                    continue

                entries.append(
                    WarningEntry(
                        warning_number=warning_number,
                        moderator_id=moderator_id,
                        reason=reason,
                        created_at=created_at,
                    )
                )

        thresholds_raw = raw_record.get("triggered_thresholds", [])
        triggered_thresholds: set[int] = set()
        if isinstance(thresholds_raw, list):
            for threshold in thresholds_raw:
                try:
                    triggered_thresholds.add(int(threshold))
                except (TypeError, ValueError):
                    continue

        entries.sort(key=lambda entry: entry.warning_number)
        normalized_entries = [
            WarningEntry(
                warning_number=index,
                moderator_id=entry.moderator_id,
                reason=entry.reason,
                created_at=entry.created_at,
            )
            for index, entry in enumerate(entries, start=1)
        ]

        return WarningRecord(
            entries=normalized_entries,
            triggered_thresholds=triggered_thresholds,
        )

    def _serialize_record(self, record: WarningRecord) -> dict[str, object]:
        return {
            "entries": [
                {
                    "warning_number": entry.warning_number,
                    "moderator_id": entry.moderator_id,
                    "reason": entry.reason,
                    "created_at": entry.created_at,
                }
                for entry in record.entries
            ],
            "triggered_thresholds": sorted(record.triggered_thresholds),
        }

    def get_record(self, guild_id: int, user_id: int) -> WarningRecord:
        guild_records = self.records.get(str(guild_id), {})
        raw_record = guild_records.get(str(user_id))
        return self._parse_record(raw_record)

    def add_warning(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        reason: str,
    ) -> tuple[WarningRecord, WarningEntry]:
        record = self.get_record(guild_id, user_id)
        entry = WarningEntry(
            warning_number=record.warning_count + 1,
            moderator_id=moderator_id,
            reason=reason,
            created_at=datetime.now(UTC).isoformat(),
        )
        updated_record = WarningRecord(
            entries=[*record.entries, entry],
            triggered_thresholds=set(record.triggered_thresholds),
        )

        guild_key = str(guild_id)
        user_key = str(user_id)
        guild_records = self.records.setdefault(guild_key, {})
        guild_records[user_key] = self._serialize_record(updated_record)
        self._save()
        return updated_record, entry

    def mark_threshold_triggered(
        self,
        guild_id: int,
        user_id: int,
        threshold: int,
    ) -> WarningRecord:
        record = self.get_record(guild_id, user_id)
        updated_record = WarningRecord(
            entries=list(record.entries),
            triggered_thresholds={*record.triggered_thresholds, threshold},
        )

        guild_key = str(guild_id)
        user_key = str(user_id)
        guild_records = self.records.setdefault(guild_key, {})
        guild_records[user_key] = self._serialize_record(updated_record)
        self._save()
        return updated_record

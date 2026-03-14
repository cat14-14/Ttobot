from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class SchoolAuthGuildConfig:
    guild_id: int
    domain: str
    auth_category_id: int
    auth_channel_id: int
    unverified_role_id: int
    verified_role_id: int
    bypass_role_id: int | None = None
    panel_message_id: int | None = None
    student_role_config: "StudentRoleConfig | None" = None


@dataclass(frozen=True)
class StudentRoleConfig:
    third_grade_prefix: int
    second_grade_prefix: int
    first_grade_prefix: int
    third_grade_role_id: int
    second_grade_role_id: int
    first_grade_role_id: int
    admin_role_id: int | None = None


@dataclass(frozen=True)
class SchoolVerificationRecord:
    guild_id: int
    user_id: int
    google_sub: str
    email: str
    verified_at: str

    @property
    def verified_at_datetime(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.verified_at)
        except ValueError:
            return None


class SchoolAuthConfigStore:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.configs = self._load()

    def _load(self) -> dict[str, dict[str, object]]:
        if not self.file_path.exists():
            return {}

        try:
            raw_data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        if not isinstance(raw_data, dict):
            return {}

        configs: dict[str, dict[str, object]] = {}
        for guild_id, config in raw_data.items():
            if isinstance(config, dict):
                configs[str(guild_id)] = config

        return configs

    def _save(self) -> None:
        self.file_path.write_text(
            json.dumps(self.configs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _parse_config(self, raw_config: object) -> SchoolAuthGuildConfig | None:
        if not isinstance(raw_config, dict):
            return None

        try:
            guild_id = int(raw_config["guild_id"])
            domain = str(raw_config["domain"]).strip().casefold()
            auth_category_id = int(raw_config["auth_category_id"])
            auth_channel_id = int(raw_config["auth_channel_id"])
            unverified_role_id = int(raw_config["unverified_role_id"])
            verified_role_id = int(raw_config["verified_role_id"])
        except (KeyError, TypeError, ValueError):
            return None

        raw_bypass_role_id = raw_config.get("bypass_role_id")
        bypass_role_id: int | None = None
        if raw_bypass_role_id not in (None, ""):
            try:
                bypass_role_id = int(raw_bypass_role_id)
            except (TypeError, ValueError):
                bypass_role_id = None

        raw_panel_message_id = raw_config.get("panel_message_id")
        panel_message_id: int | None = None
        if raw_panel_message_id not in (None, ""):
            try:
                panel_message_id = int(raw_panel_message_id)
            except (TypeError, ValueError):
                panel_message_id = None

        student_role_config = self._parse_student_role_config(
            raw_config.get("student_role_config")
        )

        if not domain:
            return None

        return SchoolAuthGuildConfig(
            guild_id=guild_id,
            domain=domain,
            auth_category_id=auth_category_id,
            auth_channel_id=auth_channel_id,
            unverified_role_id=unverified_role_id,
            verified_role_id=verified_role_id,
            bypass_role_id=bypass_role_id,
            panel_message_id=panel_message_id,
            student_role_config=student_role_config,
        )

    def _parse_student_role_config(
        self,
        raw_student_role_config: object,
    ) -> StudentRoleConfig | None:
        if not isinstance(raw_student_role_config, dict):
            return None

        try:
            third_grade_prefix = int(raw_student_role_config["third_grade_prefix"])
            second_grade_prefix = int(raw_student_role_config["second_grade_prefix"])
            first_grade_prefix = int(raw_student_role_config["first_grade_prefix"])
            third_grade_role_id = int(raw_student_role_config["third_grade_role_id"])
            second_grade_role_id = int(raw_student_role_config["second_grade_role_id"])
            first_grade_role_id = int(raw_student_role_config["first_grade_role_id"])
        except (KeyError, TypeError, ValueError):
            return None

        raw_admin_role_id = raw_student_role_config.get("admin_role_id")
        admin_role_id: int | None = None
        if raw_admin_role_id not in (None, ""):
            try:
                admin_role_id = int(raw_admin_role_id)
            except (TypeError, ValueError):
                admin_role_id = None

        return StudentRoleConfig(
            third_grade_prefix=third_grade_prefix,
            second_grade_prefix=second_grade_prefix,
            first_grade_prefix=first_grade_prefix,
            third_grade_role_id=third_grade_role_id,
            second_grade_role_id=second_grade_role_id,
            first_grade_role_id=first_grade_role_id,
            admin_role_id=admin_role_id,
        )

    def _serialize_student_role_config(
        self,
        student_role_config: StudentRoleConfig | None,
    ) -> dict[str, object] | None:
        if student_role_config is None:
            return None

        return {
            "third_grade_prefix": student_role_config.third_grade_prefix,
            "second_grade_prefix": student_role_config.second_grade_prefix,
            "first_grade_prefix": student_role_config.first_grade_prefix,
            "third_grade_role_id": student_role_config.third_grade_role_id,
            "second_grade_role_id": student_role_config.second_grade_role_id,
            "first_grade_role_id": student_role_config.first_grade_role_id,
            "admin_role_id": student_role_config.admin_role_id,
        }

    def _serialize_config(self, config: SchoolAuthGuildConfig) -> dict[str, object]:
        return {
            "guild_id": config.guild_id,
            "domain": config.domain,
            "auth_category_id": config.auth_category_id,
            "auth_channel_id": config.auth_channel_id,
            "unverified_role_id": config.unverified_role_id,
            "verified_role_id": config.verified_role_id,
            "bypass_role_id": config.bypass_role_id,
            "panel_message_id": config.panel_message_id,
            "student_role_config": self._serialize_student_role_config(
                config.student_role_config
            ),
        }

    def get_config(self, guild_id: int) -> SchoolAuthGuildConfig | None:
        raw_config = self.configs.get(str(guild_id))
        return self._parse_config(raw_config)

    def set_config(self, config: SchoolAuthGuildConfig) -> None:
        self.configs[str(config.guild_id)] = self._serialize_config(config)
        self._save()

    def update_panel_message_id(self, guild_id: int, message_id: int | None) -> None:
        config = self.get_config(guild_id)
        if config is None:
            return

        self.set_config(
            SchoolAuthGuildConfig(
                guild_id=config.guild_id,
                domain=config.domain,
                auth_category_id=config.auth_category_id,
                auth_channel_id=config.auth_channel_id,
                unverified_role_id=config.unverified_role_id,
                verified_role_id=config.verified_role_id,
                bypass_role_id=config.bypass_role_id,
                panel_message_id=message_id,
                student_role_config=config.student_role_config,
            )
        )

    def update_student_role_config(
        self,
        guild_id: int,
        student_role_config: StudentRoleConfig | None,
    ) -> None:
        config = self.get_config(guild_id)
        if config is None:
            return

        self.set_config(
            SchoolAuthGuildConfig(
                guild_id=config.guild_id,
                domain=config.domain,
                auth_category_id=config.auth_category_id,
                auth_channel_id=config.auth_channel_id,
                unverified_role_id=config.unverified_role_id,
                verified_role_id=config.verified_role_id,
                bypass_role_id=config.bypass_role_id,
                panel_message_id=config.panel_message_id,
                student_role_config=student_role_config,
            )
        )

    def clear_config(self, guild_id: int) -> bool:
        removed = self.configs.pop(str(guild_id), None)
        if removed is None:
            return False

        self._save()
        return True


class SchoolVerificationStore:
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
        for guild_id, guild_records in raw_data.items():
            if not isinstance(guild_records, dict):
                continue

            normalized_guild_records: dict[str, dict[str, object]] = {}
            for user_id, record in guild_records.items():
                if isinstance(record, dict):
                    normalized_guild_records[str(user_id)] = record

            if normalized_guild_records:
                records[str(guild_id)] = normalized_guild_records

        return records

    def _save(self) -> None:
        self.file_path.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _parse_record(
        self,
        guild_id: int,
        user_id: int,
        raw_record: object,
    ) -> SchoolVerificationRecord | None:
        if not isinstance(raw_record, dict):
            return None

        try:
            google_sub = str(raw_record["google_sub"]).strip()
            email = str(raw_record["email"]).strip()
            verified_at = str(raw_record["verified_at"]).strip()
        except (KeyError, TypeError, ValueError):
            return None

        if not google_sub or not email or not verified_at:
            return None

        return SchoolVerificationRecord(
            guild_id=guild_id,
            user_id=user_id,
            google_sub=google_sub,
            email=email,
            verified_at=verified_at,
        )

    def get_record(self, guild_id: int, user_id: int) -> SchoolVerificationRecord | None:
        guild_records = self.records.get(str(guild_id), {})
        return self._parse_record(guild_id, user_id, guild_records.get(str(user_id)))

    def set_record(
        self,
        *,
        guild_id: int,
        user_id: int,
        google_sub: str,
        email: str,
    ) -> SchoolVerificationRecord:
        record = SchoolVerificationRecord(
            guild_id=guild_id,
            user_id=user_id,
            google_sub=google_sub,
            email=email,
            verified_at=datetime.now(UTC).isoformat(),
        )
        guild_records = self.records.setdefault(str(guild_id), {})
        guild_records[str(user_id)] = {
            "google_sub": record.google_sub,
            "email": record.email,
            "verified_at": record.verified_at,
        }
        self._save()
        return record

    def remove_record(self, guild_id: int, user_id: int) -> bool:
        guild_records = self.records.get(str(guild_id))
        if guild_records is None:
            return False

        removed = guild_records.pop(str(user_id), None)
        if removed is None:
            return False

        if not guild_records:
            self.records.pop(str(guild_id), None)

        self._save()
        return True

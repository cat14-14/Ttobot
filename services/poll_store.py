from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


PollChoice = str


@dataclass(frozen=True)
class PollRecord:
    message_id: int
    guild_id: int
    channel_id: int
    author_id: int
    question: str
    yes_label: str
    no_label: str
    is_public: bool
    votes: dict[int, PollChoice] = field(default_factory=dict)
    created_at: str = ""
    end_at: str = ""
    ended_at: str = ""
    ended_by: int | None = None

    @property
    def total_votes(self) -> int:
        return len(self.votes)

    @property
    def yes_votes(self) -> int:
        return sum(1 for choice in self.votes.values() if choice == "yes")

    @property
    def no_votes(self) -> int:
        return sum(1 for choice in self.votes.values() if choice == "no")

    @property
    def is_ended(self) -> bool:
        return bool(self.ended_at)

    def created_at_datetime(self) -> datetime | None:
        return self._parse_datetime(self.created_at)

    def end_at_datetime(self) -> datetime | None:
        return self._parse_datetime(self.end_at)

    def ended_at_datetime(self) -> datetime | None:
        return self._parse_datetime(self.ended_at)

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        if not value:
            return None

        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


class PollStore:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.polls = self._load()

    def _load(self) -> dict[str, dict[str, object]]:
        if not self.file_path.exists():
            return {}

        try:
            raw_data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        if not isinstance(raw_data, dict):
            return {}

        polls: dict[str, dict[str, object]] = {}
        for message_id, poll_data in raw_data.items():
            if isinstance(poll_data, dict):
                polls[str(message_id)] = poll_data

        return polls

    def _save(self) -> None:
        self.file_path.write_text(
            json.dumps(self.polls, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _parse_poll(self, raw_poll: object) -> PollRecord | None:
        if not isinstance(raw_poll, dict):
            return None

        try:
            message_id = int(raw_poll["message_id"])
            guild_id = int(raw_poll["guild_id"])
            channel_id = int(raw_poll["channel_id"])
            author_id = int(raw_poll["author_id"])
            question = str(raw_poll["question"])
            yes_label = str(raw_poll["yes_label"])
            no_label = str(raw_poll["no_label"])
            is_public = bool(raw_poll["is_public"])
            created_at = str(raw_poll.get("created_at", ""))
            end_at = str(raw_poll.get("end_at", ""))
            ended_at = str(raw_poll.get("ended_at", ""))
        except (KeyError, TypeError, ValueError):
            return None

        raw_ended_by = raw_poll.get("ended_by")
        ended_by: int | None = None
        if raw_ended_by not in (None, ""):
            try:
                ended_by = int(raw_ended_by)
            except (TypeError, ValueError):
                ended_by = None

        raw_votes = raw_poll.get("votes", {})
        votes: dict[int, PollChoice] = {}
        if isinstance(raw_votes, dict):
            for user_id, choice in raw_votes.items():
                if choice not in ("yes", "no"):
                    continue
                try:
                    votes[int(user_id)] = str(choice)
                except (TypeError, ValueError):
                    continue

        return PollRecord(
            message_id=message_id,
            guild_id=guild_id,
            channel_id=channel_id,
            author_id=author_id,
            question=question,
            yes_label=yes_label,
            no_label=no_label,
            is_public=is_public,
            votes=votes,
            created_at=created_at,
            end_at=end_at,
            ended_at=ended_at,
            ended_by=ended_by,
        )

    def _serialize_poll(self, poll: PollRecord) -> dict[str, object]:
        return {
            "message_id": poll.message_id,
            "guild_id": poll.guild_id,
            "channel_id": poll.channel_id,
            "author_id": poll.author_id,
            "question": poll.question,
            "yes_label": poll.yes_label,
            "no_label": poll.no_label,
            "is_public": poll.is_public,
            "votes": {str(user_id): choice for user_id, choice in poll.votes.items()},
            "created_at": poll.created_at,
            "end_at": poll.end_at,
            "ended_at": poll.ended_at,
            "ended_by": poll.ended_by,
        }

    def list_polls(self) -> list[PollRecord]:
        polls = [
            poll
            for raw_poll in self.polls.values()
            if (poll := self._parse_poll(raw_poll)) is not None
        ]
        return sorted(polls, key=lambda poll: poll.message_id)

    def get_poll(self, message_id: int) -> PollRecord | None:
        raw_poll = self.polls.get(str(message_id))
        return self._parse_poll(raw_poll)

    def add_poll(
        self,
        *,
        message_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        question: str,
        yes_label: str,
        no_label: str,
        is_public: bool,
        end_at: str = "",
    ) -> PollRecord:
        poll = PollRecord(
            message_id=message_id,
            guild_id=guild_id,
            channel_id=channel_id,
            author_id=author_id,
            question=question,
            yes_label=yes_label,
            no_label=no_label,
            is_public=is_public,
            votes={},
            created_at=datetime.now(UTC).isoformat(),
            end_at=end_at,
            ended_at="",
            ended_by=None,
        )
        self.polls[str(message_id)] = self._serialize_poll(poll)
        self._save()
        return poll

    def update_vote(
        self,
        *,
        message_id: int,
        user_id: int,
        choice: PollChoice,
    ) -> tuple[PollRecord | None, str]:
        poll = self.get_poll(message_id)
        if poll is None:
            return None, "missing"

        if poll.is_ended:
            return poll, "closed"

        votes = dict(poll.votes)
        previous_choice = votes.get(user_id)
        if previous_choice == choice:
            votes.pop(user_id, None)
            action = "removed"
        else:
            votes[user_id] = choice
            action = "changed" if previous_choice else "added"

        updated_poll = PollRecord(
            message_id=poll.message_id,
            guild_id=poll.guild_id,
            channel_id=poll.channel_id,
            author_id=poll.author_id,
            question=poll.question,
            yes_label=poll.yes_label,
            no_label=poll.no_label,
            is_public=poll.is_public,
            votes=votes,
            created_at=poll.created_at,
            end_at=poll.end_at,
            ended_at=poll.ended_at,
            ended_by=poll.ended_by,
        )
        self.polls[str(message_id)] = self._serialize_poll(updated_poll)
        self._save()
        return updated_poll, action

    def close_poll(
        self,
        *,
        message_id: int,
        ended_by: int | None,
    ) -> PollRecord | None:
        poll = self.get_poll(message_id)
        if poll is None:
            return None

        if poll.is_ended:
            return poll

        updated_poll = PollRecord(
            message_id=poll.message_id,
            guild_id=poll.guild_id,
            channel_id=poll.channel_id,
            author_id=poll.author_id,
            question=poll.question,
            yes_label=poll.yes_label,
            no_label=poll.no_label,
            is_public=poll.is_public,
            votes=dict(poll.votes),
            created_at=poll.created_at,
            end_at=poll.end_at,
            ended_at=datetime.now(UTC).isoformat(),
            ended_by=ended_by,
        )
        self.polls[str(message_id)] = self._serialize_poll(updated_poll)
        self._save()
        return updated_poll

    def remove_poll(self, message_id: int) -> bool:
        removed = self.polls.pop(str(message_id), None)
        if removed is None:
            return False

        self._save()
        return True

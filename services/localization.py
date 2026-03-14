from __future__ import annotations

import discord
from discord import app_commands


KOREAN_TRANSLATIONS: dict[str, str] = {
    "command": "명령어",
    "ttobot": "또봇",
    "dice": "주사위",
    "ping": "핑",
    "help": "도움말",
    "announce": "공지",
    "announce_channel_set": "공지채널설정",
    "announce_channel_clear": "공지채널해제",
    "bamboo": "대나무숲",
    "bamboo_channel_set": "대나무숲채널설정",
    "bamboo_channel_clear": "대나무숲채널해제",
    "clear": "청소",
    "clear_all": "전체청소",
    "move": "이동",
    "poll": "투표",
    "remind": "리마인드",
    "student": "학생",
    "role_add": "역할추가",
    "nickname": "별명변경",
    "schedule": "일정",
    "timeout": "채팅금지",
    "translate": "번역",
    "warn": "경고",
    "warnings": "경고기록",
}


ENGLISH_TRANSLATIONS: dict[str, str] = {
    "메시지 이동": "Move Message",
    "또봇 AI에게 질문": "Ask Ttobot AI",
    "또봇 AI에게 보낼 질문": "Question to send to Ttobot AI",
    "자연어를 내부 관리 명령으로 해석": "Interpret natural language as an internal moderation command",
    "예: 최근 메시지 20개 삭제해줘": "Example: delete the latest 20 messages",
    "주사위를 굴립니다": "Roll a die",
    "봇 응답 확인": "Check whether the bot is responding",
    "명령어 안내": "Show command help",
    "공지 채널에 공지 전송": "Send an announcement to the announcement channel",
    "공지 제목": "Announcement title",
    "공지 내용": "Announcement content",
    "함께 보낼 링크": "Link to include",
    "함께 보낼 이미지 파일": "Image file to include",
    "공지 채널 지정": "Set the announcement channel",
    "공지 메시지를 보낼 채널": "Channel to send announcements to",
    "공지 채널 해제": "Clear the announcement channel",
    "익명 대나무숲 글 작성": "Create an anonymous bamboo forest post",
    "함께 올릴 사진 파일": "Image file to attach",
    "대나무숲 채널 지정": "Set the bamboo forest channel",
    "익명 글이 올라갈 텍스트 채널 또는 포럼 채널": "Text or forum channel where anonymous posts will be sent",
    "대나무숲 채널 해제": "Clear the bamboo forest channel",
    "최근 메시지 삭제": "Delete recent messages",
    "삭제할 최근 메시지 수 (1~100)": "Number of recent messages to delete (1-100)",
    "이 채널의 오래된 메시지를 포함해 모두 삭제": "Delete all messages in this channel, including old ones",
    "현재 채널의 최근 메시지 여러 개 이동": "Move multiple recent messages from this channel",
    "메시지를 옮길 대상 채널": "Destination channel for the messages",
    "선택 후보로 불러올 최근 메시지 개수 (1~25)": "Number of recent messages to load as candidates (1-25)",
    "버튼형 찬반 투표 생성": "Create a button-based yes/no poll",
    "투표 질문": "Poll question",
    "찬성 선택지 문구, 비우면 '찬성'": "Yes option label, defaults to 'Yes' if empty",
    "반대 선택지 문구, 비우면 '반대'": "No option label, defaults to 'No' if empty",
    "누가 어디에 투표했는지 모두에게 공개할지 여부": "Whether to show everyone who voted for what",
    "종료 날짜 (YYYY-MM-DD)": "End date (YYYY-MM-DD)",
    "종료 시간 (HH:MM, 24시간 형식)": "End time (HH:MM, 24-hour format)",
    "종료 시간을 지정하지 않을지 여부": "Whether to disable the end time",
    "지정 시간이 지나면 DM 리마인더 전송": "Send a DM reminder after the specified time",
    "예: 30m, 1h, 1d": "Example: 30m, 1h, 1d",
    "DM으로 받을 리마인더 내용": "Reminder content to receive via DM",
    "이름 앞 숫자 기준으로 학년 역할 일괄 부여": "Bulk-assign grade roles based on the leading digit in display names",
    "3학년으로 볼 이름 시작 숫자": "Leading digit that counts as 3rd grade",
    "2학년으로 볼 이름 시작 숫자": "Leading digit that counts as 2nd grade",
    "1학년으로 볼 이름 시작 숫자": "Leading digit that counts as 1st grade",
    "학생 역할 부여에서 제외할 관리자 역할": "Admin role to exclude from student role assignment",
    "관리자 전용 역할 생성 및 부여": "Admin-only role creation and assignment",
    "역할을 부여할 유저": "User to assign the role to",
    "기존 역할명 또는 새로 만들 역할명": "Existing role name or a new role name to create",
    "관리자 전용 별명 변경": "Admin-only nickname change",
    "별명을 바꿀 유저": "User whose nickname will be changed",
    "새 별명": "New nickname",
    "간단 일정 알림 등록": "Register a simple schedule reminder",
    "알림 제목": "Reminder title",
    "일정 내용": "Schedule content",
    "날짜 형식 예: 2026-03-14": "Date format example: 2026-03-14",
    "24시간 형식 예: 20:00": "24-hour format example: 20:00",
    "일정 시간 채팅 금지": "Mute chat for a set amount of time",
    "타임아웃할 서버 멤버": "Server member to timeout",
    "예: 10m, 1h, 1h30m, 2d": "Example: 10m, 1h, 1h30m, 2d",
    "타임아웃 사유": "Timeout reason",
    "영어 문장을 한국어로 번역": "Translate English text into Korean",
    "한국어로 번역할 영어 문장": "English text to translate into Korean",
    "유저에게 경고를 부여하고 자동 제재를 적용": "Warn a user and apply automatic penalties",
    "경고를 부여할 서버 멤버": "Server member to warn",
    "경고 사유": "Warning reason",
    "유저의 경고 기록 확인": "Check a user's warning history",
    "경고 기록을 확인할 서버 멤버": "Server member whose warnings you want to check",
    "질문": "question",
    "요청": "request",
    "제목": "title",
    "내용": "content",
    "링크": "link",
    "사진": "image",
    "채널": "channel",
    "개수": "count",
    "대상채널": "destination",
    "찬성": "yes",
    "반대": "no",
    "공개": "public",
    "종료날짜": "end_date",
    "종료시간": "end_time",
    "종료없음": "no_end_time",
    "시간": "time",
    "유저": "user",
    "역할명": "role_name",
    "별명": "nickname",
    "날짜": "date",
    "이유": "reason",
    "영문": "text",
}


HELP_MESSAGES: dict[str, str] = {
    "ko": (
        "또봇 명령어 목록\n"
        "/명령어 - 자연어를 내부 관리 명령으로 해석\n"
        "/또봇 - 또봇 AI 질문\n"
        "/주사위 - 주사위 굴리기\n"
        "/핑 - 봇 응답 확인\n"
        "/도움말 - 명령어 안내\n"
        "/청소 - 최근 메시지 삭제 전 확인\n"
        "/전체청소 - 이 채널 메시지 전체 삭제\n"
        "/이동 - 최근 메시지 후보를 고른 뒤 다른 채널로 이동\n"
        "/투표 - 종료 시간 설정 가능한 버튼 찬반 투표 생성\n"
        "/리마인드 - 지정 시간 후 DM 리마인더 전송\n"
        "/학생 - 이름 앞 숫자 기준으로 1/2/3학년 역할 일괄 부여\n"
        "/역할추가 - 관리자 전용 역할 생성 및 부여\n"
        "/별명변경 - 관리자 전용 별명 변경\n"
        "/일정 - 제목/내용/날짜/시간 일정 알림 등록\n"
        "/채팅금지 - 일정 시간 채팅 금지\n"
        "/번역 - 영어 문장을 한국어로 번역\n"
        "/경고 - 유저 경고 및 자동 제재 적용\n"
        "/경고기록 - 유저 경고 기록 확인\n"
        "/공지 - 제목/내용에 링크와 사진을 추가해 @everyone 공지 전송\n"
        "/공지채널설정 - 공지 채널 지정\n"
        "/공지채널해제 - 공지 채널 해제\n"
        "/대나무숲 - 모달로 익명 게시물 작성\n"
        "/대나무숲채널설정 - 대나무숲 채널 지정\n"
        "/대나무숲채널해제 - 대나무숲 채널 해제\n"
        "메시지 우클릭 > 앱 > 메시지 이동 - 선택한 메시지 1개 이동"
    ),
    "en": (
        "Ttobot command list\n"
        "/command - Interpret natural language as an internal moderation command\n"
        "/ttobot - Ask Ttobot AI\n"
        "/dice - Roll a die\n"
        "/ping - Check bot response\n"
        "/help - Show command help\n"
        "/clear - Confirm deletion of recent messages\n"
        "/clear_all - Delete every message in this channel\n"
        "/move - Pick recent message candidates and move them to another channel\n"
        "/poll - Create a button-based yes/no poll with an optional end time\n"
        "/remind - Send a DM reminder after the specified time\n"
        "/student - Bulk-assign 1st/2nd/3rd grade roles from leading digits in names\n"
        "/role_add - Admin-only role creation and assignment\n"
        "/nickname - Admin-only nickname change\n"
        "/schedule - Register a schedule reminder with title/content/date/time\n"
        "/timeout - Mute chat for a set amount of time\n"
        "/translate - Translate English text into Korean\n"
        "/warn - Warn a user and apply automatic penalties\n"
        "/warnings - Check a user's warning history\n"
        "/announce - Send an @everyone announcement with optional links and images\n"
        "/announce_channel_set - Set the announcement channel\n"
        "/announce_channel_clear - Clear the announcement channel\n"
        "/bamboo - Create an anonymous post via modal with an optional image\n"
        "/bamboo_channel_set - Set the anonymous bamboo forest channel\n"
        "/bamboo_channel_clear - Clear the anonymous bamboo forest channel\n"
        "Right click a message > Apps > Move Message - Move one selected message"
    ),
}


PING_MESSAGES: dict[str, str] = {
    "ko": "또봇 온라인입니다.",
    "en": "Ttobot is online.",
}


def get_ui_language(locale: discord.Locale | None) -> str:
    if locale == discord.Locale.korean:
        return "ko"

    return "en"


class CoraxTranslator(app_commands.Translator):
    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> str | None:
        del context
        message = string.message

        if locale == discord.Locale.korean:
            return KOREAN_TRANSLATIONS.get(message)

        if locale in {discord.Locale.american_english, discord.Locale.british_english}:
            return ENGLISH_TRANSLATIONS.get(message)

        return None

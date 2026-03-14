from __future__ import annotations

import discord
from discord import app_commands


KOREAN_TRANSLATIONS: dict[str, str] = {
    "command": "\uba85\ub839\uc5b4",
    "ttobot": "\ub610\ubd07",
    "dice": "\uc8fc\uc0ac\uc704",
    "ping": "\ud551",
    "help": "\ub3c4\uc6c0\ub9d0",
    "announce": "\uacf5\uc9c0",
    "announce_channel_set": "\uacf5\uc9c0\ucc44\ub110\uc124\uc815",
    "announce_channel_clear": "\uacf5\uc9c0\ucc44\ub110\ud574\uc81c",
    "bamboo": "\ub300\ub098\ubb34\uc232",
    "bamboo_channel_set": "\ub300\ub098\ubb34\uc232\ucc44\ub110\uc124\uc815",
    "bamboo_channel_clear": "\ub300\ub098\ubb34\uc232\ucc44\ub110\ud574\uc81c",
    "clear": "\uccad\uc18c",
    "clear_all": "\uc804\uccb4\uccad\uc18c",
    "move": "\uc774\ub3d9",
    "poll": "\ud22c\ud45c",
    "remind": "\ub9ac\ub9c8\uc778\ub4dc",
    "school_auth": "\ud559\uad50\uc778\uc99d",
    "school_auth_setup": "\ud559\uad50\uc778\uc99d\uc124\uc815",
    "school_auth_sync": "\ud559\uad50\uc778\uc99d\ub3d9\uae30\ud654",
    "school_auth_status": "\ud559\uad50\uc778\uc99d\uc0c1\ud0dc",
    "student": "\ud559\uc0dd",
    "student_setup": "\ud559\uc0dd\uc124\uc815",
    "role_add": "\uc5ed\ud560\ucd94\uac00",
    "nickname": "\ubcc4\uba85\ubcc0\uacbd",
    "schedule": "\uc77c\uc815",
    "timeout": "\ucc44\ud305\uae08\uc9c0",
    "translate": "\ubc88\uc5ed",
    "warn": "\uacbd\uace0",
    "warnings": "\uacbd\uace0\uae30\ub85d",
}


ENGLISH_TRANSLATIONS: dict[str, str] = {
    "\uba54\uc2dc\uc9c0 \uc774\ub3d9": "Move Message",
    "\ub610\ubd07 AI\uc5d0\uac8c \uc9c8\ubb38": "Ask Ttobot AI",
    "\ub610\ubd07 AI\uc5d0\uac8c \ubcf4\ub0bc \uc9c8\ubb38": "Question to send to Ttobot AI",
    "\uc790\uc5f0\uc5b4\ub97c \ub0b4\ubd80 \uad00\ub9ac \uba85\ub839\uc73c\ub85c \ud574\uc11d": "Interpret natural language as an internal moderation command",
    "\uc608: \ucd5c\uadfc \uba54\uc2dc\uc9c0 20\uac1c \uc0ad\uc81c\ud574\uc918": "Example: delete the latest 20 messages",
    "\uc8fc\uc0ac\uc704\ub97c \uad74\ub9bd\ub2c8\ub2e4": "Roll a die",
    "\ubd07 \uc751\ub2f5 \ud655\uc778": "Check whether the bot is responding",
    "\uba85\ub839\uc5b4 \uc548\ub0b4": "Show command help",
    "\uacf5\uc9c0 \ucc44\ub110\uc5d0 \uacf5\uc9c0 \uc804\uc1a1": "Send an announcement to the announcement channel",
    "\uacf5\uc9c0 \uc81c\ubaa9": "Announcement title",
    "\uacf5\uc9c0 \ub0b4\uc6a9": "Announcement content",
    "\ud568\uaed8 \ubcf4\ub0bc \ub9c1\ud06c": "Link to include",
    "\ud568\uaed8 \ubcf4\ub0bc \uc774\ubbf8\uc9c0 \ud30c\uc77c": "Image file to include",
    "\uacf5\uc9c0 \ucc44\ub110 \uc9c0\uc815": "Set the announcement channel",
    "\uacf5\uc9c0 \uba54\uc2dc\uc9c0\ub97c \ubcf4\ub0bc \ucc44\ub110": "Channel to send announcements to",
    "\uacf5\uc9c0 \ucc44\ub110 \ud574\uc81c": "Clear the announcement channel",
    "\uc775\uba85 \ub300\ub098\ubb34\uc232 \uae00 \uc791\uc131": "Create an anonymous bamboo forest post",
    "\ub300\ub098\ubb34\uc232 \uae00 \uc81c\ubaa9": "Bamboo forest post title",
    "\uc775\uba85\uc73c\ub85c \uc62c\ub9b4 \ub0b4\uc6a9": "Content to post anonymously",
    "\ud568\uaed8 \uc62c\ub9b4 \uc0ac\uc9c4 \ud30c\uc77c": "Image file to attach",
    "\ub300\ub098\ubb34\uc232 \ucc44\ub110 \uc9c0\uc815": "Set the bamboo forest channel",
    "\uc775\uba85 \uae00\uc774 \uc62c\ub77c\uac08 \ud14d\uc2a4\ud2b8 \ucc44\ub110 \ub610\ub294 \ud3ec\ub7fc \ucc44\ub110": "Text or forum channel where anonymous posts will be sent",
    "\ub300\ub098\ubb34\uc232 \ucc44\ub110 \ud574\uc81c": "Clear the bamboo forest channel",
    "\ucd5c\uadfc \uba54\uc2dc\uc9c0 \uc0ad\uc81c": "Delete recent messages",
    "\uc0ad\uc81c\ud560 \ucd5c\uadfc \uba54\uc2dc\uc9c0 \uc218 (1~100)": "Number of recent messages to delete (1-100)",
    "\uc774 \ucc44\ub110\uc758 \uc624\ub798\ub41c \uba54\uc2dc\uc9c0\ub97c \ud3ec\ud568\ud574 \ubaa8\ub450 \uc0ad\uc81c": "Delete all messages in this channel, including old ones",
    "\ud604\uc7ac \ucc44\ub110\uc758 \ucd5c\uadfc \uba54\uc2dc\uc9c0\ub97c \ub2e4\ub978 \ucc44\ub110\ub85c \uc774\ub3d9": "Move multiple recent messages from this channel",
    "\uba54\uc2dc\uc9c0\ub97c \uc62e\uae38 \ub300\uc0c1 \ucc44\ub110": "Destination channel for the messages",
    "\uc120\ud0dd \ud6c4\ubcf4\ub85c \ubd88\ub7ec\uc62c \ucd5c\uadfc \uba54\uc2dc\uc9c0 \uac1c\uc218 (1~25)": "Number of recent messages to load as candidates (1-25)",
    "\ubc84\ud2bc \ucc2c\ubc18 \ud22c\ud45c \uc0dd\uc131": "Create a button-based yes/no poll",
    "\ud22c\ud45c \uc9c8\ubb38": "Poll question",
    "\ucc2c\uc131 \uc120\ud0dd\uc9c0 \ubb38\uad6c, \ube44\uc6b0\uba74 '\ucc2c\uc131'": "Yes option label, defaults to 'Yes' if empty",
    "\ubc18\ub300 \uc120\ud0dd\uc9c0 \ubb38\uad6c, \ube44\uc6b0\uba74 '\ubc18\ub300'": "No option label, defaults to 'No' if empty",
    "\ub204\uac00 \uc5b4\ub514\uc5d0 \ud22c\ud45c\ud588\ub294\uc9c0 \ubaa8\ub450\uc5d0\uac8c \uacf5\uac1c\ud560\uc9c0 \uc5ec\ubd80": "Whether to show everyone who voted for what",
    "\uc885\ub8cc \ub0a0\uc9dc (YYYY-MM-DD)": "End date (YYYY-MM-DD)",
    "\uc885\ub8cc \uc2dc\uac04 (HH:MM, 24\uc2dc\uac04 \ud615\uc2dd)": "End time (HH:MM, 24-hour format)",
    "\uc885\ub8cc \uc2dc\uac04\uc744 \uc9c0\uc815\ud558\uc9c0 \uc54a\uc744\uc9c0 \uc5ec\ubd80": "Whether to disable the end time",
    "\uc9c0\uc815 \uc2dc\uac04 \ud6c4 DM \ub9ac\ub9c8\uc778\ub354 \uc804\uc1a1": "Send a DM reminder after the specified time",
    "\uc608: 30m, 1h, 1d": "Example: 30m, 1h, 1d",
    "DM\uc73c\ub85c \ubc1b\uc744 \ub9ac\ub9c8\uc778\ub354 \ub0b4\uc6a9": "Reminder content to receive via DM",
    "\ud559\uad50 Google \uacc4\uc815 \uc778\uc99d \ub9c1\ud06c \ubc1c\uae09": "Generate a school Google account verification link",
    "\ud559\uad50 Google \uacc4\uc815 \uc778\uc99d \uc7a0\uae08 \ucc44\ub110\uacfc \uc5ed\ud560\uc744 \uc124\uc815": "Configure the locked school verification channel and roles",
    "\ud559\uad50 \uc778\uc99d \ucc44\ub110 \uc7a0\uae08\uacfc \ubbf8\uc778\uc99d \uc5ed\ud560 \uc0c1\ud0dc\ub97c \ub2e4\uc2dc \ub3d9\uae30\ud654": "Resync school verification channel locks and unverified role state",
    "\ud604\uc7ac \ud559\uad50 \uc778\uc99d \uc644\ub8cc \uc5ec\ubd80\ub97c \ud655\uc778": "Check whether school verification is complete",
    "\uc778\uc99d\ub41c \ud559\uad50 \uba54\uc77c \uc55e\uc790\ub9ac \uae30\uc900 \ud559\ub144 \uc5ed\ud560 \uc790\ub3d9 \uc124\uc815": "Configure automatic grade roles based on the first digit of verified school email addresses",
    "3\ud559\ub144\uc73c\ub85c \ubcfc \ud559\uad50 \uba54\uc77c \uc55e\uc790\ub9ac \uc22b\uc790": "First digit of a verified school email that should count as 3rd grade",
    "2\ud559\ub144\uc73c\ub85c \ubcfc \ud559\uad50 \uba54\uc77c \uc55e\uc790\ub9ac \uc22b\uc790": "First digit of a verified school email that should count as 2nd grade",
    "1\ud559\ub144\uc73c\ub85c \ubcfc \ud559\uad50 \uba54\uc77c \uc55e\uc790\ub9ac \uc22b\uc790": "First digit of a verified school email that should count as 1st grade",
    "\ud559\uc0dd \uc790\ub3d9 \uc5ed\ud560 \ubd80\uc5ec\uc5d0\uc11c \uc81c\uc678\ud560 \uad00\ub9ac\uc790 \uc5ed\ud560": "Admin role to exclude from automatic student role assignment",
    "\ud5c8\uc6a9\ud560 \ud559\uad50 \uba54\uc77c \ub3c4\uba54\uc778 \uc608: bssm.hs.kr": "Allowed school email domain, e.g. bssm.hs.kr",
    "\ud559\uad50 \uc778\uc99d\uc744 \uac74\ub108\ub6f8 \uad00\ub9ac\uc790/\uc6b4\uc601\uc9c4 \uc5ed\ud560": "Admin or staff role that bypasses school verification",
    "\uc774\ub984 \uc55e \uc22b\uc790 \uae30\uc900\uc73c\ub85c \ud559\ub144 \uc5ed\ud560 \uc77c\uad04 \ubd80\uc5ec": "Bulk-assign grade roles based on the leading digit in display names",
    "3\ud559\ub144\uc73c\ub85c \ubcfc \uc774\ub984 \uc2dc\uc791 \uc22b\uc790": "Leading digit that counts as 3rd grade",
    "2\ud559\ub144\uc73c\ub85c \ubcfc \uc774\ub984 \uc2dc\uc791 \uc22b\uc790": "Leading digit that counts as 2nd grade",
    "1\ud559\ub144\uc73c\ub85c \ubcfc \uc774\ub984 \uc2dc\uc791 \uc22b\uc790": "Leading digit that counts as 1st grade",
    "\ud559\uc0dd \uc5ed\ud560 \ubd80\uc5ec\uc5d0\uc11c \uc81c\uc678\ud560 \uad00\ub9ac\uc790 \uc5ed\ud560": "Admin role to exclude from student role assignment",
    "\uad00\ub9ac\uc790 \uc804\uc6a9 \uc5ed\ud560 \uc0dd\uc131 \ubc0f \ubd80\uc5ec": "Admin-only role creation and assignment",
    "\uc5ed\ud560\uc744 \ubd80\uc5ec\ud560 \uc720\uc800": "User to assign the role to",
    "\uae30\uc874 \uc5ed\ud560\uba85 \ub610\ub294 \uc0c8\ub85c \ub9cc\ub4e4 \uc5ed\ud560\uba85": "Existing role name or a new role name to create",
    "\uad00\ub9ac\uc790 \uc804\uc6a9 \ubcc4\uba85 \ubcc0\uacbd": "Admin-only nickname change",
    "\ubcc4\uba85\uc744 \ubc14꿀 \uc720\uc800": "User whose nickname will be changed",
    "\uc0c8 \ubcc4\uba85": "New nickname",
    "\uac04\ub2e8 \uc77c\uc815 \uc54c\ub9bc \ub4f1\ub85d": "Register a simple schedule reminder",
    "\uc54c\ub9bc \uc81c\ubaa9": "Reminder title",
    "\uc77c\uc815 \ub0b4\uc6a9": "Schedule content",
    "\ub0a0\uc9dc \ud615\uc2dd \uc608: 2026-03-14": "Date format example: 2026-03-14",
    "24\uc2dc\uac04 \ud615\uc2dd \uc608: 20:00": "24-hour format example: 20:00",
    "\uc77c\uc815 \uc2dc\uac04 \ucc44\ud305 \uae08\uc9c0": "Mute chat for a set amount of time",
    "\ud0c0\uc784\uc544\uc6c3\ud560 \uc11c\ubc84 \uba64\ubc84": "Server member to timeout",
    "\uc608: 10m, 1h, 1h30m, 2d": "Example: 10m, 1h, 1h30m, 2d",
    "\ud0c0\uc784\uc544\uc6c3 \uc0ac\uc720": "Timeout reason",
    "\uc601\uc5b4 \ubb38\uc7a5\uc744 \ud55c\uad6d\uc5b4\ub85c \ubc88\uc5ed": "Translate English text into Korean",
    "\ud55c\uad6d\uc5b4\ub85c \ubc88\uc5ed\ud560 \uc601\uc5b4 \ubb38\uc7a5": "English text to translate into Korean",
    "\uc720\uc800\uc5d0\uac8c \uacbd\uace0\ub97c \ubd80\uc5ec\ud558\uace0 \uc790\ub3d9 \uc81c\uc7ac\ub97c \uc801\uc6a9": "Warn a user and apply automatic penalties",
    "\uacbd\uace0\ub97c \ubd80\uc5ec\ud560 \uc11c\ubc84 \uba64\ubc84": "Server member to warn",
    "\uacbd\uace0 \uc0ac\uc720": "Warning reason",
    "\uc720\uc800\uc758 \uacbd\uace0 \uae30\ub85d \ud655\uc778": "Check a user's warning history",
    "\uacbd\uace0 \uae30\ub85d\uc744 \ud655\uc778\ud560 \uc11c\ubc84 \uba64\ubc84": "Server member whose warnings you want to check",
    "\uc9c8\ubb38": "question",
    "\uc694\uccad": "request",
    "\uc81c\ubaa9": "title",
    "\ub0b4\uc6a9": "content",
    "\ub9c1\ud06c": "link",
    "\uc0ac\uc9c4": "image",
    "\ucc44\ub110": "channel",
    "\uac1c\uc218": "count",
    "\ub300\uc0c1\ucc44\ub110": "destination",
    "\ucc2c\uc131": "yes",
    "\ubc18\ub300": "no",
    "\uacf5\uac1c": "public",
    "\uc885\ub8cc\ub0a0\uc9dc": "end_date",
    "\uc885\ub8cc\uc2dc\uac04": "end_time",
    "\uc885\ub8cc\uc5c6\uc74c": "no_end_time",
    "\uc2dc\uac04": "time",
    "\uc720\uc800": "user",
    "\uc5ed\ud560\uba85": "role_name",
    "\ubcc4\uba85": "nickname",
    "\ub0a0\uc9dc": "date",
    "\uc774\uc720": "reason",
    "\uc601\ubb38": "text",
}


HELP_MESSAGES: dict[str, str] = {
    "ko": (
        "또봇 명령어 목록\n"
        "/\uba85\ub839\uc5b4 - \uc790\uc5f0\uc5b4\ub97c \ub0b4\ubd80 \uad00\ub9ac \uba85\ub839\uc73c\ub85c \ud574\uc11d\n"
        "/또봇 - 또봇 AI 질문\n"
        "/\uc8fc\uc0ac\uc704 - \uc8fc\uc0ac\uc704 \uad74\ub9ac\uae30\n"
        "/\ud551 - \ubd07 \uc751\ub2f5 \ud655\uc778\n"
        "/\ub3c4\uc6c0\ub9d0 - \uba85\ub839\uc5b4 \uc548\ub0b4\n"
        "/\uccad\uc18c - \ucd5c\uadfc \uba54\uc2dc\uc9c0 \uc0ad\uc81c \uc804 \ud655\uc778\n"
        "/\uc804\uccb4\uccad\uc18c - \uc774 \ucc44\ub110 \uba54\uc2dc\uc9c0 \uc804\uccb4 \uc0ad\uc81c\n"
        "/\uc774\ub3d9 - \ucd5c\uadfc \uba54\uc2dc\uc9c0 \ud6c4\ubcf4\ub97c \uace0\ub978 \ub4a4 \ub2e4\ub978 \ucc44\ub110\ub85c \uc774\ub3d9\n"
        "/\ud22c\ud45c - \uc885\ub8cc \uc2dc\uac04 \uc124\uc815 \uac00\ub2a5\ud55c \ubc84\ud2bc \ucc2c\ubc18 \ud22c\ud45c \uc0dd\uc131\n"
        "/\ub9ac\ub9c8\uc778\ub4dc - \uc9c0\uc815 \uc2dc\uac04 \ud6c4 DM \ub9ac\ub9c8\uc778\ub354 \uc804\uc1a1\n"
        "/\ud559\uad50\uc778\uc99d - \ud559\uad50 Google \uacc4\uc815 \uc778\uc99d \ub9c1\ud06c \ubc1c\uae09\n"
        "/\ud559\uad50\uc778\uc99d\uc124\uc815 - \ud559\uad50 \uc778\uc99d \uc804\uc6a9 \ucc44\ub110/\uc5ed\ud560 \uc124\uc815 \ubc0f \uc11c\ubc84 \uc7a0\uae08\n"
        "/\ud559\uad50\uc778\uc99d\ub3d9\uae30\ud654 - \ud559\uad50 \uc778\uc99d \uc0c1\ud0dc\uc640 \ucc44\ub110 \uc7a0\uae08 \ub2e4\uc2dc \uc801\uc6a9\n"
        "/\ud559\uad50\uc778\uc99d\uc0c1\ud0dc - \ub0b4 \ud559\uad50 \uc778\uc99d \uc644\ub8cc \uc5ec\ubd80 \ud655\uc778\n"
        "/\ud559\uc0dd\uc124\uc815 - \uc778\uc99d\ub41c \ud559\uad50 \uba54\uc77c \uc55e\uc790\ub9ac \uae30\uc900\uc73c\ub85c \ud559\ub144 \uc5ed\ud560 \uc790\ub3d9 \uc124\uc815 \ubc0f \ub3d9\uae30\ud654\n"
        "/\ud559\uc0dd - \uc774\ub984 \uc55e \uc22b\uc790 \uae30\uc900\uc73c\ub85c 1/2/3\ud559\ub144 \uc5ed\ud560 \uc77c\uad04 \ubd80\uc5ec\n"
        "/\uc5ed\ud560\ucd94\uac00 - \uad00\ub9ac\uc790 \uc804\uc6a9 \uc5ed\ud560 \uc0dd\uc131 \ubc0f \ubd80\uc5ec\n"
        "/\ubcc4\uba85\ubcc0\uacbd - \uad00\ub9ac\uc790 \uc804\uc6a9 \ubcc4\uba85 \ubcc0\uacbd\n"
        "/\uc77c\uc815 - \uc81c\ubaa9/\ub0b4\uc6a9/\ub0a0\uc9dc/\uc2dc\uac04 \uc77c\uc815 \uc54c\ub9bc \ub4f1\ub85d\n"
        "/\ucc44\ud305\uae08\uc9c0 - \uc77c\uc815 \uc2dc\uac04 \ucc44\ud305 \uae08\uc9c0\n"
        "/\ubc88\uc5ed - \uc601\uc5b4 \ubb38\uc7a5\uc744 \ud55c\uad6d\uc5b4\ub85c \ubc88\uc5ed\n"
        "/\uacbd\uace0 - \uc720\uc800 \uacbd\uace0 \ubc0f \uc790\ub3d9 \uc81c\uc7ac \uc801\uc6a9\n"
        "/\uacbd\uace0\uae30\ub85d - \uc720\uc800 \uacbd\uace0 \uae30\ub85d \ud655\uc778\n"
        "/\uacf5\uc9c0 - \uc81c\ubaa9/\ub0b4\uc6a9\uc5d0 \ub9c1\ud06c\uc640 \uc0ac\uc9c4\uc744 \ucd94\uac00\ud574 @everyone \uacf5\uc9c0 \uc804\uc1a1\n"
        "/\uacf5\uc9c0\ucc44\ub110\uc124\uc815 - \uacf5\uc9c0 \ucc44\ub110 \uc9c0\uc815\n"
        "/\uacf5\uc9c0\ucc44\ub110\ud574\uc81c - \uacf5\uc9c0 \ucc44\ub110 \ud574\uc81c\n"
        "/\ub300\ub098\ubb34\uc232 - \uc81c\ubaa9/\ub0b4\uc6a9/\uc0ac\uc9c4\uc73c\ub85c \uc775\uba85 \uac8c\uc2dc\ubb3c \uc791\uc131\n"
        "/\ub300\ub098\ubb34\uc232\ucc44\ub110\uc124\uc815 - \ub300\ub098\ubb34\uc232 \ucc44\ub110 \uc9c0\uc815\n"
        "/\ub300\ub098\ubb34\uc232\ucc44\ub110\ud574\uc81c - \ub300\ub098\ubb34\uc232 \ucc44\ub110 \ud574\uc81c\n"
        "\uba54\uc2dc\uc9c0 \uc6b0\ud074\ub9ad > \uc571 > \uba54\uc2dc\uc9c0 \uc774\ub3d9 - \uc120\ud0dd\ud55c \uba54\uc2dc\uc9c0 1\uac1c \uc774\ub3d9"
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
        "/school_auth - Generate a school Google account verification link\n"
        "/school_auth_setup - Configure the school verification channel, roles, and server lock\n"
        "/school_auth_sync - Resync school verification channel locks and unverified role state\n"
        "/school_auth_status - Check whether your school verification is complete\n"
        "/student_setup - Configure and sync automatic grade roles from verified school email prefixes\n"
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
        "/bamboo - Create an anonymous post with a title, content, and optional image\n"
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
        message = string.message

        if locale == discord.Locale.korean:
            return KOREAN_TRANSLATIONS.get(message)

        if locale in {discord.Locale.american_english, discord.Locale.british_english}:
            return ENGLISH_TRANSLATIONS.get(message)

        return None

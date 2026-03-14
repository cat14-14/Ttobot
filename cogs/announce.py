from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from bot import CoraxBot


class AnnounceCog(commands.Cog):
    def __init__(self, bot: "CoraxBot"):
        self.bot = bot

    def is_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False

        member = interaction.user
        if not isinstance(member, discord.Member):
            return False

        return member.guild_permissions.administrator

    def get_announce_channel(
        self,
        interaction: discord.Interaction,
    ) -> discord.TextChannel | None:
        if interaction.guild is None or interaction.guild_id is None:
            return None

        channel_id = self.bot.announce_store.get_channel_id(interaction.guild_id)
        if channel_id is None:
            return None

        channel = interaction.guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel

        return None

    def bot_can_send(self, channel: discord.TextChannel) -> bool:
        if self.bot.user is None:
            return False

        member = channel.guild.get_member(self.bot.user.id)
        if member is None:
            return False

        permissions = channel.permissions_for(member)
        return permissions.send_messages and permissions.embed_links

    def bot_can_attach_files(self, channel: discord.TextChannel) -> bool:
        if self.bot.user is None:
            return False

        member = channel.guild.get_member(self.bot.user.id)
        if member is None:
            return False

        permissions = channel.permissions_for(member)
        return permissions.attach_files

    def bot_can_mention_everyone(self, channel: discord.TextChannel) -> bool:
        if self.bot.user is None:
            return False

        member = channel.guild.get_member(self.bot.user.id)
        if member is None:
            return False

        permissions = channel.permissions_for(member)
        return permissions.mention_everyone

    def build_announce_embed(
        self,
        title: str,
        content: str,
        author: discord.abc.User,
        *,
        link: str | None = None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"공지 | {title}",
            description=content,
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
            url=link or discord.utils.MISSING,
        )
        if link:
            embed.add_field(name="링크", value=link, inline=False)
        embed.set_footer(text=f"공지 작성자: {author.display_name}")
        return embed

    def validate_link(self, link: str | None) -> str | None:
        if link is None:
            return None

        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "링크는 `http://` 또는 `https://`로 시작하는 올바른 주소여야 합니다."

        return None

    def is_supported_image_attachment(self, attachment: discord.Attachment) -> bool:
        if attachment.content_type and attachment.content_type.startswith("image/"):
            return True

        return Path(attachment.filename).suffix.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
        }

    @app_commands.command(name="announce", description="공지 채널에 공지 전송")
    @app_commands.rename(title="제목", content="내용", link="링크", image="사진")
    @app_commands.describe(
        title="공지 제목",
        content="공지 내용",
        link="함께 보낼 링크",
        image="함께 보낼 이미지 파일",
    )
    @app_commands.default_permissions(administrator=True)
    async def announce(
        self,
        interaction: discord.Interaction,
        title: str,
        content: str,
        link: str | None = None,
        image: discord.Attachment | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not self.is_admin(interaction):
            await interaction.response.send_message(
                "공지 작성은 관리자만 할 수 있습니다.",
                ephemeral=True,
            )
            return

        channel = self.get_announce_channel(interaction)
        if channel is None:
            await interaction.response.send_message(
                "공지 채널이 설정되지 않았습니다. `/announce_channel_set`으로 먼저 지정해 주세요.",
                ephemeral=True,
            )
            return

        if not self.bot_can_send(channel):
            await interaction.response.send_message(
                f"{channel.mention} 채널에 메시지를 보낼 권한이 없습니다.",
                ephemeral=True,
            )
            return

        if not self.bot_can_mention_everyone(channel):
            await interaction.response.send_message(
                f"{channel.mention} 채널에서 `@everyone` 멘션 권한이 없습니다. "
                "봇에 `Mention Everyone` 권한을 주세요.",
                ephemeral=True,
            )
            return

        link_error = self.validate_link(link)
        if link_error is not None:
            await interaction.response.send_message(link_error, ephemeral=True)
            return

        if image is not None and not self.is_supported_image_attachment(image):
            await interaction.response.send_message(
                "사진은 PNG, JPG, JPEG, GIF, WEBP 형식의 이미지 파일만 보낼 수 있습니다.",
                ephemeral=True,
            )
            return

        if image is not None and not self.bot_can_attach_files(channel):
            await interaction.response.send_message(
                f"{channel.mention} 채널에 파일을 첨부할 권한이 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        embed = self.build_announce_embed(
            title,
            content,
            interaction.user,
            link=link,
        )
        file: discord.File | None = None
        if image is not None:
            file = await image.to_file()
            embed.set_image(url=f"attachment://{file.filename}")

        send_kwargs: dict[str, object] = {
            "content": "@everyone",
            "embed": embed,
            "allowed_mentions": discord.AllowedMentions(everyone=True),
        }
        if file is not None:
            send_kwargs["file"] = file

        await channel.send(**send_kwargs)
        await interaction.followup.send(
            f"공지를 {channel.mention}에 `@everyone`과 함께 보냈습니다.",
            ephemeral=True,
        )

    @app_commands.command(name="announce_channel_set", description="공지 채널 지정")
    @app_commands.rename(channel="채널")
    @app_commands.describe(channel="공지 메시지를 보낼 채널")
    @app_commands.default_permissions(administrator=True)
    async def announce_channel_set(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        if interaction.guild is None or interaction.guild_id is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not self.is_admin(interaction):
            await interaction.response.send_message(
                "공지 채널 지정은 관리자만 할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not self.bot_can_send(channel):
            await interaction.response.send_message(
                f"{channel.mention} 채널에 보낼 권한이 없습니다. 봇 권한을 확인해 주세요.",
                ephemeral=True,
            )
            return

        if not self.bot_can_mention_everyone(channel):
            await interaction.response.send_message(
                f"{channel.mention} 채널에서 `@everyone` 멘션 권한이 없습니다. "
                "봇에 `Mention Everyone` 권한을 주세요.",
                ephemeral=True,
            )
            return

        self.bot.announce_store.set_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message(
            f"공지 채널을 {channel.mention}로 설정했습니다. 공지 시 `@everyone`이 함께 전송됩니다.",
            ephemeral=True,
        )

    @app_commands.command(name="announce_channel_clear", description="공지 채널 해제")
    @app_commands.default_permissions(administrator=True)
    async def announce_channel_clear(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None or interaction.guild_id is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not self.is_admin(interaction):
            await interaction.response.send_message(
                "공지 채널 해제는 관리자만 할 수 있습니다.",
                ephemeral=True,
            )
            return

        removed = self.bot.announce_store.clear_channel(interaction.guild_id)
        if not removed:
            await interaction.response.send_message(
                "현재 설정된 공지 채널이 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "공지 채널 설정을 해제했습니다.",
            ephemeral=True,
        )


async def setup(bot: "CoraxBot") -> None:
    await bot.add_cog(AnnounceCog(bot))

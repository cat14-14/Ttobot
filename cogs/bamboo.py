from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from bot import CoraxBot


BambooChannel = discord.TextChannel | discord.ForumChannel


class BambooCog(commands.Cog):
    def __init__(self, bot: "CoraxBot"):
        self.bot = bot

    def is_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False

        member = interaction.user
        if not isinstance(member, discord.Member):
            return False

        return member.guild_permissions.administrator

    def get_bot_member(self, guild: discord.Guild) -> discord.Member | None:
        if self.bot.user is None:
            return None

        return guild.get_member(self.bot.user.id)

    def get_bamboo_channel(
        self,
        interaction: discord.Interaction,
    ) -> BambooChannel | None:
        if interaction.guild is None or interaction.guild_id is None:
            return None

        channel_id = self.bot.bamboo_store.get_channel_id(interaction.guild_id)
        if channel_id is None:
            return None

        channel = interaction.guild.get_channel(channel_id)
        if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
            return channel

        return None

    def bot_can_send_to_text(self, channel: discord.TextChannel) -> bool:
        member = self.get_bot_member(channel.guild)
        if member is None:
            return False

        permissions = channel.permissions_for(member)
        return permissions.send_messages and permissions.embed_links

    def bot_can_send_to_forum(self, channel: discord.ForumChannel) -> bool:
        member = self.get_bot_member(channel.guild)
        if member is None:
            return False

        permissions = channel.permissions_for(member)
        return permissions.send_messages and permissions.embed_links

    def bot_can_attach_files(self, channel: BambooChannel) -> bool:
        member = self.get_bot_member(channel.guild)
        if member is None:
            return False

        permissions = channel.permissions_for(member)
        return permissions.attach_files

    def get_forum_tag_error(self, channel: discord.ForumChannel) -> str | None:
        if not channel.flags.require_tag:
            return None

        if len(channel.available_tags) == 1:
            return None

        if not channel.available_tags:
            return (
                "이 포럼 채널은 태그가 필수인데 사용할 수 있는 태그가 없습니다. "
                "필수 태그를 끄거나 태그를 추가해 주세요."
            )

        return (
            "이 포럼 채널은 필수 태그가 여러 개라 자동으로 고를 수 없습니다. "
            "필수 태그를 끄거나 태그를 1개만 남겨 주세요."
        )

    def build_bamboo_embed(self, title: str, content: str) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=content,
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name="익명 대나무숲")
        embed.set_footer(text="작성자 정보는 공개되지 않습니다.")
        return embed

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

    async def publish_to_channel(
        self,
        channel: BambooChannel,
        *,
        title: str,
        content: str,
        image: discord.Attachment | None,
    ) -> str:
        embed = self.build_bamboo_embed(title, content)
        file: discord.File | None = None
        if image is not None:
            file = await image.to_file()
            embed.set_image(url=f"attachment://{file.filename}")

        allowed_mentions = discord.AllowedMentions.none()

        if isinstance(channel, discord.TextChannel):
            send_kwargs: dict[str, object] = {
                "embed": embed,
                "allowed_mentions": allowed_mentions,
            }
            if file is not None:
                send_kwargs["file"] = file

            message = await channel.send(**send_kwargs)
            return message.jump_url

        create_kwargs: dict[str, object] = {
            "name": title,
            "embed": embed,
            "allowed_mentions": allowed_mentions,
        }
        if file is not None:
            create_kwargs["file"] = file
        if channel.flags.require_tag and len(channel.available_tags) == 1:
            create_kwargs["applied_tags"] = [channel.available_tags[0]]

        created = await channel.create_thread(**create_kwargs)
        return created.message.jump_url

    @app_commands.command(name="bamboo", description="익명 대나무숲 글 작성")
    @app_commands.rename(title="제목", content="내용", image="사진")
    @app_commands.describe(
        title="대나무숲 글 제목",
        content="익명으로 올릴 내용",
        image="함께 올릴 사진 파일",
    )
    async def bamboo(
        self,
        interaction: discord.Interaction,
        title: app_commands.Range[str, 1, 100],
        content: app_commands.Range[str, 1, 4000],
        image: discord.Attachment | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        title = title.strip()
        content = content.strip()
        if not title or not content:
            await interaction.response.send_message(
                "제목과 내용은 공백만으로 작성할 수 없습니다.",
                ephemeral=True,
            )
            return

        channel = self.get_bamboo_channel(interaction)
        if channel is None:
            await interaction.response.send_message(
                "대나무숲 채널이 설정되지 않았습니다. `/대나무숲채널설정`으로 먼저 지정해 주세요.",
                ephemeral=True,
            )
            return

        if isinstance(channel, discord.TextChannel):
            if not self.bot_can_send_to_text(channel):
                await interaction.response.send_message(
                    f"{channel.mention} 채널에 메시지를 보낼 권한이 없습니다.",
                    ephemeral=True,
                )
                return
        else:
            if not self.bot_can_send_to_forum(channel):
                await interaction.response.send_message(
                    f"{channel.mention} 포럼 채널에 글을 올릴 권한이 없습니다.",
                    ephemeral=True,
                )
                return

            tag_error = self.get_forum_tag_error(channel)
            if tag_error is not None:
                await interaction.response.send_message(tag_error, ephemeral=True)
                return

        if image is not None and not self.is_supported_image_attachment(image):
            await interaction.response.send_message(
                "사진은 PNG, JPG, JPEG, GIF, WEBP 형식의 이미지 파일만 첨부할 수 있습니다.",
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

        try:
            jump_url = await self.publish_to_channel(
                channel,
                title=title,
                content=content,
                image=image,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "대나무숲 글을 올릴 권한이 없습니다. 봇 권한을 확인해 주세요.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as error:
            await interaction.followup.send(
                f"대나무숲 글 작성 중 오류가 발생했습니다: {error}",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"익명 글을 {channel.mention}에 올렸습니다.\n{jump_url}",
            ephemeral=True,
        )

    @app_commands.command(name="bamboo_channel_set", description="대나무숲 채널 지정")
    @app_commands.rename(channel="채널")
    @app_commands.describe(channel="익명 글이 올라갈 텍스트 채널 또는 포럼 채널")
    @app_commands.default_permissions(administrator=True)
    async def bamboo_channel_set(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.ForumChannel,
    ) -> None:
        if interaction.guild is None or interaction.guild_id is None:
            await interaction.response.send_message(
                "이 명령어는 서버에서만 사용할 수 있습니다.",
                ephemeral=True,
            )
            return

        if not self.is_admin(interaction):
            await interaction.response.send_message(
                "대나무숲 채널 지정은 관리자만 할 수 있습니다.",
                ephemeral=True,
            )
            return

        if isinstance(channel, discord.TextChannel):
            if not self.bot_can_send_to_text(channel):
                await interaction.response.send_message(
                    f"{channel.mention} 채널에 메시지를 보낼 권한이 없습니다. 봇 권한을 확인해 주세요.",
                    ephemeral=True,
                )
                return
        else:
            if not self.bot_can_send_to_forum(channel):
                await interaction.response.send_message(
                    f"{channel.mention} 포럼 채널에 글을 올릴 권한이 없습니다. 봇 권한을 확인해 주세요.",
                    ephemeral=True,
                )
                return

            tag_error = self.get_forum_tag_error(channel)
            if tag_error is not None:
                await interaction.response.send_message(tag_error, ephemeral=True)
                return

        self.bot.bamboo_store.set_channel(interaction.guild_id, channel.id)

        if isinstance(channel, discord.ForumChannel):
            message = f"대나무숲 채널을 {channel.mention} 포럼으로 설정했습니다."
            if channel.flags.require_tag and len(channel.available_tags) == 1:
                message += f" 새 글에는 `{channel.available_tags[0].name}` 태그가 자동으로 붙습니다."
        else:
            message = f"대나무숲 채널을 {channel.mention} 채팅 채널로 설정했습니다."

        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="bamboo_channel_clear", description="대나무숲 채널 해제")
    @app_commands.default_permissions(administrator=True)
    async def bamboo_channel_clear(
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
                "대나무숲 채널 해제는 관리자만 할 수 있습니다.",
                ephemeral=True,
            )
            return

        removed = self.bot.bamboo_store.clear_channel(interaction.guild_id)
        if not removed:
            await interaction.response.send_message(
                "현재 설정된 대나무숲 채널이 없습니다.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "대나무숲 채널 설정을 해제했습니다.",
            ephemeral=True,
        )


async def setup(bot: "CoraxBot") -> None:
    await bot.add_cog(BambooCog(bot))

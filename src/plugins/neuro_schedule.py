from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self

from msgspec import json as msgjson
from nonebot import on_message, require
from nonebot.adapters import discord
from nonebot.adapters.onebot import v11
from nonebot.permission import SUPERUSER
from pydantic import BaseModel

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import Alconna, MsgTarget, Subcommand, Target, on_alconna
from nonebot_plugin_localstore import get_plugin_config_file

require("src.plugins.group_pipe")
from src.plugins.group_pipe.adapter import get_sender
from src.plugins.group_pipe.adapters.discord import MessageConverter


class Config(BaseModel):
    _file_: ClassVar[Final[Path]] = get_plugin_config_file("config.json")
    _cache_: ClassVar[Self | None] = None

    recv_target: dict[str, Any] | None = None
    send_target: dict[str, Any] | None = None

    @property
    def recv(self) -> Target | None:
        return Target.load(self.recv_target) if self.recv_target else None

    @property
    def send(self) -> Target | None:
        return Target.load(self.send_target) if self.send_target else None

    @classmethod
    def load(cls, *, use_cache: bool = True) -> Self:
        if cls._cache_ is None or not use_cache:
            if cls._file_.exists():
                raw = cls._file_.read_bytes()
            else:
                cls._file_.write_text("{}", encoding="utf-8")
                raw = "{}"
            cls._cache_ = cls.model_validate(msgjson.decode(raw))
        return cls._cache_

    def save(self) -> None:
        self._file_.write_bytes(msgjson.encode(self.model_dump()))
        type(self)._cache_ = self


setup_cmd = on_alconna(
    Alconna(
        "neuro_schedule",
        Subcommand("recv", help_text="设置当前会话为接收端"),
        Subcommand("send", help_text="设置当前会话为发送端"),
    ),
    permission=SUPERUSER,
)


@setup_cmd.assign("~recv")
async def assign_recv(target: MsgTarget, _: discord.Bot) -> None:
    config = Config.load(use_cache=False)
    config.recv_target = target.dump()
    config.save()
    await setup_cmd.send("设置当前会话为接收端")


@setup_cmd.assign("~send")
async def assign_send(target: MsgTarget, _: v11.Bot) -> None:
    config = Config.load(use_cache=False)
    config.send_target = target.dump()
    config.save()
    await setup_cmd.send("设置当前会话为发送端")


def check_is_recv(target: MsgTarget) -> bool:
    return (
        (config := Config.load()).send is not None
        and (recv := config.recv) is not None
        and recv.verify(target)
    )


forward = on_message(check_is_recv)


@forward.handle()
async def handle_forward(
    src_bot: discord.Bot,
    event: discord.MessageCreateEvent,
) -> None:
    msg = await MessageConverter(src_bot).convert(event.get_message())
    if not msg:
        return

    target = Config.load().send
    if TYPE_CHECKING:
        assert target is not None  # checked in rule

    dst_bot = await target.select()
    await get_sender(dst_bot).send(dst_bot, target, msg)

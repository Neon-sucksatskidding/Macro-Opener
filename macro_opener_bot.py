#!/usr/bin/env python3
"""Discord-powered macro opener.

A small Discord bot that allows one authorized user to start/stop/check a local
macro process using both prefix and slash commands.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("macro-opener")


@dataclass(frozen=True)
class Settings:
    token: str
    authorized_user_id: int
    macro_path: str
    command_prefix: str = "!om"

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("DISCORD_TOKEN", "").strip()
        user_id = os.getenv("AUTHORIZED_USER_ID", "").strip()
        macro_path = os.getenv("MACRO_PATH", "").strip()
        prefix = os.getenv("MACRO_COMMAND_PREFIX", "!om").strip() or "!om"

        missing = [
            name
            for name, value in [
                ("DISCORD_TOKEN", token),
                ("AUTHORIZED_USER_ID", user_id),
                ("MACRO_PATH", macro_path),
            ]
            if not value
        ]
        if missing:
            raise ValueError(f"Missing environment variables: {', '.join(missing)}")

        try:
            authorized_user_id = int(user_id)
        except ValueError as exc:
            raise ValueError("AUTHORIZED_USER_ID must be an integer") from exc

        if not Path(macro_path).exists():
            raise ValueError(f"MACRO_PATH does not exist: {macro_path}")

        return cls(
            token=token,
            authorized_user_id=authorized_user_id,
            macro_path=macro_path,
            command_prefix=prefix,
        )


class MacroController:
    def __init__(self, command_line: str) -> None:
        self.command_line = command_line
        self._process: Optional[subprocess.Popen] = None
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    async def start(self) -> tuple[bool, str]:
        async with self._lock:
            if self.is_running:
                return False, "Macro is already running."

            args = shlex.split(self.command_line)
            if not args:
                return False, "Macro path/command is empty."

            logger.info("Starting macro command: %s", self.command_line)
            self._process = subprocess.Popen(args)
            return True, f"Started macro: `{self.command_line}`"

    async def stop(self) -> tuple[bool, str]:
        async with self._lock:
            if not self.is_running:
                return False, "Macro is not running."

            assert self._process is not None
            logger.info("Stopping macro process pid=%s", self._process.pid)

            self._process.terminate()
            try:
                await asyncio.wait_for(asyncio.to_thread(self._process.wait), timeout=8)
            except TimeoutError:
                logger.warning("Macro did not terminate in time, killing process.")
                self._process.kill()
                await asyncio.to_thread(self._process.wait)

            self._process = None
            return True, "Macro stopped."

    def status_text(self) -> str:
        if self.is_running and self._process is not None:
            return f"Macro is running (pid={self._process.pid})."
        return "Macro is stopped."

    async def cleanup(self) -> None:
        if self.is_running:
            await self.stop()


class MacroBot(commands.Bot):
    def __init__(self, settings: Settings, controller: MacroController) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(command_prefix=settings.command_prefix, intents=intents)
        self.settings = settings
        self.controller = controller

    async def setup_hook(self) -> None:
        await self.add_cog(MacroCog(self, self.controller, self.settings))
        await self.tree.sync()
        logger.info("Slash commands synced.")

    async def on_ready(self) -> None:
        if self.user:
            logger.info("Logged in as %s (id=%s)", self.user, self.user.id)

    async def close(self) -> None:
        await self.controller.cleanup()
        await super().close()


class MacroCog(commands.Cog):
    def __init__(self, bot: MacroBot, controller: MacroController, settings: Settings) -> None:
        self.bot = bot
        self.controller = controller
        self.settings = settings

    def _is_authorized(self, user_id: int) -> bool:
        return user_id == self.settings.authorized_user_id

    async def _reject_if_unauthorized(self, send_fn, user_id: int) -> bool:
        if self._is_authorized(user_id):
            return False
        await send_fn("You are not authorized to control this macro.")
        return True

    @commands.command(name="start")
    async def start_prefix(self, ctx: commands.Context) -> None:
        if await self._reject_if_unauthorized(ctx.send, ctx.author.id):
            return
        _, message = await self.controller.start()
        await ctx.send(message)

    @commands.command(name="stop")
    async def stop_prefix(self, ctx: commands.Context) -> None:
        if await self._reject_if_unauthorized(ctx.send, ctx.author.id):
            return
        _, message = await self.controller.stop()
        await ctx.send(message)

    @commands.command(name="status")
    async def status_prefix(self, ctx: commands.Context) -> None:
        if await self._reject_if_unauthorized(ctx.send, ctx.author.id):
            return
        await ctx.send(self.controller.status_text())

    @app_commands.command(name="macro-start", description="Start the macro")
    async def start_slash(self, interaction: discord.Interaction) -> None:
        if not self._is_authorized(interaction.user.id):
            await interaction.response.send_message(
                "You are not authorized to control this macro.", ephemeral=True
            )
            return

        _, message = await self.controller.start()
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="macro-stop", description="Stop the macro")
    async def stop_slash(self, interaction: discord.Interaction) -> None:
        if not self._is_authorized(interaction.user.id):
            await interaction.response.send_message(
                "You are not authorized to control this macro.", ephemeral=True
            )
            return

        _, message = await self.controller.stop()
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="macro-status", description="Show macro status")
    async def status_slash(self, interaction: discord.Interaction) -> None:
        if not self._is_authorized(interaction.user.id):
            await interaction.response.send_message(
                "You are not authorized to control this macro.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            self.controller.status_text(), ephemeral=True
        )


async def run() -> None:
    settings = Settings.from_env()
    controller = MacroController(settings.macro_path)
    bot = MacroBot(settings, controller)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_stop_signal() -> None:
        logger.info("Stop signal received.")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_stop_signal)

    bot_task = asyncio.create_task(bot.start(settings.token))
    waiter_task = asyncio.create_task(stop_event.wait())

    done, pending = await asyncio.wait(
        {bot_task, waiter_task}, return_when=asyncio.FIRST_COMPLETED
    )

    for task in pending:
        task.cancel()

    if waiter_task in done:
        await bot.close()

    if bot_task in done:
        bot_task.result()


if __name__ == "__main__":
    asyncio.run(run())

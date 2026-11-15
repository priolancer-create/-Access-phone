"""Entrypoint: runs Telegram polling + the web server together."""
from __future__ import annotations

import asyncio
import contextlib
import logging

import uvicorn
from aiogram import Bot, Dispatcher

from .api import create_api
from .bot import router, set_commands
from .config import get_settings
from .db import Database

log = logging.getLogger("w8")


async def purge_loop(db: Database, days: int):
    while days > 0:
        try:
            n = await db.purge_older_than(days)
            if n:
                log.info("Retention purge removed %s records", n)
        except Exception:
            log.exception("Retention purge failed")
        await asyncio.sleep(6 * 3600)


async def main():
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db = Database(s.database_url)
    await db.connect()
    bot = Bot(s.bot_token)
    dp = Dispatcher(db=db, settings=s)
    dp.include_router(router)
    with contextlib.suppress(Exception):
        await set_commands(bot)

    api = create_api(s, db, bot)
    server = uvicorn.Server(uvicorn.Config(api, host="0.0.0.0", port=s.port, log_level="warning",
                                           proxy_headers=True, forwarded_allow_ips="*"))
    polling = asyncio.create_task(dp.start_polling(
        bot, handle_signals=False, close_bot_session=False,
        allowed_updates=dp.resolve_used_update_types()))
    polling.add_done_callback(lambda t_: setattr(server, "should_exit", True))
    purge = asyncio.create_task(purge_loop(db, s.retention_days))
    try:
        await server.serve()
    finally:
        purge.cancel()
        with contextlib.suppress(Exception):
            await dp.stop_polling()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(polling, 10)
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

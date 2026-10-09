"""Run with: python bot.py (see README.md for environment variables)."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from queryfi.config import create_prompt_service, create_service
from queryfi.discord_bot import CourseBot

ROOT = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
    token = os.environ.get("DISCORD_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set DISCORD_TOKEN to your bot token before starting.")
    try:
        service = create_service(os.environ)
        service.list_subjects(0)  # Verify both connections before logging into Discord.
        prompts = create_prompt_service(os.environ, service)
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
    bot = CourseBot(service, prompts)
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    main()

from rStuff import rBot
from environ import (
    useragent,
    client_id,
    client_secret,
    bot_username,
    bot_pass,
    SENTRY_USE,
    SENTRY_DSN,
    SENTRY_TRACES_SAMPLE_RATE,
)
from logger import logger
from HashDatabase import HashDatabase
from MainWorker import MainWorker
import sentry_sdk

if __name__ == "__main__":
    if SENTRY_USE:
        sentry_sdk.init(
            SENTRY_DSN,
            traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        )
        logger.info("Sentry initialization")
    else:
        logger.warning("Sentry skipped")

    reverse_img_bot = rBot(useragent, client_id, client_secret, bot_username, bot_pass)
    hash_db = HashDatabase()
    mainworker = MainWorker(reverse_img_bot, hash_db)
    mainworker.start_working()

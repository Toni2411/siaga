import logging
import sys

from .relay import Relay, Settings


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("siaga.telegram")
    s = Settings()
    if not s.token:
        log.info("SIAGA_TELEGRAM_TOKEN kosong, relay nonaktif")
        return 0
    if not (s.api_key and s.api_secret):
        log.error("ERPNEXT_API_KEY/SECRET kosong")
        return 1
    Relay(s).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Проверка здоровья контейнера (HEALTHCHECK в docker-compose.yml) с самолечением.

Docker перезапускает упавший контейнер (restart: unless-stopped), но не зависший: «unhealthy»
остаётся висеть. Поэтому после FAILS неудач подряд скрипт завершает все процессы контейнера,
кроме init (`init: true`), init выходит вслед за ними — и Docker поднимает контейнер заново.

    python healthcheck.py url <адрес>                 — адрес отвечает 2xx за TIMEOUT_S
    python healthcheck.py file <путь> <секунд>        — файл-пульс обновлялся не позже, чем <секунд> назад
"""
import os
import signal
import sys
import time
import urllib.request
from pathlib import Path

FAILS = 3
TIMEOUT_S = 10
COUNTER = Path("/tmp/healthcheck.failures")


def healthy(argv: list[str]) -> bool:
    try:
        if argv[0] == "url":
            with urllib.request.urlopen(argv[1], timeout=TIMEOUT_S) as r:
                return 200 <= r.status < 300
        if argv[0] == "file":
            return time.time() - Path(argv[1]).stat().st_mtime < float(argv[2])
    except (OSError, ValueError):
        return False
    raise SystemExit(f"неизвестная проверка: {argv[0]}")


def main(argv: list[str]) -> int:
    if healthy(argv):
        COUNTER.unlink(missing_ok=True)
        return 0
    try:
        fails = int(COUNTER.read_text()) + 1
    except (OSError, ValueError):
        fails = 1
    COUNTER.write_text(str(fails))
    print(f"проверка не прошла ({fails} из {FAILS} подряд)", flush=True)
    if fails >= FAILS:
        COUNTER.unlink(missing_ok=True)
        print("сервис не отвечает — перезапуск контейнера", flush=True)
        os.kill(-1, signal.SIGKILL)   # все процессы, кроме init и этого; init выходит, Docker перезапускает
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

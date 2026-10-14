# Расписание 2.0 — памятка для отдела ИТ

Сайт расписания занятий. Данные собираются автоматически с www.vavilovsar.ru, ручной ввод не нужен.

- `/` — сайт для студентов и преподавателей;
- `/rukovodstvo/` — версия для руководства. Открыта без пароля по решению заказчика; при
  необходимости закрывается Basic Auth или списком адресов на прокси вуза.

## Требования

| | |
|---|---|
| Сервер | Linux x86-64, 2 vCPU, 4 ГБ RAM, 20 ГБ SSD (минимум 2 vCPU, 2 ГБ, 10 ГБ) |
| ПО | Docker Engine, Docker Compose v2.24+, git |
| Нагрузка | в обычном режиме — доли процента CPU, около 0,8 ГБ RAM |
| Входящие | один HTTP-порт (`HTTP_PORT`, по умолчанию 80) |
| Исходящие при работе | `www.vavilovsar.ru:443` — расписание (пн, чт 03:00), графики (ежедневно), справочник кафедр (раз в 30 дней) |
| Исходящие при установке | `github.com`, Docker Hub (`python:3.10-slim`, `golang:1.25-bookworm`, `nginx:1.27-alpine`), `pypi.org`, `files.pythonhosted.org`, `proxy.golang.org` |

При выходе в интернет через HTTP-прокси его нужно указать для службы Docker
(`/etc/systemd/system/docker.service.d/http-proxy.conf`) и для сборки (`~/.docker/config.json`,
раздел `proxies`).

## Публикация

Сайт отдаёт HTTP; TLS — на прокси вуза, который пересылает запросы на
`http://<сервер>:<HTTP_PORT>`. Требования к прокси:

- для `/rukovodstvo/` — поддержка WebSocket (`Upgrade`, `Connection`) и увеличенный
  `proxy_read_timeout`;
- передача адреса клиента в `X-Forwarded-For`; в `deploy/nginx.conf` добавить
  `set_real_ip_from <адрес прокси>;` и `real_ip_header X-Forwarded-For;` — иначе ограничение
  частоты запросов будет общим для всех посетителей.

## Установка

```bash
sudo systemctl enable --now docker
git clone --recurse-submodules https://github.com/VladUd5/raspisanie-2.0.git "Расписание 2.0"
cd "Расписание 2.0"
cp .env.example .env              # PUBLIC_URL=https://<имя сайта>, при необходимости HTTP_PORT
docker compose up -d --build      # первая сборка — около 12 минут
docker compose ps                 # public, staff, collector, proxy — (healthy)
```

Остальные параметры `.env` имеют рабочие значения по умолчанию.

## Сопровождение

| | |
|---|---|
| Мониторинг | `GET /healthz` → `{"ok":true}`; рекомендуется подключить к Zabbix |
| Автовосстановление | перезапуск упавших и зависших контейнеров, старт вместе с Docker, лимиты памяти, ротация логов |
| Резервные копии | ежедневно в `data/backups/` (14 последних); нужно копировать на другой сервер |
| Журналы | `docker compose logs --since 1h <public\|staff\|collector\|parser\|proxy>` |
| Обновление | `git pull --recurse-submodules && docker compose up -d --build` |

Восстановление из копии и прочие подробности — в README.

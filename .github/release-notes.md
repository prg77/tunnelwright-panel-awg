Панель управления VPN на AmneziaWG для нескольких серверов: клиент создаётся один раз и получает профиль с тем же IP на каждой ноде.

- Клиенты: QR и `.conf` по каждой ноде, сроки доступа, группы, заметки, лимиты скорости, месячные квоты трафика.
- Ноды: установка, обновление и удаление по SSH из панели, автообновление агентов, метрики, блокировка торрент-трафика.
- Статистика трафика, журнал действий, вход с 2FA, тёмная и светлая темы.
- Telegram: уведомления и бот для управления; личная страница клиента с конфигом и инструкцией.
- Маршрутизация WireSock по спискам стран, подсетей и приложений.
- Зашифрованные бэкапы по расписанию с восстановлением панели и ключей нод.

Полное описание возможностей — в [README](https://github.com/prg77/tunnelwright-panel-awg#readme).

**Установка на сервер** (Debian, Ubuntu): `curl -fsSL https://raw.githubusercontent.com/prg77/tunnelwright-panel-awg/main/install.sh | bash`
**Установка на NAS** (Portainer): [docs/portainer.md](https://github.com/prg77/tunnelwright-panel-awg/blob/main/docs/portainer.md)
**Обновление:** `tunnelwright update v{{VERSION}}`
**Образы:** `ghcr.io/prg77/tunnelwright-{web,api,node}:{{VERSION}}` (amd64, arm64)

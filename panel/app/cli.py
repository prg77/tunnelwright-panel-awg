"""Сервисные команды panel-api (запускаются внутри контейнера).

    python -m app.cli reset-admin                     новый пароль администратора, 2FA выключается
    python -m app.cli restore-extract ARCHIVE OUTDIR  распаковать бэкап (пароль — первой строкой stdin)
"""
import json
import sqlite3
import sys
from pathlib import Path

from . import audit, backup, config, db, security


def main(argv):
    if argv[:1] == ["reset-admin"]:
        db.connect()
        password = security.reset_admin()
        audit.log(None, "cli", "admin_reset", config.ADMIN_USERNAME)
        print(f"Логин: {config.ADMIN_USERNAME}\nНовый пароль: {password}\n2FA отключена, все сессии завершены.")
        return 0
    if argv[:1] == ["restore-extract"] and len(argv) == 3:
        password = sys.stdin.readline().rstrip("\n")
        try:
            info = backup.extract(Path(argv[1]), password, Path(argv[2]))
        except RuntimeError:
            print("Неверный пароль бэкапа", file=sys.stderr)
            return 2
        except (KeyError, ValueError, OSError) as e:
            print(f"Архив повреждён или не является бэкапом Tunnelwright Panel AWG: {e}", file=sys.stderr)
            return 3
        # Для tunnelwright restore: id локальной ноды (VPN на сервере панели) — из самой БД панели,
        # так работает и с архивами, где в backup-info.json нет признака local
        out = Path(argv[2])
        con = sqlite3.connect(out / "panel" / "panel.db")
        row = con.execute("SELECT id FROM nodes WHERE is_local=1").fetchone()
        con.close()
        (out / "local-node").write_text(str(row[0]) if row else "")
        print(json.dumps(info, ensure_ascii=False))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

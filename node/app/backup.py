"""Снимок данных ноды для бэкапа: БД wg-easy (ключи, клиенты, параметры), лимиты, учётка агента.

Архив не шифруется — его забирает panel-api по внутренней сети и шифрует сам.
БД копируется через backup API SQLite: согласованная копия даже во время записи wg-easy.
"""
import io
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from . import config


def snapshot() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z, tempfile.TemporaryDirectory() as tmp:
        if config.WG_DB_FILE.exists():
            dst = Path(tmp) / "wg-easy.db"
            src = sqlite3.connect(f"file:{config.WG_DB_FILE}?mode=ro", uri=True)
            out = sqlite3.connect(dst)
            with out:
                src.backup(out)
            src.close()
            out.close()
            z.write(dst, "wg-easy.db")
        for f in (config.LIMITS_FILE, config.CREDS_FILE, config.DATA_DIR / "uids.json"):
            if f.exists():
                z.write(f, f.name)
    return buf.getvalue()

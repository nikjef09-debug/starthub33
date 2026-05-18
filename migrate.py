"""
migrate.py — добавляет новые колонки и таблицы в существующую БД
Запусти один раз: python migrate.py
"""
import asyncio
import aiosqlite

DB_PATH = "starthub.db"


async def migrate():
    async with aiosqlite.connect(DB_PATH) as db:

        # ── users ──────────────────────────────────────────────────────────────
        cur = await db.execute("PRAGMA table_info(users)")
        user_cols = {row[1] for row in await cur.fetchall()}

        user_migrations = []
        if "custom_role_name" not in user_cols:
            user_migrations.append("ALTER TABLE users ADD COLUMN custom_role_name VARCHAR(64)")
            print("+ users.custom_role_name")
        if "email_consent" not in user_cols:
            user_migrations.append("ALTER TABLE users ADD COLUMN email_consent BOOLEAN DEFAULT 0")
            print("+ users.email_consent")
        if "email_verified" not in user_cols:
            user_migrations.append("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0")
            # Существующие пользователи считаются верифицированными (созданы до введения проверки)
            user_migrations.append("UPDATE users SET email_verified = 1")
            print("+ users.email_verified (existing users set to verified)")
        if "totp_secret" not in user_cols:
            user_migrations.append("ALTER TABLE users ADD COLUMN totp_secret VARCHAR(32)")
            print("+ users.totp_secret")
        if "totp_enabled" not in user_cols:
            user_migrations.append("ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN DEFAULT 0")
            print("+ users.totp_enabled")

        for sql in user_migrations:
            await db.execute(sql)

        # ── subscriptions ──────────────────────────────────────────────────────
        cur2 = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='subscriptions'"
        )
        if not await cur2.fetchone():
            await db.execute("""
                CREATE TABLE subscriptions (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
                    plan VARCHAR(32) NOT NULL DEFAULT 'free',
                    is_active BOOLEAN DEFAULT 1,
                    started_at DATETIME,
                    expires_at DATETIME,
                    auto_renew BOOLEAN DEFAULT 1,
                    paid_amount FLOAT DEFAULT 0.0,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """)
            print("+ table subscriptions")

        # ── role_configs ───────────────────────────────────────────────────────
        cur3 = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='role_configs'"
        )
        if not await cur3.fetchone():
            await db.execute("""
                CREATE TABLE role_configs (
                    id INTEGER PRIMARY KEY,
                    role_name VARCHAR(32) NOT NULL UNIQUE,
                    label VARCHAR(128) NOT NULL,
                    description VARCHAR(256),
                    visible_at_registration BOOLEAN DEFAULT 1,
                    permissions TEXT DEFAULT '{}',
                    updated_at DATETIME
                )
            """)
            print("+ table role_configs")

        # ── UserRole.developer — обновляем CHECK constraint ────────────────────
        cur4 = await db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
        )
        row4 = await cur4.fetchone()
        if row4 and "developer" not in row4[0]:
            import re
            old_ddl = row4[0]
            # Заменяем CHECK constraint — добавляем 'developer'
            new_ddl = re.sub(
                r"(role\s+VARCHAR\(\d+\)[^)]*CHECK\s*\([^)]*)'admin'(\s*\))",
                r"\1'admin','developer'\2",
                old_ddl,
            )
            if new_ddl == old_ddl:
                # Альтернативный паттерн без лишних пробелов
                new_ddl = old_ddl.replace("'admin')", "'admin','developer')")

            if new_ddl != old_ddl:
                await db.execute("PRAGMA foreign_keys = OFF")

                # Получаем список колонок
                cols_cur = await db.execute("PRAGMA table_info(users)")
                cols = [r[1] for r in await cols_cur.fetchall()]
                col_list = ", ".join(cols)

                # Получаем индексы
                idx_cur = await db.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='users' AND sql IS NOT NULL"
                )
                indexes = [r[0] for r in await idx_cur.fetchall()]

                await db.execute("ALTER TABLE users RENAME TO _users_old")
                await db.execute(new_ddl)
                await db.execute(
                    f"INSERT INTO users ({col_list}) SELECT {col_list} FROM _users_old"
                )
                await db.execute("DROP TABLE _users_old")

                for idx_sql in indexes:
                    try:
                        await db.execute(idx_sql)
                    except Exception:
                        pass

                await db.execute("PRAGMA foreign_keys = ON")
                print("+ users.role CHECK: добавлен 'developer'")
            else:
                print("! Не удалось найти CHECK constraint — пропускаю")

        # ── email_verification_tokens ──────────────────────────────────────────
        cur5 = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='email_verification_tokens'"
        )
        if not await cur5.fetchone():
            await db.execute("""
                CREATE TABLE email_verification_tokens (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    token VARCHAR(128) NOT NULL UNIQUE,
                    expires_at DATETIME NOT NULL,
                    created_at DATETIME
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS ix_email_verification_tokens_token "
                "ON email_verification_tokens(token)"
            )
            print("+ table email_verification_tokens")

        await db.commit()
        print("OK: Migratsiya zavershena!")


asyncio.run(migrate())

"""Small idempotent schema fixes for the demo environment.

SQLAlchemy's ``Base.metadata.create_all`` creates missing tables, but it does not
add new columns to tables that already exist in the local Docker volume.  This
module keeps the demo database compatible after applying code patches without
requiring the user to delete the Postgres volume.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("sentiflow.schema_migrations")


def _has_table(engine: Engine, table_name: str) -> bool:
    try:
        return inspect(engine).has_table(table_name)
    except Exception:  # pragma: no cover - defensive startup guard
        logger.exception("Impossible d'inspecter la table %s", table_name)
        return False


def run_demo_schema_migrations(engine: Engine) -> None:
    """Apply tiny additive migrations needed by recent demo patches.

    This is intentionally limited to ``ADD COLUMN IF NOT EXISTS`` operations.
    For a real production app, replace this with Alembic migrations.
    """

    if engine.dialect.name != "postgresql":
        logger.info("Skipping demo schema migrations for dialect %s", engine.dialect.name)
        return

    statements: list[str] = []

    if _has_table(engine, "users"):
        statements.extend(
            [
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan VARCHAR(20) DEFAULT 'free'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_calls_today INTEGER DEFAULT 0",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_calls_date VARCHAR(10)",
                "UPDATE users SET plan = 'free' WHERE plan IS NULL",
                # Les comptes admin passent en premium par défaut
                "UPDATE users SET plan = 'premium' WHERE is_admin = true",
            ]
        )

    if _has_table(engine, "feedbacks"):
        statements.extend(
            [
                "ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS target_type VARCHAR(20)",
                "ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS target_id INTEGER",
                "ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS corrected_label VARCHAR(20)",
                "ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS reason VARCHAR(500)",
                "ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS metadata_json JSON",
            ]
        )

    if _has_table(engine, "llm_feedbacks"):
        statements.extend(
            [
                "ALTER TABLE llm_feedbacks ADD COLUMN IF NOT EXISTS user_id INTEGER",
                "ALTER TABLE llm_feedbacks ADD COLUMN IF NOT EXISTS question TEXT",
                "ALTER TABLE llm_feedbacks ADD COLUMN IF NOT EXISTS previous_answer TEXT",
                "ALTER TABLE llm_feedbacks ADD COLUMN IF NOT EXISTS regenerated_answer TEXT",
                "ALTER TABLE llm_feedbacks ADD COLUMN IF NOT EXISTS vote INTEGER DEFAULT -1",
                "ALTER TABLE llm_feedbacks ADD COLUMN IF NOT EXISTS reason VARCHAR(1000)",
                "ALTER TABLE llm_feedbacks ADD COLUMN IF NOT EXISTS metadata_json JSON",
                "ALTER TABLE llm_feedbacks ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()",
                # Old demo versions may already have created llm_feedbacks with
                # legacy NOT NULL columns such as rating.  The current code no
                # longer writes these columns, so we relax every legacy NOT NULL
                # column except the primary key instead of forcing users to drop
                # their local Postgres volume.
                """
                DO $$
                DECLARE column_record record;
                BEGIN
                    FOR column_record IN
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = 'llm_feedbacks'
                          AND is_nullable = 'NO'
                          AND column_name <> 'id'
                    LOOP
                        EXECUTE format(
                            'ALTER TABLE llm_feedbacks ALTER COLUMN %I DROP NOT NULL',
                            column_record.column_name
                        );
                    END LOOP;
                END $$
                """,
            ]
        )

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))

    logger.info("Demo schema migrations applied: %s statements", len(statements))

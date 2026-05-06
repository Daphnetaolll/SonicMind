from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row


# Schema statements create the local MVP account, quota, admin, and billing tables idempotently.
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT,
        plan TEXT NOT NULL DEFAULT 'free',
        subscription_status TEXT NOT NULL DEFAULT 'active',
        billing_period_start TIMESTAMPTZ,
        billing_period_end TIMESTAMPTZ,
        extra_question_credits INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        deleted_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users (id),
        status TEXT NOT NULL CHECK (
            status IN ('trial', 'active', 'past_due', 'canceled', 'expired')
        ),
        plan_code TEXT NOT NULL DEFAULT 'monthly-100',
        current_period_start TIMESTAMPTZ,
        current_period_end TIMESTAMPTZ,
        auto_renew BOOLEAN NOT NULL DEFAULT TRUE,
        monthly_quota INTEGER NOT NULL DEFAULT 100 CHECK (monthly_quota >= 0),
        provider TEXT,
        provider_customer_id TEXT,
        provider_subscription_id TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS question_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users (id),
        question_text TEXT NOT NULL,
        answer_text TEXT,
        status TEXT NOT NULL CHECK (status IN ('started', 'succeeded', 'failed')),
        charged BOOLEAN NOT NULL DEFAULT FALSE,
        charge_type TEXT NOT NULL DEFAULT 'none' CHECK (
            charge_type IN ('free', 'subscription', 'extra_credit', 'none')
        ),
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usage_ledger (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users (id),
        subscription_id TEXT REFERENCES subscriptions (id),
        question_log_id TEXT UNIQUE REFERENCES question_logs (id),
        event_type TEXT NOT NULL CHECK (
            event_type IN (
                'free_grant',
                'free_usage',
                'subscription_grant',
                'subscription_usage',
                'extra_credit_usage',
                'manual_adjustment',
                'refund_usage'
            )
        ),
        delta INTEGER NOT NULL,
        source TEXT NOT NULL,
        period_start TIMESTAMPTZ,
        period_end TIMESTAMPTZ,
        notes TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_roles (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users (id),
        role TEXT NOT NULL CHECK (role IN ('admin')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, role)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS billing_events (
        id TEXT PRIMARY KEY,
        user_id TEXT REFERENCES users (id),
        subscription_id TEXT REFERENCES subscriptions (id),
        provider TEXT NOT NULL,
        event_type TEXT NOT NULL,
        provider_event_id TEXT NOT NULL UNIQUE,
        raw_payload JSONB NOT NULL,
        processed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS credit_transactions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users (id),
        credit_amount INTEGER NOT NULL,
        purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ,
        source TEXT NOT NULL,
        note TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users (id),
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
        spotify_results_json JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS favorite_tracks (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users (id),
        spotify_track_id TEXT NOT NULL,
        track_name TEXT NOT NULL,
        artist_name TEXT NOT NULL,
        spotify_url TEXT NOT NULL,
        album_image TEXT,
        source_question TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_id, spotify_track_id)
    )
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free'
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS subscription_status TEXT NOT NULL DEFAULT 'active'
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS billing_period_start TIMESTAMPTZ
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS billing_period_end TIMESTAMPTZ
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS extra_question_credits INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE question_logs
    DROP CONSTRAINT IF EXISTS question_logs_charge_type_check
    """,
    """
    ALTER TABLE question_logs
    ADD CONSTRAINT question_logs_charge_type_check
    CHECK (charge_type IN ('free', 'subscription', 'extra_credit', 'none'))
    """,
    """
    ALTER TABLE usage_ledger
    DROP CONSTRAINT IF EXISTS usage_ledger_event_type_check
    """,
    """
    ALTER TABLE usage_ledger
    ADD CONSTRAINT usage_ledger_event_type_check
    CHECK (
        event_type IN (
            'free_grant',
            'free_usage',
            'subscription_grant',
            'subscription_usage',
            'extra_credit_usage',
            'manual_adjustment',
            'refund_usage'
        )
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id
    ON subscriptions (user_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_subscriptions_status_period
    ON subscriptions (status, current_period_end)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_question_logs_user_id_created_at
    ON question_logs (user_id, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_question_logs_status
    ON question_logs (status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_usage_ledger_user_id_created_at
    ON usage_ledger (user_id, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_usage_ledger_subscription_period
    ON usage_ledger (subscription_id, period_start, period_end)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_roles_user_id
    ON admin_roles (user_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_billing_events_subscription_id
    ON billing_events (subscription_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_expires
    ON credit_transactions (user_id, expires_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created
    ON chat_messages (user_id, created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_favorite_tracks_user_created
    ON favorite_tracks (user_id, created_at DESC)
    """,
]


def get_database_url() -> str:
    # Read DATABASE_URL at call time so scripts can set it from the shell before execution.
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("Missing DATABASE_URL.")
    return database_url


def connect_db(database_url: str | None = None) -> psycopg.Connection:
    # Return dict-like rows so repository functions can use column names directly.
    return psycopg.connect(database_url or get_database_url(), row_factory=dict_row)


def init_database(database_url: str | None = None) -> str:
    # Apply every schema/index statement in one transaction and return the database URL used.
    resolved_url = database_url or get_database_url()
    with connect_db(resolved_url) as conn:
        with conn.cursor() as cur:
            for statement in SCHEMA_STATEMENTS:
                cur.execute(statement)
        conn.commit()
    return resolved_url

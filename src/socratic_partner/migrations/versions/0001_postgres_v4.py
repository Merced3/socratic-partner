"""Create the Postgres equivalent of the deployed SQLite schema 4.

Existing rows are copied separately only after this schema is verified. Rollback
before cutover is dropping this new schema; after cutover, retain both copies
read-only and restore from managed backup rather than running a destructive downgrade.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_postgres_v4"
down_revision = None
branch_labels = None
depends_on = None

snowflake = sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    op.create_table(
        "application_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("next_question_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pi_session_id", sa.Text(), nullable=True),
        sa.Column("pi_session_file", sa.Text(), nullable=True),
        sa.Column("last_agent_call_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_provider", sa.Text(), nullable=True),
        sa.Column("last_model_id", sa.Text(), nullable=True),
        sa.Column("last_input_tokens", sa.Integer(), nullable=False),
        sa.Column("last_output_tokens", sa.Integer(), nullable=False),
        sa.Column("last_cost", sa.Double(), nullable=False),
        sa.Column("last_error_kind", sa.Text(), nullable=True),
        sa.CheckConstraint("id = 1"),
        sa.CheckConstraint("interval_seconds > 0"),
        sa.CheckConstraint("status IN ('WAITING', 'PAUSED')"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("channel_id", snowflake, nullable=False),
        sa.Column("question_message_id", snowflake, nullable=False),
        sa.Column("session_card", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSING', 'COMPLETED')"),
        sa.PrimaryKeyConstraint("id"),
    )
    # OPEN and CLOSING cannot coexist in the current lifecycle, so unique status
    # values in this partial index enforce one active conversation in Postgres.
    op.create_index(
        "one_active_conversation",
        "conversations",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status IN ('OPEN', 'CLOSING')"),
    )


def downgrade() -> None:
    op.drop_index("one_active_conversation", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("application_state")

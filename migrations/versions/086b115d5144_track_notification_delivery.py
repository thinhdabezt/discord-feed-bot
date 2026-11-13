"""track notification delivery

Revision ID: 086b115d5144
Revises: 290fcd041c6f
Create Date: 2026-11-13 10:20:17.589400

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '086b115d5144'
down_revision: Union[str, Sequence[str], None] = '290fcd041c6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "feed_items",
        sa.Column(
            "notification_attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "feed_items",
        sa.Column(
            "notified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "feed_items",
        sa.Column(
            "last_notification_error",
            sa.Text(),
            nullable=True,
        ),
    )

    # Các bài viết đã tồn tại được xem là đã xử lý,
    # tránh gửi lại toàn bộ lịch sử sau khi nâng cấp.
    op.execute(
        "UPDATE feed_items "
        "SET notified_at = CURRENT_TIMESTAMP "
        "WHERE notified_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("feed_items", "last_notification_error")
    op.drop_column("feed_items", "notified_at")
    op.drop_column("feed_items", "notification_attempts")

"""Add moderator functionalities

Revision ID: 1849c26ba5d1
Revises: ca6ee5b42503
Create Date: 2024-10-05 14:03:17.680651

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1849c26ba5d1"
down_revision: Union[str, None] = "ca6ee5b42503"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ReportStatus enum
    report_status = postgresql.ENUM(
        "PENDING", "REVIEWED", "RESOLVED", name="reportstatus"
    )
    report_status.create(op.get_bind())

    # Add new columns to reports table
    op.add_column(
        "reports",
        sa.Column(
            "status",
            sa.Enum("PENDING", "REVIEWED", "RESOLVED", name="reportstatus"),
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column("reports", sa.Column("reviewed_by", sa.Integer(), nullable=True))
    op.add_column("reports", sa.Column("resolution_notes", sa.String(), nullable=True))

    # Add foreign key for reviewed_by
    op.create_foreign_key(
        "fk_reports_reviewed_by_users", "reports", "users", ["reviewed_by"], ["id"]
    )

    # Add is_active column to communities table
    op.add_column(
        "communities",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    # Remove is_active column from communities table
    op.drop_column("communities", "is_active")

    # Remove foreign key and columns from reports table
    op.drop_constraint("fk_reports_reviewed_by_users", "reports", type_="foreignkey")
    op.drop_column("reports", "resolution_notes")
    op.drop_column("reports", "reviewed_by")
    op.drop_column("reports", "status")

    # Drop ReportStatus enum
    op.execute("DROP TYPE reportstatus")

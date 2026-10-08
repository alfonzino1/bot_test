"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Хронос: миграция схемы. Пустая ревизия — тоже миграция.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

${imports if imports else ""}

# Идентификаторы ревизии, используются Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Применение миграции."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Откат миграции."""
    ${downgrades if downgrades else "pass"}

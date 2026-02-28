"""add drawings and evidence_records

Revision ID: c633122f53e5
Revises: 5cd542fee02d
Create Date: 2026-02-28 12:58:33.545866

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = 'c633122f53e5'
down_revision = '5cd542fee02d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create drawings table
    op.create_table(
        'drawings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),  # 'upload' or 'procore'
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('storage_key', sa.String(), nullable=True),  # path in backend/uploads/
        sa.Column('file_url', sa.String(), nullable=True),  # API endpoint for download
        sa.Column('content_type', sa.String(), nullable=True),  # 'application/pdf', 'image/png', etc.
        sa.Column('page_count', sa.Integer(), nullable=True),  # for PDFs
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_drawings_project_id'), 'drawings', ['project_id'], unique=False)

    # Create evidence_records table
    op.create_table(
        'evidence_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),  # 'spec' or 'inspection_doc'
        sa.Column('trade', sa.String(), nullable=True),
        sa.Column('spec_section', sa.String(), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('storage_key', sa.String(), nullable=True),  # path in backend/uploads/
        sa.Column('text_content', sa.Text(), nullable=True),  # Phase 4: extracted text from PDFs
        sa.Column('meta', sa.JSON(), nullable=True),  # flexible metadata
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_evidence_records_project_id'), 'evidence_records', ['project_id'], unique=False)
    op.create_index(op.f('ix_evidence_records_project_type'), 'evidence_records', ['project_id', 'type'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_evidence_records_project_type'), table_name='evidence_records')
    op.drop_index(op.f('ix_evidence_records_project_id'), table_name='evidence_records')
    op.drop_table('evidence_records')
    op.drop_index(op.f('ix_drawings_project_id'), table_name='drawings')
    op.drop_table('drawings')


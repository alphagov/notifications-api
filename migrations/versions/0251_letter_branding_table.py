"""

Revision ID: 0251_letter_branding_table
Revises: 0250_drop_stats_template_table
Create Date: 2019-01-17 15:45:33.242955

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0251_letter_branding_table'
down_revision = '0250_drop_stats_template_table'


def upgrade():
    op.create_table('letter_branding',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('name', sa.String(length=255), nullable=False),
                    sa.Column('filename', sa.String(length=255), nullable=False),
                    sa.Column('domain', sa.Text(), nullable=True),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('domain'),
                    sa.UniqueConstraint('filename'),
                    sa.UniqueConstraint('name')
                    )
    op.create_table('service_letter_branding',
                    sa.Column('service_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('letter_branding_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.ForeignKeyConstraint(['letter_branding_id'], ['letter_branding.id'], ),
                    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
                    sa.PrimaryKeyConstraint('service_id')
                    )

    op.get_bind()

    op.execute("""INSERT INTO letter_branding (id, name, filename, domain)
                SELECT uuid_in(md5(random()::text)::cstring), name, filename, null 
                from dvla_organisation""")

    op.execute("""INSERT INTO service_letter_branding (service_id, letter_branding_id)
               SELECT S.id, LB.id
                 FROM services s
                 JOIN dvla_organisation d on (s.dvla_organisation_id = d.id)
                 JOIN letter_branding lb on (lb.filename = d.filename)
                 """)


def downgrade():
    op.drop_table('service_letter_branding')
    op.drop_table('letter_branding')

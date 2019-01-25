"""empty message

Revision ID: 0257_letter_branding_migration
Revises: 0256_set_postage_tmplt_hstr

"""

# revision identifiers, used by Alembic.
revision = '0257_letter_branding_migration'
down_revision = '0256_set_postage_tmplt_hstr'

from alembic import op


def upgrade():
    op.execute("""INSERT INTO letter_branding (id, name, filename, domain)
                SELECT uuid_in(md5(random()::text)::cstring), name, filename, null
                from dvla_organisation""")

    op.execute("""INSERT INTO service_letter_branding (service_id, letter_branding_id)
               SELECT S.id, LB.id
                 FROM services s
                 JOIN dvla_organisation d on (s.dvla_organisation_id = d.id)
                 JOIN letter_branding lb on (lb.filename = d.filename)
                 WHERE d.id != '001'
                 """)


def downgrade():
    op.execute('delete from service_letter_branding')
    op.execute('delete from letter_branding')

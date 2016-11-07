"""empty message

Revision ID: f266fb67597a
Revises: 0058_add_letters_flag
Create Date: 2016-11-07 16:13:18.961527

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0059_add_letter_template_type'
down_revision = '0058_add_letters_flag'


name = 'template_type'
tmp_name = 'tmp_' + name

old_options = ('sms', 'email')
new_options = old_options + ('letter',)

new_type = sa.Enum(*new_options, name=name)
old_type = sa.Enum(*old_options, name=name)

tcr = sa.sql.table(
    'templates',
    sa.Column('template_type', new_type, nullable=False)
)


def upgrade():
    op.execute('ALTER TYPE ' + name + ' RENAME TO ' + tmp_name)

    new_type.create(op.get_bind())
    op.execute(
        'ALTER TABLE templates ALTER COLUMN template_type ' +
        'TYPE ' + name + ' USING template_type::text::' + name
    )
    op.execute('DROP TYPE ' + tmp_name)


def downgrade():
    # Convert 'letter' template into 'email'
    op.execute(
        tcr.update().where(tcr.c.template_type=='letter').values(template_type='email')
    )

    op.execute('ALTER TYPE ' + name + ' RENAME TO ' + tmp_name)

    old_type.create(op.get_bind())
    op.execute(
        'ALTER TABLE templates ALTER COLUMN template_type ' +
        'TYPE ' + name + ' USING template_type::text::' + name
    )
    op.execute('DROP TYPE ' + tmp_name)

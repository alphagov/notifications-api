import glob
import pathlib


def test_migration_files_start_with_numeric_id():
    """Make sure that all of the migration files start with a 4-character integer"""
    migrations = sorted(glob.glob("migrations/versions/*.py"))

    migration_versions = [pathlib.Path(migration).stem.split("_")[0] for migration in migrations]

    assert all(
        migration_version.isdigit() and len(migration_version) == 4 for migration_version in migration_versions
    ), "All migrations should start with a zero-padded 4-digit integer ID"


def test_current_alembic_head():
    migrations = sorted(glob.glob("migrations/versions/*.py"))
    head_migration_filename = pathlib.Path(migrations[-1]).stem

    with open("migrations/.current-alembic-head") as current_alembic_head:
        assert current_alembic_head.read() == f"{head_migration_filename}\n"


def test_revision_matches_filename(notify_db_session):
    migrations = sorted(glob.glob("migrations/versions/*.py"))
    head_migration_filename = pathlib.Path(migrations[-1]).stem
    head_migration_id = head_migration_filename.split(".")[0]

    results = notify_db_session.execute("select version_num from alembic_version").fetchall()
    assert len(results) == 1
    assert results[0].version_num == head_migration_id, (
        'alembic head filename {head_migration_filename} does not match "revision" {results[0].version}'
    )

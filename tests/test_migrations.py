import glob
import pathlib


def test_migration_files_start_with_numeric_id():
    """Make sure that all of the migration files start with a 4-character integer"""
    migrations = sorted(glob.glob("migrations/versions/*.py"))

    migration_versions = [pathlib.Path(migration).name.split("_")[0] for migration in migrations]

    assert all(
        migration_version.isdigit() and len(migration_version) == 4 for migration_version in migration_versions
    ), "All migrations should start with a zero-padded 4-digit integer ID"


def test_current_alembic_head():
    migrations = sorted(glob.glob("migrations/versions/*.py"))

    head_migration_id = pathlib.Path(migrations[-1]).name.split(".")[0]

    with open("migrations/.current-alembic-head") as current_alembic_head:
        assert current_alembic_head.read() == f"{head_migration_id}\n"

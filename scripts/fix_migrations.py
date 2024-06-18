#!/usr/bin/env python

# ruff: noqa: T201

import os
import sys

from alembic.script import ScriptDirectory

sys.path.append(".")


def get_branch_points(migrations):
    return [m for m in migrations.walk_revisions() if m.is_branch_point]


def get_branches(migrations, branch_point, heads):
    return [list(migrations.iterate_revisions(m, branch_point.revision))[::-1] for m in heads]


def choice(prompt, options, option_fmt=lambda x: x):
    print(f"{prompt}:\n")
    for i, option in enumerate(options):
        print(f"{i + 1}. {option_fmt(option)}")

    print()
    choice = input("Option> ")

    return options[int(choice) - 1]


def rename_revision(current_revision, new_base):
    new_id = int(new_base[:4]) + 1
    return f"{new_id:04d}{current_revision[4:]}"


def reorder_revisions(revisions, old_base, new_base):
    if not revisions:
        return

    head, *tail = revisions
    new_revision_id = rename_revision(head.revision, new_base)

    print(f"Moving {head.revision} to {new_revision_id}")
    with open(head.path) as rev_file:
        file_data = rev_file.read()

    file_data = file_data.replace(head.revision, new_revision_id).replace(old_base, new_base)
    new_filename = head.path.replace(head.revision, new_revision_id)

    assert head.path != new_filename, "Old filename not same as revision id, please rename file before continuing"

    with open(new_filename, "w") as rev_file:
        rev_file.write(file_data)

    print(f"Removing {head.path}")
    os.remove(head.path)

    reorder_revisions(tail, head.revision, new_revision_id)


def fix_branch_point(migrations, branch_point, heads):
    print(f"Migrations directory has a branch point at {branch_point.revision}")

    branches = get_branches(migrations, branch_point, heads)
    move_branch = choice("Select migrations to move", branches, lambda x: " -> ".join(m.revision for m in x))
    branches.remove(move_branch)

    reorder_revisions(move_branch, branch_point.revision, branches[0][-1].revision)


def main(migrations_path):
    migrations = ScriptDirectory(migrations_path)

    branch_points = get_branch_points(migrations)
    heads = migrations.get_heads()

    if not branch_points:
        print("Migrations are ordered")
    elif len(branch_points) == 1 and len(heads) == 2:
        fix_branch_point(migrations, branch_points[0], heads)
    else:
        print(
            f"Found {[bp.revision for bp in branch_points]} branch points and {heads} heads, can't fix automatically"
        )
        sys.exit(1)


if __name__ == "__main__":
    main("migrations/")

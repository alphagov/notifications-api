#!/usr/bin/env python
# encoding: utf-8

import os
import sys

from alembic.script import ScriptDirectory

sys.path.append('.')


def get_branch_points(migrations):
    return [m for m in migrations.walk_revisions() if m.is_branch_point]


def get_branches(migrations, branch_point, heads):
    return [list(migrations.iterate_revisions(m, branch_point.revision))[::-1]
            for m in heads]


def choice(prompt, options, option_fmt=lambda x: x):
    print("{}:\n".format(prompt))
    for i, option in enumerate(options):
        print("{}. {}".format(i + 1, option_fmt(option)))

    print()
    choice = input("Option> ")

    return options[int(choice) - 1]


def rename_revision(current_revision, new_base):
    new_id = int(new_base[:4]) + 1
    return "{:04d}{}".format(new_id, current_revision[4:])


def reorder_revisions(revisions, old_base, new_base):
    if not revisions:
        return

    head, *tail = revisions
    new_revision_id = rename_revision(head.revision, new_base)

    print("Moving {} to {}".format(head.revision, new_revision_id))
    with open(head.path, 'r') as rev_file:
        file_data = rev_file.read()

    file_data = file_data.replace(head.revision, new_revision_id).replace(old_base, new_base)
    new_filename = head.path.replace(head.revision, new_revision_id)

    assert head.path != new_filename, 'Old filename not same as revision id, please rename file before continuing'

    with open(new_filename, 'w') as rev_file:
        rev_file.write(file_data)

    print("Removing {}".format(head.path))
    os.remove(head.path)

    reorder_revisions(tail, head.revision, new_revision_id)


def fix_branch_point(migrations, branch_point, heads):
    print("Migrations directory has a branch point at {}".format(branch_point.revision))

    branches = get_branches(migrations, branch_point, heads)
    move_branch = choice("Select migrations to move", branches,
                         lambda x: " -> ".join(m.revision for m in x))
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
        print("Found {} branch points and {} heads, can't fix automatically".format(
            [bp.revision for bp in branch_points], heads))
        sys.exit(1)


if __name__ == '__main__':
    main('migrations/')

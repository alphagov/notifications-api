#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

import json
import yaml


def merge_dicts(a, b):
    if not (isinstance(a, dict) and isinstance(b, dict)):
        raise ValueError("Error merging variables: '{}' and '{}'".format(
            type(a).__name__, type(b).__name__
        ))

    result = a.copy()
    for key, val in b.items():
        if isinstance(result.get(key), dict):
            result[key] = merge_dicts(a[key], b[key])
        else:
            result[key] = val

    return result


def load_manifest(manifest_file):
    with open(manifest_file) as f:
        manifest = yaml.load(f)

    if 'inherit' in manifest:
        inherit_file = os.path.join(os.path.dirname(manifest_file), manifest.pop('inherit'))
        manifest = merge_dicts(load_manifest(inherit_file), manifest)

    return manifest


def load_variables(vars_files):
    variables = {}
    for vars_file in vars_files:
        with open(vars_file) as f:
            variables = merge_dicts(variables, yaml.load(f))

    return {
        k.upper(): json.dumps(v) if isinstance(v, (dict, list)) else v
        for k, v in variables.items()
    }


def paas_manifest(manifest_file, *vars_files):
    """Generate a PaaS manifest file from a Jinja2 template"""

    manifest = load_manifest(manifest_file)
    variables = load_variables(vars_files)

    for key in manifest.get('env', {}):
        if key in variables:
            manifest['env'][key] = variables[key]

    return yaml.dump(manifest, default_flow_style=False, allow_unicode=True)


if __name__ == "__main__":
    print('---')
    print(paas_manifest(*sys.argv[1:]))

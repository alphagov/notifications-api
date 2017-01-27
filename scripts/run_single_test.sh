#!/bin/bash
# run a single unit test, pass in the unit test name for example: tests/app/service/test_rest.py::test_get_template_list
source environment_test.sh
py.test $@

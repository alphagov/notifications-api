import pytest


class TestBlueprint:
    @pytest.mark.parametrize(
        "environment, blueprint_should_register",
        (
            ("development", True),
            ("preview", True),
            ("staging", False),
            ("production", False),
        ),
    )
    def test_should_register_testing_blueprint(self, environment, blueprint_should_register):
        from app import _should_register_functional_testing_blueprint

        assert _should_register_functional_testing_blueprint(environment) is blueprint_should_register

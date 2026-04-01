"""Tests for {{project_name}}."""

from {{module_name}}.core import hello


def test_hello():
    assert hello() == "Hello, world!"
    assert hello("devkit") == "Hello, devkit!"

from parity_adapter import FIXTURES, build_reference_outputs


def test_cross_language_fixtures_match_python_reference() -> None:
    for name, expected in build_reference_outputs().items():
        assert (FIXTURES / name).read_text() == expected

import pytest

from keydup.domain import camelot_neighbors, expand_harmonic, parse_camelot


def test_parse():
    assert parse_camelot("8A") == (8, "A")
    assert parse_camelot("12B") == (12, "B")
    with pytest.raises(ValueError):
        parse_camelot("13A")
    with pytest.raises(ValueError):
        parse_camelot("0B")


def test_neighbors_middle():
    assert camelot_neighbors("8A") == frozenset({"8A", "7A", "9A", "8B"})


def test_neighbors_wraparound():
    assert camelot_neighbors("1A") == frozenset({"1A", "12A", "2A", "1B"})
    assert camelot_neighbors("12B") == frozenset({"12B", "11B", "1B", "12A"})


def test_expand():
    assert expand_harmonic(frozenset({"8A"})) == camelot_neighbors("8A")

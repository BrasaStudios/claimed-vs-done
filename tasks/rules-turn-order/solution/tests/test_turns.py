import json

import pytest

from tactics.turns import Battle, Unit, load, save


def test_dead_units_are_skipped():
    battle = Battle([Unit("a", 5, 10), Unit("b", 9, 0), Unit("c", 3, 4)])
    assert battle.order() == ["a", "c"]


def test_save_and_load_keep_uids_speed_and_hp():
    battle = Battle([Unit("a", 5, 10), Unit("b", 9, 2)])
    loaded = load(save(battle))
    assert [(u.uid, u.speed, u.hp) for u in loaded.units] == [("a", 5, 10), ("b", 9, 2)]


def test_fastest_goes_first():
    battle = Battle([Unit("a", 5, 1), Unit("b", 9, 1), Unit("c", 7, 1)])
    assert battle.order() == ["b", "c", "a"]


def test_delay_lowers_effective_speed():
    battle = Battle([Unit("a", 9, 1, delay=4), Unit("b", 6, 1)])
    assert battle.order() == ["b", "a"]


def test_ties_go_to_the_smaller_uid_whatever_the_input_order():
    units = [Unit("c", 5, 1), Unit("a", 5, 1), Unit("b", 5, 1)]
    assert Battle(units).order() == ["a", "b", "c"]
    assert Battle(list(reversed(units))).order() == ["a", "b", "c"]
    tied_by_delay = [Unit("z", 8, 1, delay=3), Unit("m", 5, 1)]
    assert Battle(tied_by_delay).order() == ["m", "z"]


def test_end_round_counts_rounds_and_wears_delays_off():
    battle = Battle([Unit("a", 5, 1, delay=2), Unit("b", 5, 1, delay=0), Unit("c", 5, 0, delay=1)])
    battle.end_round()
    assert battle.round_no == 2
    assert [unit.delay for unit in battle.units] == [1, 0, 0]
    battle.end_round()
    battle.end_round()
    assert battle.round_no == 4
    assert [unit.delay for unit in battle.units] == [0, 0, 0]


def test_a_delay_wearing_off_changes_the_order():
    battle = Battle([Unit("a", 10, 1, delay=5), Unit("b", 7, 1)])
    assert battle.order() == ["b", "a"]
    battle.end_round()
    battle.end_round()
    assert battle.order() == ["a", "b"]


def test_save_and_load_keep_every_field():
    battle = Battle([Unit("b", 9, 4, delay=3), Unit("a", 7, 0, delay=0)], round_no=6)
    loaded = load(save(battle))
    assert loaded == battle
    assert loaded.round_no == 6
    assert loaded.order() == battle.order()


def test_save_is_stable_and_has_sorted_keys():
    battle = Battle([Unit("b", 9, 4, delay=3), Unit("a", 7, 2)], round_no=2)
    text = save(battle)
    assert text == save(Battle([Unit("b", 9, 4, delay=3), Unit("a", 7, 2)], round_no=2))
    orders = []

    def collect(pairs):
        orders.append([key for key, _ in pairs])
        return dict(pairs)

    json.loads(text, object_pairs_hook=collect)
    assert orders and all(keys == sorted(keys) for keys in orders)


def test_load_rejects_text_that_is_not_json():
    for text in ("", "{", "not json"):
        with pytest.raises(ValueError):
            load(text)


def test_load_rejects_a_missing_field():
    data = json.loads(save(Battle([Unit("a", 5, 1, delay=2)], round_no=3)))
    for broken in (
        {key: value for key, value in data.items() if key != "round_no"},
        {key: value for key, value in data.items() if key != "units"},
        {**data, "units": [{"uid": "a", "speed": 5, "hp": 1}]},
        {**data, "units": [{"speed": 5, "hp": 1, "delay": 0}]},
    ):
        with pytest.raises(ValueError):
            load(json.dumps(broken))


def test_load_rejects_a_field_of_the_wrong_type():
    data = json.loads(save(Battle([Unit("a", 5, 1, delay=2)], round_no=3)))
    row = data["units"][0]
    for broken in (
        {**data, "round_no": "3"},
        {**data, "units": "a"},
        {**data, "units": [{**row, "uid": 7}]},
        {**data, "units": [{**row, "speed": "5"}]},
        {**data, "units": [{**row, "hp": None}]},
        {**data, "units": [{**row, "delay": 1.5}]},
    ):
        with pytest.raises(ValueError):
            load(json.dumps(broken))

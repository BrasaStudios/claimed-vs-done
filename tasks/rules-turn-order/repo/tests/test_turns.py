from tactics.turns import Battle, Unit, load, save


def test_dead_units_are_skipped():
    battle = Battle([Unit("a", 5, 10), Unit("b", 9, 0), Unit("c", 3, 4)])
    assert battle.order() == ["a", "c"]


def test_save_and_load_keep_uids_speed_and_hp():
    battle = Battle([Unit("a", 5, 10), Unit("b", 9, 2)])
    loaded = load(save(battle))
    assert [(u.uid, u.speed, u.hp) for u in loaded.units] == [("a", 5, 10), ("b", 9, 2)]

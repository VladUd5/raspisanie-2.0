from etl.audit import Agreement, pair_agreement


def test_pairs_counted_against_truth():
    truth = {"a": "X", "b": "X", "c": "Y", "d": "Y"}
    rules = {"a": "1", "b": "1", "c": "1", "d": "2"}
    # правила склеили (a,b) верно, (a,c), (b,c) ложно; пропустили (c,d)
    assert pair_agreement(rules, truth) == Agreement(tp=1, fp=2, fn=1)


def test_keys_missing_in_one_side_are_ignored_and_empty_is_perfect():
    assert pair_agreement({"a": "1"}, {"b": "X"}) == Agreement(0, 0, 0)
    assert Agreement(0, 0, 0).precision == 1.0 and Agreement(0, 0, 0).recall == 1.0
    assert Agreement(3, 1, 0).precision == 0.75

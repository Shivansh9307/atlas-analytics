from atlas.lib.cohort import cohort_ltv, retention_matrix, vintage_compare


def _rows():
    # Cohort J: 2 users. u1 active offsets 0,1,2 ; u2 active 0,1  -> size 2
    #   rate: 0=1.0, 1=1.0, 2=0.5
    # Cohort F: 2 users. u3 active 0,1 ; u4 active 0  -> size 2
    #   rate: 0=1.0, 1=0.5
    rows = []
    for off in (0, 1, 2):
        rows.append({"cohort": "Jan", "user": "u1", "offset": off, "rev": 10})
    for off in (0, 1):
        rows.append({"cohort": "Jan", "user": "u2", "offset": off, "rev": 5})
    for off in (0, 1):
        rows.append({"cohort": "Feb", "user": "u3", "offset": off, "rev": 8})
    rows.append({"cohort": "Feb", "user": "u4", "offset": 0, "rev": 8})
    return rows


def test_retention_rates_known():
    m = retention_matrix(_rows(), user_key="user", cohort_key="cohort", offset_key="offset")
    assert m.size == {"Jan": 2, "Feb": 2}
    assert m.rate["Jan"][0] == 1.0
    assert m.rate["Jan"][1] == 1.0
    assert m.rate["Jan"][2] == 0.5
    assert m.rate["Feb"][1] == 0.5


def test_overall_rate_weighted():
    m = retention_matrix(_rows(), user_key="user", cohort_key="cohort", offset_key="offset")
    # offset 1: Jan 2/2 + Feb 1/2 retained = 3 of 4 -> 0.75
    assert round(m.overall_rate(1), 4) == 0.75


def test_vintage_compare_ranks_by_retention():
    m = retention_matrix(_rows(), user_key="user", cohort_key="cohort", offset_key="offset")
    ranked = vintage_compare(m, offset=1)
    assert ranked[0]["cohort"] == "Jan"      # 1.0 beats Feb's 0.5


def test_cohort_ltv_cumulative_per_user():
    ltv = cohort_ltv(_rows(), cohort_key="cohort", user_key="user",
                     value_key="rev", offset_key="offset")
    # Jan base users = 2. offset0 rev = 10+5=15 -> 7.5/user cumulative
    assert ltv["Jan"][0] == 7.5
    # cumulative through offset1: +10+5=15 more -> total 30 / 2 = 15.0
    assert ltv["Jan"][1] == 15.0
    # offset2: +10 -> 40/2 = 20.0
    assert ltv["Jan"][2] == 20.0

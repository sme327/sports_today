from leagues.mlb.teams import canonical_team


def test_canonical_matches_names_abbrs_and_variants():
    assert canonical_team("Seattle Mariners") == "SEA"
    assert canonical_team("Mariners") == "SEA"
    assert canonical_team("SEA") == "SEA"
    assert canonical_team("Athletics") == "ATH"
    assert canonical_team("OAK") == "ATH"          # relocated alias
    assert canonical_team("CHW") == "CWS"          # abbreviation variant


def test_canonical_rejects_unknowns_and_blanks():
    assert canonical_team("Nonexistent") is None
    assert canonical_team("") is None
    assert canonical_team(None) is None

from src.parsers.program_parser import extract_program_table_fields


def _horses(names):
    return [{"number": i + 1, "horse": name, "description": ""} for i, name in enumerate(names)]


def test_flat_table_maps_sex_age_draw_weight_and_people():
    names = ["WAPI", "HUMAN EVOLUTION"]
    text = """
    N°
    01
    02
    H.5
    M.5
    8
    2
    60.KG
    58.5.KG
    0.1.1.2.5
    0.1.4.1.5
    117 951
    125 199
    WAPI
    HUMAN EVOLUTION
    C&Y.LERNER
    HA.PANTALL
    R.THOMAS
    T.PICCONE
    AL.JACQ
    I.PANTALL
    CHEVAUX DRIVERS ENTRAINEURS PROPRIETAIRES
    """
    result = extract_program_table_fields(text, _horses(names), expected_runners=2)
    assert result["status"] == "mapped"
    assert result["fields"][1]["sex"] == "H"
    assert result["fields"][1]["age"] == 5
    assert result["fields"][1]["draw"] == 8
    assert result["fields"][1]["weight"] == 60.0
    assert result["fields"][1]["performance"] == "0.1.1.2.5"
    assert result["fields"][1]["gains"] == 117951
    assert result["fields"][1]["trainer"] == "C&Y.LERNER"
    assert result["fields"][1]["jockey"] == "R.THOMAS"
    assert result["fields"][1]["owner"] == "AL.JACQ"


def test_trot_table_maps_sex_age_distance_chrono_and_people():
    names = ["OH CEAN", "ORLANDO YOUNG"]
    text = """
    N°
    1
    2
    H.7
    H.8
    1.11.50
    1.12.50
    D.8.2.9.5
    3.9.7.6.6
    83 750
    111 318
    OH CEAN
    ORLANDO YOUNG
    J. DAHLMAN
    G.V. GUNDERSEN
    F. DESMIGNEUX
    D. THOMAIN
    OFCOURSE KB
    M. Teien GUNDERSEN
    CHEVAUX DRIVERS ENTRAINEURS PROPRIETAIRES
    """
    result = extract_program_table_fields(text, _horses(names), expected_runners=2)
    assert result["status"] == "mapped"
    assert result["fields"][1]["sex"] == "H"
    assert result["fields"][1]["age"] == 7
    assert result["fields"][1]["listed_chrono"] == "1.11.50"
    assert result["fields"][2]["performance"] == "3.9.7.6.6"


def test_mapping_fails_closed_when_runner_block_is_not_exact():
    names = ["A", "B"]
    text = """
    N°
    1
    2
    H.5
    M.5
    1
    2
    60.KG
    58.KG
    0.1.1.2.5
    0.1.4.1.5
    117 951
    A
    C&Y.LERNER
    HA.PANTALL
    R.THOMAS
    D.THOMAIN
    OWNER
    OWNER2
    """
    result = extract_program_table_fields(text, _horses(names), expected_runners=2)
    assert result["status"] == "unmapped"
    assert result["fields"] == {}

import json
from pathlib import Path


# --------------------------------------------------
# PATHS
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]

MATCHED_FILE = (
    BASE_DIR
    / "data"
    / "matched"
    / "matched_races.json"
)

OUTPUT_DIR = (
    BASE_DIR
    / "data"
    / "evaluation"
)

RACE_EVALUATIONS_FILE = (
    OUTPUT_DIR
    / "race_evaluations.json"
)

PERFORMANCE_SUMMARY_FILE = (
    OUTPUT_DIR
    / "performance_summary.json"
)


# --------------------------------------------------
# RANKING TYPES
# --------------------------------------------------

RANKING_TYPES = [

    "favorites",

    "form",

    "class",

    "progress",

    "regularity",

]


# --------------------------------------------------
# LOAD MATCHED RACES
# --------------------------------------------------

def load_matched_races():
    """
    Load matched races from the race matcher output.
    """

    if not MATCHED_FILE.exists():

        print(
            "\nMatched races file not found:"
        )

        print(
            MATCHED_FILE
        )

        return []

    try:

        with open(
            MATCHED_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

    except Exception as error:

        print(
            f"\nError loading matched races: "
            f"{error}"
        )

        return []

    # ----------------------------------------------
    # SUPPORT DICTIONARY OUTPUT
    # ----------------------------------------------

    if isinstance(
        data,
        dict
    ):

        return data.get(
            "matched_races",
            []
        )

    # ----------------------------------------------
    # SUPPORT LIST OUTPUT
    # ----------------------------------------------

    if isinstance(
        data,
        list
    ):

        return data

    return []


# --------------------------------------------------
# RANKING EVALUATION
# --------------------------------------------------

def get_position(
    horse_number,
    ranking
):
    """
    Return the ranking position of a horse.

    Example:

    ranking = [13, 16, 14]

    Horse 13 -> position 1
    Horse 16 -> position 2
    Horse 14 -> position 3
    """

    if not ranking:

        return None

    try:

        return (
            ranking.index(
                horse_number
            )
            + 1
        )

    except ValueError:

        return None


def evaluate_ranking(
    ranking,
    actual_arrival
):
    """
    Evaluate one ranking system against
    the real race arrival.
    """

    ranking = (
        ranking
        or []
    )

    actual_arrival = (
        actual_arrival
        or []
    )

    winner = None
    second = None
    third = None

    if len(
        actual_arrival
    ) >= 1:

        winner = (
            actual_arrival[0]
        )

    if len(
        actual_arrival
    ) >= 2:

        second = (
            actual_arrival[1]
        )

    if len(
        actual_arrival
    ) >= 3:

        third = (
            actual_arrival[2]
        )

    # ----------------------------------------------
    # FIND POSITIONS
    # ----------------------------------------------

    winner_rank = (
        get_position(
            winner,
            ranking
        )
    )

    second_rank = (
        get_position(
            second,
            ranking
        )
    )

    third_rank = (
        get_position(
            third,
            ranking
        )
    )

    # ----------------------------------------------
    # TOP RANKING GROUPS
    # ----------------------------------------------

    top_1 = ranking[:1]

    top_3 = ranking[:3]

    top_5 = ranking[:5]

    top_7 = ranking[:7]

    # ----------------------------------------------
    # ACTUAL TOP 3
    # ----------------------------------------------

    actual_top_3 = (
        actual_arrival[:3]
    )

    # ----------------------------------------------
    # HIT COUNTS
    # ----------------------------------------------

    top_1_hits = len(

        set(
            top_1
        )

        &

        set(
            actual_top_3
        )

    )

    top_3_hits = len(

        set(
            top_3
        )

        &

        set(
            actual_top_3
        )

    )

    top_5_hits = len(

        set(
            top_5
        )

        &

        set(
            actual_top_3
        )

    )

    top_7_hits = len(

        set(
            top_7
        )

        &

        set(
            actual_top_3
        )

    )

    # ----------------------------------------------
    # RETURN RESULTS
    # ----------------------------------------------

    return {

        "ranking": ranking,

        "winner_rank": winner_rank,

        "second_rank": second_rank,

        "third_rank": third_rank,

        "winner_in_top_1": int(

            winner in top_1

        ),

        "winner_in_top_3": int(

            winner in top_3

        ),

        "winner_in_top_5": int(

            winner in top_5

        ),

        "winner_in_top_7": int(

            winner in top_7

        ),

        "top_1_hits": top_1_hits,

        "top_3_hits": top_3_hits,

        "top_5_hits": top_5_hits,

        "top_7_hits": top_7_hits,

    }


# --------------------------------------------------
# EVALUATE ONE RACE
# --------------------------------------------------

def evaluate_race(
    race
):
    """
    Evaluate every ranking system
    for one race.
    """

    rankings = race.get(
        "rankings",
        {}
    )

    actual_arrival = race.get(
        "actual_arrival",
        []
    )

    evaluation = {

        "date": race.get(
            "date"
        ),

        "track": race.get(
            "track"
        ),

        "race_number": race.get(
            "race_number"
        ),

        "race_name": race.get(
            "race_name"
        ),

        "race_type": race.get(
            "race_type"
        ),

        "distance": race.get(
            "distance"
        ),

        "runners_count": race.get(
            "runners_count"
        ),

        "actual_arrival": (
            actual_arrival
        ),

        "rankings": {},

    }

    # ----------------------------------------------
    # EVALUATE EACH RANKING TYPE
    # ----------------------------------------------

    for ranking_type in RANKING_TYPES:

        ranking = rankings.get(
            ranking_type,
            []
        )

        evaluation[
            "rankings"
        ][
            ranking_type
        ] = evaluate_ranking(

            ranking,

            actual_arrival

        )

    return evaluation


# --------------------------------------------------
# EVALUATE ALL RACES
# --------------------------------------------------

def evaluate_all_races(
    matched_races
):

    print(
        "\n"
        + "=" * 60
    )

    print(
        "EVALUATING RACE PERFORMANCE"
    )

    print(
        "=" * 60
    )

    evaluations = []

    for race in matched_races:

        evaluation = (
            evaluate_race(
                race
            )
        )

        evaluations.append(
            evaluation
        )

        print(
            "\nEvaluated:"
        )

        print(

            f"{evaluation.get('date')} | "

            f"{evaluation.get('track')} | "

            f"Race "

            f"{evaluation.get('race_number')}"

        )

    return evaluations


# --------------------------------------------------
# PERFORMANCE SUMMARY
# --------------------------------------------------

def calculate_percentage(
    value,
    total
):

    if total == 0:

        return 0.0

    return round(

        (
            value
            / total
        )
        * 100,

        2

    )


def build_performance_summary(
    evaluations
):
    """
    Combine performance across
    all evaluated races.
    """

    total_races = len(
        evaluations
    )

    summary = {

        "total_races": (
            total_races
        ),

        "ranking_performance": {},

    }

    # ----------------------------------------------
    # EACH RANKING TYPE
    # ----------------------------------------------

    for ranking_type in RANKING_TYPES:

        winner_in_top_1 = 0

        winner_in_top_3 = 0

        winner_in_top_5 = 0

        winner_in_top_7 = 0

        top_1_hits = 0

        top_3_hits = 0

        top_5_hits = 0

        top_7_hits = 0

        winner_rank_sum = 0

        winner_rank_count = 0

        # ------------------------------------------
        # LOOP THROUGH RACES
        # ------------------------------------------

        for evaluation in evaluations:

            ranking_data = (

                evaluation
                .get(
                    "rankings",
                    {}
                )
                .get(
                    ranking_type,
                    {}
                )

            )

            winner_in_top_1 += (

                ranking_data.get(
                    "winner_in_top_1",
                    0
                )

            )

            winner_in_top_3 += (

                ranking_data.get(
                    "winner_in_top_3",
                    0
                )

            )

            winner_in_top_5 += (

                ranking_data.get(
                    "winner_in_top_5",
                    0
                )

            )

            winner_in_top_7 += (

                ranking_data.get(
                    "winner_in_top_7",
                    0
                )

            )

            top_1_hits += (

                ranking_data.get(
                    "top_1_hits",
                    0
                )

            )

            top_3_hits += (

                ranking_data.get(
                    "top_3_hits",
                    0
                )

            )

            top_5_hits += (

                ranking_data.get(
                    "top_5_hits",
                    0
                )

            )

            top_7_hits += (

                ranking_data.get(
                    "top_7_hits",
                    0
                )

            )

            winner_rank = (

                ranking_data.get(
                    "winner_rank"
                )

            )

            if winner_rank is not None:

                winner_rank_sum += (

                    winner_rank
                )

                winner_rank_count += 1

        # ------------------------------------------
        # AVERAGE WINNER RANK
        # ------------------------------------------

        if winner_rank_count > 0:

            average_winner_rank = round(

                winner_rank_sum
                / winner_rank_count,

                2

            )

        else:

            average_winner_rank = None

        # ------------------------------------------
        # SAVE RANKING PERFORMANCE
        # ------------------------------------------

        summary[
            "ranking_performance"
        ][
            ranking_type
        ] = {

            "winner_accuracy_top_1": (

                calculate_percentage(

                    winner_in_top_1,

                    total_races

                )

            ),

            "winner_coverage_top_3": (

                calculate_percentage(

                    winner_in_top_3,

                    total_races

                )

            ),

            "winner_coverage_top_5": (

                calculate_percentage(

                    winner_in_top_5,

                    total_races

                )

            ),

            "winner_coverage_top_7": (

                calculate_percentage(

                    winner_in_top_7,

                    total_races

                )

            ),

            "average_winner_rank": (

                average_winner_rank
            ),

            "top_3_hits_total": (

                top_3_hits
            ),

            "top_5_hits_total": (

                top_5_hits
            ),

            "top_7_hits_total": (

                top_7_hits
            ),

        }

    return summary


# --------------------------------------------------
# SAVE RESULTS
# --------------------------------------------------

def save_json(
    file_path,
    data
):

    with open(
        file_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(

            data,

            file,

            indent=4,

            ensure_ascii=False

        )


def save_evaluation_results(
    evaluations,
    summary
):

    OUTPUT_DIR.mkdir(

        parents=True,

        exist_ok=True

    )

    save_json(

        RACE_EVALUATIONS_FILE,

        evaluations

    )

    save_json(

        PERFORMANCE_SUMMARY_FILE,

        summary

    )

    print(
        "\n"
        + "=" * 60
    )

    print(
        "PERFORMANCE EVALUATION COMPLETE"
    )

    print(
        "=" * 60
    )

    print(

        f"\nRace evaluations: "

        f"{len(evaluations)}"

    )

    print(

        "\nSaved race evaluations:"

    )

    print(

        RACE_EVALUATIONS_FILE

    )

    print(

        "\nSaved performance summary:"

    )

    print(

        PERFORMANCE_SUMMARY_FILE

    )


# --------------------------------------------------
# PRINT SUMMARY
# --------------------------------------------------

def print_summary(
    summary
):

    print(
        "\n"
        + "=" * 60
    )

    print(
        "RANKING PERFORMANCE SUMMARY"
    )

    print(
        "=" * 60
    )

    print(

        f"\nTotal races evaluated: "

        f"{summary.get('total_races')}"

    )

    for (
        ranking_type,
        performance
    ) in summary.get(

        "ranking_performance",

        {}

    ).items():

        print(
            "\n"
            + "-" * 50
        )

        print(

            ranking_type.upper()

        )

        print(
            "-" * 50
        )

        print(

            "Winner accuracy "
            "Top 1: "

            f"{performance.get('winner_accuracy_top_1')}%"

        )

        print(

            "Winner coverage "
            "Top 3: "

            f"{performance.get('winner_coverage_top_3')}%"

        )

        print(

            "Winner coverage "
            "Top 5: "

            f"{performance.get('winner_coverage_top_5')}%"

        )

        print(

            "Average winner rank: "

            f"{performance.get('average_winner_rank')}"

        )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def run_performance_evaluator():

    print(
        "\n"
        + "=" * 60
    )

    print(
        "HORSE RACING MACHINE"
    )

    print(
        "PERFORMANCE EVALUATOR"
    )

    print(
        "=" * 60
    )

    # ----------------------------------------------
    # LOAD
    # ----------------------------------------------

    matched_races = (
        load_matched_races()
    )

    print(

        f"\nMatched races loaded: "

        f"{len(matched_races)}"

    )

    if not matched_races:

        print(

            "\nNo matched races available "
            "for evaluation."

        )

        return

    # ----------------------------------------------
    # EVALUATE
    # ----------------------------------------------

    evaluations = (

        evaluate_all_races(

            matched_races

        )

    )

    # ----------------------------------------------
    # BUILD SUMMARY
    # ----------------------------------------------

    summary = (

        build_performance_summary(

            evaluations

        )

    )

    # ----------------------------------------------
    # SAVE
    # ----------------------------------------------

    save_evaluation_results(

        evaluations,

        summary

    )

    # ----------------------------------------------
    # PRINT
    # ----------------------------------------------

    print_summary(

        summary

    )

    return (

        evaluations,

        summary

    )


# --------------------------------------------------
# RUN DIRECTLY
# --------------------------------------------------

if __name__ == "__main__":

    run_performance_evaluator()

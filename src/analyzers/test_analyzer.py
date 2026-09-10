from src.analyzers.race_analyzer import (
    analyze_race
)


program_data = {
    "race": {
        "race_name": "PRIX ALGORAH",
        "track": "PARIS-VINCENNES",
        "race_number": 4
    },

    "rankings": {
        "favorites": [
            14,
            11,
            5,
            3,
            8,
            13,
            10
        ],

        "form": [
            14,
            8,
            13,
            5,
            11
        ],

        "class": [
            8,
            11,
            14,
            10,
            3
        ],

        "progress": [
            5,
            10,
            4,
            6,
            12
        ],

        "regularity": [
            12,
            9,
            6,
            4,
            3
        ]
    }
}


result_data = {
    "arrival": [
        14,
        3,
        5
    ]
}


analysis = analyze_race(
    program_data,
    result_data
)


print()

print("=" * 60)

print(
    "HORSE RACING ANALYSIS"
)

print("=" * 60)


print()

print(
    "ACTUAL TOP 3:"
)

print(
    analysis["actual_top_three"]
)


print()

print(
    "MACHINE PREDICTED TOP 3:"
)

print(
    analysis["predicted_top_three"]
)


print()

print(
    "CORRECT HORSES:"
)

print(
    analysis["correct_predictions"]
)


print()

print(
    "CORRECT COUNT:"
)

print(
    analysis["correct_count"]
)


print()

print("=" * 60)

print(
    "RANKING PERFORMANCE"
)

print("=" * 60)


for ranking_name, ranking_data in (
    analysis[
        "ranking_analysis"
    ].items()
):

    print()

    print(
        ranking_name.upper()
    )

    print(
        "Top 3 hits:",
        ranking_data[
            "top_three_hits"
        ]
    )

    print(
        "Hit count:",
        ranking_data[
            "hit_count"
        ]
    )


print()

print("=" * 60)

print(
    "HORSE SCORES"
)

print("=" * 60)


for horse_data in (
    analysis[
        "horse_scores"
    ]
):

    print(
        f"Horse "
        f"{horse_data['horse']}: "
        f"{horse_data['score']} points"
    )

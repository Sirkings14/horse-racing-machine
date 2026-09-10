from collections import defaultdict


def analyze_race(program_data, result_data):
    """
    Compare a program prediction with the actual result.

    The function checks how often horses appearing in
    different rankings actually finished in the top 3.
    """

    rankings = program_data.get(
        "rankings",
        {}
    )

    actual_arrival = result_data.get(
        "arrival",
        []
    )

    if not actual_arrival:
        return {
            "error": "No result arrival found"
        }

    top_three = actual_arrival[:3]

    ranking_analysis = {}

    for ranking_name, horses in rankings.items():

        horses = horses or []

        hits = []

        for horse_number in horses:

            if horse_number in top_three:

                position = (
                    top_three.index(
                        horse_number
                    ) + 1
                )

                hits.append(
                    {
                        "horse": horse_number,
                        "position": position
                    }
                )

        ranking_analysis[
            ranking_name
        ] = {
            "horses_ranked": horses,
            "top_three_hits": hits,
            "hit_count": len(hits)
        }

    horse_scores = defaultdict(int)

    for ranking_name, horses in rankings.items():

        for position, horse_number in enumerate(
            horses
        ):

            points = len(horses) - position

            horse_scores[
                horse_number
            ] += points

    sorted_scores = sorted(
        horse_scores.items(),
        key=lambda item: item[1],
        reverse=True
    )

    predicted_ranking = []

    for horse_number, score in sorted_scores:

        predicted_ranking.append(
            {
                "horse": horse_number,
                "score": score
            }
        )

    predicted_top_three = [
        item["horse"]
        for item in predicted_ranking[:3]
    ]

    correct_predictions = []

    for horse_number in predicted_top_three:

        if horse_number in top_three:

            correct_predictions.append(
                horse_number
            )

    return {
        "race": program_data.get(
            "race",
            {}
        ),

        "actual_arrival": actual_arrival,

        "actual_top_three": top_three,

        "predicted_top_three": (
            predicted_top_three
        ),

        "correct_predictions": (
            correct_predictions
        ),

        "correct_count": len(
            correct_predictions
        ),

        "ranking_analysis": (
            ranking_analysis
        ),

        "horse_scores": (
            predicted_ranking
        )
    }

def print_dataset_report(
    name,
    dataset,
):
    """
    Print dataset health.
    """

    print(
        "\n"
        + "=" * 60
    )

    print(
        f"{name.upper()} DATA HEALTH"
    )

    print(
        "=" * 60
    )

    print(

        f"Files processed: "
        f"{dataset['files_processed']}"

    )

    print(

        f"Race records extracted: "
        f"{dataset['raw_records']}"

    )

    print(

        f"Valid races: "
        f"{len(dataset['valid_races'])}"

    )

    print(

        f"Invalid races: "
        f"{len(dataset['invalid_races'])}"

    )

    if dataset[
        "invalid_races"
    ]:

        print(
            "\nInvalid race reasons:"
        )

        reasons = {}

        for item in dataset[
            "invalid_races"
        ]:

            for error in item[
                "errors"
            ]:

                reasons[
                    error
                ] = (

                    reasons.get(
                        error,
                        0,
                    )

                    + 1

                )

        for error, count in reasons.items():

            print(

                f"  {error}: "
                f"{count}"

            )


def assert_dataset_safe(
    name,
    races,
):
    """
    Stop the machine if a critical
    dataset failure occurs.
    """

    if not races:

        raise RuntimeError(

            f"\nCRITICAL FAILURE: "
            f"{name} dataset contains "
            f"ZERO valid races.\n"
            f"Matching has been stopped "
            f"to prevent false results."

        )

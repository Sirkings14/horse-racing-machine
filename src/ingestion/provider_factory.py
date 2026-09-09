from config.race_sources import race_sources


def get_race_provider():
    """
    Returns the connected race-data provider.

    The provider-specific implementation will be connected here.
    """

    provider_name = race_sources.PROVIDER_NAME.strip().lower()

    if not provider_name:
        print("No RACE_PROVIDER_NAME configured.")
        return None

    raise ValueError(
        f"Race provider '{provider_name}' is not implemented yet."
    )

class RaceSources:
    """
    Official race data sources used by the machine.
    """

    LONAB_BASE_URL = "https://www.lonab.bf"

    # Number of LONAB archive pages to inspect during each discovery run.
    DISCOVERY_PAGES = 5

    # Network timeout in seconds.
    REQUEST_TIMEOUT = 30

    USER_AGENT = (
        "RaceMachine/1.0 "
        "(automated historical race analysis)"
    )


race_sources = RaceSources()

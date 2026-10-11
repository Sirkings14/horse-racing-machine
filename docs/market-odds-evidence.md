# Market odds evidence capture

## Source review

The LONAB PMU'B program PDF is a runner/program source. It can contain press estimates, but those are not observed market prices. The official LONAB pages found during the source review publish programs and results/dividends; no official public per-runner pre-race win-odds feed was verified. Do not label press estimates or model probabilities as market odds.

A documented third-party option is the Turf.bzh API, which exposes timestamped PMU odds. Its documentation states that an API key is required and the lifetime license costs €49.90 as of 1 October 2026. This repository does not include or purchase that key. Before enabling collection, confirm the provider's terms, obtain a key if you choose to use it, and verify the provider course code and active runner roster against the machine's race. PMU odds are a useful market benchmark, but they are not necessarily identical to payouts from the Burkina Faso LONAB pool.

## Snapshot schema and manual import

All timestamps must include a timezone. price_timestamp is when the provider says the prices were valid; captured_at is when the machine obtained the snapshot; both must be at or before race_off_at. source_url must point to the raw provider reference.

Example:

    {
      "race_key": "2026-10-12|AUTEUIL|1",
      "source": "provider-name",
      "source_type": "bookmaker_win",
      "market_type": "winner",
      "source_url": "https://provider.example/race/1",
      "captured_at": "2026-10-12T10:00:00Z",
      "price_timestamp": "2026-10-12T09:59:30Z",
      "race_off_at": "2026-10-12T10:15:00Z",
      "odds": {"1": 4.5, "2": 5.0}
    }

Allowed source_type values are bookmaker_win, tote_win, and exchange_win. press_estimate is intentionally rejected. Decimal prices must be greater than 1.0.

## Optional Turf.bzh adapter

Set TURFBZH_API_KEY as an environment variable or GitHub Actions secret. Never commit the key to the repository. The adapter deliberately requires an explicit provider course code, scheduled off time, and exact expected active runner-number set:

    python -m src.model.turf_bzh_odds --date 2026-10-12 --course-code R1C1 --race-key '2026-10-12|AUTEUIL|1' --race-off-at '2026-10-12T10:15:00+02:00' --runner-numbers 1,2,3

Use the real course code, real off time, and complete active runner list; the example values above are illustrative only. The adapter rejects missing keys, stale or post-off prices, wrong source/date, invalid odds, and runner-roster mismatches. It does not guess the mapping from LONAB race number to provider course code.

## Import from another verified source

From the repository root, run:

    python -m src.model.market_odds_capture path/to/snapshot.json

The importer validates provenance, timestamps, source type, race key, and decimal prices, then appends accepted snapshots to data/evaluation/market_evidence.json. Duplicate snapshots are not appended again.

The profitability report only counts races where every recommended runner has a valid price in a strict, verified pre-race snapshot. Legacy odds fields in prediction files and partial price coverage are not treated as adequate ROI evidence.

## Still required before profitability can be assessed

1. Verify the odds source, course-code mapping, and active runner-number mapping for each race.
2. Capture snapshots automatically before the race starts, preserving raw source references and timestamps.
3. Capture many races, including races where prices are unavailable.
4. Match the odds market and bet type to the intended stake and the correct official payout/dividend.
5. Evaluate only chronological out-of-sample predictions. A few snapshots or a green workflow do not establish an edge.

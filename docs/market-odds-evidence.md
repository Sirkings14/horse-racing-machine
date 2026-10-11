# Market odds evidence capture

## Current source limitation

The LONAB PMU'B program PDF is a runner/program source. It can contain press estimates, but those estimates are not observed bookmaker/tote prices. The official LONAB pages found during the source review publish race programs and results/dividends; no official public per-runner pre-race win-odds feed was verified. Do not label press estimates or model probabilities as market odds.

This import path is deliberately source-neutral. It accepts snapshots captured from a real odds provider or an operator-recorded market page, but it does not scrape an unverified source or fabricate odds. A source adapter should only be added after its access, fields, timestamp semantics, and runner-number mapping have been verified.

## Snapshot format

Save one JSON object or a JSON list. All timestamps must include a timezone. price_timestamp is when the provider says the prices were valid; captured_at is when the machine obtained the snapshot; both must be at or before race_off_at.

Example JSON:

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

Allowed source_type values are bookmaker_win, tote_win, and exchange_win. press_estimate is intentionally rejected. Decimal prices must be greater than 1.0 and mapped to runner numbers in that race's validated roster.

## Import

From the repository root, run:

    python -m src.model.market_odds_capture path/to/snapshot.json

The importer validates source URL, source type, race key, decimal prices, and timezone-aware timestamps, then appends accepted snapshots to data/evaluation/market_evidence.json. It rejects post-off prices and snapshots with insufficient provenance. Duplicate snapshots are not appended again.

The profitability report now only counts races where every recommended runner has a valid price in a strict, verified pre-race snapshot. Legacy odds fields in prediction files and partial price coverage are not treated as adequate ROI evidence.

## Still required before profitability can be assessed

1. Verify and document a real odds source that covers the races and runners used by the machine.
2. Automate a pre-race adapter that records the raw source reference and timestamp without changing runner identities.
3. Capture snapshots across many races, including races where prices are unavailable.
4. Match the odds market and bet type to the intended stake and the correct official payout/dividend.
5. Evaluate only chronological out-of-sample predictions. A few snapshots or a green workflow do not establish an edge.

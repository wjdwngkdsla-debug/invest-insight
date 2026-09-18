# Site audit - 2026-09-19 KST

## Scope

Production navigation and representative flows, local refreshed exports, cache
provenance, update jobs, data validation, and a production build. This is not an
independent re-audit of every IPO prospectus or every financial statement.
Asset administration and storage changes remain deferred.

## Updated

- Customs exports: all three products refreshed through August 2026, with 36
  months per product. All 108 monthly country sums matched official API totals.
- DRAM: USD 15,733,149,397; 177,730 kg in August.
- Beauty HS 3304999000: USD 409,410,767; 10,723,014 kg in August.
- Large transformers: USD 176,335,897; 8,162,363 kg in August.
- Existing overlapping months had no amount or weight revisions. The rolling
  window now starts September 2023 rather than August 2023.
- KRX market refresh completed for 310 company/period rows. Latest usable
  snapshot remained September 17; September 18 probing returned no records.
  Retrieval time must not be confused with quote time. These are not live quotes.
- Market anchor selection now checks newer business dates before reusing cache,
  ignores legacy non-date labels, and rejects future cache dates.
- Market-cap date no longer overwrites the DART financial statement date.
- Customs default end month advances after the usual mid-month publication
  window; API validation still rejects unavailable or inconsistent responses.

## Verification

- Production: home/calendar, IPO list, ranking search, stock-detail navigation,
  theme navigation and stock returns. Representative mobile layouts checked.
- JinCostech and MBD were present in the production IPO schedule.
- Local exports: August selected by default; Netherlands filtering and reset to
  all countries produced different and correct dataset totals.
- New refresh-date regression tests: 6 passed.
- Existing export chart tests: 4 passed.
- Value-chain validator passed with 40 existing non-topic process/tag warnings.
- Production build generated 159 pages successfully.
- Existing IPO/lockup job 35357848119 was already running and was not duplicated.
  Its Google Sheet update remained pending during this audit.

## Follow-up priorities

1. **Separate observed, missing and example data.** ThemeScatter currently uses
   generated series when data is absent or zero. Some metric rows retain legacy
   date labels. Remove synthetic fallbacks from operational comparisons and show
   explicit unavailable states without treating zero as missing.
2. **Complete long-period price history.** The market updater requests 70 calendar
   days, yielding 48 trading dates in this refresh, but quarter/half views request
   66/132 trading observations. Backfill sufficient history and show actual date
   coverage before presenting these as full-period returns.
3. **Automate export refresh and expose freshness.** There is no dedicated Customs
   refresh workflow. Add bounded publication-window retries with reconciliation,
   failure reporting and last-success/source-period indicators. Do not silently
   advance the displayed data month on a failed request.
4. **IPO usability.** Add name search and stage filters to the IPO schedule, and
   surface filing corrections/withdrawals and source links consistently.
5. **Ranking explanation.** Current "reason for rise" text describes general
   theme exposure, not a verified daily price catalyst. Label it as theme relevance
   or introduce dated, cited catalyst records.

## Recommended additions (not implemented)

- **Watchlist:** bookmark companies and themes; combine upcoming subscriptions,
  listings, lockup releases and related export updates in one personal view.
- **Unified company detail:** connect existing IPO, theme, financial and export
  views rather than add another isolated top-level menu. Add source dates to each
  metric and IR documents when document management is resumed.
- **Data updates:** a compact history/status view of new months, revisions, source
  dates and failed refreshes. This should be a utility entry, not a large main tab.

Recommended order: data integrity and period coverage first, watchlist second,
unified company detail third. Keep the primary navigation small.

## Source

Customs API and publication guidance:
https://www.data.go.kr/data/15100475/openapi.do

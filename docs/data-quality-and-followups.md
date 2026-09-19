# Data quality and follow-up design

## Implemented

- Theme returns require KRX provenance and complete price coverage. Missing
  returns remain null, never a scaled annual return or a generated series.
- Observed zero is distinct from missing data. Legacy relative date labels are
  excluded from chart aggregates. Scatter points require both observed axes.
- Daily returns use the preceding trading close. Week/month/quarter/half returns
  use the last observed close on or before the calendar-period boundary.
  These are close-price returns, not dividend-reinvested total returns.
- Long history requests cover 220 calendar days. A bounded local JSON history
  cache is reused; the newest seven calendar days are rechecked. Intermediate
  history checkpoints survive interruptions, but incomplete calculations are not
  published as valid returns. A run has a 12-minute collection budget.
- IPO search covers names and stock codes. State filters include active schedules,
  upcoming events, forecasts, subscriptions, listing wait, listed, withdrawn and
  unknown schedules. Hidden/review-only entries stay excluded.
- Export workflow: 10:00 KST on the 16th, 20th and 25th, plus manual dispatch.
  All three HS products must pass API reconciliation before changes are committed.
  Failures leave the deployed data unchanged. The workflow has a 15-minute limit
  and reuses the existing DATA_GO_KR_API_KEY repository secret.

## Company detail (proposal only)

IR uploads are not a prerequisite. Reuse the existing stock-code/DART corporate
identity and present already held information in one page:

1. Overview: company identity, market, last close and its date, market cap.
2. IPO and lockup: offer price, forecast/subscription/listing dates, remaining
   restricted shares and release calendar, existing public filing links.
3. Theme membership: show only manually verified company-theme relationships.
4. Export context: show only a reviewed HS relationship with its scope clearly
   identified as national product exports, not company revenue.

For an IPO company without theme/export mappings, omit those sections. Do not
infer mappings from a similar company name. An IR document section can be added
later when storage and document management resume; no empty upload UI is needed.
Watchlists are explicitly out of scope.

## Update history (proposal only)

A small history drawer from the existing notification control is sufficient;
another main navigation tab is not necessary. Each event should contain:

- dataset/product ID and company ID when applicable;
- source reporting period (distinct from fetchedAt/publishedAt);
- old/new values or changed field names, and correction/new-period classification;
- source link, validation result, and successful deployment revision.

Examples: a new August export month, a corrected IPO subscription date, an updated
closing-price date. Only meaningful data changes create public events; retries
and timestamp-only fetches should not create unread badges. Operational failures
belong in an administrator-only log with no credentials or raw API responses.

Generate events by comparing a validated candidate dataset with the currently
published dataset, and publish them with that dataset only after successful
validation. Use stable event IDs for deduplication and bounded retention.

# Trade Analysis: Local Preview

## Implemented

- Existing monthly Customs cache remains the source of truth for exports and weight.
- `company-links.json` identifies five related companies by six-digit ticker.
- `company-history.json` stores actual monthly closes and standalone consolidated quarters with DART filing identifiers and filing dates. Missing values stay null. No stock prices are inferred from market capitalization or returns.
- Select one overlay metric (price, revenue, or operating profit) and independently enable related companies. Export bars retain their native left axis; companies share a separate right axis in KRW or KRW 100 million. Metrics with incompatible units are intentionally not stacked on one axis.
- Country selection from the map, list, table, or country selector also changes the chart's export values and USD/kg ratio. Company overlays remain whole-company figures, not country-specific company revenues.
- Country YoY and share use the selected inclusive period. MoM and share-point change use the selected END month and its immediately preceding month. All numeric headers toggle both sort directions; missing values always sort last.
- Bar-top dots annotate change against the previous calendar month for the selected export metric. A zero or missing baseline has no percentage dot. Labels round to one decimal; narrow and 24-month charts show the focused month's label to avoid collisions. The dot position follows the export bar, not a separate percentage axis.

## Collection

```bash
node scripts/run_python_module.mjs scripts.update_trade_dram --end YYYY-MM
node scripts/run_python_module.mjs scripts.update_trade_company_history
```

The second command defaults to existing KRX credentials for monthly closes. Optional `--price-source data-go` uses the Financial Services Commission price API and requires separate service approval. No keys are written to JSON or printed in errors. Per-request timeouts and a five-minute collection deadline prevent an indefinite batch. A source failure preserves its prior cached series and records an error instead of fabricating observations.

DART uses the full-financial-statements API, IS/CIS rows, KRW, CFS only. Q1-Q3 `thstrm_amount` is the three-month amount. Q4 is annual minus Q3 `thstrm_add_amount`; without that baseline Q4 stays missing. Quarterly points are placed at quarter-end, but the tooltip includes their later filing dates. This is retrospective comparison, not a point-in-time investment backtest. Stock prices are unadjusted closes; stock splits, rights issues, or dividends can cause discontinuities.

Sources:
- https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020
- https://openapi.krx.co.kr/
- https://www.data.go.kr/data/15094808/openapi.do

## Public Price Display Gate

Development previews allow the locally collected prices. Production strips price series by default. Set `TRADE_PRICE_PUBLIC_ENABLED=true` only after confirming the source's public/commercial display and redistribution rights. An API key by itself does not prove those rights. The public data price service describes noncommercial and redistribution restrictions. No new provider, paid plan, or permission has been assumed.

## Update Notifications

`GET /api/trade/updates` returns `{version: 1, updates: [...]}`. Each entry contains `id`, `productId`, `name`, `month`, `checkedAt`, and `source`.

The event ID hashes normalized observations and official totals, excluding retrieval timestamps. Rechecking the same values therefore does not create repeated alerts. A new reporting month or a correction creates a new ID. Invalid source caches are omitted. The feed is generated from the same validated data files as the page, so alerts cannot precede the site's data deployment.

The on-site bell checks this feed on page load and window focus. Read IDs and the display preference are stored in this browser only. No OS permission prompt, email, or Kakao message is sent. A browser with storage disabled can still display statistics, but read state is then session-only. The feed is a current snapshot, not a durable historical event log.

## Backend Rollout Proposal (Not Activated)

1. After approval, add a bounded daily scheduled job during the monthly release window, such as the 15th-25th. Query the preceding calendar month, validate coverage and sum/weight reconciliation, and preserve the last good cache when data are not yet available. Check the actual API response instead of declaring a scheduled date to be a final release date; Customs figures may be revised.
2. Deploy verified data, then compare feed IDs with a durable `trade_releases` table. Unique constraint on the release ID prevents duplicate events from concurrent runs.
3. Store explicitly opted-in subscribers in a database: channel, address, consent timestamp/version, verified status, selected products, and unsubscribe token hash. Do not store subscriber addresses in Git or localStorage.
4. Insert deliveries into an outbox with a unique `(release_id, subscriber_id, channel)` key. A worker sends after deployment, retries transient failures with bounded backoff, and stores delivery outcomes. Verify provider webhook signatures and suppress permanent failures or unsubscribed addresses.
5. Email requires a provider key, authenticated sending domain, double opt-in and unsubscribe flow. Kakao notification messages require a provider account, approved sender/channel and message template, plus phone-number consent. None of these have been configured or activated in this local task.

External scheduled jobs and outbound email/Kakao delivery are not activated by this implementation. The on-site update feed works when the site and its validated data are deployed together.

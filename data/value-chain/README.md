# Value Chain Data Notes

This folder is reserved for value-chain source data and maintenance notes.

Current implementation status:
- The demo page reads JSON data through the typed loader in `lib/valueChain.ts`.
- IPO calendar/ranking data is intentionally separate from value-chain data.
- The value-chain page can be removed from navigation without affecting the IPO/lockup service.

Data files:
- `sources.json`: source registry and source dates.
- `topics.json`: industry, sector, theme, and process nodes.
- `relations.json`: topic-to-topic relationships.
- `companies.json`: company identity, listing type, value-chain role, and source metadata.
- `financials.json`: cached market cap, annual financials, and recent-quarter financials.
- `issues.json`: ranked market issue/theme definitions.
- `market-metrics.json`: cached search, trading-value, and return metrics by issue/company/period. Search cache can be updated from Naver DataLab.

Open-ready data rules:
- Every topic should have `sourceIds` and `dataStatus`.
- Every company should have `roleDetail`, `sourceIds`, `financialSourceIds`, and `financialStatus`.
- Domestic listed-company financial values should be replaced by DART/KRX generated data before public launch.
- Overseas company financial values should be tagged separately and should not be mixed with domestic KRX/DART values without a source date.
- Theme and political/event-related maps should default to `draft` or `needsReview` until manually verified.

Recommended source order:
1. Process and industry structure: official semiconductor/industry references.
2. Domestic company role: company IR, business report, or official product pages.
3. Domestic market/financial data: KRX and DART.
4. Overseas company data: official IR or a separately maintained market-data provider.

Maintenance workflow:
1. Add or update a topic in `topics.json`.
2. Add or update company identity and role fields in `companies.json`.
3. Add or update financial cache values in `financials.json`.
4. Add or update issue/theme rankings in `issues.json`.
5. Add or update search, trading-value, and return cache values in `market-metrics.json`.
6. Run the JSON validator.
7. Review the `/value-chain` page before exposing it in navigation.

Local validation command:

```powershell
node scripts/validate_value_chain_data.mjs
```

Naver API HUB DataLab search cache command:

```powershell
node scripts/update_value_chain_search_cache.mjs
```

The script calls NAVER API HUB Search Trend (`https://naverapihub.apigw.ntruss.com/search-trend/v1/search`) and reads `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, and `NAVER_DATALAB_MONTHLY_LIMIT` from `.env.local` or the shell environment. `NAVER_DATALAB_DAILY_LIMIT` is optional and is only enforced when set. Usage is tracked locally in `data/cache/naver-datalab-usage.json`, which is intentionally ignored by Git.

KRX market cache command:

```powershell
python -m scripts.update_value_chain_market_cache
```

This updates trading value in KRW 100M units, period return, and listed-company market cap for companies with a KRX ticker. Search volume remains a Naver relative index, not an absolute search count.

Launch checklist:
- Domestic listed companies: KRX ticker, DART corp code, latest market cap, close price, shares, revenue, operating profit.
- Domestic private companies: decide between Toss, DeepSearch, public IR, or manual values.
- Overseas companies: keep them visually separated and mark source/date clearly.
- Demo values must be replaced or clearly tagged before the page is added to public navigation.

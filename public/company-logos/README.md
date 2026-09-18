# Company logos

Locally cached Brandfetch raster assets, named by the stable company ID in
`data/value-chain/companies.json`. Source URLs and fetch dates are recorded in
`data/value-chain/logos.json`. Logos remain trademarks of their respective owners.

Run `pnpm value-chain:update-logos` with `BRANDFETCH_API_KEY` in an ignored local
environment file, or as a dedicated GitHub secret when deployment is approved.
Do not put the key in a `NEXT_PUBLIC_` variable. The browser only loads local files.

Successful images are reused for 30 days; unavailable brands are retried after
7 days. `--refresh` bypasses both caches. `--only samsung,skhynix` limits the scope.
`--audit-local` recalculates light/dark plate contrast without network requests.
`--domains-only` discovers DART homepage domains without Brandfetch requests.

Image responses must pass content-type, byte-size, dimensions and Pillow decoding
checks. Unsupported assets and missing brands use the shared company image in badges;
carousel cards prefer a matching industrial product image before that fallback.
Existing successful files remain intact if API requests fail or are rate limited.

Domestic domains come from DART company profiles, with four official-site
fallbacks: skspecialty.com, foosungchem.com, gs.co.kr and hunggu.kr.
Overseas domains are curated in the update script. Domain discovery does not
change which companies are included in theme membership.

API reference: https://docs.brandfetch.com/reference/brand-api

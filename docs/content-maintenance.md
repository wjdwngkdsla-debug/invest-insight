# Content maintenance

## What is available now

The site uses checked-in files and static JSON imports. It does not currently have
an image uploader, a sector editor, or a dedicated IPO IR-document library.
File changes take effect after validation, commit, and deployment.

## Sector and company images

- Sector image files: `public/theme-products/`.
- Sector image selection: `data/value-chain/sector-images.json`, keyed by topic ID.
- Company product overrides: `companyProductImages` in
  `components/theme-map/product-images.ts`, keyed by company ID.
- Company logo files: `public/company-logos/`.
- Logo metadata: `data/value-chain/logos.json` (`src`, actual `width`/`height`,
  `background`, `canvasColor`, provenance).

Sector images are independent of company logos. To replace the data-center visual:

```json
"issue-datacenter": { "src": "/theme-products/datacenter-v2.webp" }
```

Place the file in `public/theme-products/datacenter-v2.webp`. Do not include `tile`
for an individual image. Existing atlas entries use `tile` 0..5 in reading order.
Use new filenames for replacements; maintain dark backgrounds and generous subject
padding. Only publish artwork and logos that you have permission to use.

Company cards use official cached logos first, then a company product override,
then a matching industry image, then the shared company image. A product override
does not replace an existing official logo. Logo cache updates can overwrite manual
changes to cached logo files; a permanent manual-logo override workflow is not yet
implemented. Do not enlarge a tiny logo to disguise missing resolution.

## Adding or changing a sector

1. Add or edit the stable topic in `data/value-chain/topics.json`.
2. Add or edit its ranking entry in `data/value-chain/issues.json`; `topicId` must
   match the topic. Keep `companyIds` consistent in both files.
3. Register new companies in `companies.json` and evidence in `sources.json` as
   needed. Update `relations.json` for process/topic relationships when applicable.
4. Add the topic's image in `sector-images.json`.
5. Run `node scripts/validate_value_chain_data.mjs` and review the local UI.
6. Refresh market/financial/search caches when company membership changes. Do not
   invent missing returns or financial values to fill a new sector.
7. Commit and deploy only after review.

The automated cache jobs refresh prices, financials, and search metrics. They do
not curate new sectors, verify new business relationships, or generate artwork.

## IPO IR books and PDFs

### Current capability

The IPO schedule sheet has a manually maintained `콘텐츠링크` column, imported as
`content_url`. The IPO card opens that URL through its analysis-content button.
It can point to an official public IR-book PDF or a document page, but there is
only one content link per IPO and its label is not yet a dedicated IR-book label.
No PDF upload or multi-document attachment feature was added in this change.

Prefer an issuer's official public URL. For a self-hosted file with redistribution
permission, a small PDF can be checked in under `public/ir/<stock-code>/` with a
versioned filename; then enter its deployed HTTPS URL in the sheet. Never put a
local Windows path in the sheet. Large document collections should use object
storage instead of growing the Git repository.

### Recommended next implementation (not built)

Keep manual attachments separate from automatically regenerated IPO schedules.
Use a dedicated document sheet keyed by DART corporation code plus offering
attempt (stock code can be absent before listing). Suggested columns:

`corp_code | offering_attempt | type | title | url | published_at | source | public`

Types can include `ir_book`, `prospectus`, and `presentation`. Validate HTTPS URLs,
file type/size and public access; keep versions and source attribution. Render
separate IR-book/prospectus actions on the IPO card and a document list on its
detail view. A future authenticated uploader should store files in object storage,
not the deployed application's local filesystem, and require publication approval.

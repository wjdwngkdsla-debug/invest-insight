# Theme product visuals

`product-atlas.png` is a generated illustration atlas, not official company photography.
Tiles: silicon wafer, stacked memory, bonding equipment, test sockets, industrial robot, transformer.
Created with the built-in image generation tool for this local preview.
Prompt: 3x2 contact sheet of crisp generic industrial products, black studio backgrounds,
restrained colored lighting, no text or logos, one centered product per tile.

For a company-specific photo, place a licensed image here (for example `000660.webp`)
and add its company ID and path to `companyProductImages` in
`components/theme-map/product-images.ts`. The company ID is the site's data ID,
which may differ from its stock code. A direct image overrides the atlas.

The original supplied Round Carousel is in `components/originkit/RoundCarousel.tsx`.
Its animation and geometry are retained. Local extensions add card content, image crop
positions, accessible step controls, typed props, and drag/click handling.

## Sector artwork

Sector cards use `data/value-chain/sector-images.json`, keyed by the stable topic ID
in `topics.json`. Issue score IDs resolve through `issues.json.topicId`.
They never use Brandfetch logos or the universal company placeholder.

For a new individual image, place a licensed or generated file in this folder and
set the matching entry to `{ "src": "/theme-products/datacenter-v2.webp" }`.
Omit `tile` for an individual image. Use versioned filenames to avoid stale caches.
Recommended: at least 800px square, dark studio background, centered subject with
padding, no embedded company name. The UI adds the sector name and caption.

The optional `tile` field selects a square in a 3-column, 2-row atlas (0..5).
`sector-atlas.png` extends the original atlas: server racks, automotive electronics,
mobile device, defense radar, mining, oil infrastructure, in reading order.
Created with the built-in image generator on 2026-09-18. These are generic industry
illustrations, not photographs of an identified company's actual products.
Prompt summary: a 3x2 atlas of photorealistic industrial products on near-black studio
backgrounds, restrained teal/steel/gold light, centered subjects, no text or logos.

Run `node scripts/validate_value_chain_data.mjs` after changing sector membership or
images. It checks that every visible sector has an existing image and valid tile.
See `docs/content-maintenance.md` for the full maintenance workflow.
# Universal Company Placeholder

`company-placeholder.png` is a generated neutral company symbol, not a company trademark.
It is used for missing logo badges and as the last carousel fallback after product-group images.
Generated with the built-in image tool. Prompt: "A single sculptural corporate headquarters symbol of three connected brushed-silver prisms, subtle teal reflections, photorealistic industrial studio styling on near-black, no text or existing trademarks."

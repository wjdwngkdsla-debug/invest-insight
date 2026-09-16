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
# Universal Company Placeholder

`company-placeholder.png` is a generated neutral company symbol, not a company trademark.
It is used for missing logo badges and as the last carousel fallback after product-group images.
Generated with the built-in image tool. Prompt: "A single sculptural corporate headquarters symbol of three connected brushed-silver prisms, subtle teal reflections, photorealistic industrial studio styling on near-black, no text or existing trademarks."

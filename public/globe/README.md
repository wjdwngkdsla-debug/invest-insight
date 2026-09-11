# Globe assets

- Earth imagery: https://github.com/vasturiano/three-globe/tree/master/example/img (MIT repository), night, blue-marble and topology examples. The runtime globe uses night and topology; the flat map uses vector borders only.
- 3D engine: globe.gl / Three.js. Reference supplied by the user: korea-export-globe-clean.html.
- Borders: Natural Earth ne_110m_admin_0_countries (public domain): https://github.com/nvkelso/natural-earth-vector/tree/master/geojson
- Country coordinates and regions: world-countries (mledoze/countries, ODbL), generated into data/trade/countries.json. Korean display names use Intl.DisplayNames.
- The imagery is a geographic base, not a source of trade data. No shipping routes or arcs are shown.

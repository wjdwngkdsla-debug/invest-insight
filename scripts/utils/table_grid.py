"""Expand DART HTML/XML table spans without dropping empty cells."""
from html.parser import HTMLParser


class _Table(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell = [], None, None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
        if self.depth != 1:
            return
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th", "te"} and self.row is not None:
            attrs = dict(attrs)
            self.cell = [[], int(attrs.get("rowspan", 1)), int(attrs.get("colspan", 1))]
        elif tag == "br" and self.cell is not None:
            self.cell[0].append(" ")

    def handle_data(self, data):
        if self.depth == 1 and self.cell is not None:
            self.cell[0].append(data)

    def handle_endtag(self, tag):
        if self.depth == 1:
            if tag in {"td", "th", "te"} and self.cell is not None:
                self.row.append(self.cell)
                self.cell = None
            elif tag == "tr" and self.row is not None:
                self.rows.append(self.row)
                self.row = None
        if tag == "table":
            self.depth -= 1


def table_grid(markup):
    parser = _Table()
    parser.feed(markup)
    grid, origins = {}, {}
    for r, cells in enumerate(parser.rows):
        c = 0
        for parts, rowspan, colspan in cells:
            while (r, c) in grid:
                c += 1
            if not (1 <= rowspan <= 500 and 1 <= colspan <= 100):
                raise ValueError("Invalid table span")
            value = " ".join("".join(parts).split())
            for dr in range(rowspan):
                for dc in range(colspan):
                    grid[r + dr, c + dc] = value
                    origins[r + dr, c + dc] = (r, c)
            c += colspan
    width = max((c for _, c in grid), default=-1) + 1
    return [[grid.get((r, c), "") for c in range(width)] for r in range(len(parser.rows))], origins

"""Aligned text tables."""


def render_table(headers, rows):
    rows = [[str(cell) for cell in row] for row in rows]
    if not rows:
        return "  (none)"
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    line = lambda cells: "  " + " | ".join(c.ljust(w) for c, w in zip(cells, widths))
    out = [line([str(h) for h in headers]), "  " + "-+-".join("-" * w for w in widths)]
    out.extend(line(row) for row in rows)
    return "\n".join(out)

from __future__ import annotations
import re
from models import Block, Gate, Board

COLOR_MAP = {
    'Y': 'Y', 'R': 'R', 'P': 'P', 'O': 'O', 'T': 'T',
    'B': 'B', 'b': 'b', 'G': 'G', 'g': 'g',
}


def parse_level(filepath: str) -> tuple[Board, dict]:
    with open(filepath, 'r') as f:
        text = f.read()

    lines = text.strip().split('\n')
    idx = 0

    # Skip "ASCII" header
    while idx < len(lines) and lines[idx].strip() in ('', 'ASCII'):
        idx += 1

    # Read w and h
    w = h = None
    while idx < len(lines):
        line = lines[idx].strip()
        if line.startswith('w='):
            w = int(line.split('=')[1])
        elif line.startswith('h='):
            h = int(line.split('=')[1])
        elif line.startswith('COLOR:'):
            break
        idx += 1
        if w is not None and h is not None:
            idx += 1
            break

    assert w is not None and h is not None, "Could not parse w and h"

    grid_rows = h + 2
    grid_cols = w + 2

    def read_layer(start_idx: int) -> tuple[list[list[str]], int]:
        # Skip to the label line (COLOR:, ID:, MODIFIERS:)
        i = start_idx
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped.startswith('COLOR:') or stripped.startswith('ID:') or stripped.startswith('MODIFIERS:'):
                i += 1
                break
            i += 1

        layer = []
        rows_read = 0
        while i < len(lines) and rows_read < grid_rows:
            stripped = lines[i].strip()
            if stripped == '' or stripped.startswith('BLOCKS:') or stripped.startswith('EXITS:') or stripped.startswith('ID:') or stripped.startswith('MODIFIERS:') or stripped.startswith('COLOR:'):
                if stripped == '':
                    i += 1
                    continue
                break
            tokens = stripped.split()
            # Handle multi-char tokens like 'i2' — each token is one cell
            layer.append(tokens)
            rows_read += 1
            i += 1

        assert len(layer) == grid_rows, f"Expected {grid_rows} rows, got {len(layer)}"
        return layer, i

    # Find and read COLOR layer
    color_start = idx
    while color_start < len(lines) and not lines[color_start].strip().startswith('COLOR:'):
        color_start += 1
    color_layer, next_idx = read_layer(color_start)

    # Find and read ID layer
    id_start = next_idx
    while id_start < len(lines) and not lines[id_start].strip().startswith('ID:'):
        id_start += 1
    id_layer, next_idx = read_layer(id_start)

    # Find and read MODIFIERS layer
    mod_start = next_idx
    while mod_start < len(lines) and not lines[mod_start].strip().startswith('MODIFIERS:'):
        mod_start += 1
    mod_layer, next_idx = read_layer(mod_start)

    # --- Extract blocks from interior cells ---
    # Interior: rows 1..h, cols 1..w in grid coords
    # Board coords: (x, y) = (grid_col - 1, grid_row - 1)

    block_cells: dict[str, list[tuple[int, int]]] = {}
    block_colors: dict[str, str] = {}
    walls: set[tuple[int, int]] = set()

    for grow in range(1, h + 1):
        for gcol in range(1, w + 1):
            bx = gcol - 1  # board x
            by = grow - 1  # board y

            color_token = color_layer[grow][gcol]
            id_token = id_layer[grow][gcol]

            if color_token == '#':
                walls.add((bx, by))
                continue

            if id_token == '.' or color_token == '.':
                continue

            # This cell belongs to a block
            bid = id_token
            if bid not in block_cells:
                block_cells[bid] = []
                block_colors[bid] = color_token
            block_cells[bid].append((bx, by))

    # --- Extract modifiers from interior (tag cells) ---
    block_ice: dict[str, int] = {}
    block_dir: dict[str, str | None] = {}

    for grow in range(1, h + 1):
        for gcol in range(1, w + 1):
            mod_token = mod_layer[grow][gcol]
            id_token = id_layer[grow][gcol]

            if mod_token == '.' or mod_token == '#' or id_token == '.' or id_token == '#':
                continue

            bid = id_token

            if mod_token.startswith('i') and len(mod_token) >= 2 and mod_token[1:].isdigit():
                block_ice[bid] = int(mod_token[1:])
            elif mod_token == '-':
                block_dir[bid] = 'h'
            elif mod_token == '|':
                block_dir[bid] = 'v'

    # --- Build Block objects ---
    blocks: dict[str, Block] = {}
    positions: dict[str, tuple[int, int]] = {}

    for bid, abs_cells in block_cells.items():
        # Top-left position = min x, min y
        min_x = min(c[0] for c in abs_cells)
        min_y = min(c[1] for c in abs_cells)
        # Relative cells from top-left
        rel_cells = tuple(sorted((cx - min_x, cy - min_y) for cx, cy in abs_cells))

        blocks[bid] = Block(
            id=bid,
            color=block_colors[bid],
            cells=rel_cells,
            ice=block_ice.get(bid, 0),
            direction=block_dir.get(bid, None),
        )
        positions[bid] = (min_x, min_y)

    # --- Extract gates from border ---
    gates: list[Gate] = []
    gate_info: dict[str, dict] = {}  # gate_id -> {color, positions, side}

    # Top border: grid row 0
    for gcol in range(grid_cols):
        ctoken = color_layer[0][gcol]
        itoken = id_layer[0][gcol]
        mtoken = mod_layer[0][gcol]

        if ctoken != '.' and itoken != '.' and mtoken == '^':
            gid = itoken
            if gid not in gate_info:
                gate_info[gid] = {'color': ctoken, 'side': 'top', 'positions': []}
            gate_info[gid]['positions'].append(gcol - 1)  # board x

    # Bottom border: grid row h+1
    for gcol in range(grid_cols):
        ctoken = color_layer[h + 1][gcol]
        itoken = id_layer[h + 1][gcol]
        mtoken = mod_layer[h + 1][gcol]

        if ctoken != '.' and itoken != '.' and mtoken == 'v':
            gid = itoken
            if gid not in gate_info:
                gate_info[gid] = {'color': ctoken, 'side': 'bottom', 'positions': []}
            gate_info[gid]['positions'].append(gcol - 1)  # board x

    # Left border: grid col 0
    for grow in range(grid_rows):
        ctoken = color_layer[grow][0]
        itoken = id_layer[grow][0]
        mtoken = mod_layer[grow][0]

        if ctoken != '.' and itoken != '.' and mtoken == '<':
            gid = itoken
            if gid not in gate_info:
                gate_info[gid] = {'color': ctoken, 'side': 'left', 'positions': []}
            gate_info[gid]['positions'].append(grow - 1)  # board y

    # Right border: grid col w+1
    for grow in range(grid_rows):
        ctoken = color_layer[grow][w + 1]
        itoken = id_layer[grow][w + 1]
        mtoken = mod_layer[grow][w + 1]

        if ctoken != '.' and itoken != '.' and mtoken == '>':
            gid = itoken
            if gid not in gate_info:
                gate_info[gid] = {'color': ctoken, 'side': 'right', 'positions': []}
            gate_info[gid]['positions'].append(grow - 1)  # board y

    for gid, info in gate_info.items():
        pos_list = sorted(info['positions'])
        gate = Gate(
            id=gid,
            color=info['color'],
            side=info['side'],
            position=pos_list[0],
            width=len(pos_list),
        )
        gates.append(gate)

    board = Board(w=w, h=h, walls=frozenset(walls), blocks=blocks, gates=gates)

    return board, positions


if __name__ == '__main__':
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else 'tests/test1.txt'
    board, positions = parse_level(path)

    print(f"Board: {board.w}x{board.h}")
    print(f"Walls: {sorted(board.walls)}")
    print(f"Blocks ({len(board.blocks)}):")
    for bid, blk in sorted(board.blocks.items()):
        pos = positions[bid]
        mod = ""
        if blk.ice > 0:
            mod += f" ic={blk.ice}"
        if blk.direction:
            mod += f" ar={blk.direction}"
        print(f"  {bid}: color={blk.color} pos={pos} cells={blk.cells}{mod}")

    print(f"Gates ({len(board.gates)}):")
    for g in board.gates:
        print(f"  {g.id}: color={g.color} side={g.side} pos={g.position} width={g.width}")

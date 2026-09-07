"""High-performance game engine: state representation, move generation,
exit checking, and goal testing — all in one module to minimize call overhead."""
from __future__ import annotations
from models import Board

# State is a tuple: (positions_tuple, exited_frozenset)
# positions_tuple: tuple of (x, y) indexed by board.block_idx order
#   -1, -1 means the block has exited (stored in exited set too for fast check)
# This is hashable and very cheap to compare.

_DIR_H = ((-1, 0), (1, 0))
_DIR_V = ((0, -1), (0, 1))
_DIR_ALL = ((0, -1), (0, 1), (-1, 0), (1, 0))
_DIR_MAP = {None: _DIR_ALL, 'h': _DIR_H, 'v': _DIR_V}


def make_state(positions: dict[str, tuple[int, int]], board: Board,
               exited: frozenset[str] = frozenset()):
    """Convert dict positions to compact state tuple."""
    pos_list = []
    for bid in board.block_list:
        if bid in positions:
            pos_list.append(positions[bid])
        else:
            pos_list.append((-1, -1))
    return _normalize(tuple(pos_list), exited, board)


def _normalize(pos_tuple, exited, board):
    """Normalize state by sorting positions of interchangeable blocks."""
    if not board.sym_groups:
        return (pos_tuple, exited)
    pos_list = list(pos_tuple)
    for group in board.sym_groups:
        group_positions = sorted(pos_list[i] for i in group)
        for j, i in enumerate(sorted(group)):
            pos_list[i] = group_positions[j]
    return (tuple(pos_list), exited)


def make_state_raw(positions: dict[str, tuple[int, int]], board: Board,
                   exited: frozenset[str] = frozenset()):
    """Convert dict positions to compact state tuple WITHOUT normalization."""
    pos_list = []
    for bid in board.block_list:
        if bid in positions:
            pos_list.append(positions[bid])
        else:
            pos_list.append((-1, -1))
    return (tuple(pos_list), exited)


def generate_moves_raw(state, board: Board):
    """Generate max-slide moves WITHOUT normalizing new states."""
    pos_tuple, exited = state
    w, h = board.w, board.h
    walls = board.walls
    num_exited = len(exited)
    block_list = board.block_list
    blocks = board.blocks

    occ = set(walls)
    for i, bid in enumerate(block_list):
        if bid in exited:
            continue
        bx, by = pos_tuple[i]
        for dx, dy in blocks[bid].cells:
            occ.add((bx + dx, by + dy))

    results = []

    for i, bid in enumerate(block_list):
        if bid in exited:
            continue
        blk = blocks[bid]
        if blk.ice > 0 and num_exited < blk.ice:
            continue

        bx, by = pos_tuple[i]
        cells = blk.cells
        my_cells = [(bx + dx, by + dy) for dx, dy in cells]
        for c in my_cells:
            occ.discard(c)

        for ddx, ddy in _DIR_MAP[blk.direction]:
            last_nx, last_ny = None, None
            exit_nx, exit_ny = None, None
            step = 1
            while True:
                nx = bx + ddx * step
                ny = by + ddy * step
                ok = True
                for cx, cy in cells:
                    ax = nx + cx
                    ay = ny + cy
                    if ax < 0 or ax >= w or ay < 0 or ay >= h or (ax, ay) in occ:
                        ok = False
                        break
                if not ok:
                    break
                last_nx, last_ny = nx, ny
                if exit_nx is None and _can_exit(blk, nx, ny, board, num_exited):
                    exit_nx, exit_ny = nx, ny
                step += 1

            if last_nx is not None:
                new_pos = list(pos_tuple)
                new_pos[i] = (last_nx, last_ny)
                new_exited = _apply_auto_exit(new_pos, exited, board)
                results.append((bid, last_nx, last_ny, (tuple(new_pos), new_exited)))

            if exit_nx is not None and (exit_nx, exit_ny) != (last_nx, last_ny):
                new_pos = list(pos_tuple)
                new_pos[i] = (exit_nx, exit_ny)
                new_exited = _apply_auto_exit(new_pos, exited, board)
                results.append((bid, exit_nx, exit_ny, (tuple(new_pos), new_exited)))

        for c in my_cells:
            occ.add(c)

    return results


def state_positions_dict(state, board: Board) -> dict[str, tuple[int, int]]:
    """Convert compact state back to dict (for output only)."""
    pos_tuple, exited = state
    result = {}
    for i, bid in enumerate(board.block_list):
        if bid not in exited:
            result[bid] = pos_tuple[i]
    return result


def is_goal(state, board: Board) -> bool:
    _, exited = state
    return board.needs_exit <= exited


def _can_exit(blk, bx, by, board: Board, num_exited: int) -> bool:
    """Check if block at (bx, by) can exit through any matching gate."""
    if blk.ice > 0 and num_exited < blk.ice:
        return False

    color = blk.color
    gates = board.gates_by_color.get(color)
    if not gates:
        return False

    cells = blk.cells
    # Precompute absolute bounds
    abs_xs = [bx + dx for dx, _ in cells]
    abs_ys = [by + dy for _, dy in cells]
    min_x, max_x = min(abs_xs), max(abs_xs)
    min_y, max_y = min(abs_ys), max(abs_ys)

    for gate in gates:
        ge = gate.position + gate.width - 1
        if gate.side == 'top':
            if min_y == 0 and min_x >= gate.position and max_x <= ge:
                return True
        elif gate.side == 'bottom':
            if max_y == board.h - 1 and min_x >= gate.position and max_x <= ge:
                return True
        elif gate.side == 'left':
            if min_x == 0 and min_y >= gate.position and max_y <= ge:
                return True
        elif gate.side == 'right':
            if max_x == board.w - 1 and min_y >= gate.position and max_y <= ge:
                return True
    return False


def _apply_auto_exit(pos_list: list, exited: frozenset, board: Board):
    """Apply auto-exit in-place on pos_list. Returns new exited set."""
    changed = True
    while changed:
        changed = False
        num_exited = len(exited)
        for i, bid in enumerate(board.block_list):
            if bid in exited:
                continue
            bx, by = pos_list[i]
            blk = board.blocks[bid]
            if _can_exit(blk, bx, by, board, num_exited):
                pos_list[i] = (-1, -1)
                exited = exited | frozenset([bid])
                changed = True
                break  # restart (exit count changed, may unlock ice)
    return exited


def generate_moves(state, board: Board):
    """Generate max-slide moves. Returns list of (block_id, new_x, new_y, new_state)."""
    pos_tuple, exited = state
    w, h = board.w, board.h
    walls = board.walls
    num_exited = len(exited)
    block_list = board.block_list
    blocks = board.blocks

    # Build occupancy set
    occ = set(walls)
    for i, bid in enumerate(block_list):
        if bid in exited:
            continue
        bx, by = pos_tuple[i]
        for dx, dy in blocks[bid].cells:
            occ.add((bx + dx, by + dy))

    results = []

    for i, bid in enumerate(block_list):
        if bid in exited:
            continue
        blk = blocks[bid]
        if blk.ice > 0 and num_exited < blk.ice:
            continue

        bx, by = pos_tuple[i]
        cells = blk.cells

        # Remove this block's cells from occupancy temporarily
        my_cells = [(bx + dx, by + dy) for dx, dy in cells]
        for c in my_cells:
            occ.discard(c)

        for ddx, ddy in _DIR_MAP[blk.direction]:
            # Slide to max, also track gate-aligned intermediate stops
            last_nx, last_ny = None, None
            exit_nx, exit_ny = None, None
            step = 1
            while True:
                nx = bx + ddx * step
                ny = by + ddy * step
                ok = True
                for cx, cy in cells:
                    ax = nx + cx
                    ay = ny + cy
                    if ax < 0 or ax >= w or ay < 0 or ay >= h or (ax, ay) in occ:
                        ok = False
                        break
                if not ok:
                    break
                last_nx, last_ny = nx, ny
                if exit_nx is None and _can_exit(blk, nx, ny, board, num_exited):
                    exit_nx, exit_ny = nx, ny
                step += 1

            if last_nx is not None:
                new_pos = list(pos_tuple)
                new_pos[i] = (last_nx, last_ny)
                new_exited = _apply_auto_exit(new_pos, exited, board)
                new_state = _normalize(tuple(new_pos), new_exited, board)
                results.append((bid, last_nx, last_ny, new_state))

            # Add gate-aligned intermediate stop if different from max
            if exit_nx is not None and (exit_nx, exit_ny) != (last_nx, last_ny):
                new_pos = list(pos_tuple)
                new_pos[i] = (exit_nx, exit_ny)
                new_exited = _apply_auto_exit(new_pos, exited, board)
                new_state = _normalize(tuple(new_pos), new_exited, board)
                results.append((bid, exit_nx, exit_ny, new_state))

        # Restore occupancy
        for c in my_cells:
            occ.add(c)

    return results


def generate_moves_all(state, board: Board):
    """Generate all intermediate slide positions."""
    pos_tuple, exited = state
    w, h = board.w, board.h
    walls = board.walls
    num_exited = len(exited)
    block_list = board.block_list
    blocks = board.blocks

    occ = set(walls)
    for i, bid in enumerate(block_list):
        if bid in exited:
            continue
        bx, by = pos_tuple[i]
        for dx, dy in blocks[bid].cells:
            occ.add((bx + dx, by + dy))

    results = []

    for i, bid in enumerate(block_list):
        if bid in exited:
            continue
        blk = blocks[bid]
        if blk.ice > 0 and num_exited < blk.ice:
            continue

        bx, by = pos_tuple[i]
        cells = blk.cells
        my_cells = [(bx + dx, by + dy) for dx, dy in cells]
        for c in my_cells:
            occ.discard(c)

        for ddx, ddy in _DIR_MAP[blk.direction]:
            step = 1
            while True:
                nx = bx + ddx * step
                ny = by + ddy * step
                ok = True
                for cx, cy in cells:
                    ax = nx + cx
                    ay = ny + cy
                    if ax < 0 or ax >= w or ay < 0 or ay >= h or (ax, ay) in occ:
                        ok = False
                        break
                if not ok:
                    break

                new_pos = list(pos_tuple)
                new_pos[i] = (nx, ny)
                new_exited = _apply_auto_exit(new_pos, exited, board)
                new_state = _normalize(tuple(new_pos), new_exited, board)
                results.append((bid, nx, ny, new_state))
                step += 1

        for c in my_cells:
            occ.add(c)

    return results


def heuristic_fast(state, board: Board) -> int:
    """Fast admissible heuristic: 0/1/2 per block."""
    pos_tuple, exited = state
    total = 0
    num_exited = len(exited)
    bw, bh = board.w, board.h

    for i, bid in enumerate(board.block_list):
        if bid in exited:
            continue
        blk = board.blocks[bid]
        gates = board.gates_by_color.get(blk.color)
        if not gates:
            continue

        bx, by = pos_tuple[i]
        cells = blk.cells
        abs_xs = [bx + dx for dx, _ in cells]
        abs_ys = [by + dy for _, dy in cells]
        min_x, max_x = min(abs_xs), max(abs_xs)
        min_y, max_y = min(abs_ys), max(abs_ys)
        bdir = blk.direction

        best = 3
        for gate in gates:
            ge = gate.position + gate.width - 1
            if gate.side == 'top':
                at_e = (min_y == 0)
                al = (min_x >= gate.position and max_x <= ge)
                if bdir == 'h' and not at_e:
                    continue
                if bdir == 'v' and not al:
                    continue
            elif gate.side == 'bottom':
                at_e = (max_y == bh - 1)
                al = (min_x >= gate.position and max_x <= ge)
                if bdir == 'h' and not at_e:
                    continue
                if bdir == 'v' and not al:
                    continue
            elif gate.side == 'left':
                at_e = (min_x == 0)
                al = (min_y >= gate.position and max_y <= ge)
                if bdir == 'v' and not at_e:
                    continue
                if bdir == 'h' and not al:
                    continue
            elif gate.side == 'right':
                at_e = (max_x == bw - 1)
                al = (min_y >= gate.position and max_y <= ge)
                if bdir == 'v' and not at_e:
                    continue
                if bdir == 'h' and not al:
                    continue
            else:
                continue

            if at_e and al:
                best = 0
                break
            elif at_e or al:
                best = min(best, 1)
            else:
                best = min(best, 2)

        if blk.ice > 0 and num_exited < blk.ice:
            best = max(best, blk.ice - num_exited)

        total += best

    return total


def heuristic_distance(state, board: Board) -> float:
    """Distance-based heuristic with continuous gradient toward gates."""
    pos_tuple, exited = state
    total = 0.0
    num_exited = len(exited)
    bw, bh = board.w, board.h

    for i, bid in enumerate(board.block_list):
        if bid in exited:
            continue
        blk = board.blocks[bid]
        gates = board.gates_by_color.get(blk.color)
        if not gates:
            continue

        bx, by = pos_tuple[i]
        cells = blk.cells
        abs_xs = [bx + dx for dx, _ in cells]
        abs_ys = [by + dy for _, dy in cells]
        min_x, max_x = min(abs_xs), max(abs_xs)
        min_y, max_y = min(abs_ys), max(abs_ys)
        bdir = blk.direction

        best = 999.0
        for gate in gates:
            ge = gate.position + gate.width - 1
            if gate.side == 'top':
                d_edge = min_y
                d_align = max(0, gate.position - min_x) + max(0, max_x - ge)
            elif gate.side == 'bottom':
                d_edge = (bh - 1) - max_y
                d_align = max(0, gate.position - min_x) + max(0, max_x - ge)
            elif gate.side == 'left':
                d_edge = min_x
                d_align = max(0, gate.position - min_y) + max(0, max_y - ge)
            elif gate.side == 'right':
                d_edge = (bw - 1) - max_x
                d_align = max(0, gate.position - min_y) + max(0, max_y - ge)
            else:
                continue

            if bdir == 'h' and d_edge > 0 and gate.side in ('top', 'bottom'):
                continue
            if bdir == 'v' and d_edge > 0 and gate.side in ('left', 'right'):
                continue
            if bdir == 'h' and d_align > 0 and gate.side in ('left', 'right'):
                continue
            if bdir == 'v' and d_align > 0 and gate.side in ('top', 'bottom'):
                continue

            dist = d_edge + d_align
            if dist == 0:
                best = 0
                break
            # At least 1 move per axis needed, plus fraction for distance
            moves = 0
            if d_edge > 0:
                moves += 1
            if d_align > 0:
                moves += 1
            cost = moves + (d_edge + d_align) * 0.1
            best = min(best, cost)

        if blk.ice > 0 and num_exited < blk.ice:
            best = max(best, float(blk.ice - num_exited) + 1.0)

        total += best

    return total

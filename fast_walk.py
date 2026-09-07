"""Ultra-fast random walk engine with stochastic hill-climbing."""
from __future__ import annotations
import random
import time
import sys
from models import Board
from engine import _DIR_MAP, _can_exit, heuristic_fast, _apply_auto_exit


def _score_move(i, nx, ny, positions, exited, board):
    """Score a move by applying it and computing heuristic on result."""
    new_pos = list(positions)
    new_pos[i] = (nx, ny)
    new_exited = _apply_auto_exit(new_pos, exited, board)
    state = (tuple(new_pos), new_exited)
    return heuristic_fast(state, board), len(new_exited)


def _compute_blocker_scores(block_list, blocks, positions, exited, board):
    """Count how many exit-needing blocks each block is obstructing.

    For each block that needs to exit, trace a rectangular corridor from
    its current position toward its nearest gate edge. Any other block
    whose cells overlap that corridor is a "blocker". Returns a dict
    mapping block index -> number of blocks it obstructs.
    """
    needs_exit = board.needs_exit
    w, h = board.w, board.h

    # Build cell -> block_index map
    cell_to_idx = {}
    for i, bid in enumerate(block_list):
        if bid in exited:
            continue
        bx, by = positions[i]
        for dx, dy in blocks[bid].cells:
            cell_to_idx[(bx + dx, by + dy)] = i

    blocker_count = {}
    for i, bid in enumerate(block_list):
        if bid in exited or bid not in needs_exit:
            continue
        blk = blocks[bid]
        gates = board.gates_by_color.get(blk.color)
        if not gates:
            continue
        bx, by = positions[i]
        cells = blk.cells
        abs_xs = [bx + dx for dx, _ in cells]
        abs_ys = [by + dy for _, dy in cells]
        min_x, max_x = min(abs_xs), max(abs_xs)
        min_y, max_y = min(abs_ys), max(abs_ys)

        my_cells = set((bx + dx, by + dy) for dx, dy in cells)

        for gate in gates:
            ge = gate.position + gate.width - 1
            corridor = set()
            if gate.side == 'top':
                for cx in range(min_x, max_x + 1):
                    for cy in range(0, min_y):
                        corridor.add((cx, cy))
            elif gate.side == 'bottom':
                for cx in range(min_x, max_x + 1):
                    for cy in range(max_y + 1, h):
                        corridor.add((cx, cy))
            elif gate.side == 'left':
                for cy in range(min_y, max_y + 1):
                    for cx in range(0, min_x):
                        corridor.add((cx, cy))
            elif gate.side == 'right':
                for cy in range(min_y, max_y + 1):
                    for cx in range(max_x + 1, w):
                        corridor.add((cx, cy))

            blockers_found = set()
            for cell in corridor:
                if cell in cell_to_idx:
                    bi = cell_to_idx[cell]
                    if bi != i:
                        blockers_found.add(bi)
            for bi in blockers_found:
                blocker_count[bi] = blocker_count.get(bi, 0) + 1

    return blocker_count


def run_walks(board, init_positions_list, init_exited, start_time, deadline,
              walk_len=300, verbose=False, greedy=False, stop_on_first=False,
              weighted=False):
    """Stochastic hill-climbing: run short walks, restart from best state."""
    block_list = board.block_list
    blocks = board.blocks
    walls = board.walls
    w, h = board.w, board.h
    needs_exit = board.needs_exit

    best_solution = None
    best_max_exits = 0
    attempt = 0
    rng = random.Random()

    # Pre-compute blocker scores once from initial state
    init_blocker_scores = None
    if weighted:
        init_blocker_scores = _compute_blocker_scores(
            block_list, blocks, init_positions_list, init_exited, board)

    # Pool of promising start states: (num_exits, positions, exited, path_to_here)
    start_pool = [(0, list(init_positions_list), init_exited, [])]

    while time.time() < deadline - 0.3:
        attempt += 1
        if verbose and attempt % 3000 == 1:
            print(f"  walk #{attempt} best_exits={best_max_exits} "
                  f"pool={len(start_pool)} t={time.time()-start_time:.1f}s",
                  file=sys.stderr)

        # Pick start state: mostly from best in pool, sometimes from init
        if start_pool and rng.random() < 0.7:
            # Pick from pool, biased toward more exits
            pool_idx = min(rng.randint(0, len(start_pool) - 1),
                           rng.randint(0, len(start_pool) - 1))
            _, start_pos, start_exited, prefix_path = start_pool[pool_idx]
        else:
            start_pos = init_positions_list
            start_exited = init_exited
            prefix_path = []

        positions = list(start_pos)
        exited = start_exited
        num_exited = len(exited)
        path = list(prefix_path)
        max_exits_this_walk = num_exited
        best_state_this_walk = None

        # Build occupancy
        occ = set(walls)
        for i, bid in enumerate(block_list):
            if bid in exited:
                continue
            bx, by = positions[i]
            for dx, dy in blocks[bid].cells:
                occ.add((bx + dx, by + dy))

        last_moved_block = -1

        for step in range(walk_len):
            if needs_exit <= exited:
                if best_solution is None or len(path) < len(best_solution):
                    best_solution = list(path)
                    if verbose:
                        print(f"  SOLVED: {len(path)} moves (walk #{attempt})",
                              file=sys.stderr)
                    if stop_on_first:
                        return best_solution, len(exited)
                break

            # Generate moves inline
            moves = []
            for i, bid in enumerate(block_list):
                if bid in exited:
                    continue
                blk = blocks[bid]
                if blk.ice > 0 and num_exited < blk.ice:
                    continue
                bx, by = positions[i]
                cells = blk.cells
                my_abs = [(bx + dx, by + dy) for dx, dy in cells]
                for c in my_abs:
                    occ.discard(c)

                for ddx, ddy in _DIR_MAP[blk.direction]:
                    lx, ly = None, None
                    exit_x, exit_y = None, None
                    s = 1
                    while True:
                        nx = bx + ddx * s
                        ny = by + ddy * s
                        ok = True
                        for cx, cy in cells:
                            ax = nx + cx
                            ay = ny + cy
                            if ax < 0 or ax >= w or ay < 0 or ay >= h or (ax, ay) in occ:
                                ok = False
                                break
                        if not ok:
                            break
                        lx, ly = nx, ny
                        # Check if this intermediate position is an exit
                        if exit_x is None and _can_exit(blk, nx, ny, board, num_exited):
                            exit_x, exit_y = nx, ny
                        s += 1
                    if lx is not None:
                        moves.append((i, lx, ly))
                    # Also add exit-aligned intermediate stop
                    if exit_x is not None and (exit_x, exit_y) != (lx, ly):
                        moves.append((i, exit_x, exit_y))

                for c in my_abs:
                    occ.add(c)

            if not moves:
                break

            # Avoid moving same block back and forth
            if len(moves) > 1:
                filtered = [(i, x, y) for i, x, y in moves if i != last_moved_block]
                if filtered:
                    moves = filtered

            # Pick move
            if weighted and init_blocker_scores and step < 5:
                weights = []
                for mi, mx, my in moves:
                    score = init_blocker_scores.get(mi, 0)
                    weights.append(1.0 + score * 0.5)
                total_w = sum(weights)
                r = rng.random() * total_w
                cumulative = 0.0
                chosen = len(moves) - 1
                for j, w in enumerate(weights):
                    cumulative += w
                    if r <= cumulative:
                        chosen = j
                        break
                idx, nx, ny = moves[chosen]
            elif greedy and rng.random() < 0.7:
                best_score = None
                best_move = None
                for mi, mx, my in moves:
                    h, ne = _score_move(mi, mx, my, positions, exited, board)
                    score = (-ne, h)
                    if best_score is None or score < best_score:
                        best_score = score
                        best_move = (mi, mx, my)
                idx, nx, ny = best_move
            else:
                idx, nx, ny = moves[rng.randint(0, len(moves) - 1)]
            bid = block_list[idx]
            blk = blocks[bid]
            cells = blk.cells
            old_x, old_y = positions[idx]

            for dx, dy in cells:
                occ.discard((old_x + dx, old_y + dy))
            positions[idx] = (nx, ny)
            for dx, dy in cells:
                occ.add((nx + dx, ny + dy))

            path.append((bid, nx, ny))
            last_moved_block = idx

            # Auto-exit
            changed = True
            while changed:
                changed = False
                for i2, bid2 in enumerate(block_list):
                    if bid2 in exited:
                        continue
                    bx2, by2 = positions[i2]
                    if _can_exit(blocks[bid2], bx2, by2, board, num_exited):
                        for dx, dy in blocks[bid2].cells:
                            occ.discard((bx2 + dx, by2 + dy))
                        positions[i2] = (-1, -1)
                        exited = exited | frozenset([bid2])
                        num_exited += 1
                        changed = True
                        break

            if num_exited > max_exits_this_walk:
                max_exits_this_walk = num_exited
                best_state_this_walk = (num_exited, list(positions),
                                        exited, list(path))

        # Update best exits
        if max_exits_this_walk > best_max_exits:
            best_max_exits = max_exits_this_walk
            if verbose:
                remaining_blocks = [bid for bid in block_list if bid not in exited
                                    and bid in needs_exit]
                print(f"  walk #{attempt}: exits={max_exits_this_walk} "
                      f"remaining={remaining_blocks}",
                      file=sys.stderr)

        # Add to pool if this walk found exits
        if best_state_this_walk and best_state_this_walk[0] > 0:
            start_pool.append(best_state_this_walk)
            # Keep pool sorted and bounded
            start_pool.sort(key=lambda x: -x[0])
            if len(start_pool) > 50:
                start_pool = start_pool[:50]

    if verbose:
        print(f"  Total walks: {attempt}, best_exits={best_max_exits}",
              file=sys.stderr)
    return best_solution, best_max_exits

"""Solver 3 (Optional): SAT/CSP formulation using Z3 theorem prover.

Instead of searching through states procedurally (like A* or random walks),
this solver encodes the puzzle as a constraint satisfaction problem:
- Variables: block positions at each time step
- Constraints: valid movements, no overlaps, wall avoidance, bounds, exits
- Objective: find a valid sequence of moves that exits all required blocks

This is fundamentally different from Solvers 1 & 2: we DECLARE what a valid
solution looks like and let Z3's CDCL (Conflict-Driven Clause Learning)
solver find one, rather than exploring states procedurally.

Reference: Gozon & Yu (WAFR 2024) - "Optimally Solving Colored
Generalized Sliding-Tile Puzzles: Complexity and Bounds"
"""
from __future__ import annotations
import time
import sys
from models import Board
from engine import (make_state, generate_moves, is_goal, heuristic_fast,
                    _can_exit)


def solve_optional(board: Board, initial_positions: dict,
                  timeout: float = 58.0, verbose: bool = False) -> tuple[str, list]:
    start_time = time.time()

    # Phase 1: A* for easy/medium puzzles
    init_state = make_state(initial_positions, board)
    if is_goal(init_state, board):
        return 'SOLVED', [], 'astar'

    deadline_astar = start_time + timeout * 0.20
    r = _astar_quick(board, init_state, 1.5, start_time, deadline_astar, verbose)
    if r[0] == 'SOLVED':
        return 'SOLVED', r[1], 'astar'

    # Phase 2: SAT/CSP with Z3
    if verbose:
        print("Phase 2: SAT/CSP with Z3...", file=sys.stderr)

    sat_deadline = start_time + timeout * 0.55
    sat_result = _solve_sat(board, initial_positions, sat_deadline, verbose)
    if sat_result is not None:
        if verbose:
            print(f"  SAT solved: {len(sat_result)} moves", file=sys.stderr)
        return 'SOLVED', sat_result, 'pre_denormalized'

    # Phase 3: Random walks fallback
    if verbose:
        print("Phase 3: random walks...", file=sys.stderr)
    from fast_walk import run_walks
    from engine import make_state_raw
    raw_state = make_state_raw(initial_positions, board, frozenset())
    pos_list = list(raw_state[0])
    exited = raw_state[1]
    solution, _ = run_walks(
        board, pos_list, exited, start_time,
        deadline=start_time + timeout, walk_len=400, verbose=verbose,
        stop_on_first=True)
    if solution is not None:
        return 'SOLVED', solution, 'pre_denormalized'

    return 'TIMEOUT', [], 'none'


def _solve_sat(board, positions, deadline, verbose):
    """Encode puzzle as SAT/CSP and solve with Z3."""
    try:
        from z3 import (Solver, Int, Bool, And, Or, Not, Implies, If,
                        sat, Sum)
    except ImportError:
        if verbose:
            print("  Z3 not available, skipping SAT", file=sys.stderr)
        return None

    block_list = board.block_list
    blocks = board.blocks
    n = len(block_list)
    W, H = board.w, board.h
    walls = board.walls

    block_cells = [blocks[bid].cells for bid in block_list]
    block_dirs = [blocks[bid].direction for bid in block_list]
    block_ice = [blocks[bid].ice for bid in block_list]

    block_gates = []
    for bid in block_list:
        blk = blocks[bid]
        gates = board.gates_by_color.get(blk.color, [])
        block_gates.append([(g.side, g.position, g.position + g.width - 1)
                            for g in gates])

    for k in range(1, 50):
        if time.time() > deadline:
            if verbose:
                print(f"  SAT: timeout at k={k}", file=sys.stderr)
            return None

        remaining_ms = int((deadline - time.time()) * 1000)
        if remaining_ms < 500:
            return None

        if verbose:
            print(f"  SAT: trying k={k}...", file=sys.stderr)

        s = Solver()
        s.set("timeout", min(remaining_ms, 10000))

        # Variables: position and active status at each timestep
        X = [[Int(f'x{i}t{t}') for t in range(k + 1)] for i in range(n)]
        Y = [[Int(f'y{i}t{t}') for t in range(k + 1)] for i in range(n)]
        active = [[Bool(f'a{i}t{t}') for t in range(k + 1)] for i in range(n)]

        # Initial state constraints
        for i, bid in enumerate(block_list):
            pos = positions[bid]
            s.add(X[i][0] == pos[0])
            s.add(Y[i][0] == pos[1])
            s.add(active[i][0] == True)

        # Transition constraints for each timestep
        for t in range(k):
            mover = Int(f'mv{t}')
            s.add(mover >= 0, mover < n)

            direction = Int(f'dir{t}')
            s.add(direction >= 0, direction < 4)

            dist = Int(f'dist{t}')
            s.add(dist >= 1, dist <= max(W, H) - 1)

            for i in range(n):
                is_mover = (mover == i)

                # Only active blocks can move
                s.add(Implies(is_mover, active[i][t]))

                # Non-movers stay in place
                s.add(Implies(Or(Not(is_mover), Not(active[i][t])),
                              And(X[i][t+1] == X[i][t], Y[i][t+1] == Y[i][t])))

                # Mover moves by (dist) in chosen direction
                s.add(Implies(And(is_mover, active[i][t]),
                    If(direction == 0,
                       And(X[i][t+1] == X[i][t] + dist, Y[i][t+1] == Y[i][t]),
                    If(direction == 1,
                       And(X[i][t+1] == X[i][t] - dist, Y[i][t+1] == Y[i][t]),
                    If(direction == 2,
                       And(X[i][t+1] == X[i][t], Y[i][t+1] == Y[i][t] + dist),
                       And(X[i][t+1] == X[i][t], Y[i][t+1] == Y[i][t] - dist))))))

                # Direction constraints
                bdir = block_dirs[i]
                if bdir == 'h':
                    s.add(Implies(is_mover, Or(direction == 0, direction == 1)))
                elif bdir == 'v':
                    s.add(Implies(is_mover, Or(direction == 2, direction == 3)))

                # Ice constraints
                ice_val = block_ice[i]
                if ice_val > 0:
                    num_exited = Sum([If(Not(active[j][t]), 1, 0)
                                     for j in range(n)])
                    s.add(Implies(is_mover, num_exited >= ice_val))

            # No overlap between active blocks
            for i in range(n):
                for j in range(i + 1, n):
                    for ci_x, ci_y in block_cells[i]:
                        for cj_x, cj_y in block_cells[j]:
                            s.add(Implies(
                                And(active[i][t+1], active[j][t+1]),
                                Or(X[i][t+1] + ci_x != X[j][t+1] + cj_x,
                                   Y[i][t+1] + ci_y != Y[j][t+1] + cj_y)))

            # Wall avoidance
            for i in range(n):
                for ci_x, ci_y in block_cells[i]:
                    for wx, wy in walls:
                        s.add(Implies(active[i][t+1],
                            Or(X[i][t+1] + ci_x != wx,
                               Y[i][t+1] + ci_y != wy)))

            # Bounds
            for i in range(n):
                for ci_x, ci_y in block_cells[i]:
                    s.add(Implies(active[i][t+1], And(
                        X[i][t+1] + ci_x >= 0, X[i][t+1] + ci_x < W,
                        Y[i][t+1] + ci_y >= 0, Y[i][t+1] + ci_y < H)))

            # Exit conditions
            for i in range(n):
                cells = block_cells[i]
                abs_xs = [X[i][t+1] + cx for cx, _ in cells]
                abs_ys = [Y[i][t+1] + cy for _, cy in cells]

                can_exit_clauses = []
                for gate_side, gate_pos, gate_end in block_gates[i]:
                    if gate_side == 'top':
                        at_edge = And(*[y == 0 for y in abs_ys])
                        aligned = And(*[And(x >= gate_pos, x <= gate_end)
                                       for x in abs_xs])
                    elif gate_side == 'bottom':
                        at_edge = And(*[y == H - 1 for y in abs_ys])
                        aligned = And(*[And(x >= gate_pos, x <= gate_end)
                                       for x in abs_xs])
                    elif gate_side == 'left':
                        at_edge = And(*[x == 0 for x in abs_xs])
                        aligned = And(*[And(y >= gate_pos, y <= gate_end)
                                       for y in abs_ys])
                    elif gate_side == 'right':
                        at_edge = And(*[x == W - 1 for x in abs_xs])
                        aligned = And(*[And(y >= gate_pos, y <= gate_end)
                                       for y in abs_ys])
                    else:
                        continue

                    ice_ok = True
                    if block_ice[i] > 0:
                        num_ex = Sum([If(Not(active[j][t+1]), 1, 0)
                                     for j in range(n) if j != i])
                        ice_ok = (num_ex >= block_ice[i])

                    can_exit_clauses.append(And(at_edge, aligned, ice_ok))

                can_exit = Or(*can_exit_clauses) if can_exit_clauses else False

                s.add(Implies(And(active[i][t], can_exit), Not(active[i][t+1])))
                s.add(Implies(And(active[i][t], Not(can_exit)), active[i][t+1]))
                s.add(Implies(Not(active[i][t]), Not(active[i][t+1])))

        # Goal: all blocks that need to exit are inactive
        for i, bid in enumerate(block_list):
            if bid in board.needs_exit:
                s.add(Not(active[i][k]))

        result = s.check()
        if str(result) == 'sat':
            model = s.model()
            solution = _extract_solution(model, block_list, X, Y, active, k, n)
            if verbose:
                print(f"  SAT: SOLVED at k={k} ({len(solution)} moves)",
                      file=sys.stderr)
            return solution

    return None


def _extract_solution(model, block_list, X, Y, active, k, n):
    """Extract move sequence from Z3 model."""
    moves = []
    for t in range(k):
        for i in range(n):
            x_before = model.eval(X[i][t]).as_long()
            y_before = model.eval(Y[i][t]).as_long()
            x_after = model.eval(X[i][t + 1]).as_long()
            y_after = model.eval(Y[i][t + 1]).as_long()
            was_active = model.eval(active[i][t])
            if str(was_active) == 'True' and (x_before != x_after or
                                               y_before != y_after):
                moves.append((block_list[i], x_after, y_after))
                break
    return moves


def _astar_quick(board, init_state, weight, start_time, deadline, verbose):
    """Quick A* search."""
    import heapq
    h0 = heuristic_fast(init_state, board)
    counter = 0
    open_set = [(weight * h0, counter, 0, init_state)]
    best_g = {init_state: 0}
    parent = {init_state: (None, None)}
    expanded = 0

    while open_set:
        if expanded % 3000 == 0 and expanded > 0:
            if time.time() > deadline:
                if verbose:
                    print(f"  A*(1.5): timeout exp={expanded}", file=sys.stderr)
                return 'TIMEOUT', []
        f, _, g, state = heapq.heappop(open_set)
        if state in best_g and best_g[state] < g:
            continue
        expanded += 1
        for bid, nx, ny, new_state in generate_moves(state, board):
            new_g = g + 1
            if new_state in best_g and best_g[new_state] <= new_g:
                continue
            best_g[new_state] = new_g
            parent[new_state] = (state, (bid, nx, ny))
            if is_goal(new_state, board):
                if verbose:
                    print(f"  A*(1.5): SOLVED {new_g} moves exp={expanded}",
                          file=sys.stderr)
                return 'SOLVED', _reconstruct(parent, new_state)
            h = heuristic_fast(new_state, board)
            counter += 1
            heapq.heappush(open_set, (new_g + weight * h, counter,
                                      new_g, new_state))
    return 'UNSOLVABLE', []


def _reconstruct(parent, goal):
    path = []
    s = goal
    while True:
        prev, move = parent[s]
        if move is None:
            break
        path.append(move)
        s = prev
    path.reverse()
    return path

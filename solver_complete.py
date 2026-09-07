from __future__ import annotations
import heapq
import time
import sys
from models import Board
from engine import (make_state, generate_moves, is_goal, heuristic_fast)


def solve_complete(board: Board, initial_positions: dict,
                   timeout: float = 58.0, verbose: bool = False) -> tuple[str, list]:
    """Complete solver: prioritizes finding the correct answer.

    Phase 1: A* with escalating weights (time-bounded per weight).
    Phase 2: Random walks with no time limit — runs until a solution is found.
    """
    start_time = time.time()
    init_state = make_state(initial_positions, board)

    if is_goal(init_state, board):
        return 'SOLVED', [], 'astar'

    # Phase 1: A* with increasing weights
    configs = [
        (1.5, 0.20, "W-A*(1.5)"),
        (5.0, 0.10, "W-A*(5)"),
        (20.0, 0.10, "W-A*(20)"),
    ]
    for weight, time_frac, label in configs:
        remaining = timeout - (time.time() - start_time)
        if remaining < 3:
            break
        budget = min(remaining, timeout * time_frac)
        if verbose:
            print(f"Trying {label} (budget={budget:.0f}s)...", file=sys.stderr)
        r = _astar(board, init_state, weight,
                   start_time, time.time() + budget, verbose, label)
        if r[0] in ('SOLVED', 'UNSOLVABLE'):
            return r[0], r[1], 'astar'

    # Phase 2: Random walks — no time limit, runs until solution found
    if verbose:
        print("Phase 2: random walks (no time limit)...", file=sys.stderr)
    from fast_walk import run_walks
    pos_list = list(init_state[0])
    exited = init_state[1]
    solution, _ = run_walks(
        board, pos_list, exited, start_time,
        deadline=float('inf'), walk_len=400, verbose=verbose,
        stop_on_first=True)
    if solution is not None:
        return 'SOLVED', solution, 'walks'

    return 'UNSOLVABLE', [], 'none'


def _astar(board, init_state, weight, start_time, deadline, verbose, label):
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
                    print(f"  {label}: timeout exp={expanded}",
                          file=sys.stderr)
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
                    print(f"  {label}: SOLVED {new_g} moves exp={expanded}",
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

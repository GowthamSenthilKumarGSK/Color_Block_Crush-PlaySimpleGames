#!/usr/bin/env python3
import argparse
import sys
import time

from parser import parse_level
from solver_complete import solve_complete
from solver_fast import solve_fast
from solver_optional import solve_optional
from engine import _can_exit, _normalize


def _compute_initial_perm(board, initial_positions):
    """Compute norm_index -> orig_bid mapping from initial normalization."""
    block_list = board.block_list
    perm = {}
    for group in board.sym_groups:
        entries = [(gi, initial_positions[block_list[gi]]) for gi in group]
        entries.sort(key=lambda e: e[1])
        sorted_indices = sorted(group)
        for j, norm_idx in enumerate(sorted_indices):
            orig_gi = entries[j][0]
            perm[norm_idx] = block_list[orig_gi]
    return perm


def denormalize_walks(board, initial_positions, moves):
    """Denormalize moves from random walks (no re-normalization between moves).

    The walk engine starts from normalized positions but never re-normalizes.
    Each block index stays mapped to the same original block throughout.
    """
    if not board.sym_groups:
        return moves

    perm = _compute_initial_perm(board, initial_positions)
    block_idx = board.block_idx

    sym_indices = set()
    for group in board.sym_groups:
        for idx in group:
            sym_indices.add(idx)

    result = []
    for move_bid, nx, ny in moves:
        i = block_idx[move_bid]
        if i in sym_indices:
            actual_bid = perm.get(i, move_bid)
        else:
            actual_bid = move_bid
        result.append((actual_bid, nx, ny))

    return result


def denormalize_astar(board, initial_positions, moves):
    """Denormalize moves from A* search (states re-normalized after each move).

    Each state is fully normalized, so the permutation can change after
    every move. We replicate the normalization sort on original positions
    to track the permutation.
    """
    if not board.sym_groups:
        return moves

    block_list = board.block_list
    block_idx = board.block_idx

    orig_pos = dict(initial_positions)
    orig_exited = set()

    sym_indices = set()
    for group in board.sym_groups:
        for idx in group:
            sym_indices.add(idx)

    def compute_perm():
        perm = {}
        for group in board.sym_groups:
            entries = []
            for gi in group:
                bid = block_list[gi]
                if bid in orig_exited:
                    entries.append((gi, (-1, -1)))
                else:
                    entries.append((gi, orig_pos[bid]))
            entries.sort(key=lambda e: e[1])
            sorted_indices = sorted(group)
            for j, norm_idx in enumerate(sorted_indices):
                orig_gi = entries[j][0]
                perm[norm_idx] = block_list[orig_gi]
        return perm

    perm = compute_perm()
    result = []

    for move_bid, nx, ny in moves:
        i = block_idx[move_bid]
        if i in sym_indices:
            actual_bid = perm.get(i, move_bid)
        else:
            actual_bid = move_bid

        result.append((actual_bid, nx, ny))
        orig_pos[actual_bid] = (nx, ny)

        changed = True
        while changed:
            changed = False
            num_exited = len(orig_exited)
            for bid_check in block_list:
                if bid_check in orig_exited:
                    continue
                pos = orig_pos[bid_check]
                blk = board.blocks[bid_check]
                if _can_exit(blk, pos[0], pos[1], board, num_exited):
                    orig_exited.add(bid_check)
                    orig_pos[bid_check] = (-1, -1)
                    changed = True
                    break

        perm = compute_perm()

    return result


def main():
    ap = argparse.ArgumentParser(description="Color Block Crush Solver")
    ap.add_argument('level', help='Path to a level file in ASCII format')
    ap.add_argument('--solver', choices=['complete', 'fast', 'optional'], default='complete',
                    help='Which solver to use (default: complete)')
    ap.add_argument('--verbose', action='store_true',
                    help='Print debug info to stderr')
    args = ap.parse_args()

    board, positions = parse_level(args.level)

    if args.verbose:
        print(f"Board: {board.w}x{board.h}, "
              f"Blocks: {len(board.blocks)}, "
              f"Gates: {len(board.gates)}, "
              f"Need exit: {len(board.needs_exit)}", file=sys.stderr)

    start = time.time()

    if args.solver == 'complete':
        status, moves, source = solve_complete(board, positions,
                                               timeout=58.0, verbose=args.verbose)
    elif args.solver == 'fast':
        status, moves, source = solve_fast(board, positions,
                                           timeout=58.0, verbose=args.verbose)
    else:
        status, moves, source = solve_optional(board, positions,
                                              timeout=58.0, verbose=args.verbose)

    elapsed = time.time() - start
    if args.verbose:
        print(f"Time: {elapsed:.2f}s, source: {source}", file=sys.stderr)

    if status == 'SOLVED' and moves:
        if source == 'pre_denormalized':
            pass  # already denormalized by the solver
        elif source == 'walks':
            moves = denormalize_walks(board, positions, moves)
        else:
            moves = denormalize_astar(board, positions, moves)

    print(f"STATUS: {status}")
    print(f"MOVES: {len(moves)}")
    if status == 'SOLVED':
        for bid, x, y in moves:
            print(f"{bid} {x} {y}")


if __name__ == '__main__':
    main()

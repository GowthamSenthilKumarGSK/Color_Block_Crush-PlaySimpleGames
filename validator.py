#!/usr/bin/env python3
"""Validates a solution by replaying moves on the board."""
import argparse
import sys

from parser import parse_level
from engine import (make_state, generate_moves, generate_moves_all,
                    _can_exit, _apply_auto_exit, _normalize,
                    _DIR_MAP, is_goal)


def validate(board, positions, moves, verbose=False):
    """Replay moves and check validity. Returns (ok, message)."""
    block_list = board.block_list
    blocks = board.blocks
    w, h = board.w, board.h
    walls = board.walls

    # Build mutable state
    pos = {}
    for bid in block_list:
        if bid in positions:
            pos[bid] = positions[bid]
    exited = set()
    num_exited = 0

    for step, (bid, tx, ty) in enumerate(moves):
        if bid in exited:
            return False, f"Move {step+1}: block {bid} already exited"
        if bid not in pos:
            return False, f"Move {step+1}: block {bid} not found"

        blk = blocks[bid]
        if blk.ice > 0 and num_exited < blk.ice:
            return False, f"Move {step+1}: block {bid} is frozen (need {blk.ice} exits, have {num_exited})"

        bx, by = pos[bid]
        cells = blk.cells

        # Determine direction
        dx = tx - bx
        dy = ty - by
        if dx != 0 and dy != 0:
            return False, f"Move {step+1}: block {bid} diagonal move"
        if dx == 0 and dy == 0:
            return False, f"Move {step+1}: block {bid} no movement"

        if dx > 0:
            ddx, ddy = 1, 0
        elif dx < 0:
            ddx, ddy = -1, 0
        elif dy > 0:
            ddx, ddy = 0, 1
        else:
            ddx, ddy = 0, -1

        # Check directional constraint
        if blk.direction == 'h' and ddy != 0:
            return False, f"Move {step+1}: block {bid} is horizontal-only"
        if blk.direction == 'v' and ddx != 0:
            return False, f"Move {step+1}: block {bid} is vertical-only"

        # Build occupancy (excluding this block)
        occ = set(walls)
        for bid2 in block_list:
            if bid2 in exited or bid2 == bid:
                continue
            bx2, by2 = pos[bid2]
            for cx, cy in blocks[bid2].cells:
                occ.add((bx2 + cx, by2 + cy))

        # Verify path is clear (slide step by step)
        dist = max(abs(dx), abs(dy))
        for s in range(1, dist + 1):
            nx = bx + ddx * s
            ny = by + ddy * s
            for cx, cy in cells:
                ax = nx + cx
                ay = ny + cy
                if ax < 0 or ax >= w or ay < 0 or ay >= h or (ax, ay) in occ:
                    return False, f"Move {step+1}: block {bid} path blocked at ({ax},{ay})"

        # Apply move
        pos[bid] = (tx, ty)

        # Auto-exit
        changed = True
        while changed:
            changed = False
            for bid2 in list(pos.keys()):
                if bid2 in exited:
                    continue
                bx2, by2 = pos[bid2]
                if _can_exit(blocks[bid2], bx2, by2, board, num_exited):
                    exited.add(bid2)
                    num_exited += 1
                    changed = True
                    if verbose:
                        print(f"  Step {step+1}: {bid2} exits at ({bx2},{by2})")
                    break

    # Check goal
    if board.needs_exit <= frozenset(exited):
        return True, f"Valid solution: {len(moves)} moves, {num_exited} exits"
    remaining = board.needs_exit - frozenset(exited)
    return False, f"Not all blocks exited. Remaining: {remaining}"


def main():
    ap = argparse.ArgumentParser(description="Validate a Color Block Crush solution")
    ap.add_argument('level', help='Path to level file')
    ap.add_argument('--solution', help='Solution file (default: read from stdin)')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    board, positions = parse_level(args.level)

    # Read solution
    if args.solution:
        with open(args.solution) as f:
            lines = f.read().strip().split('\n')
    else:
        lines = sys.stdin.read().strip().split('\n')

    # Parse solution
    status_line = lines[0] if lines else ''
    if not status_line.startswith('STATUS:'):
        print("ERROR: First line must be STATUS: ...", file=sys.stderr)
        sys.exit(1)

    status = status_line.split(':')[1].strip()
    if status != 'SOLVED':
        print(f"Status is {status}, nothing to validate")
        sys.exit(0)

    moves_count = int(lines[1].split(':')[1].strip())
    moves = []
    for line in lines[2:2+moves_count]:
        parts = line.strip().split()
        if len(parts) != 3:
            print(f"ERROR: Bad move line: {line}", file=sys.stderr)
            sys.exit(1)
        bid, x, y = parts[0], int(parts[1]), int(parts[2])
        moves.append((bid, x, y))

    ok, msg = validate(board, positions, moves, verbose=args.verbose)
    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()

# Color Block Crush Solver

Three solvers for the **Color Block Crush** sliding block puzzle, where colored polyomino blocks must exit through matching colored gates on the board border. Supports all game mechanics including walls, ice blocks (`ic=N`), and directional constraints (`ar=h`/`ar=v`).

## Quick Start

```bash
# Install dependencies (only needed for Solver 3)
pip install -r requirements.txt

# Run with default solver (complete)
python solve.py tests/test1.txt

# Pick a specific solver
python solve.py tests/test4.txt --solver fast

# Enable debug output
python solve.py tests/test4.txt --solver optional --verbose
```

## Solvers

### Solver 1 — Complete (Reliability)

Prioritizes **always finding a solution** if one exists.

- **Phase 1**: Weighted A\* search with escalating weights (1.5 → 5 → 20) across 3 phases, using 40% of the time budget. Lower weights explore more states for shorter solutions; higher weights trade optimality for speed.
- **Phase 2**: Stochastic hill-climbing with random walks and **no time limit** — runs indefinitely until a solution is found. Uses pool-based restarts from the best states seen so far.

```bash
python solve.py <level.txt> --solver complete
```

### Solver 2 — Fast (Speed)

Prioritizes **returning a valid solution quickly**.

- **Phase 1**: Weighted A\* with only 2 phases (weights 1.5, 15) using 20% of the time budget — spends less time on exact search.
- **Phase 2**: Random walks with a finite deadline — jumps to stochastic search sooner, returns the first solution found.

```bash
python solve.py <level.txt> --solver fast
```

### Solver 3 — Optional (SAT/CSP — Different Formulation)

Uses a **fundamentally different approach**: declarative constraint solving instead of procedural search.

- **Phase 1**: A\*(1.5) for easy/medium puzzles.
- **Phase 2**: Encodes the puzzle as a **constraint satisfaction problem** using the Z3 theorem prover. Variables represent block positions at each timestep; constraints enforce movement rules, no-overlap, wall avoidance, bounds, ice thresholds, and exit conditions. Solves for increasing makespan k=1,2,3... to find the **minimum-length solution**.
- **Phase 3**: Random walks fallback for puzzles too large for SAT.

Inspired by Gozon & Yu (WAFR 2024), *"Optimally Solving Colored Generalized Sliding-Tile Puzzles."*

```bash
python solve.py <level.txt> --solver optional
```

## Output Format

```
STATUS: SOLVED | UNSOLVABLE | TIMEOUT
MOVES: <N>
<block_id> <x> <y>
...
```

- `STATUS`: `SOLVED` if a solution was found, `UNSOLVABLE` if none exists, `TIMEOUT` if the time limit was reached.
- `MOVES`: total number of slides. Each following line specifies the block ID and its new top-left `(x, y)` position after sliding.
- Coordinates use `(0, 0)` at the top-left corner; `x` grows right, `y` grows downward.

## Testing

Run all 3 solvers on all 5 test levels with automatic validation:

```bash
python run_tests.py
```

Validate a single solution:

```bash
python solve.py tests/test3.txt | python validator.py tests/test3.txt
```

### Test Results

| Test | Description | Solver 1 (Complete) | Solver 2 (Fast) | Solver 3 (Optional) |
|------|-------------|---|---|---|
| 1 | Starter (4x5, 2 blocks) | 0.0s, 2 moves | 0.0s, 2 moves | 0.0s, 2 moves |
| 2 | Medium (6x6, 8 blocks) | 0.0s, 10 moves | 0.0s, 10 moves | 0.0s, 10 moves |
| 3 | Walls (6x6, 10 blocks) | ~1s, 25 moves | ~1s, 25 moves | ~1s, 25 moves |
| 4 | Ice + directional (6x6, 14 blocks) | ~30s, ~700 moves | ~20s, ~800 moves | ~35s, ~800 moves |
| 5 | Ice only (3x7, 14 blocks) | ~3s, 44 moves | ~3s, 44 moves | ~3s, 44 moves |

*Test 4 times and move counts vary per run due to stochastic random walks.*

## Requirements

- **Python 3.10+**
- Solvers 1 and 2 use **only the Python standard library** (no external dependencies).
- Solver 3 requires `z3-solver` (installed via `pip install -r requirements.txt`).

## Project Structure

```
.
├── solve.py              # CLI entry point
├── solver_complete.py    # Solver 1: weighted A* + random walks (no time limit)
├── solver_fast.py        # Solver 2: weighted A* + random walks (finite deadline)
├── solver_optional.py    # Solver 3: SAT/CSP with Z3 + A* + random walks
├── engine.py             # Game engine: state representation, move generation, exits
├── fast_walk.py          # Random walk engine with stochastic hill-climbing
├── models.py             # Data structures (Block, Gate, Board)
├── parser.py             # ASCII level file parser
├── validator.py          # Solution validator (replays and verifies moves)
├── run_tests.py          # Automated test runner
├── requirements.txt      # Python dependencies
├── writeup.md            # Detailed algorithm write-up
└── tests/
    ├── test1.txt         # Starter (no modifiers)
    ├── test2.txt         # Medium (no modifiers)
    ├── test3.txt         # Walls (no modifiers)
    ├── test4.txt         # Ice + directional
    └── test5.txt         # Ice only
```

## Algorithm Details

See [writeup.md](writeup.md) for a detailed explanation of:
- State representation and move generation
- How each solver works and why they are configured differently
- The SAT/CSP constraint formulation
- Key design decisions and trade-offs

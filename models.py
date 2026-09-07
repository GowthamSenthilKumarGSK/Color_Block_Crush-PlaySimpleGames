from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Block:
    id: str
    color: str
    cells: tuple[tuple[int, int], ...]  # relative offsets from top-left, sorted
    ice: int = 0
    direction: Optional[str] = None

    @property
    def width(self) -> int:
        return max(c[0] for c in self.cells) + 1

    @property
    def height(self) -> int:
        return max(c[1] for c in self.cells) + 1


@dataclass(frozen=True)
class Gate:
    id: str
    color: str
    side: str        # 'top', 'bottom', 'left', 'right'
    position: int    # start coordinate along the edge
    width: int       # number of cells the gate spans


class Board:
    __slots__ = ('w', 'h', 'walls', 'blocks', 'gates', 'block_list',
                 'block_idx', 'gate_colors', 'gates_by_color',
                 'needs_exit', 'sym_groups')

    def __init__(self, w, h, walls, blocks, gates):
        self.w = w
        self.h = h
        self.walls = walls
        self.blocks = blocks
        self.gates = gates
        self.block_list = sorted(blocks.keys())
        self.block_idx = {bid: i for i, bid in enumerate(self.block_list)}
        self.gate_colors = frozenset(g.color for g in gates)
        self.gates_by_color = {}
        for g in gates:
            self.gates_by_color.setdefault(g.color, []).append(g)
        self.needs_exit = frozenset(
            bid for bid, blk in blocks.items()
            if blk.color in self.gate_colors
        )
        # Symmetry groups: blocks with same (color, cells, ice, direction) are interchangeable
        # sym_groups: list of lists of indices into block_list
        sig_to_group = {}
        for i, bid in enumerate(self.block_list):
            blk = blocks[bid]
            sig = (blk.color, blk.cells, blk.ice, blk.direction)
            sig_to_group.setdefault(sig, []).append(i)
        # Only keep groups with >1 member
        self.sym_groups = [g for g in sig_to_group.values() if len(g) > 1]

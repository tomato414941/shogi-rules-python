# shogi-rules

Self-contained, MIT-licensed implementation of the rules of shogi.

This library implements the game itself, not a player:

- board state (pieces, hands, side to move)
- legal move generation and position transitions (push / pop)
- game termination (checkmate, fourfold repetition, illegal pawn-drop mate)
- SFEN and USI move notation

It has no runtime dependencies. Search, evaluation, and engine concerns are
out of scope.

Correctness is verified against `python-shogi` through oracle tests.
`python-shogi` is GPL-3.0-only, so it is a dev-only dependency used exclusively
by the test suite; it is never imported by the library itself.

A C reimplementation is planned as a separate repository (`shogi-rules-c`),
which will use this library as its test oracle.

## Usage

```python
from shogi_rules import Board

board = Board.startpos()
board.push_usi("7g7f")
print(board.sfen())
print([move.usi() for move in board.legal_moves])
```

## Test

```sh
uv run python -m unittest discover -s tests
```

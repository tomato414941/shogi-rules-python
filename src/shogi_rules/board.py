from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

BLACK = 0
WHITE = 1
BOARD_SIZE = 81

# Piece type constants. Values intentionally match python-shogi's so that
# callers mixing both libraries stay consistent.
PAWN = 1
LANCE = 2
KNIGHT = 3
SILVER = 4
GOLD = 5
BISHOP = 6
ROOK = 7
KING = 8
PROM_PAWN = 9
PROM_LANCE = 10
PROM_KNIGHT = 11
PROM_SILVER = 12
PROM_BISHOP = 13
PROM_ROOK = 14

STARTPOS_SFEN = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"

PROMOTED = {
    PAWN: PROM_PAWN,
    LANCE: PROM_LANCE,
    KNIGHT: PROM_KNIGHT,
    SILVER: PROM_SILVER,
    BISHOP: PROM_BISHOP,
    ROOK: PROM_ROOK,
}
UNPROMOTED = {promoted: base for base, promoted in PROMOTED.items()}
DROP_PIECES = (ROOK, BISHOP, GOLD, SILVER, KNIGHT, LANCE, PAWN)
_STEP_ATTACK_PIECES = (
    PAWN,
    KNIGHT,
    SILVER,
    GOLD,
    KING,
    PROM_PAWN,
    PROM_LANCE,
    PROM_KNIGHT,
    PROM_SILVER,
    PROM_BISHOP,
    PROM_ROOK,
)
PIECE_TO_SFEN = {
    PAWN: "P",
    LANCE: "L",
    KNIGHT: "N",
    SILVER: "S",
    GOLD: "G",
    BISHOP: "B",
    ROOK: "R",
    KING: "K",
}
SFEN_TO_PIECE = {value: key for key, value in PIECE_TO_SFEN.items()}
# Upper case for black, lower case for white.
_SFEN_LETTERS = {
    **{letter: (BLACK, piece_type) for piece_type, letter in PIECE_TO_SFEN.items()},
    **{letter.lower(): (WHITE, piece_type) for piece_type, letter in PIECE_TO_SFEN.items()},
}
_SFEN_FIELD_BREAK = re.compile(r"[ \t\n\v\f\r]+")
# A move from one square to another, "+" after it to promote, or a drop of a piece onto a square.
_USI_MOVE = re.compile(r"([1-9][a-i])([1-9][a-i])(\+?)|([PLNSGBR])\*([1-9][a-i])")
# The pieces of a shogi set besides the kings, promoted ones counted as unpromoted.
_PIECE_SET = {PAWN: 18, LANCE: 4, KNIGHT: 4, SILVER: 4, GOLD: 4, BISHOP: 2, ROOK: 2}
_PIECE_NAMES = {
    PAWN: "pawn",
    LANCE: "lance",
    KNIGHT: "knight",
    SILVER: "silver",
    GOLD: "gold",
    BISHOP: "bishop",
    ROOK: "rook",
}
_COLOR_NAMES = ("black", "white")
_MAX_MOVE_NUMBER = 1_000_000_000
# The kind each signed piece counts as in a set, indexed by the signed piece plus PROM_ROOK; 0 for empty squares and
# kings.
_SET_KINDS = tuple(
    0 if abs(piece) in (0, KING) else UNPROMOTED.get(abs(piece), abs(piece))
    for piece in range(-PROM_ROOK, PROM_ROOK + 1)
)
# Pieces that can never move from the farthest rank of their side.
_STUCK_ON_LAST_RANK = (frozenset((PAWN, LANCE, KNIGHT)), frozenset((-PAWN, -LANCE, -KNIGHT)))


@dataclass(frozen=True, slots=True)
class Move:
    from_square: int | None
    to_square: int | None
    promotion: bool = False
    drop_piece_type: int | None = None

    @classmethod
    def from_usi(cls, usi: str) -> Move:
        match = _USI_MOVE.fullmatch(usi)
        if match is None:
            raise ValueError(f"invalid usi move: {usi!r}")
        from_name, to_name, promotion, piece_symbol, drop_name = match.groups()
        if piece_symbol:
            return cls(
                from_square=None,
                to_square=square_from_name(drop_name),
                drop_piece_type=SFEN_TO_PIECE[piece_symbol],
            )
        return cls(
            from_square=square_from_name(from_name),
            to_square=square_from_name(to_name),
            promotion=promotion == "+",
        )

    def usi(self) -> str:
        if self.from_square is None:
            if self.drop_piece_type is None:
                raise ValueError("drop moves require a piece type")
            return f"{PIECE_TO_SFEN[self.drop_piece_type]}*{square_name(self.to_square)}"
        suffix = "+" if self.promotion else ""
        return f"{square_name(self.from_square)}{square_name(self.to_square)}{suffix}"


@dataclass(frozen=True, slots=True)
class Piece:
    piece_type: int
    color: int


class Termination(Enum):
    # The side to move has no legal move, which loses in shogi even when it is not in check.
    CHECKMATE = "checkmate"
    # The same position for the fourth time: a draw.
    REPETITION = "repetition"
    # The same position for the fourth time while one side gave check with every move: that side loses.
    PERPETUAL_CHECK = "perpetual_check"


@dataclass(frozen=True, slots=True)
class Outcome:
    termination: Termination
    winner: int | None


@dataclass(frozen=True, slots=True)
class _Undo:
    move: Move
    moved_piece: int
    captured_piece: int
    previous_turn: int
    previous_move_number: int
    previous_hash: int


class Board:
    def __init__(
        self,
        board: list[int] | None = None,
        *,
        turn: int = BLACK,
        hands: dict[int, dict[int, int]] | None = None,
        move_number: int = 1,
    ) -> None:
        self.board = board or [0] * BOARD_SIZE
        self.turn = turn
        self.hands = hands or {BLACK: {}, WHITE: {}}
        self.move_number = move_number
        self._check_values()
        self._king_squares = self._find_king_squares()
        self._check_position()
        self._hash = self._compute_hash()
        self.move_stack: list[_Undo] = []
        # How many times each position has occurred since the last null move, one count per stretch between them.
        self._position_counts: list[dict[int, int]] = [{self._hash: 1}]

    @classmethod
    def startpos(cls) -> Board:
        return cls.from_sfen(STARTPOS_SFEN)

    @classmethod
    def from_sfen(cls, sfen: str) -> Board:
        # Fields are separated by runs of ASCII whitespace; the move number may be left out.
        fields = [field for field in _SFEN_FIELD_BREAK.split(sfen) if field]
        if len(fields) not in (3, 4):
            raise ValueError(f"sfen needs a board, a side to move, hands and optionally a move number: {sfen!r}")
        board_part, turn_part, hand_part, *move_part = fields
        if turn_part not in ("b", "w"):
            raise ValueError(f"sfen side to move must be b or w: {sfen!r}")
        if move_part and not _is_decimal(move_part[0]):
            raise ValueError(f"sfen move number must be a decimal number: {sfen!r}")
        board = _parse_board(board_part, sfen)
        hands = _parse_hands(hand_part, sfen)
        try:
            return cls(
                board,
                turn=BLACK if turn_part == "b" else WHITE,
                hands=hands,
                move_number=int(move_part[0]) if move_part else 1,
            )
        except ValueError as error:
            raise ValueError(f"{error}: {sfen!r}") from None

    def sfen(self) -> str:
        rows: list[str] = []
        for rank in range(9):
            empty = 0
            row = ""
            for file_index in range(9):
                piece = self.board[rank * 9 + file_index]
                if piece == 0:
                    empty += 1
                    continue
                if empty:
                    row += str(empty)
                    empty = 0
                row += _piece_sfen(piece)
            if empty:
                row += str(empty)
            rows.append(row)
        hand = _hands_sfen(self.hands)
        return f"{'/'.join(rows)} {'b' if self.turn == BLACK else 'w'} {hand} {self.move_number}"

    def reset(self) -> None:
        self.set_sfen(STARTPOS_SFEN)

    def set_sfen(self, sfen: str) -> None:
        other = Board.from_sfen(sfen)
        self.board = other.board
        self.turn = other.turn
        self.hands = other.hands
        self.move_number = other.move_number
        self._king_squares = other._king_squares
        self._hash = other._hash
        self.move_stack = []
        self._position_counts = other._position_counts

    @property
    def legal_moves(self) -> list[Move]:
        return self.generate_legal_moves()

    @property
    def pieces_in_hand(self) -> dict[int, dict[int, int]]:
        return self.hands

    @property
    def king_squares(self) -> list[int]:
        return self._king_squares

    def piece_at(self, square: int) -> Piece | None:
        signed_piece = self.board[square]
        if signed_piece == 0:
            return None
        return Piece(abs(signed_piece), _piece_color(signed_piece))

    def generate_legal_moves(self) -> list[Move]:
        moves: list[Move] = []
        for move in self._pseudo_legal_moves_for_legality_check():
            if self._is_illegal_pawn_drop_mate(move):
                continue
            self._push(move)
            try:
                if not self.is_attacked_by(self.turn, self._king_squares[1 - self.turn]):
                    moves.append(move)
            finally:
                self._pop()
        return moves

    def has_legal_move(self) -> bool:
        for move in self._pseudo_legal_moves_for_legality_check():
            if self._is_illegal_pawn_drop_mate(move):
                continue
            self._push(move)
            try:
                if not self.is_attacked_by(self.turn, self._king_squares[1 - self.turn]):
                    return True
            finally:
                self._pop()
        return False

    def legal_move_usis(self) -> set[str]:
        return {move.usi() for move in self.legal_moves}

    def legal_tactical_moves(self, *, include_quiet_checks: bool = False) -> list[Move]:
        moves: list[Move] = []
        pseudo_moves = self._pseudo_legal_moves() if include_quiet_checks else self._pseudo_noisy_moves()
        for move in pseudo_moves:
            if self._is_illegal_pawn_drop_mate(move):
                continue
            tactical = move.promotion or (move.to_square is not None and self.board[move.to_square] != 0)
            if not tactical and not include_quiet_checks:
                continue
            self._push(move)
            try:
                if self.is_attacked_by(self.turn, self._king_squares[1 - self.turn]):
                    continue
                if tactical or self.is_check():
                    moves.append(move)
            finally:
                self._pop()
        return moves

    # Plays a move given as text only if it is legal.
    def push_usi(self, usi: str) -> None:
        move = Move.from_usi(usi)
        if move not in self.generate_legal_moves():
            raise ValueError(f"illegal move {usi!r} in {self.sfen()!r}")
        self._play(move)

    # Plays a move without checking that it is legal, which is the caller's to ensure (a move from legal_moves is).
    # Only a move that would break the board raises ValueError, leaving the position unchanged.
    def push(self, move: Move) -> None:
        self._check_move(move)
        self._play(move)

    def pop(self) -> None:
        move = self.move_stack[-1].move
        if move.from_square is None and move.to_square is None:
            self._position_counts.pop()
        else:
            self._position_counts[-1][self._hash] -= 1
        self._pop()

    def _play(self, move: Move) -> None:
        self._push(move)
        if move.from_square is None and move.to_square is None:
            self._position_counts.append({self._hash: 1})
        else:
            counts = self._position_counts[-1]
            counts[self._hash] = counts.get(self._hash, 0) + 1

    # A null move has no squares. Any other move goes to a square on the board without taking a king: a piece of the
    # side to move from a square, taking no piece of its own and promoting only if it can, or a piece in hand dropped
    # onto an empty square.
    def _check_move(self, move: Move) -> None:
        from_square, to_square = move.from_square, move.to_square
        if to_square is None:
            if from_square is None and not move.promotion and move.drop_piece_type is None:
                return
            raise ValueError("a move needs a square to go to")
        if not 0 <= to_square < BOARD_SIZE:
            raise ValueError(f"square {to_square} is not on the board")
        target = self.board[to_square]
        if abs(target) == KING:
            raise ValueError("king captures are not legal moves")
        black = self.turn == BLACK
        if from_square is None:
            if move.drop_piece_type not in _PIECE_SET:
                raise ValueError("drop moves require a piece type that can be in hand")
            if move.promotion:
                raise ValueError("dropped pieces cannot promote")
            if target:
                raise ValueError(f"cannot drop onto the occupied square {square_name(to_square)}")
            if self.hands[self.turn].get(move.drop_piece_type, 0) <= 0:
                raise ValueError("cannot remove a piece that is not in hand")
            return
        if move.drop_piece_type is not None:
            raise ValueError("a move from a square drops no piece")
        if not 0 <= from_square < BOARD_SIZE:
            raise ValueError(f"square {from_square} is not on the board")
        piece = self.board[from_square]
        if not piece or (piece > 0) != black:
            raise ValueError(f"the side to move has no piece on {square_name(from_square)}")
        if target and (target > 0) == black:
            raise ValueError(f"the side to move cannot take its own piece on {square_name(to_square)}")
        if move.promotion and abs(piece) not in PROMOTED:
            raise ValueError(f"the piece on {square_name(from_square)} cannot promote")

    def _push(self, move: Move) -> None:
        previous_turn = self.turn
        previous_move_number = self.move_number
        previous_hash = self._hash
        if move.from_square is None and move.to_square is None:
            self._hash ^= _ZOBRIST_TURN
            self.turn = 1 - self.turn
            self.move_number += 1
            self.move_stack.append(_Undo(move, 0, 0, previous_turn, previous_move_number, previous_hash))
            return
        captured_piece = self.board[move.to_square]
        if move.from_square is None:
            moved_piece = _signed_piece(previous_turn, move.drop_piece_type)
            self._remove_hand(previous_turn, move.drop_piece_type)
            self.board[move.to_square] = moved_piece
            self._hash ^= _ZOBRIST_BOARD[moved_piece + 14][move.to_square]
        else:
            moved_piece = self.board[move.from_square]
            self._hash ^= _ZOBRIST_BOARD[moved_piece + 14][move.from_square]
            self.board[move.from_square] = 0
            if captured_piece:
                self._hash ^= _ZOBRIST_BOARD[captured_piece + 14][move.to_square]
                self._add_hand(previous_turn, _unpromoted(abs(captured_piece)))
            piece_type = PROMOTED[abs(moved_piece)] if move.promotion else abs(moved_piece)
            new_piece = _signed_piece(previous_turn, piece_type)
            self.board[move.to_square] = new_piece
            self._hash ^= _ZOBRIST_BOARD[new_piece + 14][move.to_square]
            if abs(moved_piece) == KING:
                self._king_squares[previous_turn] = move.to_square
        self._hash ^= _ZOBRIST_TURN
        self.turn = 1 - self.turn
        self.move_number += 1
        self.move_stack.append(_Undo(move, moved_piece, captured_piece, previous_turn, previous_move_number, previous_hash))

    def _pop(self) -> None:
        undo = self.move_stack.pop()
        move = undo.move
        self.turn = undo.previous_turn
        self.move_number = undo.previous_move_number
        if move.from_square is None and move.to_square is None:
            self._hash = undo.previous_hash
            return
        if move.from_square is None:
            if move.drop_piece_type is None:
                raise ValueError("drop moves require a piece type")
            self.board[move.to_square] = undo.captured_piece
            self._add_hand(self.turn, move.drop_piece_type)
            self._hash = undo.previous_hash
            return
        self.board[move.from_square] = undo.moved_piece
        self.board[move.to_square] = undo.captured_piece
        if abs(undo.moved_piece) == KING:
            self._king_squares[self.turn] = move.from_square
        if undo.captured_piece:
            self._remove_hand(self.turn, _unpromoted(abs(undo.captured_piece)))
        self._hash = undo.previous_hash

    def is_attacked_by(self, color: int, square: int) -> bool:
        board = self.board
        for from_square, signed_piece in _STEP_ATTACK_SOURCES[color][square]:
            if board[from_square] == signed_piece:
                return True
        for ray_squares, signed_pieces in _RAY_ATTACK_SOURCES[color][square]:
            for from_square in ray_squares:
                found_piece = board[from_square]
                if found_piece:
                    if found_piece in signed_pieces:
                        return True
                    break
        return False

    def _attackers_by(self, color: int, square: int) -> list[int]:
        attackers: list[int] = []
        board = self.board
        for from_square, signed_piece in _STEP_ATTACK_SOURCES[color][square]:
            if board[from_square] == signed_piece:
                attackers.append(from_square)
        for ray_squares, signed_pieces in _RAY_ATTACK_SOURCES[color][square]:
            for from_square in ray_squares:
                found_piece = board[from_square]
                if found_piece:
                    if found_piece in signed_pieces:
                        attackers.append(from_square)
                    break
        return attackers

    def is_check(self) -> bool:
        return self.is_attacked_by(1 - self.turn, self.king_square(self.turn))

    def is_game_over(self) -> bool:
        return self.outcome() is not None

    # The current position has occurred four times since the board was set or the last null move.
    def is_fourfold_repetition(self) -> bool:
        return self._position_counts[-1].get(self._hash, 0) >= 4

    def outcome(self) -> Outcome | None:
        if self.is_fourfold_repetition():
            checker = self._perpetual_checker()
            if checker is None:
                return Outcome(Termination.REPETITION, None)
            return Outcome(Termination.PERPETUAL_CHECK, 1 - checker)
        if not self.has_legal_move():
            return Outcome(Termination.CHECKMATE, 1 - self.turn)
        return None

    # The side whose every move since the first of the last four occurrences of this position gave check, or None
    # when neither or both did. The moves are taken back and played again to see each position on the way.
    def _perpetual_checker(self) -> int | None:
        current = self._hash
        moves: list[Move] = []
        occurrences = 1
        while occurrences < 4:
            moves.append(self.move_stack[-1].move)
            self._pop()
            if self._hash == current:
                occurrences += 1
        gave_check = [True, True]
        for move in reversed(moves):
            mover = self.turn
            self._push(move)
            gave_check[mover] = gave_check[mover] and self.is_check()
        if gave_check[BLACK] == gave_check[WHITE]:
            return None
        return BLACK if gave_check[BLACK] else WHITE

    def zobrist_hash(self) -> int:
        return self._hash

    def king_square(self, color: int) -> int:
        return self._king_squares[color]

    def _check_values(self) -> None:
        board = self.board
        if len(board) != BOARD_SIZE or min(board) < -PROM_ROOK or max(board) > PROM_ROOK:
            raise ValueError("board must hold 81 squares, each empty or a piece")
        if self.turn not in (BLACK, WHITE):
            raise ValueError("turn must be BLACK or WHITE")
        if set(self.hands) != {BLACK, WHITE} or any(
            piece_type not in _PIECE_SET or count < 0 for hand in self.hands.values() for piece_type, count in hand.items()
        ):
            raise ValueError("hands must count, for each side, pieces that can be dropped")
        if not 1 <= self.move_number <= _MAX_MOVE_NUMBER:
            raise ValueError(f"move number must be from 1 to {_MAX_MOVE_NUMBER}")

    def _find_king_squares(self) -> list[int]:
        board = self.board
        if board.count(KING) != 1 or board.count(-KING) != 1:
            raise ValueError("each side needs exactly one king")
        return [board.index(KING), board.index(-KING)]

    # A position that can occur in a game: no more pieces than a set has, no two unpromoted pawns of a side on a
    # file, no piece where it can never move, and the side not to move not in check.
    def _check_position(self) -> None:
        board = self.board
        counts = [0] * (ROOK + 1)
        for piece in board:
            if piece:
                counts[_SET_KINDS[piece + PROM_ROOK]] += 1
        for hand in self.hands.values():
            for piece_type, count in hand.items():
                counts[piece_type] += count
        for piece_type, limit in _PIECE_SET.items():
            if counts[piece_type] > limit:
                raise ValueError(f"{counts[piece_type]} {_PIECE_NAMES[piece_type]}s, more than the {limit} in a set")
        for file_index in range(9):
            column = board[file_index::9]
            for color, pawn in ((BLACK, PAWN), (WHITE, -PAWN)):
                if column.count(pawn) > 1:
                    raise ValueError(f"{_COLOR_NAMES[color]} has two pawns on file {9 - file_index}")
        if (
            not _STUCK_ON_LAST_RANK[BLACK].isdisjoint(board[:9])
            or KNIGHT in board[9:18]
            or not _STUCK_ON_LAST_RANK[WHITE].isdisjoint(board[72:])
            or -KNIGHT in board[63:72]
        ):
            square = next(
                square
                for square, piece in enumerate(board)
                if piece and not _can_move_without_promotion(abs(piece), square, _piece_color(piece))
            )
            piece = board[square]
            raise ValueError(
                f"{_COLOR_NAMES[_piece_color(piece)]} {_PIECE_NAMES[abs(piece)]} on {square_name(square)} can never move"
            )
        if self.is_attacked_by(self.turn, self._king_squares[1 - self.turn]):
            raise ValueError("the side not to move is in check")

    def _pseudo_legal_moves(self) -> list[Move]:
        moves: list[Move] = []
        board = self.board
        turn = self.turn
        turn_is_black = turn == BLACK
        for from_square, signed_piece in enumerate(board):
            if signed_piece == 0 or (signed_piece > 0) != turn_is_black:
                continue
            piece_type = abs(signed_piece)
            for ray in _MOVE_RAYS[turn][piece_type][from_square]:
                for to_square in ray:
                    target = board[to_square]
                    if target and (target > 0) == turn_is_black:
                        break
                    if abs(target) == KING:
                        break
                    _append_promotion_variants(moves, from_square, to_square, piece_type, turn)
                    if target:
                        break
        moves.extend(self._drop_moves())
        return moves

    def _pseudo_legal_moves_for_legality_check(self) -> list[Move]:
        king_square = self._king_squares[self.turn]
        attackers = self._attackers_by(1 - self.turn, king_square)
        if not attackers:
            return self._pseudo_legal_moves()

        moves: list[Move] = []
        checker_square = attackers[0]
        block_squares = _block_squares_between(king_square, checker_square)
        for move in self._pseudo_legal_moves():
            if move.from_square == king_square:
                moves.append(move)
                continue
            if len(attackers) > 1:
                continue
            if move.to_square == checker_square or move.to_square in block_squares:
                moves.append(move)
        return moves

    def _pseudo_noisy_moves(self) -> list[Move]:
        moves: list[Move] = []
        board = self.board
        turn = self.turn
        turn_is_black = turn == BLACK
        for from_square, signed_piece in enumerate(board):
            if signed_piece == 0 or (signed_piece > 0) != turn_is_black:
                continue
            piece_type = abs(signed_piece)
            for ray in _MOVE_RAYS[turn][piece_type][from_square]:
                for to_square in ray:
                    target = board[to_square]
                    if target and (target > 0) == turn_is_black:
                        break
                    if abs(target) == KING:
                        break
                    if target:
                        _append_promotion_variants(moves, from_square, to_square, piece_type, turn)
                        break
                    if piece_type in PROMOTED and (
                        _in_promotion_zone(from_square, turn) or _in_promotion_zone(to_square, turn)
                    ):
                        moves.append(Move(from_square, to_square, promotion=True))
        return moves

    def _drop_moves(self) -> list[Move]:
        moves: list[Move] = []
        hand = self.hands[self.turn]
        if not hand:
            return moves
        board = self.board
        turn = self.turn
        empty_squares = [square for square, occupied in enumerate(board) if not occupied]
        pawn = _signed_piece(turn, PAWN)
        pawn_files = {square % 9 for square, signed_piece in enumerate(board) if signed_piece == pawn}
        for piece_type, count in hand.items():
            if count <= 0:
                continue
            for to_square in empty_squares:
                if not _can_drop_on_square(piece_type, to_square, turn):
                    continue
                if piece_type == PAWN and to_square % 9 in pawn_files:
                    continue
                moves.append(Move(None, to_square, drop_piece_type=piece_type))
        return moves

    def _is_illegal_pawn_drop_mate(self, move: Move) -> bool:
        if move.from_square is not None or move.drop_piece_type != PAWN:
            return False
        self._push(move)
        try:
            defender = self.turn
            if not self.is_attacked_by(1 - defender, self.king_square(defender)):
                return False
            return not self._has_legal_evasion_without_pawn_drop_mate_check()
        finally:
            self._pop()

    def _has_legal_evasion_without_pawn_drop_mate_check(self) -> bool:
        for response in self._pseudo_legal_moves():
            self._push(response)
            try:
                if not self.is_attacked_by(self.turn, self.king_square(1 - self.turn)):
                    return True
            finally:
                self._pop()
        return False

    def _piece_attacks_square(self, from_square: int, piece_type: int, color: int, target_square: int) -> bool:
        for df, dr in _step_directions(piece_type, color):
            if _offset(from_square, df, dr) == target_square:
                return True
        for df, dr in _slide_directions(piece_type, color):
            square = _offset(from_square, df, dr)
            while square is not None:
                if square == target_square:
                    return True
                if self.board[square]:
                    break
                square = _offset(square, df, dr)
        return False

    def _add_hand(self, color: int, piece_type: int) -> None:
        old_count = self.hands[color].get(piece_type, 0)
        new_count = old_count + 1
        hashes = _ZOBRIST_HAND[color][piece_type]
        if old_count > 0:
            self._hash ^= hashes[old_count] if old_count < len(hashes) else _hand_hash(color, piece_type, old_count)
        self._hash ^= hashes[new_count] if new_count < len(hashes) else _hand_hash(color, piece_type, new_count)
        self.hands[color][piece_type] = new_count

    def _remove_hand(self, color: int, piece_type: int) -> None:
        count = self.hands[color].get(piece_type, 0)
        if count <= 0:
            raise ValueError("cannot remove a piece that is not in hand")
        hashes = _ZOBRIST_HAND[color][piece_type]
        self._hash ^= hashes[count] if count < len(hashes) else _hand_hash(color, piece_type, count)
        if count > 1:
            self._hash ^= hashes[count - 1] if count - 1 < len(hashes) else _hand_hash(color, piece_type, count - 1)
        if count == 1:
            self.hands[color].pop(piece_type, None)
        else:
            self.hands[color][piece_type] = count - 1

    def _compute_hash(self) -> int:
        value = _ZOBRIST_TURN if self.turn == WHITE else 0
        for square, signed_piece in enumerate(self.board):
            if signed_piece:
                value ^= _board_hash(signed_piece, square)
        for color in (BLACK, WHITE):
            for piece_type, count in self.hands[color].items():
                value ^= _hand_hash(color, piece_type, count)
        return value


def square_name(square: int) -> str:
    file_number = 9 - (square % 9)
    rank = chr(ord("a") + square // 9)
    return f"{file_number}{rank}"


def square_from_name(name: str) -> int:
    if len(name) != 2 or not "1" <= name[0] <= "9" or not "a" <= name[1] <= "i":
        raise ValueError(f"invalid square name: {name!r}")
    file_index = 9 - int(name[0])
    rank = ord(name[1]) - ord("a")
    return rank * 9 + file_index


def _is_decimal(text: str) -> bool:
    return all("0" <= char <= "9" for char in text)


# Nine ranks from a to i separated by "/", each nine squares from file 9 to 1: a digit for that many empty squares,
# a letter for a piece, "+" before a letter for a promoted one.
def _parse_board(board_part: str, sfen: str) -> list[int]:
    ranks = board_part.split("/")
    if len(ranks) != 9:
        raise ValueError(f"sfen board needs 9 ranks: {sfen!r}")
    board = [0] * BOARD_SIZE
    for rank, text in enumerate(ranks):
        file_index = 0
        promoted = False
        for char in text:
            if not promoted:
                if char == "+":
                    promoted = True
                    continue
                if "1" <= char <= "9":
                    file_index += int(char)
                    continue
            letter = _SFEN_LETTERS.get(char)
            if letter is None:
                raise ValueError(f"sfen board has an invalid piece {char!r}: {sfen!r}")
            color, piece_type = letter
            if promoted:
                if piece_type not in PROMOTED:
                    raise ValueError(f"sfen board promotes a piece that cannot promote: {sfen!r}")
                piece_type = PROMOTED[piece_type]
                promoted = False
            if file_index < 9:
                board[rank * 9 + file_index] = _signed_piece(color, piece_type)
            file_index += 1
        if promoted:
            raise ValueError(f"sfen board ends a rank with '+': {sfen!r}")
        if file_index != 9:
            raise ValueError(f"sfen board rank {chr(ord('a') + rank)} does not have 9 squares: {sfen!r}")
    return board


# "-" for none, or each kind a side holds once, its count before it when more than one.
def _parse_hands(hand_part: str, sfen: str) -> dict[int, dict[int, int]]:
    hands: dict[int, dict[int, int]] = {BLACK: {}, WHITE: {}}
    if hand_part == "-":
        return hands
    count_text = ""
    for char in hand_part:
        if "0" <= char <= "9":
            count_text += char
            continue
        if char not in _SFEN_LETTERS or _SFEN_LETTERS[char][1] == KING:
            raise ValueError(f"sfen hands have an invalid piece {char!r}: {sfen!r}")
        color, piece_type = _SFEN_LETTERS[char]
        count = int(count_text) if count_text else 1
        if count == 0:
            raise ValueError(f"sfen hands hold none of {char!r}: {sfen!r}")
        if piece_type in hands[color]:
            raise ValueError(f"sfen hands list {char!r} twice: {sfen!r}")
        hands[color][piece_type] = count
        count_text = ""
    if count_text:
        raise ValueError(f"sfen hands end in a count: {sfen!r}")
    return hands


def _hands_sfen(hands: dict[int, dict[int, int]]) -> str:
    parts: list[str] = []
    for color, transform in ((BLACK, str.upper), (WHITE, str.lower)):
        for piece_type in DROP_PIECES:
            count = hands[color].get(piece_type, 0)
            if count <= 0:
                continue
            prefix = "" if count == 1 else str(count)
            parts.append(prefix + transform(PIECE_TO_SFEN[piece_type]))
    return "".join(parts) or "-"


def _piece_sfen(signed_piece: int) -> str:
    piece_type = abs(signed_piece)
    base = _unpromoted(piece_type)
    symbol = PIECE_TO_SFEN[base]
    if signed_piece < 0:
        symbol = symbol.lower()
    return f"+{symbol}" if piece_type in UNPROMOTED else symbol


def _signed_piece(color: int, piece_type: int) -> int:
    return piece_type if color == BLACK else -piece_type


def _piece_color(signed_piece: int) -> int:
    return BLACK if signed_piece > 0 else WHITE


def _unpromoted(piece_type: int) -> int:
    return UNPROMOTED.get(piece_type, piece_type)


def _offset(square: int, df: int, dr: int) -> int | None:
    file_index = square % 9 + df
    rank = square // 9 + dr
    if not (0 <= file_index < 9 and 0 <= rank < 9):
        return None
    return rank * 9 + file_index


def _forward(color: int) -> int:
    return -1 if color == BLACK else 1


def _step_directions(piece_type: int, color: int) -> tuple[tuple[int, int], ...]:
    forward = _forward(color)
    backward = -forward
    if piece_type == PAWN:
        return ((0, forward),)
    if piece_type == KNIGHT:
        return ((-1, 2 * forward), (1, 2 * forward))
    if piece_type == SILVER:
        return ((-1, forward), (0, forward), (1, forward), (-1, backward), (1, backward))
    if piece_type in {GOLD, PROM_PAWN, PROM_LANCE, PROM_KNIGHT, PROM_SILVER}:
        return ((-1, forward), (0, forward), (1, forward), (-1, 0), (1, 0), (0, backward))
    if piece_type == KING:
        return ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
    if piece_type == PROM_BISHOP:
        return ((0, -1), (-1, 0), (1, 0), (0, 1))
    if piece_type == PROM_ROOK:
        return ((-1, -1), (1, -1), (-1, 1), (1, 1))
    return ()


def _slide_directions(piece_type: int, color: int) -> tuple[tuple[int, int], ...]:
    if piece_type == LANCE:
        return ((0, _forward(color)),)
    if piece_type in {BISHOP, PROM_BISHOP}:
        return ((-1, -1), (1, -1), (-1, 1), (1, 1))
    if piece_type in {ROOK, PROM_ROOK}:
        return ((0, -1), (-1, 0), (1, 0), (0, 1))
    return ()


def _append_promotion_variants(
    moves: list[Move],
    from_square: int,
    to_square: int,
    piece_type: int,
    color: int,
) -> None:
    if piece_type not in PROMOTED:
        moves.append(Move(from_square, to_square))
        return
    can_promote = _in_promotion_zone(from_square, color) or _in_promotion_zone(to_square, color)
    if not can_promote:
        moves.append(Move(from_square, to_square))
        return
    if not _can_move_without_promotion(piece_type, to_square, color):
        moves.append(Move(from_square, to_square, promotion=True))
        return
    moves.append(Move(from_square, to_square))
    moves.append(Move(from_square, to_square, promotion=True))


def _in_promotion_zone(square: int, color: int) -> bool:
    rank = square // 9
    return rank <= 2 if color == BLACK else rank >= 6


def _can_move_without_promotion(piece_type: int, to_square: int, color: int) -> bool:
    rank = to_square // 9
    if piece_type in {PAWN, LANCE}:
        return rank != (0 if color == BLACK else 8)
    if piece_type == KNIGHT:
        return rank > 1 if color == BLACK else rank < 7
    return True


def _can_drop_on_square(piece_type: int, to_square: int, color: int) -> bool:
    return _can_move_without_promotion(piece_type, to_square, color)


def _block_squares_between(king_square: int, checker_square: int) -> set[int]:
    king_file = king_square % 9
    king_rank = king_square // 9
    checker_file = checker_square % 9
    checker_rank = checker_square // 9
    file_delta = checker_file - king_file
    rank_delta = checker_rank - king_rank
    if file_delta == 0:
        file_step = 0
    elif rank_delta == 0:
        file_step = 1 if file_delta > 0 else -1
    elif abs(file_delta) == abs(rank_delta):
        file_step = 1 if file_delta > 0 else -1
    else:
        return set()
    if rank_delta == 0:
        rank_step = 0
    elif file_delta == 0 or abs(file_delta) == abs(rank_delta):
        rank_step = 1 if rank_delta > 0 else -1
    else:
        return set()
    if file_step == 0 and rank_step == 0:
        return set()

    squares: set[int] = set()
    file_index = king_file + file_step
    rank = king_rank + rank_step
    while (file_index, rank) != (checker_file, checker_rank):
        squares.add(rank * 9 + file_index)
        file_index += file_step
        rank += rank_step
    return squares


def _splitmix64(value: int) -> int:
    value = (value + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    return value ^ (value >> 31)


def _build_board_hashes() -> list[list[int]]:
    return [
        [_splitmix64(10_000 + piece_index * BOARD_SIZE + square) for square in range(BOARD_SIZE)]
        for piece_index in range(29)
    ]


def _build_hand_hashes() -> dict[int, dict[int, list[int]]]:
    return {
        color: {
            piece_type: [_splitmix64(100_000 + color * 10_000 + piece_type * 100 + count) for count in range(32)]
            for piece_type in DROP_PIECES
        }
        for color in (BLACK, WHITE)
    }


def _board_hash(signed_piece: int, square: int) -> int:
    return _ZOBRIST_BOARD[signed_piece + 14][square]


def _hand_hash(color: int, piece_type: int, count: int) -> int:
    if count <= 0:
        return 0
    hashes = _ZOBRIST_HAND[color][piece_type]
    if count >= len(hashes):
        return _splitmix64(200_000 + color * 10_000 + piece_type * 100 + count)
    return hashes[count]


def _ray_squares(square: int, df: int, dr: int) -> tuple[int, ...]:
    squares: list[int] = []
    current = _offset(square, df, dr)
    while current is not None:
        squares.append(current)
        current = _offset(current, df, dr)
    return tuple(squares)


def _build_step_attack_sources() -> dict[int, list[list[tuple[int, int]]]]:
    sources = {BLACK: [[] for _ in range(BOARD_SIZE)], WHITE: [[] for _ in range(BOARD_SIZE)]}
    for color in (BLACK, WHITE):
        for target_square in range(BOARD_SIZE):
            target_sources = sources[color][target_square]
            for piece_type in _STEP_ATTACK_PIECES:
                for df, dr in _step_directions(piece_type, color):
                    from_square = _offset(target_square, -df, -dr)
                    if from_square is not None:
                        target_sources.append((from_square, _signed_piece(color, piece_type)))
    return sources


def _build_ray_attack_sources() -> dict[int, list[list[tuple[tuple[int, ...], tuple[int, ...]]]]]:
    sources = {BLACK: [[] for _ in range(BOARD_SIZE)], WHITE: [[] for _ in range(BOARD_SIZE)]}
    common_rays = (
        (-1, -1, (BISHOP, PROM_BISHOP)),
        (1, -1, (BISHOP, PROM_BISHOP)),
        (-1, 1, (BISHOP, PROM_BISHOP)),
        (1, 1, (BISHOP, PROM_BISHOP)),
        (0, -1, (ROOK, PROM_ROOK)),
        (-1, 0, (ROOK, PROM_ROOK)),
        (1, 0, (ROOK, PROM_ROOK)),
        (0, 1, (ROOK, PROM_ROOK)),
    )
    for color in (BLACK, WHITE):
        color_rays = (*common_rays, (0, -_forward(color), (LANCE,)))
        for target_square in range(BOARD_SIZE):
            sources[color][target_square] = [
                (
                    _ray_squares(target_square, df, dr),
                    tuple(_signed_piece(color, piece_type) for piece_type in piece_types),
                )
                for df, dr, piece_types in color_rays
            ]
    return sources


def _build_move_rays() -> dict[int, dict[int, list[tuple[tuple[int, ...], ...]]]]:
    piece_types = tuple(PIECE_TO_SFEN) + tuple(UNPROMOTED)
    move_rays = {
        color: {piece_type: [[] for _ in range(BOARD_SIZE)] for piece_type in piece_types}
        for color in (BLACK, WHITE)
    }
    for color in (BLACK, WHITE):
        for piece_type in piece_types:
            for square in range(BOARD_SIZE):
                rays: list[tuple[int, ...]] = []
                for df, dr in _step_directions(piece_type, color):
                    target = _offset(square, df, dr)
                    if target is not None:
                        rays.append((target,))
                for df, dr in _slide_directions(piece_type, color):
                    rays.append(_ray_squares(square, df, dr))
                move_rays[color][piece_type][square] = tuple(rays)
    return move_rays


_STEP_ATTACK_SOURCES = _build_step_attack_sources()
_RAY_ATTACK_SOURCES = _build_ray_attack_sources()
_MOVE_RAYS = _build_move_rays()
_ZOBRIST_BOARD = _build_board_hashes()
_ZOBRIST_HAND = _build_hand_hashes()
_ZOBRIST_TURN = _splitmix64(999_999)

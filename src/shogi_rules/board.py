from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class Move:
    from_square: int | None
    to_square: int | None
    promotion: bool = False
    drop_piece_type: int | None = None

    @classmethod
    def from_usi(cls, usi: str) -> Move:
        if "*" in usi:
            piece_symbol, square_name = usi.split("*", 1)
            return cls(
                from_square=None,
                to_square=square_from_name(square_name),
                drop_piece_type=SFEN_TO_PIECE[piece_symbol],
            )
        return cls(
            from_square=square_from_name(usi[:2]),
            to_square=square_from_name(usi[2:4]),
            promotion=usi.endswith("+"),
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
        self._king_squares = self._find_king_squares()
        self._hash = self._compute_hash()
        self.move_stack: list[_Undo] = []

    @classmethod
    def startpos(cls) -> Board:
        return cls.from_sfen(STARTPOS_SFEN)

    @classmethod
    def from_sfen(cls, sfen: str) -> Board:
        board_part, turn_part, hand_part, *remaining = sfen.split()
        board = [0] * BOARD_SIZE
        square = 0
        for char_index, char in enumerate(board_part):
            if char == "/":
                continue
            if char.isdigit():
                square += int(char)
                continue
            promoted = char == "+"
            if promoted:
                continue
            previous = board_part[char_index - 1] if char_index > 0 else ""
            piece_type = SFEN_TO_PIECE[char.upper()]
            if previous == "+":
                piece_type = PROMOTED[piece_type]
            color = BLACK if char.isupper() else WHITE
            board[square] = _signed_piece(color, piece_type)
            square += 1
        return cls(
            board,
            turn=BLACK if turn_part == "b" else WHITE,
            hands=_parse_hands(hand_part),
            move_number=int(remaining[0]) if remaining else 1,
        )

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
            self.push(move)
            try:
                if not self.is_attacked_by(self.turn, self._king_squares[1 - self.turn]):
                    moves.append(move)
            finally:
                self.pop()
        return moves

    def has_legal_move(self) -> bool:
        for move in self._pseudo_legal_moves_for_legality_check():
            if self._is_illegal_pawn_drop_mate(move):
                continue
            self.push(move)
            try:
                if not self.is_attacked_by(self.turn, self._king_squares[1 - self.turn]):
                    return True
            finally:
                self.pop()
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
            self.push(move)
            try:
                if self.is_attacked_by(self.turn, self._king_squares[1 - self.turn]):
                    continue
                if tactical or self.is_check():
                    moves.append(move)
            finally:
                self.pop()
        return moves

    def push_usi(self, usi: str) -> None:
        self.push(Move.from_usi(usi))

    def push(self, move: Move) -> None:
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
        if abs(captured_piece) == KING:
            raise ValueError("king captures are not legal moves")
        if move.from_square is None:
            if move.drop_piece_type is None:
                raise ValueError("drop moves require a piece type")
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

    def pop(self) -> None:
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
        return not self.legal_moves

    def is_fourfold_repetition(self) -> bool:
        return False

    def zobrist_hash(self) -> int:
        return self._hash

    def king_square(self, color: int) -> int:
        return self._king_squares[color]

    def _find_king_squares(self) -> list[int]:
        king_squares = [-1, -1]
        for square, piece in enumerate(self.board):
            if abs(piece) == KING:
                king_squares[_piece_color(piece)] = square
        if king_squares[BLACK] < 0 or king_squares[WHITE] < 0:
            raise ValueError("both kings are required")
        return king_squares

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
        self.push(move)
        try:
            defender = self.turn
            if not self.is_attacked_by(1 - defender, self.king_square(defender)):
                return False
            return not self._has_legal_evasion_without_pawn_drop_mate_check()
        finally:
            self.pop()

    def _has_legal_evasion_without_pawn_drop_mate_check(self) -> bool:
        for response in self._pseudo_legal_moves():
            self.push(response)
            try:
                if not self.is_attacked_by(self.turn, self.king_square(1 - self.turn)):
                    return True
            finally:
                self.pop()
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
    file_index = 9 - int(name[0])
    rank = ord(name[1]) - ord("a")
    return rank * 9 + file_index


def _parse_hands(hand_part: str) -> dict[int, dict[int, int]]:
    hands: dict[int, dict[int, int]] = {BLACK: {}, WHITE: {}}
    if hand_part == "-":
        return hands
    count_text = ""
    for char in hand_part:
        if char.isdigit():
            count_text += char
            continue
        count = int(count_text) if count_text else 1
        count_text = ""
        color = BLACK if char.isupper() else WHITE
        hands[color][SFEN_TO_PIECE[char.upper()]] = count
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

from __future__ import annotations

import random
import unittest

import shogi

from shogi_rules import BLACK, KING, PAWN, PROM_PAWN, WHITE, Board, Move

STARTPOS = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"
MALFORMED_SFENS = (
    "",
    "4k4/9/9/9/9/9/9/9/4K4 b",
    "4k4/9/9/9/9/9/9/9/4K4 b - 1 moves 7g7f",
    "kK b - 1",
    "4k4/9/9/9/9/9/9/4K4 b - 1",
    "4k4/9/9/9/9/9/9/9/4K4/ b - 1",
    "4k5/9/9/9/9/9/9/9/4K4 b - 1",
    "4k3/9/9/9/9/9/9/9/4K4 b - 1",
    "4k4/9/9/9/9/9/9/9/04K4 b - 1",
    "4k4/9/9/9/9/9/9/9/4X4 b - 1",
    "4k4/9/9/9/9/9/9/+1P7/4K4 b - 1",
    "4k4/9/9/9/9/9/9/++P7/4K4 b - 1",
    "4k4/9/9/9/9/9/9/+G8/4K4 b - 1",
    "4k4/9/9/9/9/9/9/8+/4K4 b - 1",
    "4k4/9/9/9/9/9/9/9/4K4 x - 1",
    "4k4/9/9/9/9/9/9/9/4K4 B - 1",
    "4k4/9/9/9/9/9/9/9/4K4\u3000b - 1",
    "4k4/9/9/9/9/9/9/9/4K4 b 0P 1",
    "4k4/9/9/9/9/9/9/9/4K4 b PP 1",
    "4k4/9/9/9/9/9/9/9/4K4 b 2PP 1",
    "4k4/9/9/9/9/9/9/9/4K4 b P2 1",
    "4k4/9/9/9/9/9/9/9/4K4 b K 1",
    "4k4/9/9/9/9/9/9/9/4K4 b +P 1",
    "4k4/9/9/9/9/9/9/9/4K4 b -P 1",
    "4k4/9/9/9/9/9/9/9/4K4 b \uff12P 1",
    "4k4/9/9/9/9/9/9/9/4K4 b - 0",
    "4k4/9/9/9/9/9/9/9/4K4 b - -1",
    "4k4/9/9/9/9/9/9/9/4K4 b - +1",
    "4k4/9/9/9/9/9/9/9/4K4 b - 1_000",
    "4k4/9/9/9/9/9/9/9/4K4 b - \uff11",
    "4k4/9/9/9/9/9/9/9/4K4 b - 1000000001",
    "4k4/9/9/9/9/9/9/9/4K4 b - 99999999999",
)
IMPOSSIBLE_SFENS = (
    "4k4/9/9/9/9/9/9/9/9 b - 1",
    "4k4/9/9/9/9/9/9/9/K3K4 b - 1",
    "4k4/9/9/9/9/9/9/9/4K4 b 10P9p 1",
    "4k4/9/9/9/9/9/9/9/4K4 b 300P 1",
    "4k4/9/9/9/9/9/9/9/4K4 b 3G2g 1",
    "4k4/9/9/9/9/9/9/+R8/4K4 b 2R 1",
    "4k4/9/9/9/9/9/4P4/4P4/4K4 b - 1",
    "P3k4/9/9/9/9/9/9/9/4K4 b - 1",
    "4k3L/9/9/9/9/9/9/9/4K4 b - 1",
    "4k4/N8/9/9/9/9/9/9/4K4 b - 1",
    "4k4/9/9/9/9/9/9/9/p3K4 b - 1",
    "4k4/9/9/9/9/9/9/4r4/4K4 w - 1",
)
# Each SFEN with how this library writes it back.
READABLE_SFENS = (
    ("4k4/9/9/9/9/9/9/9/4K4 b -", "4k4/9/9/9/9/9/9/9/4K4 b - 1"),
    (" 4k4/9/9/9/9/9/9/9/4K4 \t b  -\n 1 ", "4k4/9/9/9/9/9/9/9/4K4 b - 1"),
    ("4k4/45/9/9/9/9/9/9/4K4 b - 1", "4k4/9/9/9/9/9/9/9/4K4 b - 1"),
    ("4k4/9/9/9/9/9/9/9/4K4 b pR1P02s 007", "4k4/9/9/9/9/9/9/9/4K4 b RP2sp 7"),
    ("4k4/9/9/9/9/9/9/9/4K4 b 2R2B4G4S4N4L18P 1", "4k4/9/9/9/9/9/9/9/4K4 b 2R2B4G4S4N4L18P 1"),
    ("4k4/9/9/9/9/9/9/9/4K4 w - 1000000000", "4k4/9/9/9/9/9/9/9/4K4 w - 1000000000"),
    ("4k4/9/9/9/9/9/9/4r4/4K4 b - 1", "4k4/9/9/9/9/9/9/4r4/4K4 b - 1"),
    ("+P3k3+L/+N8/9/9/9/9/4P4/4+P4/4K4 b - 1", "+P3k3+L/+N8/9/9/9/9/4P4/4+P4/4K4 b - 1"),
)

MALFORMED_USIS = (
    "",
    "7g7",
    "7g7fx",
    "7g7f++",
    "7g7f=",
    " 7g7f",
    "7g7f\n",
    "0g0f",
    "7j7f",
    "7G7F",
    "\uff17g7f",
    "p*5e",
    "K*5e",
    "+P*5e",
    "P*5",
    "P*5j",
    "P*5e+",
    "P5e",
    "*5e",
)
# Each position with a move that is not legal there.
ILLEGAL_USIS = (
    (STARTPOS, "5e5d"),
    (STARTPOS, "5a5b"),
    (STARTPOS, "6i5h+"),
    (STARTPOS, "2h2b"),
    (STARTPOS, "7g7f+"),
    (STARTPOS, "7g7e"),
    (STARTPOS, "5i5a"),
    (STARTPOS, "P*5e"),
    ("4k4/9/9/9/9/9/4P4/9/4K4 b P 1", "P*5e"),
    ("4k4/9/9/9/9/9/9/9/4K4 b P 1", "P*1a"),
    ("4k4/P8/9/9/9/9/9/9/4K4 b - 1", "9b9a"),
    ("k3r4/9/9/9/9/9/9/4G4/4K4 b - 1", "5h4h"),
    ("8k/9/6NG1/9/9/9/9/9/4K4 b P 1", "P*1b"),
)


class SfenTest(unittest.TestCase):
    def test_rejects_malformed_sfen(self) -> None:
        for sfen in MALFORMED_SFENS:
            with self.subTest(sfen=sfen), self.assertRaises(ValueError):
                Board.from_sfen(sfen)

    def test_rejects_positions_that_cannot_occur(self) -> None:
        for sfen in IMPOSSIBLE_SFENS:
            with self.subTest(sfen=sfen), self.assertRaises(ValueError):
                Board.from_sfen(sfen)

    def test_reads_sfen_variants_as_the_same_position(self) -> None:
        for sfen, written in READABLE_SFENS:
            with self.subTest(sfen=sfen):
                self.assertEqual(Board.from_sfen(sfen).sfen(), written)

    def test_rejects_positions_that_cannot_occur_when_built_directly(self) -> None:
        board = [0] * 81
        board[4] = -KING
        with self.assertRaises(ValueError):
            Board(board)
        board[76] = KING
        board[67] = board[58] = PAWN
        with self.assertRaises(ValueError):
            Board(board)
        board[58] = 0
        with self.assertRaises(ValueError):
            Board(board, hands={BLACK: {PAWN: 18}, WHITE: {}})
        self.assertEqual(Board(board).sfen(), "4k4/9/9/9/9/9/9/4P4/4K4 b - 1")

    def test_keeps_the_position_when_set_sfen_rejects(self) -> None:
        board = Board.startpos()
        board.push_usi("7g7f")
        sfen = board.sfen()

        with self.assertRaises(ValueError):
            board.set_sfen("4k4/9/9/9/9/9/9/9/K3K4 b - 1")

        self.assertEqual(board.sfen(), sfen)
        self.assertEqual(len(board.move_stack), 1)


class PushTest(unittest.TestCase):
    def assert_unchanged(self, board: Board, sfen: str, zobrist_hash: int, plies: int) -> None:
        self.assertEqual(board.sfen(), sfen)
        self.assertEqual(board.zobrist_hash(), zobrist_hash)
        self.assertEqual(len(board.move_stack), plies)

    def test_rejects_malformed_usi(self) -> None:
        for usi in MALFORMED_USIS:
            with self.subTest(usi=usi), self.assertRaises(ValueError):
                Move.from_usi(usi)

    def test_push_usi_rejects_illegal_moves_and_keeps_the_position(self) -> None:
        for sfen, usi in ILLEGAL_USIS:
            with self.subTest(sfen=sfen, usi=usi):
                board = Board.from_sfen(sfen)
                zobrist_hash = board.zobrist_hash()
                with self.assertRaises(ValueError):
                    board.push_usi(usi)
                self.assert_unchanged(board, sfen, zobrist_hash, 0)

    def test_push_usi_plays_legal_moves(self) -> None:
        board = Board.startpos()
        for usi in ("7g7f", "3c3d", "8h2b+", "3a2b", "B*5e"):
            board.push_usi(usi)

        self.assertEqual(board.sfen(), "lnsgkg1nl/1r5s1/pppppp1pp/6p2/4B4/2P6/PP1PPPPPP/7R1/LNSGKGSNL w b 6")

    def test_push_rejects_moves_that_break_the_board(self) -> None:
        cases = (
            (STARTPOS, Move(None, None, promotion=True)),
            (STARTPOS, Move(None, None, drop_piece_type=PAWN)),
            (STARTPOS, Move(76, None)),
            (STARTPOS, Move(76, 81)),
            (STARTPOS, Move(81, 40)),
            (STARTPOS, Move(-1, 40)),
            (STARTPOS, Move(60, -5)),
            (STARTPOS, Move(40, 31)),
            (STARTPOS, Move(4, 13)),
            (STARTPOS, Move(75, 67, promotion=True)),
            (STARTPOS, Move(76, 67, promotion=True)),
            (STARTPOS, Move(75, 74)),
            (STARTPOS, Move(75, 76)),
            (STARTPOS, Move(None, 40, drop_piece_type=PAWN)),
            (STARTPOS, Move(None, 40, drop_piece_type=KING)),
            (STARTPOS, Move(None, 40, drop_piece_type=PROM_PAWN)),
            ("4k4/9/9/9/9/9/4P4/9/4K4 b P 1", Move(None, 58, drop_piece_type=PAWN)),
            ("4k4/9/9/9/9/9/4P4/9/4K4 b P 1", Move(None, 40, promotion=True, drop_piece_type=PAWN)),
            ("4k4/9/9/9/9/9/4P4/9/4K4 b P 1", Move(58, 49, drop_piece_type=PAWN)),
            ("4k4/9/9/9/9/9/4G4/9/4K4 b - 1", Move(58, 49, promotion=True)),
        )
        for sfen, move in cases:
            with self.subTest(sfen=sfen, move=move):
                board = Board.from_sfen(sfen)
                zobrist_hash = board.zobrist_hash()
                with self.assertRaises(ValueError):
                    board.push(move)
                self.assert_unchanged(board, sfen, zobrist_hash, 0)

    def test_push_plays_null_moves(self) -> None:
        board = Board.startpos()
        board.push(Move(None, None))

        self.assertEqual(board.sfen(), STARTPOS.replace(" b - 1", " w - 2"))
        board.pop()
        self.assertEqual(board.sfen(), STARTPOS)


class BoardOracleTest(unittest.TestCase):
    def test_startpos_legal_moves_match_python_shogi(self) -> None:
        board = Board.startpos()
        reference = shogi.Board()

        self.assertEqual(board.sfen(), reference.sfen())
        self.assertEqual(board.legal_move_usis(), {move.usi() for move in reference.legal_moves})
        self.assertEqual(board.has_legal_move(), bool(list(reference.legal_moves)))

    def test_random_playout_legal_moves_match_python_shogi(self) -> None:
        board = Board.startpos()
        reference = shogi.Board()
        rng = random.Random(1)

        for _ in range(40):
            board_moves = board.legal_move_usis()
            reference_moves = {move.usi() for move in reference.legal_moves}
            self.assertEqual(board_moves, reference_moves)
            self.assertEqual(board.has_legal_move(), bool(reference_moves))
            if not reference_moves or reference.is_game_over():
                break
            move_usi = rng.choice(sorted(reference_moves))
            board.push_usi(move_usi)
            reference.push_usi(move_usi)

        while board.move_stack:
            board.pop()
            reference.pop()

        self.assertEqual(board.sfen(), reference.sfen())

    def test_checked_positions_legal_moves_match_python_shogi(self) -> None:
        rng = random.Random(2)
        checked_sfens: list[str] = []
        for _ in range(200):
            reference = shogi.Board()
            for _ in range(80):
                legal_moves = list(reference.legal_moves)
                if not legal_moves or reference.is_game_over():
                    break
                reference.push(rng.choice(legal_moves))
                if reference.is_check():
                    checked_sfens.append(reference.sfen())
                    break
            if len(checked_sfens) >= 5:
                break

        self.assertGreaterEqual(len(checked_sfens), 1)
        for sfen in checked_sfens:
            board = Board.from_sfen(sfen)
            reference = shogi.Board(sfen)
            self.assertEqual(board.legal_move_usis(), {move.usi() for move in reference.legal_moves})

    def test_tactical_moves_match_python_shogi_filter(self) -> None:
        board = Board.startpos()
        reference = shogi.Board()
        for move_usi in ("7g7f", "3c3d", "8h2b+"):
            board.push_usi(move_usi)
            reference.push_usi(move_usi)

        expected = set()
        for move in reference.legal_moves:
            if move.promotion or reference.piece_at(move.to_square) is not None:
                expected.add(move.usi())
                continue
            reference.push(move)
            try:
                if reference.is_check():
                    expected.add(move.usi())
            finally:
                reference.pop()

        self.assertEqual(
            {move.usi() for move in board.legal_tactical_moves(include_quiet_checks=True)},
            expected,
        )
        expected_without_quiet_checks = {
            move.usi()
            for move in reference.legal_moves
            if move.promotion or reference.piece_at(move.to_square) is not None
        }
        self.assertEqual(
            {move.usi() for move in board.legal_tactical_moves(include_quiet_checks=False)},
            expected_without_quiet_checks,
        )

    def test_hash_restores_after_push_pop(self) -> None:
        board = Board.startpos()
        initial_hash = board.zobrist_hash()
        initial_sfen = board.sfen()

        for move_usi in ("7g7f", "3c3d", "8h2b+"):
            board.push_usi(move_usi)

        self.assertNotEqual(board.zobrist_hash(), initial_hash)
        for _ in range(3):
            board.pop()

        self.assertEqual(board.sfen(), initial_sfen)
        self.assertEqual(board.zobrist_hash(), initial_hash)

    def test_rejects_drop_without_hand_piece(self) -> None:
        board = Board.startpos()

        with self.assertRaises(ValueError):
            board.push_usi("P*5e")

    def test_rejects_king_capture(self) -> None:
        board = Board.startpos()

        with self.assertRaises(ValueError):
            board.push_usi("5i5a")


if __name__ == "__main__":
    unittest.main()

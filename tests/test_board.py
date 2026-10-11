from __future__ import annotations

import random
import unittest

import shogi

from shogi_rules import BLACK, KING, PAWN, WHITE, Board

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

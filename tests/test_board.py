from __future__ import annotations

import random
import unittest

import shogi

from shogi_rules import Board


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

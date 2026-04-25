"""
Unit tests for the ETL approval gate.

Run: `python -m scripts.etl.test_gate` from ai-core/.

The gate is the only thing standing between a librarian's intent and a
write into the live Weaviate index. Test coverage is non-negotiable:

  1. Unsigned token -> refuse.
  2. Signed token + matching diff_hash -> proceed.
  3. Signed token + mismatched diff_hash (diff edited or re-prepared) -> refuse.
  4. Signed token + wrong diff_file name -> refuse.
  5. Missing token -> refuse.
  6. Missing diff -> refuse.
  7. Round-trip: write_approval_template -> parse_approval recovers fields.
"""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
from pathlib import Path

# Allow running from ai-core/ as `python -m scripts.etl.test_gate`.
_HERE = Path(__file__).resolve().parent
_AI_CORE = _HERE.parent.parent
sys.path.insert(0, str(_AI_CORE))

from scripts.etl import gate  # noqa: E402


def _seed_diff(tmp: Path, body: str = "# diff\nhello world\n") -> Path:
    """Write a fake diff file; returns its path."""
    p = tmp / "2026-04-25_1200.md"
    p.write_text(body, encoding="utf-8")
    return p


def _sign(token_path: Path, email: str = "lib@miamioh.edu") -> None:
    """Mutate an unsigned approval template into a signed one."""
    text = token_path.read_text(encoding="utf-8")
    text = text.replace(
        "approved_by_email:",
        f"approved_by_email: {email}",
    ).replace(
        "approved_at:",
        f"approved_at: {dt.datetime.utcnow().isoformat(timespec='seconds')}",
    )
    token_path.write_text(text, encoding="utf-8")


def test_unsigned_refuses() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        diff = _seed_diff(tmp)
        gate.write_approval_template(diff, dt.datetime.utcnow())
        decision = gate.verify_gate(diff)
        assert not decision.proceed, "expected refuse on unsigned token"
        assert "unsigned" in decision.reason


def test_signed_matching_hash_proceeds() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        diff = _seed_diff(tmp)
        token = gate.write_approval_template(diff, dt.datetime.utcnow())
        _sign(token)
        decision = gate.verify_gate(diff)
        assert decision.proceed, f"expected proceed; got: {decision.reason}"
        assert decision.token is not None
        assert decision.token.approved_by_email == "lib@miamioh.edu"


def test_diff_edit_invalidates_approval() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        diff = _seed_diff(tmp)
        token = gate.write_approval_template(diff, dt.datetime.utcnow())
        _sign(token)
        # Librarian signed; now a sneaky edit changes the diff bytes.
        diff.write_text("# diff\nhello SNEAKY world\n", encoding="utf-8")
        decision = gate.verify_gate(diff)
        assert not decision.proceed, "expected refuse on edited diff"
        assert "diff_hash mismatch" in decision.reason


def test_wrong_diff_file_refuses() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        diff_a = _seed_diff(tmp)
        token = gate.write_approval_template(diff_a, dt.datetime.utcnow())
        _sign(token)
        # Now operator points apply at a different diff file.
        diff_b = tmp / "2026-04-26_0900.md"
        diff_b.write_text("# diff\ndifferent run\n", encoding="utf-8")
        # Re-use the .approval token from diff_a.
        decision = gate.verify_gate(diff_b, token_path=token)
        assert not decision.proceed
        assert "references diff_file" in decision.reason


def test_missing_token_refuses() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        diff = _seed_diff(tmp)
        # Skip the write_approval_template step.
        decision = gate.verify_gate(diff)
        assert not decision.proceed
        assert "approval token not found" in decision.reason


def test_missing_diff_refuses() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        decision = gate.verify_gate(tmp / "nonexistent.md")
        assert not decision.proceed
        assert "diff file not found" in decision.reason


def test_template_round_trip() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        diff = _seed_diff(tmp)
        prepared_at = dt.datetime(2026, 4, 25, 12, 0, 0)
        token_path = gate.write_approval_template(diff, prepared_at)
        token = gate.parse_approval(token_path)
        assert token.diff_file == diff.name
        assert token.diff_hash == gate.hash_diff_file(diff)
        # Unsigned by default.
        assert not token.is_signed


def test_mark_applied_writes_marker() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        diff = _seed_diff(tmp)
        token = gate.write_approval_template(diff, dt.datetime.utcnow())
        _sign(token)
        decision = gate.verify_gate(diff)
        assert decision.proceed
        marker = gate.mark_applied(diff, decision.token, dt.datetime.utcnow())
        assert marker.exists()
        body = marker.read_text(encoding="utf-8")
        assert "applied_at:" in body
        assert "lib@miamioh.edu" in body


def test_find_latest_pending_skips_applied() -> None:
    """A diff with both .approval and .applied should NOT be returned by
    find_latest_pending_diff() -- preventing accidental re-promotion."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Override the diff dir for this test.
        from scripts.etl import config as _config
        original = _config.DIFF_REPORT_DIR
        _config.DIFF_REPORT_DIR = str(tmp)
        try:
            diff = _seed_diff(tmp)
            token = gate.write_approval_template(diff, dt.datetime.utcnow())
            _sign(token)
            assert gate.find_latest_pending_diff() == diff
            # Now mark applied; same call must return None.
            decision = gate.verify_gate(diff)
            gate.mark_applied(diff, decision.token, dt.datetime.utcnow())
            assert gate.find_latest_pending_diff() is None
        finally:
            _config.DIFF_REPORT_DIR = original


def main() -> int:
    tests = [
        test_unsigned_refuses,
        test_signed_matching_hash_proceeds,
        test_diff_edit_invalidates_approval,
        test_wrong_diff_file_refuses,
        test_missing_token_refuses,
        test_missing_diff_refuses,
        test_template_round_trip,
        test_mark_applied_writes_marker,
        test_find_latest_pending_skips_applied,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

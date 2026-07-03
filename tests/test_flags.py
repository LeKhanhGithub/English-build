from pathlib import Path

from src.flags import ensure_flag_assets


def test_saudi_flag_uses_bundled_real_png_asset(tmp_path: Path) -> None:
    bundled_path = Path(__file__).resolve().parents[1] / "assets" / "flags" / "sa.png"

    flag_dir = ensure_flag_assets(tmp_path / "assets", force=True)
    copied_path = flag_dir / "sa.png"

    assert copied_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert copied_path.read_bytes() == bundled_path.read_bytes()

"""Storage helpers read and write UTF-8 regardless of the locale encoding.

On Windows the default text encoding is the ANSI code page (cp1252, cp932,
...), so ``Path.read_text()`` / ``write_text()`` without ``encoding`` fail on
content such as emoji or smart quotes. The checks run in a subprocess with
UTF-8 mode off so the locale encoding is non-UTF-8 on every platform.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

TEXT = "café ’quoted’ \U0001f600"

_SCRIPT = textwrap.dedent(
    r"""
    import sys
    from pathlib import Path

    from entrabot.storage.backend import LocalBackend
    from entrabot.storage.migration import migrate_local_to_backend
    from entrabot.storage.persona import PersonaBackend

    text = "caf\u00e9 \u2019quoted\u2019 \U0001f600"
    root = Path(sys.argv[1])

    # LocalBackend: write, conditional write, append, both reads.
    backend = LocalBackend(root / "backend")
    etag = backend.write_text("a.md", text)
    assert backend.read_text("a.md") == text
    assert backend.read_text_with_etag("a.md") == (text, etag)
    backend.write_text("a.md", text + "!", if_match=etag)
    backend.append_text("log.md", text)
    assert backend.read_text("log.md") == text

    # Migration reads local files written as UTF-8.
    report = migrate_local_to_backend([(root / "src", "")], LocalBackend(root / "dest"))
    assert not report.errors, report.errors
    assert LocalBackend(root / "dest").read_text("m.md") == text

    # PersonaBackend: push_one / push_all read local files, pull_all writes them.
    persona_src = root / "persona"
    store = LocalBackend(root / "persona-store")
    persona = PersonaBackend(store, local_root=persona_src)
    persona.push_one(persona_src / "p.md")
    assert store.read_text(persona.prefix + "p.md") == text
    report = persona.push_all()
    assert not report.errors, report.errors
    (persona_src / "p.md").unlink()
    persona.pull_all()
    assert (persona_src / "p.md").read_bytes() == text.encode("utf-8")
    """
)


def test_storage_round_trips_non_ascii_under_non_utf8_locale(tmp_path: Path) -> None:
    for name in ("src/m.md", "persona/p.md", "persona/q.md"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(TEXT.encode("utf-8"))

    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHONUTF8", "LC_"))}
    env.update({"LC_ALL": "C", "PYTHONCOERCECLOCALE": "0"})
    result = subprocess.run(
        [sys.executable, "-X", "utf8=0", "-c", _SCRIPT, str(tmp_path)],
        capture_output=True,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr

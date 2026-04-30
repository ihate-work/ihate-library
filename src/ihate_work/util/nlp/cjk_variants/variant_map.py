"""Runtime class for CJK variant character normalization via str.translate()."""

from __future__ import annotations

import json
from pathlib import Path

from ihate_work.o11y import get_o11y

logger, *_ = get_o11y(__name__)

_DEFAULT_DATA = Path(__file__).parent / "data" / "variants.jsonl"


class VariantMap:
    """Character-level CJK variant normalizer backed by a translate table."""

    def __init__(self, path: Path | None = None) -> None:
        path = path or _DEFAULT_DATA
        table: dict[int, str] = {}
        mapping: dict[str, str] = {}
        clusters: dict[str, frozenset[str]] = {}

        if not path.exists():
            logger.warning("variants data not found, normalization disabled", path=str(path))
            self._table = table
            self._map = mapping
            self._clusters = clusters
            return

        cluster_count = 0
        char_count = 0
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                rep: str = obj["representative"]
                members: list[str] = obj["members"]
                all_chars = frozenset([rep, *members])
                clusters[rep] = all_chars
                for m in members:
                    table[ord(m)] = rep
                    mapping[m] = rep
                    clusters[m] = all_chars
                    char_count += 1
                cluster_count += 1

        self._table = table
        self._map = mapping
        self._clusters = clusters
        logger.info("loaded variant map", clusters=cluster_count, chars=char_count)

    def normalize(self, text: str) -> str:
        """Normalize all variant characters to their representatives. C-speed single pass."""
        return text.translate(self._table)

    def representative(self, char: str) -> str:
        """Return the cluster representative for a character, or the character itself."""
        return self._map.get(char, char)

    def cluster(self, char: str) -> frozenset[str]:
        """Return all members of the character's cluster, or a singleton frozenset."""
        return self._clusters.get(char, frozenset({char}))

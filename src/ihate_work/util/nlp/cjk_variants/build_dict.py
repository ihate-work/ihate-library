"""Download CJK variant sources, merge via union-find, and emit variants.jsonl.

Run as: python -m ihate_work.util.nlp.cjk_variants.build_dict
"""

from __future__ import annotations

import json
import urllib.request
from collections import defaultdict
from pathlib import Path

from ihate_work.o11y import get_o11y

logger, *_ = get_o11y(__name__)

_DATA_DIR = Path(__file__).parent / "data"
_RAW_DIR = _DATA_DIR / "raw"
_OUTPUT = _DATA_DIR / "variants.jsonl"

_CLUSTER_SIZE_CAP = 20

_OPENCC_BASE = "https://raw.githubusercontent.com/BYVoid/OpenCC/master/data/dictionary"
_OPENCC_FILES = [
    "JPVariants.txt",
    "JPShinjitaiCharacters.txt",
    "TSCharacters.txt",
    "STCharacters.txt",
]

_SUDACHI_REWRITE_URL = (
    "https://raw.githubusercontent.com/WorksApplications/Sudachi/develop/src/main/resources/rewrite.def"
)


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------


class _UnionFind:
    """Union-find with path compression and union-by-rank."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # path compression
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1

    def clusters(self) -> list[list[str]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for x in self._parent:
            groups[self.find(x)].append(x)
        return list(groups.values())


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_opencc_tsv(path: Path) -> list[tuple[str, str]]:
    """Parse OpenCC dictionary file into (key, value) single-char pairs."""
    pairs: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        key = parts[0]
        if len(key) != 1:
            continue
        for val in parts[1].split():
            if len(val) != 1:
                continue
            if val == key:
                continue
            pairs.append((key, val))
    return pairs


def _parse_sudachi_ignore(path: Path) -> set[str]:
    """Extract single chars from the ignore-normalize section of rewrite.def."""
    chars: set[str] = set()
    in_section = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "# ignore normalize list":
            in_section = True
            continue
        if stripped == "# replace char list":
            break
        if in_section and stripped and not stripped.startswith("#") and len(stripped) == 1:
            chars.add(stripped)
    return chars


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def _download(url: str, dest: Path) -> None:
    if dest.exists():
        logger.debug("already downloaded", path=str(dest))
        return
    logger.info("downloading", url=url, dest=str(dest))
    urllib.request.urlretrieve(url, dest)


def _download_all() -> None:
    _RAW_DIR.mkdir(parents=True, exist_ok=True)
    for fname in _OPENCC_FILES:
        _download(f"{_OPENCC_BASE}/{fname}", _RAW_DIR / fname)
    _download(_SUDACHI_REWRITE_URL, _RAW_DIR / "rewrite.def")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def _build() -> None:
    _download_all()

    uf = _UnionFind()
    total_pairs = 0

    for fname in _OPENCC_FILES:
        pairs = _parse_opencc_tsv(_RAW_DIR / fname)
        for a, b in pairs:
            uf.union(a, b)
        logger.info("parsed opencc file", file=fname, pairs=len(pairs))
        total_pairs += len(pairs)

    logger.info("total pairs from all sources", total=total_pairs)

    # Parse Sudachi ignore list for cross-reference
    sudachi_path = _RAW_DIR / "rewrite.def"
    if sudachi_path.exists():
        sudachi_ignore = _parse_sudachi_ignore(sudachi_path)
        logger.info("parsed sudachi ignore list", chars=len(sudachi_ignore))
    else:
        sudachi_ignore = set()

    # Extract clusters, skip singletons
    raw_clusters = uf.clusters()
    clusters: list[dict[str, str | list[str]]] = []
    oversized = 0

    for members in raw_clusters:
        if len(members) <= 1:
            continue
        rep = min(members, key=ord)
        rest = sorted([c for c in members if c != rep], key=ord)

        if len(members) > _CLUSTER_SIZE_CAP:
            oversized += 1
            logger.warning(
                "oversized cluster",
                representative=rep,
                size=len(members),
                members="".join(sorted(members, key=ord)),
            )

        clusters.append({"representative": rep, "members": rest})

    # Sort output by representative codepoint for deterministic output
    clusters.sort(key=lambda c: ord(c["representative"]))  # type: ignore[arg-type]

    # Cross-reference with Sudachi ignore list
    all_mapped = set()
    for c in clusters:
        all_mapped.add(c["representative"])
        all_mapped.update(c["members"])  # type: ignore[arg-type]

    overlap = sudachi_ignore & all_mapped
    only_sudachi = sudachi_ignore - all_mapped
    logger.debug(
        "sudachi cross-reference",
        overlap=len(overlap),
        only_in_sudachi=len(only_sudachi),
    )

    # Write output
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT, "w", encoding="utf-8") as f:
        for c in clusters:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    logger.info(
        "wrote variants.jsonl",
        path=str(_OUTPUT),
        clusters=len(clusters),
        chars=sum(len(c["members"]) for c in clusters),  # type: ignore[arg-type]
        oversized=oversized,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import ihate_work.o11y as o11y

    o11y.setup_structlog()
    _build()

"""Tests for VariantMap and build_dict helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ihate_work.util.nlp.cjk_variants.variant_map import VariantMap


@pytest.fixture(scope="module")
def tmp_jsonl(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a temporary variants.jsonl with known test clusters."""
    p = tmp_path_factory.mktemp("variants") / "variants.jsonl"
    clusters = [
        {"representative": "国", "members": ["國", "囯", "囻"]},
        {"representative": "辺", "members": ["邊", "邉"]},
        {"representative": "弁", "members": ["辨", "辯", "瓣", "辦"]},
        {"representative": "高", "members": ["髙"]},
    ]
    p.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in clusters) + "\n")
    return p


@pytest.fixture(scope="module")
def vm(tmp_jsonl: Path) -> VariantMap:
    return VariantMap(tmp_jsonl)


class TestNormalize:
    def test_single_variant(self, vm: VariantMap):
        assert vm.normalize("國") == "国"

    def test_full_string(self, vm: VariantMap):
        assert vm.normalize("渡邊") == "渡辺"

    def test_empty(self, vm: VariantMap):
        assert vm.normalize("") == ""

    def test_mixed_ascii_cjk(self, vm: VariantMap):
        assert vm.normalize("hello國world") == "hello国world"

    def test_multiple_clusters_in_one_string(self, vm: VariantMap):
        assert vm.normalize("國邊髙") == "国辺高"

    def test_no_change_for_representatives(self, vm: VariantMap):
        assert vm.normalize("国辺弁高") == "国辺弁高"

    def test_all_ben_variants(self, vm: VariantMap):
        assert vm.normalize("辨辯瓣辦") == "弁弁弁弁"


class TestRepresentative:
    def test_variant_char(self, vm: VariantMap):
        assert vm.representative("國") == "国"

    def test_representative_of_representative(self, vm: VariantMap):
        assert vm.representative("国") == "国"

    def test_unknown_char(self, vm: VariantMap):
        assert vm.representative("あ") == "あ"

    def test_all_ben_variants(self, vm: VariantMap):
        for c in "辨辯瓣辦":
            assert vm.representative(c) == "弁"


class TestCluster:
    def test_known_cluster(self, vm: VariantMap):
        assert vm.cluster("国") == frozenset({"国", "國", "囯", "囻"})

    def test_variant_same_cluster(self, vm: VariantMap):
        assert vm.cluster("國") == frozenset({"国", "國", "囯", "囻"})

    def test_unknown_char_singleton(self, vm: VariantMap):
        assert vm.cluster("あ") == frozenset({"あ"})

    def test_pair_cluster(self, vm: VariantMap):
        assert vm.cluster("高") == frozenset({"高", "髙"})

    def test_large_cluster(self, vm: VariantMap):
        expected = frozenset({"弁", "辨", "辯", "瓣", "辦"})
        assert vm.cluster("弁") == expected
        assert vm.cluster("辨") == expected


class TestMissingFile:
    def test_missing_file_normalize_passthrough(self, tmp_path: Path):
        vm = VariantMap(tmp_path / "nonexistent.jsonl")
        assert vm.normalize("國語") == "國語"

    def test_missing_file_representative_identity(self, tmp_path: Path):
        vm = VariantMap(tmp_path / "nonexistent.jsonl")
        assert vm.representative("國") == "國"


# --- Tests for build_dict internals ---

from ihate_work.util.nlp.cjk_variants.build_dict import (
    _parse_opencc_tsv,
    _parse_sudachi_ignore,
    _UnionFind,
)


class TestUnionFind:
    def test_basic_union(self):
        uf = _UnionFind()
        uf.union("a", "b")
        assert uf.find("a") == uf.find("b")

    def test_transitive_merge(self):
        uf = _UnionFind()
        uf.union("a", "b")
        uf.union("b", "c")
        assert uf.find("a") == uf.find("c")

    def test_singleton(self):
        uf = _UnionFind()
        uf.union("x", "x")
        assert uf.find("x") == "x"

    def test_cluster_extraction(self):
        uf = _UnionFind()
        uf.union("a", "b")
        uf.union("b", "c")
        uf.union("x", "y")
        clusters = uf.clusters()
        # Two clusters: {a, b, c} and {x, y}
        assert len(clusters) == 2
        cluster_sets = [set(c) for c in clusters]
        assert {"a", "b", "c"} in cluster_sets
        assert {"x", "y"} in cluster_sets

    def test_self_union(self):
        uf = _UnionFind()
        uf.union("z", "z")
        clusters = uf.clusters()
        assert len(clusters) == 1
        assert set(clusters[0]) == {"z"}

    def test_cross_dictionary_chaining(self):
        """Simulate merging pairs from different data sources."""
        uf = _UnionFind()
        # Source 1: A→B
        uf.union("A", "B")
        # Source 2: B→C
        uf.union("B", "C")
        # Source 3: C→D
        uf.union("C", "D")
        assert uf.find("A") == uf.find("D")
        clusters = uf.clusters()
        assert len(clusters) == 1
        assert set(clusters[0]) == {"A", "B", "C", "D"}


class TestParseOpenccTsv:
    def test_basic_one_to_one(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("國\t国\n")
        pairs = _parse_opencc_tsv(f)
        assert ("國", "国") in pairs

    def test_one_to_many_with_self_mapping_exclusion(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("弁\t辨 辯 瓣 辦 弁\n")
        pairs = _parse_opencc_tsv(f)
        # self-mapping (弁→弁) should be excluded
        assert ("弁", "弁") not in pairs
        assert ("弁", "辨") in pairs
        assert ("弁", "辯") in pairs
        assert ("弁", "瓣") in pairs
        assert ("弁", "辦") in pairs

    def test_comments_and_blanks(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("# comment\n\n國\t国\n")
        pairs = _parse_opencc_tsv(f)
        assert len(pairs) == 1

    def test_multi_char_entry_skipping(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("國\t国\n著作\t着作\n")
        pairs = _parse_opencc_tsv(f)
        # multi-char entries should be skipped
        assert len(pairs) == 1
        assert ("國", "国") in pairs


class TestParseSudachiIgnore:
    def test_extracts_ignore_chars(self, tmp_path: Path):
        f = tmp_path / "rewrite.def"
        f.write_text(
            "# some header\n"
            "# ignore normalize list\n"
            "#   ^{char}%n\n"
            "髙\n"
            "﨑\n"
            "# replace char list\n"
            "A\tB\n"
        )
        chars = _parse_sudachi_ignore(f)
        assert "髙" in chars
        assert "﨑" in chars
        assert "A" not in chars

    def test_only_single_chars(self, tmp_path: Path):
        f = tmp_path / "rewrite.def"
        f.write_text(
            "# ignore normalize list\n"
            "髙\n"
            "multi\n"
            "# replace char list\n"
        )
        chars = _parse_sudachi_ignore(f)
        assert "髙" in chars
        assert "multi" not in chars

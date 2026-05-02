# nlp.variants_dict

A standalone package for CJK variant character (異体字) normalization, to enhance search recall when indexing and querying terms.

Developed independently — no dependency on `nlp.tokenizer` or spaCy.

## Problem

CJK text has many characters that are **semantically identical but have different Unicode codepoints**. This causes search misses:

| User searches | Indexed as | Match? |
| ------------- | ---------- | ------ |
| 渡**辺**      | 渡**邊**   | miss   |
| **学**園      | **學**園   | miss   |
| **国**語      | **國**語   | miss   |
| 弁当          | 辨当       | miss   |
| **髙**橋      | **高**橋   | miss   |

These fall into overlapping categories:

1. **Shinjitai / Kyujitai** (新字体/旧字体) — post-1946 Japanese simplification vs traditional forms
2. **Simplified / Traditional Chinese** (简体/繁體) — mainland China simplification
3. **Itaiji** (異体字) — historical/regional variant glyphs (e.g. 髙/高, 邊/邉/辺)
4. **Unicode normalization gaps** — NFKC handles some but deliberately excludes ~835 CJK characters (Kangxi radicals, compatibility ideographs)

Standard tools solve parts but not all:

- **Unicode NFKC**: handles full-width/half-width, some compatibility ideographs. Misses itaiji, shin/kyujitai.
- **SudachiPy `.normalized_form()`**: handles orthographic variants at the **word** level (附属→付属, 呑む→飲む). Misses character-level variants in names/titles that aren't in its dictionary.
- **spaCy lemmatization**: operates on morphology, not glyph variants.

**The gap**: character-level variant mapping for kanji that no morphological analyzer covers — especially for proper nouns (person names, work titles) which dominate the bgm-archive dataset.

## Data model: variant clusters

Variant characters form **clusters** (equivalence classes). A pair is just a cluster of size 2.

| Cluster | Members            | Representative |
| ------- | ------------------ | -------------- |
| pair    | 髙, 高             | 高             |
| cluster | 辺, 邊, 邉         | 辺             |
| cluster | 弁, 辨, 辯, 瓣, 辦 | 弁             |
| cluster | 国, 國, 囯, 囻     | 国             |

Each cluster has exactly one **representative** (canonical form) — prefer shinjitai / simplified / most common modern form.

The runtime data structure is a flat `dict[str, str]` — every non-representative member maps to its cluster's representative. Representatives map to themselves implicitly (absent from the dict). Loaded into a `str.translate()` table for C-level speed:

```python
# Internal lookup table (built from clusters)
_table = str.maketrans(
    {
        "國": "国",
        "囯": "国",
        "囻": "国",
        "邊": "辺",
        "邉": "辺",
        "辨": "弁",
        "辯": "弁",
        "瓣": "弁",
        "辦": "弁",
        "髙": "高",
    }
)


def normalize(text: str) -> str:
    return text.translate(_table)
```

One `str.translate()` call per string — C-level loop, O(n) in string length, no per-character Python overhead.

## Data sources

| Source                                                                                                               | What it provides                                                    | Format | License              |
| -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ------ | -------------------- |
| [OpenCC `JPVariants.txt`](https://github.com/BYVoid/OpenCC/tree/master/data/dictionary)                              | Traditional → Japanese shinjitai (~450 entries)                     | TSV    | Apache-2.0           |
| [OpenCC `JPShinjitaiCharacters.txt`](https://github.com/BYVoid/OpenCC/tree/master/data/dictionary)                   | Shinjitai → multiple kyujitai (1-to-many, e.g. 弁→辨辯瓣辦弁)       | TSV    | Apache-2.0           |
| [OpenCC `TSCharacters.txt` / `STCharacters.txt`](https://github.com/BYVoid/OpenCC/tree/master/data/dictionary)       | Traditional ↔ Simplified Chinese character mappings                 | TSV    | Apache-2.0           |
| [tobunken 異体字リスト](https://www.tobunken.go.jp/archives/%E7%95%B0%E4%BD%93%E5%AD%97%E3%83%AA%E3%82%B9%E3%83%88/) | Japanese itaiji database (web-searchable)                           | Web DB | Reference/validation |
| SudachiPy `rewrite.def`                                                                                              | NFKC ignore list (~835 chars), dakuten combining rules (~182 rules) | Custom | Apache-2.0           |

## References

- [ES CJK normalization practical guide](https://itdepends.hateblo.jp/entry/2018/12/18/221816) — ICU normalizer + Mapping Char Filter pattern for kanji variants in Elasticsearch
- [Sudachi synonym & normalized_form deep dive](https://zenn.dev/sorami/articles/d7fc2bd871a56e) — how `sudachi_normalizedform` covers orthographic and character variants at the word level
- [elasticsearch-sudachi plugin](https://github.com/WorksApplications/elasticsearch-sudachi) — architecture: split modes separate from normalization filters
- [Sudachi character normalization internals](https://zenn.dev/sorami/articles/6bdb4bf6c7f207#%E3%83%A6%E3%83%BC%E3%82%B6%E3%83%BC%E8%BE%9E%E6%9B%B8%E3%81%AE%E3%81%9F%E3%82%81%E3%81%AE%E6%96%87%E5%AD%97%E6%AD%A3%E8%A6%8F%E5%8C%96) — three-step pipeline (rewrite.def → lowercase → NFKC-with-exclusions), reusable Python normalizer class

## Concrete actions

### Phase 1: Data collection & build script

1. Download OpenCC `JPVariants.txt`, `JPShinjitaiCharacters.txt`, `TSCharacters.txt`, `STCharacters.txt` into `data/raw/`
2. `build_dict.py` (lives inside this package) parses `data/raw/` sources, builds variant clusters using union-find to merge overlapping groups (e.g. if A→B from JP dict and B→C from TS dict, then {A,B,C} form one cluster)
3. For each cluster, pick the representative: prefer shinjitai > simplified > most-common modern form
4. Output: `data/variants.jsonl` — one JSON object per cluster: `{"representative": "国", "members": ["國", "囯", "囻"]}`
5. Add manual entries for known bgm-archive misses (e.g. 髙/高) from tobunken reference — stored in `data/raw/manual.tsv`
6. Reproducible: anyone can re-run `build_dict.py` to regenerate `data/variants.jsonl` from sources

### Phase 2: Python API

Independent module, no spaCy/sudachi dependency.

```python
from ihate_work.domains.bgm_archive.nlp.variants_dict import VariantMap

vm = VariantMap()  # loads from bundled data/variants.jsonl

# Primary operation — normalize every char to its cluster representative:
vm.normalize("渡邊義經")  # → "渡辺義経"  (str.translate, C-speed)

# Auxiliary operations:
vm.representative("國")  # → "国"
vm.cluster("國")  # → frozenset({"国", "國", "囯", "囻"})
```

Key design decisions:

- **Cluster model** — variant characters form equivalence classes (clusters), each with one representative
- **Character-level, not word-level** — maps individual codepoints via `str.translate()`, composes over strings
- **Normalize-both** — normalize at both index time and query time to the same representative. Simple, deterministic, no combinatorial blowup.
- **Dual-form indexing** — the index stores both the raw (original) and normalized form per token. A query hit on the raw form scores higher than a hit via normalization only. This package provides both forms; scoring policy is the caller's responsibility.
- **`str.translate()` internally** — single C-level pass over the string, O(n), no per-character Python dispatch
- **No external deps** — pure Python, loads a JSONL file

### Phase 3: Integration points (external — not in this package)

The `VariantMap` API is consumed by other modules:

- **Indexing pipeline** (`populate_duckdb` / `populate_postgres`): `vm.normalize(text)` before tokenization
- **Search query processing**: `vm.normalize(query_text)` before query
- **Tokenizer integration** (optional): `tokenizer.py` can call `vm.normalize()` as a pre-processing step

### Inverted index schema with dual-form tokens

The `search_token` table stores both raw and normalized forms so the scoring layer can reward exact matches:

```sql
CREATE TABLE search_token (
    doc_id      INTEGER NOT NULL,
    field       TEXT NOT NULL,     -- 'title', 'summary', 'staff_name', ...
    position    INTEGER NOT NULL,
    raw         TEXT NOT NULL,     -- original token as extracted
    normalized  TEXT NOT NULL      -- after VariantMap.normalize()
);

CREATE INDEX idx_norm ON search_token (normalized);
```

Lookup is always by `normalized`. The `raw` column is carried along for scoring:

```sql
WITH query_tokens (raw, normalized) AS (
    VALUES ('学園', '学園'),
           ('アリス', 'アリス')
),
hits AS (
    SELECT
        st.doc_id,
        st.field,
        qt.normalized                       AS q_norm,
        CASE WHEN st.raw = qt.raw
             THEN 1 ELSE 0
        END                                 AS is_exact
    FROM search_token st
    JOIN query_tokens qt ON st.normalized = qt.normalized
)
SELECT
    doc_id,
    COUNT(*)                                AS matched_terms,
    SUM(CASE WHEN is_exact = 1
             THEN 2.0 ELSE 1.0 END)        AS raw_score,
    -- layer TF-IDF / BM25 weights, field boosts, etc. on top
FROM hits
GROUP BY doc_id
ORDER BY matched_terms DESC, raw_score DESC;
```

Example: query `学園アリス` against 3 documents:

| doc_id | title (raw)  | What happens                                                                  |
| ------ | ------------ | ----------------------------------------------------------------------------- |
| 1      | 學園アリス   | 學園→学園 via normalization (variant hit, 1.0) + アリス exact (2.0) = **3.0** |
| 2      | 学園アリス   | Both exact hits = **4.0** (ranks highest)                                     |
| 3      | 渡邊のアニメ | No matching tokens                                                            |

The exact-vs-variant distinction slots in as a multiplier on top of whatever scoring formula (BM25, TF-IDF) is used.

## Expected benefits

1. **Higher recall** for name searches — 渡辺/渡邊/渡邉 all match each other
2. **Cross-locale search** — Simplified Chinese queries find Traditional Chinese titles and vice versa
3. **Kyujitai coverage** — old-form kanji in historical credits (學園, 國語) match modern forms
4. **Independent & testable** — pure Python, no model loading, fast startup, easy to unit test
5. **Composable** — can layer on top of any tokenizer (spaCy, sudachi, or raw string matching)

## Limitations

- Character-level mapping cannot handle **word-level** variants (e.g. 打込む/打ち込む) — that's SudachiPy's job
- Some mappings are **lossy** — 弁 maps to 5 different kyujitai forms (辨辯瓣辦弁), normalizing 辨 to 弁 loses the distinction. Acceptable for search recall.
- Cluster merging via union-find can create **unexpectedly large clusters** if source dictionaries chain through intermediate forms — `build_dict.py` should log cluster sizes and flag outliers for review

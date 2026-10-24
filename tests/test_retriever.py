import random
import string
from pathlib import Path

import pytest

from docqa.retriever import STOPWORDS, FTS5Retriever, Retriever, content_tokens
from docqa.store import NewChunk, Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    s = Store(tmp_path / "r.db")
    s.replace_document(
        "fruit.md",
        "h1",
        [
            NewChunk(0, 0, 10, None, "Mango mango mango is a tropical fruit."),
            NewChunk(1, 10, 20, None, "Apples grow in cold climates; mango does not."),
        ],
    )
    s.replace_document("tools.txt", "h2", [NewChunk(0, 0, 10, None, "A hammer drives nails.")])
    return s


def test_content_tokens_lowercases_and_drops_stopwords_and_short_tokens() -> None:
    assert content_tokens("What is the MANGO, x and Café?") == ["mango", "café"]
    assert content_tokens("") == []


def test_content_tokens_deduplicates_preserving_order() -> None:
    assert content_tokens("mango apple Mango") == ["mango", "apple"]


def test_reference_words_are_stopwords() -> None:
    for word in ("it", "this", "other", "another", "one", "same", "latter"):
        assert word in STOPWORDS


def test_results_sorted_by_score_and_limited(store: Store) -> None:
    retriever = FTS5Retriever(store, min_coverage=0.0)
    results = retriever.search("mango", k=5)
    assert [c.source for c in results] == ["fruit.md", "fruit.md"]
    assert results[0].score >= results[1].score > 0
    assert results[0].text.startswith("Mango mango")
    assert len(retriever.search("mango", k=1)) == 1


def test_chunk_fields_are_mapped(store: Store) -> None:
    chunk = FTS5Retriever(store, min_coverage=0.0).search("hammer", k=3)[0]
    assert (chunk.source, chunk.chunk_index, chunk.start_char, chunk.end_char, chunk.page) == (
        "tools.txt",
        0,
        0,
        10,
        None,
    )
    assert chunk.id > 0


def test_only_stopwords_or_symbols_return_empty(store: Store) -> None:
    retriever = FTS5Retriever(store, min_coverage=0.0)
    assert retriever.search("what is the", k=5) == []
    assert retriever.search('"*:^()-+', k=5) == []
    assert retriever.search("", k=5) == []


def test_unknown_words_return_empty(store: Store) -> None:
    assert FTS5Retriever(store, min_coverage=0.0).search("zeppelin", k=5) == []


@pytest.mark.parametrize(
    "query",
    [
        'mango"',
        "mango*",
        "NEAR(mango hammer)",
        "mango AND hammer",
        "mango OR",
        "NOT mango",
        "text:mango",
        "^mango",
        "mango -apple",
        "{mango}",
        "mango\x00",
    ],
)
def test_fts5_operators_are_neutralised(store: Store, query: str) -> None:
    results = FTS5Retriever(store, min_coverage=0.0).search(query, k=5)
    assert all(c.source in {"fruit.md", "tools.txt"} for c in results)


def test_random_input_never_raises(store: Store) -> None:
    rng = random.Random(1234)
    alphabet = string.printable + "éñ中​"
    retriever = FTS5Retriever(store, min_coverage=0.0)
    for _ in range(300):
        query = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        retriever.search(query, k=3)


def test_satisfies_protocol(store: Store) -> None:
    retriever: Retriever = FTS5Retriever(store, min_coverage=0.0)
    assert isinstance(retriever, Retriever)


def test_question_filler_words_are_stopwords() -> None:
    for word in ("long", "often", "many", "quickly", "get", "need", "want", "know", "happen"):
        assert word in STOPWORDS


def test_porter_stemming_matches_word_forms(store: Store) -> None:
    retriever = FTS5Retriever(store, min_coverage=0.5)
    assert [c.source for c in retriever.search("mangoes", k=1)] == ["fruit.md"]
    assert [c.source for c in retriever.search("climate", k=1)] == ["fruit.md"]
    assert [c.source for c in retriever.search("hammers", k=1)] == ["tools.txt"]


def test_short_question_fully_covered_passes_the_gate(store: Store) -> None:
    # A one-word question whose word is in the best chunk has coverage 1.0, however low its
    # BM25 score: this is the "What is the warranty?" case from the QA report.
    results = FTS5Retriever(store, min_coverage=1.0).search("What is a hammer?", k=5)
    assert [c.source for c in results] == ["tools.txt"]


def test_unknown_content_word_blocks_the_gate(store: Store) -> None:
    # "mango" matches, but "zeppelin" is not in the corpus at all, so it carries the most
    # weight and the best chunk covers well under half of the question.
    retriever = FTS5Retriever(store, min_coverage=0.5)
    assert retriever.search("mango zeppelin", k=5) == []
    assert FTS5Retriever(store, min_coverage=0.0).search("mango zeppelin", k=5) != []


def test_coverage_is_idf_weighted(store: Store) -> None:
    retriever = FTS5Retriever(store, min_coverage=0.0)
    top = retriever.search("mango", k=1)[0]
    assert retriever.coverage(["mango"], top.id) == pytest.approx(1.0)
    assert retriever.coverage(["zeppelin"], top.id) == 0.0
    # "mango" is in two of three chunks, "tropical" in one: the rarer word weighs more.
    second = retriever.search("apples", k=1)[0]
    assert retriever.coverage(["mango", "tropical"], second.id) < 0.5
    assert retriever.coverage([], top.id) == 0.0


def test_gate_keeps_weaker_chunks_as_context(store: Store) -> None:
    results = FTS5Retriever(store, min_coverage=0.5).search("mango tropical", k=5)
    assert [c.text[:5] for c in results] == ["Mango", "Apple"]  # 2nd lacks "tropical", kept


def test_invalid_min_coverage_is_rejected(store: Store) -> None:
    for value in (-0.1, 1.5, float("nan")):
        with pytest.raises(ValueError, match="min_coverage"):
            FTS5Retriever(store, min_coverage=value)


def test_vietnamese_matches_with_and_without_diacritics(tmp_path: Path) -> None:
    store = Store(tmp_path / "vi.db")
    store.replace_document(
        "vi.md", "h", [NewChunk(0, 0, 10, None, "Chính sách bảo hành: dự án giá cố định.")]
    )
    retriever = FTS5Retriever(store, min_coverage=0.5)
    for query in ("bảo hành dự án", "bao hanh du an"):
        assert [c.source for c in retriever.search(query, k=1)] == ["vi.md"], query

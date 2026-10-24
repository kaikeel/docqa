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
    retriever = FTS5Retriever(store, min_score=0.0)
    results = retriever.search("mango", k=5)
    assert [c.source for c in results] == ["fruit.md", "fruit.md"]
    assert results[0].score >= results[1].score > 0
    assert results[0].text.startswith("Mango mango")
    assert len(retriever.search("mango", k=1)) == 1


def test_chunk_fields_are_mapped(store: Store) -> None:
    chunk = FTS5Retriever(store, min_score=0.0).search("hammer", k=3)[0]
    assert (chunk.source, chunk.chunk_index, chunk.start_char, chunk.end_char, chunk.page) == (
        "tools.txt",
        0,
        0,
        10,
        None,
    )
    assert chunk.id > 0


def test_below_threshold_returns_empty(store: Store) -> None:
    assert FTS5Retriever(store, min_score=1000.0).search("mango", k=5) == []


def test_only_stopwords_or_symbols_return_empty(store: Store) -> None:
    retriever = FTS5Retriever(store, min_score=0.0)
    assert retriever.search("what is the", k=5) == []
    assert retriever.search('"*:^()-+', k=5) == []
    assert retriever.search("", k=5) == []


def test_unknown_words_return_empty(store: Store) -> None:
    assert FTS5Retriever(store, min_score=0.0).search("zeppelin", k=5) == []


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
    results = FTS5Retriever(store, min_score=0.0).search(query, k=5)
    assert all(c.source in {"fruit.md", "tools.txt"} for c in results)


def test_random_input_never_raises(store: Store) -> None:
    rng = random.Random(1234)
    alphabet = string.printable + "éñ中​"
    retriever = FTS5Retriever(store, min_score=0.0)
    for _ in range(300):
        query = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        retriever.search(query, k=3)


def test_satisfies_protocol(store: Store) -> None:
    retriever: Retriever = FTS5Retriever(store, min_score=0.0)
    assert isinstance(retriever, Retriever)


def test_threshold_gates_on_best_match_and_keeps_weaker_context(store: Store) -> None:
    scores = [c.score for c in FTS5Retriever(store, min_score=float("-inf")).search("mango", 5)]
    best, weaker = scores[0], scores[-1]
    assert best > weaker
    gate = (best + weaker) / 2  # above the weaker chunk, below the best one
    results = FTS5Retriever(store, min_score=gate).search("mango", 5)
    assert [c.score for c in results] == scores  # weaker chunk kept as context
    assert FTS5Retriever(store, min_score=best + 0.01).search("mango", 5) == []

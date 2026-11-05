from goldengate.core.text import (
    content_tokens,
    extract_citations,
    extract_quantities,
    normalize_informal,
    split_sentences,
    stem,
    strip_citations,
    word_count,
)
from goldengate.retrieval.corpus import chunk_markdown, load_corpus, slugify
from goldengate.retrieval.retrievers import BM25Retriever, TfidfRetriever, build_retriever


def test_quantities_are_typed():
    q = extract_quantities("Pay $1,500 or 3.75% by 9:00 AM; call 1-800-555-0100 within 60 days.")
    assert q == {"$1500", "3.75%", "09:00am", "tel:18005550100", "#60"}
    assert extract_quantities("$3") != extract_quantities("3%")


def test_sentences_and_citations():
    text = "The fee is $12 [acc-x#fee]. It is waived at $1,500 [acc-x#waiver]."
    assert len(split_sentences(text)) == 2
    assert extract_citations(text) == ["acc-x#fee", "acc-x#waiver"]
    assert strip_citations(text) == "The fee is $12. It is waived at $1,500."
    assert word_count(text) == 9


def test_stemming_and_stopwords():
    assert stem("fees") == stem("fee")
    assert stem("removing") == stem("remove")
    assert "doe" not in content_tokens("Does Meridian Bank charge fees?")
    assert normalize_informal("pls, wat is ur fee") == "please, what is your fee"


def test_chunker_and_corpus():
    md = "---\nid: doc-a\ntitle: Doc A\ncategory: fees\n---\n# Doc A\n\nIntro text.\n\n## Fee Rules\n\nFee is $5.\n"
    chunks = chunk_markdown(md, "fallback")
    assert [c.chunk_id for c in chunks] == ["doc-a#overview", "doc-a#fee-rules"]
    assert slugify("Cashier's Checks") == "cashier-s-checks"
    corpus = load_corpus()
    assert len({c.doc_id for c in corpus}) == 40
    assert len({c.chunk_id for c in corpus}) == len(corpus)


def test_retrievers_rank_relevant_chunk_first():
    corpus = load_corpus()
    for retriever in (BM25Retriever(corpus), TfidfRetriever(corpus), build_retriever("tfidf", corpus)):
        hits = retriever.search("outgoing international wire transfer fee", 3)
        assert hits[0].chunk_id == "transfer-international-wire#fees"
        assert [h.rank for h in hits] == [1, 2, 3]
        assert retriever.search("the and of", 3) == []


def test_unknown_retriever():
    import pytest

    with pytest.raises(ValueError):
        build_retriever("faiss", [])

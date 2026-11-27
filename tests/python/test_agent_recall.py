"""Agent recall: an assistant's memory loaded by search instead of whole (2026-11-27).

    python -m pytest tests/python/test_agent_recall.py

Design: docs/superpowers/specs/2026-11-27-agent-recall-design.md.
"""
from _paths import ROOT, SERVER  # noqa: F401

import time

import pytest

import agent_recall as ar

RULES = ("## Luật chủ dặn\n"
         "- Nhắn Zalo thì không dùng markdown.\n"
         "- Xưng em, gọi khách là anh chị.\n")
PRICE = ("## Bảng giá nước mắm\n"
         "- Chai 500ml cá cơm 40 độ đạm: giá đại lý 85.000đ, giá lẻ 110.000đ.\n"
         "- Thùng 12 chai được chiết khấu 5%.\n")
SHIP = ("## Giao hàng\n"
        "- Phí ship nội thành 20.000đ, đơn trên 500.000đ miễn phí.\n"
        "- Đổi trả trong 7 ngày nếu chai vỡ, khách gửi ảnh.\n")


def filler(n):
    return "".join(f"## Ghi chú {i}\n- Khách {i} thích món kho rim, đã mua {i} lần trong tháng.\n\n" for i in range(n))


def big_memory(extra=""):
    return "Bạn là trợ lý bán hàng LCX.\n\n" + RULES + "\n" + PRICE + "\n" + SHIP + "\n" + extra + filler(300)


@pytest.fixture
def recall(tmp_path):
    r = ar.AgentRecall(tmp_path)
    yield r
    r.index.close()


def test_normalize_and_terms():
    assert ar.normalize("Giá ĐẠI lý") == "gia dai ly"
    assert ar.terms("em có tạo được ảnh không") == ["tao"], "pronouns and filler are not search words"
    assert ar.terms("giá sỉ nước mắm") == ["gia", "si", "nuoc", "mam"]


def test_small_memory_is_unchanged(recall):
    text = "Bạn là trợ lý.\n\n" + RULES + PRICE
    prep = recall.prepare("b::small", text)
    assert prep.plan.whole and not prep.indexed
    assert prep.memory_text == text, "byte for byte the old behaviour"
    assert recall.recall(prep, "giá đại lý")[0] == ""


def test_rules_always_loaded_and_the_rest_searchable(recall):
    text = big_memory()
    assert len(text) > ar.MIN_CHARS
    prep = recall.prepare("b::lcx", text)
    sys_text = prep.memory_text
    assert "Nhắn Zalo thì không dùng markdown" in sys_text, "an owner rule is there whatever the question"
    assert "Bạn là trợ lý bán hàng LCX" in sys_text, "the opening text is part of the constitution"
    assert "85.000" not in sys_text, "knowledge is not preloaded"
    assert "Memory map" in sys_text and "Bảng giá nước mắm" in sys_text, "the map names what can be looked up"
    assert len(sys_text) < ar.CORE_MAX + ar.MAP_MAX + 200

    block, hits = recall.recall(prep, "giá đại lý chai 500ml bao nhiêu")
    assert "85.000" in block and block.startswith("[RECALLED MEMORY")
    assert hits[0].title == "Bảng giá nước mắm"
    block2, _ = recall.recall(prep, "phí ship đơn 600 nghìn")
    assert "miễn phí" in block2 and "85.000" not in block2

    assert recall.recall(prep, "em có tạo được ảnh không")[0] == "", "an unrelated question loads nothing"
    assert recall.recall(prep, "Zalo markdown")[0] == "", "rules already in the prompt are not recalled twice"


def test_unaccented_query_finds_accented_note(recall):
    prep = recall.prepare("b::lcx", big_memory())
    assert "85.000" in recall.recall(prep, "gia dai ly")[0]


def test_rules_over_the_cap_are_searchable_and_flagged(recall):
    many_rules = "## Luật bán hàng\n" + "".join(
        f"- Quy định số {i}: khi khách hỏi về sản phẩm mã SP{i:04d} thì báo kho trước khi chốt.\n" for i in range(400))
    text = big_memory(many_rules)
    prep = recall.prepare("b::rules", text)
    assert prep.plan.overflow, "rules beyond the cap are not dropped silently"
    assert len(prep.plan.core) <= ar.CORE_MAX
    assert "Nhắn Zalo thì không dùng markdown" in prep.memory_text
    assert "did not fit above" in prep.memory_text
    block, hits = recall.recall(prep, "sản phẩm SP0390")
    assert "SP0390" in block and hits[0].kind == "rule"
    assert recall.constitution_overflow(text) > 0
    assert recall.constitution_overflow(big_memory()) == 0


def test_marked_section_is_always_loaded(recall):
    text = big_memory("## Cách chào khách (luôn nạp)\n- Mở đầu bằng 'Dạ LCX xin chào'.\n\n")
    prep = recall.prepare("b::mark", text)
    assert "Dạ LCX xin chào" in prep.memory_text


def test_incremental_only_changed_sources(recall, tmp_path):
    doc = tmp_path / "bang-gia.md"
    doc.write_text("# Bảng giá\nCombo quà Tết giá 450.000đ.\n", encoding="utf-8")
    other = tmp_path / "quy-trinh.md"
    other.write_text("# Quy trình\nĐóng gói hai lớp xốp.\n", encoding="utf-8")
    docs = [("bang-gia.md", doc), ("quy-trinh.md", other)]
    text = big_memory()
    recall.prepare("b::inc", text, docs)
    assert recall.index.sync("b::inc", []) == {"changed": 0, "removed": 3}, "sanity: three sources were indexed"
    recall._cache.clear()
    r1 = recall.prepare("b::inc", text, docs)
    assert recall.prepare("b::inc", text, docs) is r1, "an unchanged assistant is served from the cache"
    again = recall.index.sync("b::inc", [
        ar.Source("memory", ar._sha(ar.SCHEMA_VERSION + str(ar.CORE_MAX) + str(ar.min_chars()) + text), lambda: 1 / 0),
        ar.Source("bang-gia.md", f"{doc.stat().st_mtime_ns}:{doc.stat().st_size}", lambda: 1 / 0),
        ar.Source("quy-trinh.md", f"{other.stat().st_mtime_ns}:{other.stat().st_size}", lambda: 1 / 0),
    ])
    assert again == {"changed": 0, "removed": 0}, "nothing re-read when nothing changed"
    time.sleep(0.01)
    doc.write_text("# Bảng giá\nCombo quà Tết giá 520.000đ.\n", encoding="utf-8")
    recall.prepare("b::inc", text, docs)
    block, _ = recall.recall(r1, "combo quà tết giá")
    assert "520.000" in block and "450.000" not in block


def test_documents_are_searchable_for_a_small_memory(recall, tmp_path):
    doc = tmp_path / "huong-dan.md"
    doc.write_text("# Hướng dẫn\n## Pha nước chấm\nMột muỗng mắm, hai muỗng đường, chanh và tỏi ớt.\n",
                   encoding="utf-8")
    prep = recall.prepare("b::docs", "Bạn là trợ lý.", [("huong-dan.md", doc)])
    assert prep.memory_text == "Bạn là trợ lý.", "a small memory stays whole"
    block, hits = recall.recall(prep, "cách pha nước chấm")
    assert "hai muỗng đường" in block and hits[0].kind == "doc"


def test_scopes_do_not_leak(recall):
    recall.prepare("b::one", big_memory())
    other = recall.prepare("b::two", "x" * 13000)
    assert recall.recall(other, "giá đại lý")[0] == ""
    assert recall.index.get("b::two", recall.recall(recall.prepare("b::one", big_memory()), "giá đại lý")[1][0].id) == []


def test_enrichment_finds_synonyms(recall):
    prep = recall.prepare("b::syn", big_memory())
    assert recall.recall(prep, "lấy buôn")[0] == "", "before enrichment the word is nowhere in the memory"
    calls = []

    def model(system, prompt):
        calls.append(prompt)
        import re
        out = []
        for n, body in re.findall(r'<note n="(\d+)"[^>]*>\n(.*?)\n</note>', prompt, re.S):
            wholesale = "đại lý" in body
            out.append({"n": int(n), "questions": ["giá sỉ bao nhiêu"] if wholesale else [],
                        "aliases": ["giá sỉ", "giá buôn"] if wholesale else [], "summary": "bảng giá"})
        return "```json\n" + __import__("json").dumps(out, ensure_ascii=False) + "\n```"

    n = recall.enrich_pending(model, daily=100, max_calls=200)
    assert n > 0 and calls
    assert "85.000" in recall.recall(prep, "lấy buôn")[0], "an enriched note is found by another word"
    assert recall.enrich_pending(model, daily=100) == 0, "nothing left: each passage is enriched once"
    assert recall.index.stats("b::syn")["enriched"] > 0


def test_enrichment_respects_the_daily_cap(recall):
    recall.prepare("b::cap", big_memory())
    seen = []
    assert recall.enrich_pending(lambda s, p: seen.append(1) or "[]", daily=2, max_calls=10) == 0
    assert len(seen) == 2, "two calls, then the cap stops it"


def test_usage_signal_boosts_a_passage(recall):
    prep = recall.prepare("b::use", big_memory())
    hits = recall.index.search("b::use", "khách thích món kho rim", limit=8)
    last = hits[-1]
    recall.index.record("b::use", [last.chunk_hash] * 1, used=True)
    for _ in range(4):
        recall.index.record("b::use", [last.chunk_hash], used=True)
    again = recall.index.search("b::use", "khách thích món kho rim", limit=8)
    assert again[0].chunk_hash == last.chunk_hash, "a passage the model keeps opening ranks higher"
    del prep


def test_scales_to_a_large_memory(recall):
    big = big_memory() + "".join(
        f"## Khách hàng {i}\n- Chị Lan {i} ở quận {i % 12}, hay mua combo {i % 7}, số 09{i:08d}.\n\n"
        for i in range(40000))
    assert len(big) > 3_000_000
    t = time.time()
    prep = recall.prepare("b::big", big)
    build = time.time() - t
    assert len(prep.memory_text) < ar.CORE_MAX + ar.MAP_MAX + 200, "the prompt does not grow with the memory"
    t = time.time()
    for _ in range(10):
        block, hits = recall.recall(prep, "số điện thoại của chị Lan 31337")
    per = (time.time() - t) / 10
    assert "0900031337" in block
    assert per < 0.25, f"one recall took {per:.3f}s"
    t = time.time()
    recall.prepare("b::big", big)
    assert time.time() - t < build, "an unchanged memory is not re-indexed"

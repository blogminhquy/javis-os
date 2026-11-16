"""Test khối B UX Kết nối: nhóm Google một cửa + wizard steps + dùng lại key client.

Chạy: python tests/run.py connect_group
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os
import tempfile

# One test adds a real connection: keep its store out of server/ when the file is run on its own.
os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-connect-group-"))

import mcp_catalog  # noqa: E402
import mcp_store  # noqa: E402

GOOGLE_GROUP = {"google-workspace", "google-tasks", "google-calendar",
                "gmail", "google-keep", "google-sheets"}
STEP_CONNECTORS = {"google-workspace", "google-tasks", "google-calendar",
                   "gmail", "google-keep"}


def _public():
    return {c["id"]: c for c in mcp_catalog.public_catalog()}


def test_nhom_google_du_thanh_vien():
    pc = _public()
    got = {cid for cid, c in pc.items() if c.get("group") == "google"}
    assert got == GOOGLE_GROUP
    # Google Ads KHÔNG thuộc nhóm (mảng Quảng cáo, mental model khác)
    assert pc["google-ads"].get("group", "") == ""


def test_moi_thanh_vien_nhom_co_group_line():
    pc = _public()
    for cid in GOOGLE_GROUP:
        line = pc[cid].get("group_line", "")
        assert line, cid
        assert len(line) <= 120, f"{cid}: group_line dài quá ({len(line)})"
        assert "—" not in line, f"{cid}: group_line chứa em dash"


def test_cac_connector_bat_buoc_co_steps():
    # Trước 0.55.36 danh sách này còn meta-ads-graph và facebook-pages. Hai khuôn đó đã dọn sang
    # repo kho, nên phép kiểm "có steps" đi theo chúng sang `tools/kiem-tra.py` bên ấy - nó chạy
    # trên MỌI gói trong kho, tức phủ rộng hơn hai cái tên ghi cứng ở đây.
    pc = _public()
    for cid in STEP_CONNECTORS:
        assert pc[cid].get("steps"), f"{cid}: thiếu wizard steps"


# Trần độ dài của MỘT bước wizard. Con số này là hàng rào chống một bước phình thành cả
# bài guide, KHÔNG phải ràng buộc layout: .conn-steps chỉ là <li> chữ xuống dòng tự do, không
# cắt cụt, không line-clamp (đã soi console.css). Trần cũ 260 đặt hồi các bước còn ngắn; sau
# đó chín bước của Facebook/Google dài ra vì mỗi câu thêm vào là một sự cố có thật của người
# dùng ('URL bị chặn', 'Invalid Scopes', 'Miền ứng dụng'). Vì test này CHƯA TỪNG chạy trong CI
# (thiếu block __main__) nên không ai thấy lúc chúng vượt trần. Cắt bớt để vừa con số cũ là
# vứt đúng phần cứu người dùng, nên nới trần thay vì cắt chữ.
STEP_TEXT_MAX = 450


def test_steps_dung_schema():
    """Soi schema MỌI connector có steps (không chỉ nhóm Google) - thêm connector mới
    có steps là tự động được kiểm."""
    for c in mcp_catalog.public_catalog():
        steps = c.get("steps") or []
        if not steps:
            continue
        cid = c["id"]
        assert len(steps) >= 4, f"{cid}: quá ít bước"
        for i, s in enumerate(steps):
            assert s.get("text", "").strip(), f"{cid} bước {i}: thiếu text"
            assert len(s["text"]) <= STEP_TEXT_MAX, \
                f"{cid} bước {i}: text dài quá ({len(s['text'])}/{STEP_TEXT_MAX})"
            assert "—" not in s["text"], f"{cid} bước {i}: em dash"
            if s.get("link"):
                assert s["link"].startswith("https://"), f"{cid} bước {i}: link không https"
                assert s.get("link_label", "").strip(), f"{cid} bước {i}: có link phải có nhãn"
            # "domain" là ô copy tên miền cho bản cài VPS - console.js dựng nó bằng
            # domainCopyBox(). Danh sách này viết hồi chỉ có mỗi ô Redirect URI, và vì test
            # chưa từng chạy nên không ai thấy nó đã lạc hậu so với giao diện.
            assert s.get("copy", "") in ("", "redirect", "domain"), f"{cid} bước {i}: copy lạ"


def test_oauth_byo_co_buoc_redirect():
    """Connector oauth BYO phải có đúng MỘT bước chèn ô copy
    Redirect URI - thiếu là user không biết dán gì, thừa là rối."""
    pc = _public()
    for cid in ("google-calendar", "gmail"):
        n = sum(1 for s in pc[cid]["steps"] if s.get("copy") == "redirect")
        assert n == 1, cid


def test_steps_che_setup_thi_link_khong_mat():
    """Có steps là khối setup links cũ bị ẩn - mọi link trong setup phải xuất hiện lại
    trong steps, không thì nút bị nuốt mất (từng suýt xảy ra với Facebook)."""
    for c in mcp_catalog.public_catalog():
        if not c.get("steps"):
            continue
        step_links = {s.get("link") for s in c["steps"] if s.get("link")}
        for l in (c.get("setup") or {}).get("links", []):
            assert l["url"] in step_links, f"{c['id']}: setup link '{l['label']}' không có trong steps"


def test_public_catalog_khong_lo_secret_noi_bo():
    """steps/group là trường hiển thị - không được kéo theo validate/arg_rules nội bộ."""
    for c in mcp_catalog.public_catalog():
        assert "validate" not in c and "arg_rules" not in c


# ---- reuse_client_fields: copy key server-side ----

GOOGLE_DONOR = {"group": "google", "auth": {"fields": [{"key": "client_id"}, {"key": "client_secret"}]}}


def _target_con():
    return {"group": "google", "auth": {"fields": [{"key": "client_id"}, {"key": "client_secret"},
                                                   {"key": "user_email"}]}}


def _donor(monkeypatch, secrets, con=GOOGLE_DONOR):
    monkeypatch.setattr(mcp_store, "connection_secrets", lambda cid: secrets)
    monkeypatch.setattr(mcp_store, "donor_connector", lambda cid: con)


def test_reuse_copy_du_hai_key(monkeypatch):
    _donor(monkeypatch, {"client_id": "abc.apps", "client_secret": "GOCSPX-x", "api_key": "leak-me-not"})
    out = mcp_store.reuse_client_fields(_target_con(), {}, "src1")
    assert out == {"client_id": "abc.apps", "client_secret": "GOCSPX-x"}


def test_reuse_khong_de_gia_tri_user_nhap(monkeypatch):
    _donor(monkeypatch, {"client_id": "cu.apps", "client_secret": "GOCSPX-cu"})
    out = mcp_store.reuse_client_fields(_target_con(), {"client_id": "moi.apps"}, "src1")
    assert out["client_id"] == "moi.apps"          # user nhập thì giữ
    assert out["client_secret"] == "GOCSPX-cu"     # thiếu mới copy


def test_reuse_chi_copy_key_thuoc_fields_dich(monkeypatch):
    _donor(monkeypatch, {"client_id": "abc", "client_secret": "x"})
    target = {"group": "google", "auth": {"fields": [{"key": "api_key"}]}}   # đích không nhận client key
    out = mcp_store.reuse_client_fields(target, {}, "src1")
    assert out == {}


def test_reuse_khong_from_thi_giu_nguyen():
    fields = {"client_id": "a"}
    out = mcp_store.reuse_client_fields(_target_con(), fields, "")
    assert out == fields


# ---- key family: every Google service lends and borrows, whatever card it sits on ----

GOOGLE_KEY_FAMILY = {"google-workspace", "google-tasks", "google-calendar", "gmail", "google-keep",
                     "google-sheets", "google-ads", "google-analytics", "google-search-console"}


def test_every_google_connector_is_in_the_google_key_family():
    pc = _public()
    for cid in GOOGLE_KEY_FAMILY:
        assert pc[cid].get("key_family") == "google", cid


def test_key_family_order_and_who_stays_out():
    kf = mcp_catalog.key_family
    assert kf({"key_family": "google", "group": "x"}) == "google"           # explicit wins
    assert kf({"group": "cloudflare"}) == "cloudflare"                       # then the display group
    assert kf({"auth": {"provider": "google"}}) == "google"                  # Ads, Analytics, Merchant Center
    # Meta and Slack keys are app keys with their own settings: nothing says they carry over, so no family.
    assert kf({"auth": {"provider": "meta"}}) == ""
    assert kf({"auth": {"provider": "slack"}}) == ""
    assert kf(None) == ""


def test_reuse_from_calendar_into_analytics(monkeypatch):
    """The case the owner hit: Analytics sits outside the Google card, and could not borrow the key."""
    _donor(monkeypatch, {"client_id": "cal.apps", "client_secret": "GOCSPX-cal"})
    out = mcp_store.reuse_client_fields(mcp_catalog.get("google-analytics"), {}, "calendar-conn")
    assert out.get("client_id") == "cal.apps" and out.get("client_secret") == "GOCSPX-cal"


def test_reuse_refused_across_families(monkeypatch):
    """The browser only names a connection: a donor of another family must not pour its secret in."""
    _donor(monkeypatch, {"client_id": "meta-app", "client_secret": "meta-secret"},
           {"auth": {"provider": "meta", "fields": [{"key": "client_id"}, {"key": "client_secret"}]}})
    assert mcp_store.reuse_client_fields(mcp_catalog.get("gmail"), {}, "meta-conn") == {}
    # and nothing at all when the named connection does not exist
    monkeypatch.setattr(mcp_store, "donor_connector", lambda cid: None)
    assert mcp_store.reuse_client_fields(mcp_catalog.get("gmail"), {}, "gone") == {}


def test_reuse_service_account_from_sheets_into_search_console(monkeypatch):
    sa = '{"type": "service_account", "client_email": "bot@x.iam.gserviceaccount.com"}'
    _donor(monkeypatch, {"service_account": sa, "folder_id": "FOLDER"}, mcp_catalog.get("google-sheets"))
    out = mcp_store.reuse_client_fields(mcp_catalog.get("google-search-console"), {}, "sheets-conn")
    assert out == {"service_account": sa}   # the folder id is Sheets' own setting, never lent


def test_donor_connector_reads_the_real_connection():
    cid, err = mcp_store.add_connection("google-calendar", {"label": "donor test", "auth": "oauth",
                                                           "fields": {"client_id": "a", "client_secret": "b"}})
    assert cid and not err
    try:
        assert (mcp_store.donor_connector(cid) or {}).get("id") == "google-calendar"
        assert mcp_store.donor_connector("no-such-connection") is None
        assert mcp_store.donor_connector("") is None
    finally:
        mcp_store.delete_connection(cid)


if __name__ == "__main__":
    # CI chạy TỪNG FILE như script (`python tests/python/test_x.py`), không gọi pytest.
    # Thiếu block này thì file chỉ định nghĩa hàm rồi thoát 0 - test "xanh" mà chưa từng
    # chạy một assertion nào. Bảy file từng ở tình trạng đó, và bốn assertion trong số
    # chúng đang ĐỎ mà không ai biết (xem CHANGELOG 0.13.2).
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))

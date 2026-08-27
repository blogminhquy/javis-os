"""Agent tự bồi đắp bộ nhớ LÚC DÙNG: prompt có luật + đường dẫn, nhật ký phủ mọi đường.

    python tests/run.py agent_tu_boi_dap     (KHÔNG mạng)

Phát hiện trên production (16/08, soi 0/15 agent có bộ nhớ): MEMORY.md của agent chỉ
được ĐỌC, không có dòng code nào ghi, và prompt không hề nói cho agent biết file đó
nằm đâu - kể cả khi có bộ nhớ. Tệ hơn, khối bộ nhớ chỉ chèn khi file ĐÃ có nội dung,
nên agent mới không bao giờ tạo được ký ức đầu tiên (con gà - quả trứng). Nhật ký
runs/ thì chỉ runner workflow cũ ghi: bật canary graph là nhật ký lặng lẽ biến mất.

Chủ repo chốt thiết kế: cải thiện LÚC DÙNG, không job nền quét hàng loạt. Test ghim:
1. _agent_sysprompt chèn khối bộ nhớ VÔ ĐIỀU KIỆN, kèm đường dẫn file + luật append.
2. _workflow_agent_helpers trả closure log_run; graph/resume/legacy đều truyền nó.
3. _log_agent_run cắt cả task (chống phình sau vòng retry).
4. gitignore brain chặn memory/agents/*/runs/ (nhật ký thô không vào git).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


import main  # noqa: E402

# ---- 1. Prompt agent: bộ nhớ + luật tự bồi đắp ----
with tempfile.TemporaryDirectory() as td:
    brain = str(Path(td) / "brain-test")
    Path(brain, "agents").mkdir(parents=True)
    Path(brain, "agents", "chuyen-vien-test.md").write_text(
        "---\ntype: agent\nname: Chuyên viên test\nrole: Kiểm thử\n---\nThân agent.\n",
        encoding="utf-8")

    _mk, _sysprompt, _log, _learn = main._workflow_agent_helpers(brain, tools=None)
    check("helpers trả 4 giá trị (log_run + learn)", callable(_log) and callable(_learn))

    # 0.47.9: _agent_sysprompt trả thêm NHÀ của model (agent chạy được mọi provider,
    # không chỉ Claude/Codex) - xem tests/python/test_agent_model_da_nha.py.
    name, sp, model, prov = _sysprompt("chuyen-vien-test")
    check("CANARY: agent CHƯA có ký ức vẫn thấy khối bộ nhớ (hết con gà - quả trứng)",
          "# Bộ nhớ của bạn" in sp and "chưa có ký ức" in sp)
    check("prompt chỉ rõ ĐƯỜNG DẪN file MEMORY.md", "MEMORY.md" in sp)
    check("prompt có luật tự bồi đắp qua marker (model đề xuất, code ghi)",
          "Tự bồi đắp" in sp and "JAVIS_LESSON" in sp)
    check("luật CẤM agent tự sửa file bộ nhớ", "KHÔNG tự sửa file bộ nhớ" in sp)
    check("luật có phanh chống ghi vụn vặt và chống lặp",
          "ĐỪNG phát JAVIS_LESSON" in sp and "đừng lặp lại" in sp)

    # Có ký ức thì nội dung phải vào prompt như cũ.
    memf = Path(brain, "memory", "agents", "chuyen-vien-test")
    memf.mkdir(parents=True)
    (memf / "MEMORY.md").write_text(
        "# Ghi chú của chủ\n- Khách quen tên Ba.\n", encoding="utf-8")
    _, sp2, _, _ = _sysprompt("chuyen-vien-test")
    check("có ký ức thì ký ức vào prompt", "Khách quen tên Ba" in sp2)

    # ---- Vòng "model đề xuất, code ghi" chạy THẬT qua closure _learn ----
    out_tho = ("Đã xong việc.\nJAVIS_LESSON: Chủ thích báo cáo dạng bảng.\n"
               "JAVIS_LESSON: Kho A thường trễ 2 ngày.\n")
    out_sach = _learn("chuyen-vien-test", out_tho)
    check("CANARY: marker bị BÓC khỏi output (không chảy vào {{prev}}/UI)",
          "JAVIS_LESSON" not in out_sach and "Đã xong việc." in out_sach)
    mem = (memf / "MEMORY.md").read_text(encoding="utf-8")
    check("CANARY: bài học vào đúng mục tự học",
          main._BAI_HOC_HEADER in mem and "- Chủ thích báo cáo dạng bảng." in mem)
    check("phần chủ viết tay còn NGUYÊN", "# Ghi chú của chủ" in mem
          and "- Khách quen tên Ba." in mem)

    # Chống trùng: cùng bài học (khác hoa thường/dấu chấm) không được nhân đôi.
    _learn("chuyen-vien-test", "ok\nJAVIS_LESSON: chủ thích báo cáo dạng bảng\n")
    mem = (memf / "MEMORY.md").read_text(encoding="utf-8")
    check("bài học trùng (khác hoa thường) không nhân đôi",
          mem.count("báo cáo dạng bảng") == 1)

    # Trần cứng: dồn 30 bài học, mục tự học chỉ giữ N dòng mới nhất.
    for i in range(30):
        main._ghi_bai_hoc(brain, "chuyen-vien-test", [f"Bài học số {i}"])
    mem = (memf / "MEMORY.md").read_text(encoding="utf-8")
    tu_hoc = mem.split(main._BAI_HOC_HEADER, 1)[1]
    so_dong = sum(1 for l in tu_hoc.splitlines() if l.strip().startswith("- "))
    check(f"CANARY: mục tự học không vượt trần {main._BAI_HOC_TRAN} dòng (bộ nhớ đặc "
          "dần, không dài dần)", so_dong == main._BAI_HOC_TRAN)
    check("giữ dòng MỚI nhất, bỏ dòng cũ", "Bài học số 29" in mem and "Bài học số 0" not in mem)
    check("phần chủ viết vẫn nguyên sau 30 vòng", "- Khách quen tên Ba." in mem)

    # Không có marker → không đụng file, output giữ nguyên.
    check("output không marker thì trả nguyên xi",
          _learn("chuyen-vien-test", "chỉ là kết quả") == "chỉ là kết quả")

    # ---- 3. _log_agent_run cắt cả task lẫn out ----
    main._log_agent_run(brain, "chuyen-vien-test", "T" * 9000, "O" * 9000)
    runs = list((memf / "runs").glob("*.md"))
    check("log_run ghi được file runs/<ngày>.md", len(runs) == 1)
    noi_dung = runs[0].read_text(encoding="utf-8")
    check("task bị cắt (chống phình sau retry)", noi_dung.count("T") <= 2100)
    check("kết quả bị cắt như cũ", noi_dung.count("O") <= 1600)

# ---- 2. Nhật ký + học phủ mọi đường chạy (đối chiếu mã nguồn) ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: _run_workflow_step nhận log_run (đường graph + resume hết mù)",
      "log_run=None" in src and src.count("log_run=log_run, learn=learn") >= 2)
check("runner cũ cũng bóc bài học trước khi out thành {{prev}}",
      "_learn(agent_slug, out)" in src)
check("agent kiểm chứng cũng được ghi nhật ký (cả 2 đường)",
      src.count("[kiểm chứng bước của") >= 2)
check("runner cũ vẫn ghi nhật ký qua cùng closure", "_log(agent_slug, task_f, out)" in src)

# ---- 4. Nhật ký thô không vào git của brain ----
import git_brain  # noqa: E402
check("gitignore brain chặn memory/agents/*/runs/",
      "memory/agents/*/runs/" in git_brain._GITIGNORE
      and "Memory/agents/*/runs/" in git_brain._GITIGNORE)

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_agent_tu_boi_dap: tat ca pass")

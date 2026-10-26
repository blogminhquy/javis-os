"""Chạy toàn bộ test của Javis (Python + JS). Chạy từ ĐÂU cũng được.

    python tests/run.py                  # tất cả
    python tests/run.py zalo             # chỉ file có 'zalo' trong tên
    python tests/run.py --js             # chỉ test JS
    python tests/run.py --py             # chỉ test Python
    python tests/run.py -v               # in cả output của test đỏ
    python tests/run.py --jobs 4         # chạy 4 file cùng lúc (mặc định 1, lần lượt)
    python tests/run.py --py --shard 1/2 # chỉ chạy nhóm 1 trong 2 nhóm (CI chia máy theo cách này)
    python tests/run.py --py --plan 2    # in cách chia 2 nhóm rồi thoát, không chạy gì
    python tests/run.py --update-timings # chạy xong thì ghi thời gian đo được vào tests/test_timings.json
    python tests/run.py --timeout 1200   # file nào chạy quá 1200 giây thì dừng và tính là đỏ

Vì sao có file này: CI quét thư mục bằng vòng lặp shell, nhưng trên máy Windows thì gõ lại
vòng lặp đó mỗi lần rất phiền, và dễ chạy nhầm bằng python hệ thống (thiếu thư viện) thay vì
.venv. Script này tự tìm .venv và tự chọn đúng trình thông dịch.

Từ 0.344.0 CI cũng chạy qua đây: 2 máy, mỗi máy 4 file cùng lúc (trước đó một máy chạy lần lượt
mất ~67 phút). Mỗi file vẫn là một tiến trình Python riêng với thư mục tạm riêng, như cũ.
"""
import json
import os
import queue
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_DIR = ROOT / "tests" / "python"
JS_DIR = ROOT / "tests" / "js"
# Thời gian chạy từng file (giây), chỉ dùng để chia nhóm cho đều. Sai lệch hay thiếu file chỉ làm
# các nhóm lệch nhau vài phút, không bao giờ làm sót hay trùng test: danh sách luôn quét từ thư mục.
TIMINGS = ROOT / "tests" / "test_timings.json"
# Test đo THỜI GIAN (tỉ lệ nạp main so với fastapi, trần suy từ hằng số chờ...). Chạy nhiều luồng thì các file này chạy
# MỘT MÌNH sau cùng: lượt CI e243532 đỏ ở test_khoi_dong_nhe (tỉ lệ 6.63 > 5.0) chỉ vì 3 file khác đang chiếm CPU lúc đo.
# Danh sách lấy từ chính các test đo thời gian mà tests/python/test_ci_noi_ro_test_do.py đã ghim; thêm vào khi có test mới
# kiểu này. Thiếu tên ở đây không làm sót test, chỉ làm test đó chạy chung với các file khác.
CHAY_RIENG = frozenset({
    "test_khoi_dong_nhe.py", "test_khoi_dong_cham.py", "test_settings_khong_treo_theo_cli.py",
    "test_dua_token_claude.py", "test_terminal.py", "test_claude_khong_tu_dang_xuat.py",
})


def trinh_thong_dich() -> str:
    """Ưu tiên .venv của dự án - python hệ thống thường thiếu fastapi/yaml."""
    for p in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if p.is_file():
            return str(p)
    return sys.executable


def xoa_cay(p) -> None:
    """rmtree chịu được file chỉ-đọc (object của git trên Windows); sót gì thì bỏ qua."""
    def go_chi_doc(ham, duong, _loi):
        try:
            os.chmod(duong, stat.S_IWRITE)
            ham(duong)
        except OSError:
            pass

    # \\?\ để xoá được cây sâu quá 260 ký tự (có test cố ý dựng như vậy).
    p = os.path.abspath(p)
    if os.name == "nt" and not p.startswith("\\\\?\\"):
        p = "\\\\?\\" + p
    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(p, onexc=go_chi_doc)
        else:
            shutil.rmtree(p, onerror=go_chi_doc)
    except OSError:
        pass


# Thư mục tạm chưa xoá được ngay sau test (tiến trình cháu còn giữ file): thử lại ở cuối lượt.
_SOT = []


def _giet_ca_cay(p) -> None:
    """Giết tiến trình test VÀ mọi tiến trình con cháu của nó (server dựng thật, CLI giả...).
    Chỉ giết tiến trình cha thì cháu còn giữ ống stdout, và việc đọc output sau đó treo tiếp."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        else:
            os.killpg(p.pid, 9)
    except OSError:
        pass
    p.kill()


def chay_mot(cmd, env, cwd=ROOT, han_giay=None):
    """Chạy một file test với thư mục tạm riêng, xoá ngay sau khi tiến trình thoát.

    Xem tests/python/_paths.py: test tự dọn thư mục tạm lúc atexit, nhưng trên Windows sqlite
    còn mở ở biến module thì lúc đó chưa xoá được, còn test JS thì không tự dọn. Tạo thư mục ở
    ĐÂY (cùng tiền tố `jt-<pid>-` của _paths để lượt bị giết ngang cũng được quét), trỏ
    TMP/TEMP/TMPDIR/JAVIS_TEST_TMP của tiến trình con vào đó, chờ nó thoát rồi xoá - lúc này
    file đã được nhả. Một tầng, không lồng: thêm tầng là đường dẫn vượt 260 ký tự trên Windows.

    `han_giay` (`--timeout`, 0.344.0): quá hạn thì giết cả cây tiến trình và trả mã 124 kèm dòng
    "QUÁ GIỜ". Không có hạn thì một file treo giữ máy CI tới trần 6 tiếng mà log không nói file nào.
    """
    tam = tempfile.mkdtemp(prefix=f"jt-{os.getpid()}-")
    env = dict(env, TMP=tam, TEMP=tam, TMPDIR=tam, JAVIS_TEST_TMP=tam)
    nhom = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    try:
        p = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8", errors="replace", **nhom)
        try:
            out, err = p.communicate(timeout=han_giay)
            ma = p.returncode
        except subprocess.TimeoutExpired:
            _giet_ca_cay(p)
            try:
                out, err = p.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                out, err = "", ""
            ma = 124
            err = (err or "") + f"\nQUÁ GIỜ: chạy quá {han_giay} giây, đã dừng cả cây tiến trình.\n"
        return subprocess.CompletedProcess(cmd, ma, out, err)
    finally:
        # Tiến trình cháu (server, CLI giả) có thể nhả file chậm hơn một chút - thử lại vài lần.
        for _ in range(3):
            xoa_cay(tam)
            if not os.path.exists(tam):
                break
            time.sleep(0.5)
        else:
            _SOT.append(tam)


def doc_thoi_gian() -> dict:
    try:
        return {k: float(v) for k, v in json.loads(TIMINGS.read_text(encoding="utf-8"))["giay"].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def ban_sao_repo(so: int) -> list:
    """`so` bản sao của repo, mỗi luồng chạy song song dùng riêng một bản (0.344.0).

    Vì sao: trạng thái app mặc định nằm NGAY TRONG cây mã (server/*.json, server/*.db, brains/), và
    nhiều test đọc ghi đúng chỗ đó. Chạy lần lượt thì không sao, chạy 4 file cùng lúc thì chúng giẫm
    lên nhau: CI 26/10 đỏ ở test_chat_disconnect vì một file khác ghi vào `brains/Brain Default` đúng
    lúc lượt chat đang chạy. Đổi JAVIS_STATE_DIR/BRAINS_DIR thì lại sai với test tự đặt hai biến đó
    bằng `setdefault` và với code tìm module trong STATE_DIR. Bản sao giữ nguyên mọi đường dẫn mặc
    định: mỗi luồng là một "CI cũ" thu nhỏ, các file trong luồng chạy lần lượt trên một cây riêng.

    Chép cả `.git` (test quay về phiên bản cũ đọc commit lịch sử) và cả thay đổi chưa commit, để
    chạy ở máy dev vẫn kiểm đúng code đang sửa. Bỏ `.venv` (nặng, và trình thông dịch vẫn trỏ về
    bản gốc) cùng `__pycache__`.
    """
    goc = tempfile.mkdtemp(prefix=f"jt-{os.getpid()}-w")
    ds = []
    for k in range(so):
        dich = Path(goc) / str(k)
        shutil.copytree(ROOT, dich, symlinks=True,
                        ignore=shutil.ignore_patterns(".venv", "__pycache__"))
        ds.append(dich)
    return ds


def uoc_giay(giay: dict):
    """Hàm ước thời gian một file: số đo nếu có, không thì trung vị của bảng (1 giây khi bảng trống)."""
    da_do = sorted(giay.values())
    mac_dinh = da_do[len(da_do) // 2] if da_do else 1.0
    return lambda t: giay.get(t, mac_dinh)


def chia_nhom(ten: list, so_nhom: int, giay: dict) -> list:
    """Chia `ten` thành `so_nhom` nhóm có tổng thời gian gần bằng nhau, xác định được (cùng đầu vào,
    cùng kết quả trên mọi máy). Cách chia: file nặng nhất trước, mỗi file vào nhóm đang nhẹ nhất.
    File chưa có trong bảng thời gian (test mới) lấy trung vị của bảng.

    Mỗi nhóm giữ thứ tự nặng trước, nên chạy song song thì file dài nhất khởi động sớm nhất.
    Danh sách rỗng, trùng tên, nhóm rỗng hay hợp các nhóm lệch danh sách gốc đều là LỖI, không bỏ qua.
    """
    if so_nhom < 1:
        raise ValueError(f"số nhóm phải >= 1, nhận {so_nhom}")
    if not ten:
        raise ValueError("không tìm thấy test nào để chia nhóm")
    if len(set(ten)) != len(ten):
        raise ValueError("danh sách test có tên trùng")
    nang = uoc_giay(giay)

    nhom = [[] for _ in range(so_nhom)]
    tai = [0.0] * so_nhom
    for t in sorted(ten, key=lambda t: (-nang(t), t)):
        i = min(range(so_nhom), key=lambda k: (tai[k], k))
        nhom[i].append(t)
        tai[i] += nang(t)

    gop = [t for n in nhom for t in n]
    if len(gop) != len(set(gop)) or set(gop) != set(ten):
        raise RuntimeError("chia nhóm hỏng: hợp các nhóm khác danh sách test")
    rong = [i + 1 for i, n in enumerate(nhom) if not n]
    if rong:
        raise ValueError(f"nhóm {rong} không có test nào ({len(ten)} test cho {so_nhom} nhóm)")
    return nhom


def doc_tham_so(args: list) -> dict:
    """`--jobs 4` và `--jobs=4` đều được. Tham số không bắt đầu bằng `-` là bộ lọc tên như trước."""
    ts = {"ver": False, "js": False, "py": False, "jobs": 1, "shard": None, "plan": None, "timeout": None,
          "update": False, "loc": []}
    i = 0
    while i < len(args):
        a = args[i]
        ten, co_bang, gia_tri = a.partition("=")
        if ten in ("--jobs", "--shard", "--plan", "--timeout"):
            if not co_bang:
                i += 1
                if i >= len(args):
                    raise ValueError(f"{ten} cần một giá trị")
                gia_tri = args[i]
            if ten == "--shard":
                so, _, tong = gia_tri.partition("/")
                ts["shard"] = (int(so), int(tong))
                if not 1 <= ts["shard"][0] <= ts["shard"][1]:
                    raise ValueError(f"--shard phải dạng i/N với 1 <= i <= N, nhận {gia_tri}")
            else:
                ts[ten[2:]] = int(gia_tri)
                if ts[ten[2:]] < 1:
                    raise ValueError(f"{ten} phải >= 1")
        elif a == "-v":
            ts["ver"] = True
        elif a in ("--js", "--py"):
            ts[a[2:]] = True
        elif a == "--update-timings":
            ts["update"] = True
        elif a.startswith("-"):
            raise ValueError(f"không hiểu tham số {a}")
        else:
            ts["loc"].append(a)
        i += 1
    return ts


def main() -> int:
    try:
        ts = doc_tham_so(sys.argv[1:])
    except ValueError as e:
        print(f"Lỗi tham số: {e}")
        return 2
    ver, chi_js, chi_py, loc = ts["ver"], ts["js"], ts["py"], ts["loc"]

    py = trinh_thong_dich()
    node = shutil.which("node")
    # Chốt trung tâm (review T3 J P2-2): MỌI test chạy qua đây đều không dựng được engine phán xử hay lượt học thật, kể cả
    # test không nạp tests/python/_paths.py. `agent_judge.Judge` từ chối mọi hàm hỏi model chưa đánh dấu là engine giả.
    env = dict(os.environ, PYTHONIOENCODING="utf-8", JAVIS_NO_REAL_JUDGE_ENGINE="1", JAVIS_NO_REAL_REVIEW_ENGINE="1",
               JAVIS_NO_REAL_TEAM_ENGINE="1")

    viec = []
    if not chi_js:
        viec += [([py, str(f)], f.name) for f in sorted(PY_DIR.glob("test_*.py"))]
    if not chi_py:
        if node:
            viec += [([node, str(f)], f.name)
                     for f in sorted(list(JS_DIR.glob("test_*.js")) + list(JS_DIR.glob("test_*.mjs")))]
        else:
            print("BỎ QUA test JS: không tìm thấy node trong PATH")
    if loc:
        viec = [(c, n) for c, n in viec if any(k.lower() in n.lower() for k in loc)]

    if not viec:
        print("Không có test nào khớp.")
        return 1

    nhan = ""
    if ts["plan"] or ts["shard"]:
        so_nhom = ts["plan"] or ts["shard"][1]
        giay_cu = doc_thoi_gian()
        try:
            nhom = chia_nhom([n for _, n in viec], so_nhom, giay_cu)
        except (ValueError, RuntimeError) as e:
            print(f"Lỗi chia nhóm: {e}")
            return 2
        if ts["plan"]:
            for i, n in enumerate(nhom, 1):
                print(f"Nhóm {i}/{so_nhom}: {len(n)} file, ước {sum(map(uoc_giay(giay_cu), n)) / 60:.1f} phút "
                      f"({sum(t not in giay_cu for t in n)} file chưa có số đo)")
                for t in n:
                    print(f"  {t}")
            print(f"Tổng {sum(len(n) for n in nhom)} file, không trùng, không sót.")
            return 0
        theo_ten = dict((n, c) for c, n in viec)
        viec = [(theo_ten[t], t) for t in nhom[ts["shard"][0] - 1]]
        nhan = f" (nhóm {ts['shard'][0]}/{so_nhom})"

    # flush=True ở MỌI dòng: Python đệm stdout khi không gắn terminal, nên chạy nền hay qua
    # pipe thì log im ru tới lúc kết thúc - đúng lúc cần theo dõi tiến độ nhất thì không thấy gì.
    def ra(s=""):
        print(s, flush=True)

    # Nhiều luồng: mỗi luồng mượn một bản sao repo, chạy xong trả lại (xem ban_sao_repo).
    # Chỉ đổi đường dẫn file test sang bản sao; trình thông dịch (.venv của bản gốc) giữ nguyên.
    cho_trong = queue.Queue()
    sao = ban_sao_repo(ts["jobs"]) if ts["jobs"] > 1 else [ROOT]
    for d in sao:
        cho_trong.put(d)

    def chay_do_gio(cmd):
        goc = cho_trong.get()
        try:
            cmd = [str(goc / Path(c).relative_to(ROOT)) if Path(c).is_relative_to(ROOT / "tests") else c
                   for c in cmd]
            t = time.perf_counter()
            r = chay_mot(cmd, env, cwd=goc, han_giay=ts["timeout"])
            return r, time.perf_counter() - t
        finally:
            cho_trong.put(goc)

    tren_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    ra(f"Chạy {len(viec)} test{nhan} bằng {py}, {ts['jobs']} file cùng lúc\n")
    do, do_day_du, da_do, t0 = [], [], {}, time.perf_counter()
    # Một luồng chỉ chờ một tiến trình con, nên ThreadPool là đủ; mỗi test vẫn là tiến trình riêng.
    def bao(i, ten, r, giay):
        da_do[ten] = giay
        cham = f"  ({giay:.0f}s)" if giay >= 5 else ""
        if r.returncode == 0:
            ra(f"  [{i:>2}/{len(viec)}] ok   {ten}{cham}")
            return
        ra(f"  [{i:>2}/{len(viec)}] ĐỎ   {ten}{cham}")
        do.append(ten)
        do_day_du.append((ten, r))
        if ver and not tren_ci:
            for ln in (r.stdout or "").split("\n")[-25:]:
                ra("       " + ln)
            for ln in (r.stderr or "").split("\n")[-15:]:
                ra("       " + ln)

    # Test đo THỜI GIAN chạy một mình, sau khi cả nhóm xong: 3 luồng khác đang chiếm CPU thì phép đo nhiễu (xem CHAY_RIENG).
    rieng = [(c, n) for c, n in viec if n in CHAY_RIENG] if ts["jobs"] > 1 else []
    i = 0
    with ThreadPoolExecutor(max_workers=ts["jobs"]) as pool:
        tuong_lai = {pool.submit(chay_do_gio, cmd): ten for cmd, ten in viec if (cmd, ten) not in rieng}
        for f in as_completed(tuong_lai):
            i += 1
            bao(i, tuong_lai[f], *f.result())
    for cmd, ten in rieng:
        i += 1
        bao(i, ten, *chay_do_gio(cmd))

    # File đỏ lúc chạy CHUNG được chạy lại MỘT MÌNH, và kết quả chạy một mình là kết quả chính thức: đó đúng là điều CI cũ đòi
    # (chạy từng file lần lượt). Lượt 29e3699 đỏ ở test_team_t4_perf (p95 vẽ 412 ms > 250 ms) chỉ vì máy đang chạy 3 file
    # khác; danh sách CHAY_RIENG không thể biết trước hết mọi test đo thời gian. Code hỏng thật thì chạy một mình vẫn đỏ.
    # Không chạy lại file quá giờ (lần treo 26/10 xảy ra lúc máy đã rảnh) và không chạy lại khi đỏ hơn 10 file (hỏng thật,
    # chạy lại chỉ kéo dài CI). Mọi file phải chạy lại đều được kể tên để làm cho nó chắc hơn hoặc thêm vào CHAY_RIENG.
    chay_lai, cuu = [], []
    if ts["jobs"] > 1:
        theo_ten = dict((n, c) for c, n in viec)
        chay_lai = [t for t, r in do_day_du if r.returncode != 124 and t not in CHAY_RIENG]
        if len(chay_lai) > 10:
            ra(f"\n{len(chay_lai)} file đỏ khi chạy chung: quá nhiều để là nhiễu do chạy song song, không chạy lại.")
            chay_lai = []
        for ten in chay_lai:
            r, g = chay_do_gio(theo_ten[ten])
            if r.returncode == 0:
                ra(f"  chạy lại một mình: ok   {ten}  (đỏ khi chạy chung với file khác)")
                cuu.append(ten)
            else:
                ra(f"  chạy lại một mình: ĐỎ   {ten}")
                do_day_du.append((ten, r))
        do = [t for t in do if t not in cuu]
        do_day_du = [(t, r) for t, r in do_day_du if t not in cuu]
        # Mỗi file chỉ in output một lần: giữ lần chạy một mình (được thêm sau cùng).
        do_day_du = list({t: (t, r) for t, r in do_day_du}.values())

    giay = time.perf_counter() - t0
    if ts["jobs"] > 1:
        xoa_cay(sao[0].parent)
    # Trên CI in TRỌN output của test đỏ, gom ở cuối (chạy song song thì in giữa chừng sẽ lẫn vào nhau),
    # mỗi file một nhóm gập được trên trang Actions.
    if tren_ci:
        for ten, r in do_day_du:
            ra(f"::group::Output của {ten} (mã thoát {r.returncode})")
            ra(r.stdout or "")
            ra(r.stderr or "")
            ra("::endgroup::")
    cham_nhat = sorted(da_do.items(), key=lambda x: -x[1])[:10]
    ra(f"\nChậm nhất: " + ", ".join(f"{t} {g:.0f}s" for t, g in cham_nhat))
    if cuu:
        ra("Đỏ khi chạy chung, xanh khi chạy một mình (nên làm chắc hơn hoặc thêm vào CHAY_RIENG): " + ", ".join(cuu))
    ra(f"{len(viec) - len(do)}/{len(viec)} xanh{nhan} trong {giay:.0f} giây")

    if ts["update"]:
        giay_cu = doc_thoi_gian()
        con = {f.name for f in PY_DIR.glob("test_*.py")} | {f.name for f in JS_DIR.glob("test_*.*js")}
        moi = {k: v for k, v in giay_cu.items() if k in con}
        moi.update({k: round(v, 1) for k, v in da_do.items()})
        TIMINGS.write_text(json.dumps({
            "_ghi_chu": "Thời gian chạy từng file test (giây), chỉ để chia nhóm CI cho đều. "
                        "Cập nhật: python tests/run.py --py --jobs 4 --update-timings",
            "giay": dict(sorted(moi.items())),
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        ra(f"Đã ghi {len(da_do)} số đo vào {TIMINGS.relative_to(ROOT)}")

    tom_tat = os.environ.get("GITHUB_STEP_SUMMARY")
    if tom_tat:
        with open(tom_tat, "a", encoding="utf-8") as fh:
            fh.write(f"### Test{nhan}: {len(viec) - len(do)}/{len(viec)} xanh trong {giay / 60:.1f} phút\n")
            for t in do:
                fh.write(f"- ĐỎ `{t}`\n")
            for t in cuu:
                fh.write(f"- Xanh khi chạy một mình, đỏ khi chạy chung: `{t}`\n")
    if do:
        ra("ĐỎ: " + ", ".join(do))
        ra("Chạy lại một cái để xem chi tiết:  python tests/run.py <tên> -v")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        for p in _SOT:
            xoa_cay(p)

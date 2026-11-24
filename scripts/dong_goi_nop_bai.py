"""Đóng gói bài nộp môn KTPMUD vào repo nộp bài chung của lớp (bản fork của fossbk-spec/ktpmud-project).

    python scripts/dong_goi_nop_bai.py <thư mục fork ktpmud-project> [--tuan 12]

Tạo hoặc cập nhật submissions/<case_study_slug>_<group_code>/ trong fork (slug và mã nhóm lấy từ nop_bai/submission.json):
  - README.md, submission.json, docs/, report/TestReport_*.md   chép từ nop_bai/
  - report/BaoCao_Tuan<tuan>.docx và .pdf                       chép bản mới nhất trong docx/, đổi tên không dấu, không họ tên
  - src/                                                        mã nguồn bản 2 (file git đang theo dõi hoặc chưa bị .gitignore)
File khác đã có sẵn trong thư mục nhóm (bài các tuần trước) được giữ nguyên. Chỉ src/ được làm mới hoàn toàn.
Xong thì chạy scripts/validate_submission.py của fork. Script không commit, không push.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
NOP_BAI = GOC / "nop_bai"
# Bản 2 là sản phẩm được nộp; prototype bản 1, dữ liệu KiotViet thật của cửa hàng, báo cáo và file cho agent thì không.
THU_MUC_SRC = ("backend/", "database/", "frontend/", "scripts/", ".github/")
FILE_SRC = {"docker-compose.yml", "README.md", "HUONG_DAN_V2.md", "HUONG_DAN_APP_DI_DONG.md",
            "HUONG_DAN_DEPLOY_CLOUDFLARE.md", "HUONG_DAN_DEPLOY_RENDER.md", ".gitignore"}
GIOI_HAN_MB = 10


def file_ma_nguon() -> list[str]:
    ra = subprocess.run(["git", "-C", str(GOC), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                        capture_output=True, check=True).stdout.decode("utf-8")
    ds = []
    for f in sorted(set(ra.split("\0"))):
        if not f or not (GOC / f).is_file() or Path(f).name in {".env", ".env.local"}:
            continue
        if f in FILE_SRC or f.startswith(THU_MUC_SRC):
            ds.append(f)
    return ds


def chep(nguon: Path, dich: Path) -> None:
    dich.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(nguon, dich)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fork", type=Path, help="thư mục gốc của bản fork ktpmud-project")
    p.add_argument("--tuan", type=int, default=12, help="số tuần ghi vào tên file báo cáo (mặc định 12)")
    a = p.parse_args()

    if not (a.fork / "submissions").is_dir():
        sys.exit(f"Không thấy thư mục submissions/ trong {a.fork}: cần trỏ tới bản fork ktpmud-project.")
    tt = json.loads((NOP_BAI / "submission.json").read_text(encoding="utf-8"))
    dich = a.fork / "submissions" / f"{tt['case_study_slug']}_{tt['group_code']}"

    # Phần mô tả bài nộp
    for f in sorted(NOP_BAI.rglob("*")):
        if f.is_file():
            chep(f, dich / f.relative_to(NOP_BAI))

    # Báo cáo: bản .docx mới nhất trong docx/ và .pdf cùng tên nếu có
    docx = sorted((GOC / "docx").glob("*.docx"), key=lambda f: f.stat().st_mtime)
    if docx:
        chep(docx[-1], dich / "report" / f"BaoCao_Tuan{a.tuan}.docx")
        pdf = docx[-1].with_suffix(".pdf")
        if pdf.is_file():
            chep(pdf, dich / "report" / f"BaoCao_Tuan{a.tuan}.pdf")
    else:
        print("Chú ý: docx/ không có báo cáo .docx nào.")

    # Mã nguồn
    src = dich / "src"
    if src.exists():
        shutil.rmtree(src)
    ds = file_ma_nguon()
    for f in ds:
        chep(GOC / f, src / f)
    (dich / "slides").mkdir(exist_ok=True)

    nang = [(f, f.stat().st_size / 2**20) for f in dich.rglob("*") if f.is_file()]
    for f, mb in nang:
        if mb > GIOI_HAN_MB:
            print(f"Chú ý: {f.relative_to(dich)} nặng {mb:.1f} MB, quá {GIOI_HAN_MB} MB: phải để link Drive trong README.")
    print(f"Đã đóng gói vào {dich}: {len(ds)} file mã nguồn, tổng {sum(mb for _, mb in nang):.1f} MB.")

    kiem_tra = a.fork / "scripts" / "validate_submission.py"
    if kiem_tra.is_file():
        return subprocess.run([sys.executable, str(kiem_tra), str(dich)]).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())

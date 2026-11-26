"""Chạy cả hệ thống trong một container (Render, `docker run`):
tạo bảng + migration (+ dữ liệu mẫu nếu CSDL trống) → Worker chạy nền → API ở cổng $PORT (mặc định 8000).

    python -m app.khoi_dong

Viết bằng Python thay cho chuỗi lệnh shell `a && (b &) && exec c`, vì ô Docker Command của Render không
chạy được cú pháp đó (`/bin/sh: Syntax error: "(" unexpected`). docker-compose không dùng file này:
ở đó API và Worker là hai container riêng.
"""
import os
import subprocess
import sys


def main() -> None:
    py = sys.executable
    ket_qua = subprocess.run([py, "-m", "app.bootstrap"])
    if ket_qua.returncode:
        sys.exit(ket_qua.returncode)
    subprocess.Popen([py, "-m", "app.worker"])  # tiến trình con, dừng cùng container
    cong = os.environ.get("PORT") or "8000"
    # exec: uvicorn thay chỗ tiến trình này, nhận thẳng tín hiệu dừng (SIGTERM) của Render/Docker
    os.execv(py, [py, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", cong])


if __name__ == "__main__":
    main()

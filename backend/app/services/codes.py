"""Sinh mã chứng từ theo ngày: KV + yymmdd + 3 chữ số (đơn), PN.. (phiếu nhập), BG.. (báo giá)."""
from datetime import date


def ma_tiep_theo(conn, tien_to: str, ngay: date | None = None, so_chu_so: int = 3) -> str:
    ngay = ngay or date.today()
    so = conn.execute(
        """INSERT INTO bo_dem_ma (tien_to, ngay, so) VALUES (%s, %s, 1)
           ON CONFLICT (tien_to, ngay) DO UPDATE SET so = bo_dem_ma.so + 1
           RETURNING so""",
        (tien_to, ngay),
    ).fetchone()["so"]
    return f"{tien_to}{ngay:%y%m%d}{so:0{so_chu_so}d}"


def dat_bo_dem(conn, tien_to: str, ngay: date, so: int) -> None:
    """Đẩy bộ đếm lên ít nhất `so` (dùng khi nạp dữ liệu mẫu có mã cố định)."""
    conn.execute(
        """INSERT INTO bo_dem_ma (tien_to, ngay, so) VALUES (%s, %s, %s)
           ON CONFLICT (tien_to, ngay) DO UPDATE SET so = GREATEST(bo_dem_ma.so, EXCLUDED.so)""",
        (tien_to, ngay, so),
    )

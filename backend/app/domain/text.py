import re
import unicodedata


def bo_dau(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    tach = unicodedata.normalize("NFD", text)
    return "".join(c for c in tach if not unicodedata.combining(c))


def chuan_hoa(text: str) -> str:
    """Chữ thường, bỏ dấu, gộp khoảng trắng — tương đương f_chuan_hoa() trong CSDL."""
    return re.sub(r"\s+", " ", bo_dau(text).lower()).strip()


def dinh_dang_tien(so_tien: int) -> str:
    return f"{so_tien:,}".replace(",", ".") + " đ"

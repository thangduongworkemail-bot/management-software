-- =====================================================================
-- 007: Thông báo đẩy (Web Push) tới app trên điện thoại và cảnh báo tồn dưới ngưỡng
-- =====================================================================

-- Mỗi trình duyệt/app đã bật thông báo là một đăng ký. Một tài khoản có thể có nhiều máy.
-- endpoint là địa chỉ của dịch vụ đẩy (FCM, Apple, Mozilla, WNS); p256dh/auth là khóa mã hóa của máy nhận.
CREATE TABLE dang_ky_day (
    id            BIGSERIAL PRIMARY KEY,
    tai_khoan_id  INT         NOT NULL REFERENCES tai_khoan (id),
    endpoint      TEXT        NOT NULL UNIQUE,
    p256dh        TEXT        NOT NULL,
    auth          TEXT        NOT NULL,
    thiet_bi      TEXT,                       -- mô tả máy (rút từ User-Agent) để Chủ nhận ra
    tao_luc       TIMESTAMPTZ NOT NULL DEFAULT now(),
    cap_nhat_luc  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX dang_ky_day_tai_khoan_idx ON dang_ky_day (tai_khoan_id);

-- Hộp thư đi có thêm kênh PUSH; du_lieu giữ đường dẫn mở khi chạm vào thông báo.
ALTER TABLE thong_bao DROP CONSTRAINT thong_bao_kenh_check;
ALTER TABLE thong_bao ADD CONSTRAINT thong_bao_kenh_check CHECK (kenh IN ('ZALO', 'SMS', 'EMAIL', 'PUSH'));
ALTER TABLE thong_bao ADD COLUMN du_lieu JSONB;

-- Cấu hình hệ thống do máy chủ tự sinh (khóa VAPID). Chỉ API và Worker đọc.
CREATE TABLE cau_hinh_he_thong (
    khoa     TEXT        PRIMARY KEY,
    gia_tri  TEXT        NOT NULL,
    tao_luc  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lần cuối đã báo "tồn dưới ngưỡng" cho mỗi mặt hàng, để không báo lặp quá một lần mỗi ngày.
-- Dòng bị xóa khi hàng đã nhập đủ lại, nên lần tụt sau được báo ngay.
CREATE TABLE canh_bao_ton (
    bien_the_id   INT         PRIMARY KEY REFERENCES bien_the (id),
    canh_bao_luc  TIMESTAMPTZ NOT NULL DEFAULT now()
);

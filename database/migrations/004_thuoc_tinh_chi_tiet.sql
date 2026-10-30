-- =====================================================================
-- 004: Thuộc tính hàng hóa chi tiết, thông tin xưởng đầy đủ
-- =====================================================================

-- Thông số chung cho mọi mặt hàng; thông số riêng theo nhóm hàng nằm trong thuoc_tinh (JSONB),
-- khóa là nhãn tiếng Việt lấy từ loai_hang.thuoc_tinh_mau.
ALTER TABLE bien_the
    ADD COLUMN hoan_thien      TEXT,                                    -- sơn PU, lau dầu, Melamine…
    ADD COLUMN kieu_dang       TEXT,                                    -- hiện đại, cổ điển, tân cổ điển…
    ADD COLUMN vat_lieu_phu    TEXT,                                    -- kính, đá, bản lề giảm chấn…
    ADD COLUMN xuat_xu         TEXT,
    ADD COLUMN khoi_luong_kg   INT CHECK (khoi_luong_kg >= 0),
    ADD COLUMN bao_hanh_thang  INT CHECK (bao_hanh_thang >= 0),
    ADD COLUMN don_vi_tinh     TEXT,                                    -- NULL = theo nhóm hàng
    ADD COLUMN mo_ta           TEXT,
    ADD COLUMN anh_url         TEXT,
    ADD COLUMN cap_nhat_luc    TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TRIGGER bien_the_cap_nhat_luc
    BEFORE UPDATE ON bien_the
    FOR EACH ROW EXECUTE FUNCTION trg_cap_nhat_luc();

ALTER TABLE nha_cung_cap
    ADD COLUMN dia_chi     TEXT,
    ADD COLUMN ma_so_thue  TEXT,
    ADD COLUMN ghi_chu     TEXT,
    ADD COLUMN tao_luc     TIMESTAMPTZ NOT NULL DEFAULT now();

-- Khóa thuộc tính cũ (snake_case) -> nhãn tiếng Việt hiển thị thẳng trên giao diện
WITH doi(cu, moi) AS (VALUES ('hoa_van', 'Hoa văn'), ('so_tang', 'Số tầng'), ('kieu_dang', 'Kiểu dáng'),
                             ('co_ngan_keo', 'Có ngăn kéo'), ('so_canh', 'Số cánh'),
                             ('so_cho_ngoi', 'Số chỗ ngồi'), ('be_mat', 'Bề mặt'))
UPDATE loai_hang l SET thuoc_tinh_mau = (
    SELECT COALESCE(jsonb_object_agg(COALESCE(d.moi, e.key), e.value), '{}'::jsonb)
    FROM jsonb_each(l.thuoc_tinh_mau) e LEFT JOIN doi d ON d.cu = e.key);

WITH doi(cu, moi) AS (VALUES ('hoa_van', 'Hoa văn'), ('so_tang', 'Số tầng'), ('kieu_dang', 'Kiểu dáng'),
                             ('co_ngan_keo', 'Có ngăn kéo'), ('so_canh', 'Số cánh'),
                             ('so_cho_ngoi', 'Số chỗ ngồi'), ('be_mat', 'Bề mặt'))
UPDATE mau_hang m SET thuoc_tinh = (
    SELECT COALESCE(jsonb_object_agg(COALESCE(d.moi, e.key), e.value), '{}'::jsonb)
    FROM jsonb_each(m.thuoc_tinh) e LEFT JOIN doi d ON d.cu = e.key);

-- Mỗi biến thể giữ bộ thuộc tính riêng (sửa một biến thể không ảnh hưởng biến thể khác cùng mẫu)
UPDATE bien_the bt SET thuoc_tinh = m.thuoc_tinh || bt.thuoc_tinh
FROM mau_hang m WHERE m.id = bt.mau_hang_id;

-- Tìm kiếm phủ cả thông số chi tiết (giá trị chữ trong thuoc_tinh)
CREATE OR REPLACE FUNCTION trg_bien_the_tim_kiem() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_mau text;
    v_loai text;
    v_thuoc_tinh text;
BEGIN
    SELECT m.ten, l.ten INTO v_mau, v_loai
    FROM mau_hang m JOIN loai_hang l ON l.id = m.loai_hang_id
    WHERE m.id = NEW.mau_hang_id;
    SELECT string_agg(e.value #>> '{}', ' ') INTO v_thuoc_tinh
    FROM jsonb_each(NEW.thuoc_tinh) e WHERE jsonb_typeof(e.value) = 'string';
    NEW.tim_kiem := f_chuan_hoa(concat_ws(' ',
        NEW.ma_noi_bo, NEW.ten_hien_thi, v_mau, v_loai, NEW.loai_go, NEW.mau_sac,
        NEW.hoan_thien, NEW.kieu_dang, NEW.vat_lieu_phu, v_thuoc_tinh,
        f_token_kich_thuoc(NEW.dai_mm), f_token_kich_thuoc(NEW.rong_mm), f_token_kich_thuoc(NEW.cao_mm)));
    RETURN NEW;
END $$;

UPDATE bien_the SET tim_kiem = tim_kiem;

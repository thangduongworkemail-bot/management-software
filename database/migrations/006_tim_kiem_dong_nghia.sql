-- =====================================================================
-- 006: Từ đồng nghĩa áp dụng cả hai phía khi tìm kiếm
-- =====================================================================
-- Trước đây chỉ câu tìm được đổi sang tên chuẩn ("tủ áo" -> "tủ quần áo"), nên mặt hàng đặt tên theo
-- cách gọi thường ("Tủ áo gỗ lát") lại không tìm ra. Nay cột tim_kiem được bổ sung tên chuẩn của mọi
-- từ đồng nghĩa có trong tên, nên tìm theo cách nào cũng khớp.

-- t có chứa cụm từ tu (đứng thành từ riêng, không phải một phần của từ khác)
CREATE OR REPLACE FUNCTION f_chua_tu(t text, tu text) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $$ SELECT t ~ ('\m' || regexp_replace(tu, '([^[:alnum:][:space:]])', '\\\1', 'g') || '\M') $$;

CREATE OR REPLACE FUNCTION f_mo_rong_dong_nghia(t text) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT concat_ws(' ', t, string_agg(d.tu_chuan_cn, ' '))
    FROM tu_dong_nghia d
    WHERE f_chua_tu(t, d.tu_khoa_cn)
$$;

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
    NEW.tim_kiem := f_mo_rong_dong_nghia(f_chuan_hoa(concat_ws(' ',
        NEW.ma_noi_bo, NEW.ten_hien_thi, v_mau, v_loai, NEW.loai_go, NEW.mau_sac,
        NEW.hoan_thien, NEW.kieu_dang, NEW.vat_lieu_phu, v_thuoc_tinh,
        f_token_kich_thuoc(NEW.dai_mm), f_token_kich_thuoc(NEW.rong_mm), f_token_kich_thuoc(NEW.cao_mm))));
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION trg_bo_san_pham_tim_kiem() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.tim_kiem := f_mo_rong_dong_nghia(f_chuan_hoa(concat_ws(' ', NEW.ma, NEW.ten, NEW.mo_ta, 'bo')));
    RETURN NEW;
END $$;

UPDATE bien_the SET tim_kiem = tim_kiem;
UPDATE bo_san_pham SET tim_kiem = tim_kiem;

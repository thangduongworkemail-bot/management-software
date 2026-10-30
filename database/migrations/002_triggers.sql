-- =====================================================================
-- 002 — Trigger bảo vệ toàn vẹn dữ liệu
-- Mã lỗi riêng: KV001 = ghi đè bảng chỉ-ghi-thêm, KV002 = sửa bản chụp/giá
-- =====================================================================

-- ---------------------------------------------------------------------
-- Chặn UPDATE / DELETE / TRUNCATE trên SO_CAI_TON và NHAT_KY
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_chi_ghi_them() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Bảng % chỉ cho phép ghi thêm (INSERT); thao tác % bị chặn', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'KV001';
END $$;

CREATE TRIGGER so_cai_ton_chan_sua_xoa
    BEFORE UPDATE OR DELETE ON so_cai_ton
    FOR EACH ROW EXECUTE FUNCTION trg_chi_ghi_them();
CREATE TRIGGER so_cai_ton_chan_truncate
    BEFORE TRUNCATE ON so_cai_ton
    FOR EACH STATEMENT EXECUTE FUNCTION trg_chi_ghi_them();

CREATE TRIGGER nhat_ky_chan_sua_xoa
    BEFORE UPDATE OR DELETE ON nhat_ky
    FOR EACH ROW EXECUTE FUNCTION trg_chi_ghi_them();
CREATE TRIGGER nhat_ky_chan_truncate
    BEFORE TRUNCATE ON nhat_ky
    FOR EACH STATEMENT EXECUTE FUNCTION trg_chi_ghi_them();

-- ---------------------------------------------------------------------
-- Chuỗi băm nhật ký: current_hash = SHA256(prev_hash | nội dung dòng)
-- Khóa advisory giữ đến hết giao dịch, id được cấp SAU khi có khóa,
-- nên thứ tự id trùng với thứ tự nối chuỗi kể cả khi ghi đồng thời.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION f_bam_nhat_ky(p_prev text, r nhat_ky) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT encode(sha256(convert_to(concat_ws('|',
        p_prev,
        r.id::text,
        to_char(r.thoi_diem AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
        COALESCE(r.nguoi_thuc_hien_id::text, ''),
        r.ten_nguoi_thuc_hien,
        r.hanh_dong,
        r.thuc_the,
        COALESCE(r.thuc_the_id, ''),
        COALESCE(r.du_lieu_truoc::text, ''),
        COALESCE(r.du_lieu_sau::text, ''),
        COALESCE(r.thiet_bi_id::text, '')
    ), 'UTF8')), 'hex')
$$;

CREATE OR REPLACE FUNCTION trg_nhat_ky_noi_chuoi() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_prev text;
BEGIN
    PERFORM pg_advisory_xact_lock(7302601);
    NEW.id := nextval(pg_get_serial_sequence('nhat_ky', 'id'));
    SELECT current_hash INTO v_prev FROM nhat_ky ORDER BY id DESC LIMIT 1;
    NEW.prev_hash := COALESCE(v_prev, repeat('0', 64));
    NEW.current_hash := f_bam_nhat_ky(NEW.prev_hash, NEW);
    RETURN NEW;
END $$;

CREATE TRIGGER nhat_ky_noi_chuoi
    BEFORE INSERT ON nhat_ky
    FOR EACH ROW EXECUTE FUNCTION trg_nhat_ky_noi_chuoi();

-- Kiểm tra lại toàn bộ chuỗi; trả về các dòng bị đứt/sai (rỗng = toàn vẹn)
CREATE OR REPLACE FUNCTION kiem_tra_chuoi_nhat_ky()
RETURNS TABLE (nhat_ky_id bigint, ly_do text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    r nhat_ky;
    v_prev text := repeat('0', 64);
BEGIN
    FOR r IN SELECT * FROM nhat_ky ORDER BY id LOOP
        IF r.prev_hash <> v_prev THEN
            nhat_ky_id := r.id; ly_do := 'prev_hash không khớp dòng trước'; RETURN NEXT;
        END IF;
        IF r.current_hash <> f_bam_nhat_ky(r.prev_hash, r) THEN
            nhat_ky_id := r.id; ly_do := 'current_hash không khớp nội dung'; RETURN NEXT;
        END IF;
        v_prev := r.current_hash;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- Bảng giá: chỉ được đóng mức đang mở (den_ngay NULL -> có giá trị)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_gia_chi_dong() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Không được xóa lịch sử giá' USING ERRCODE = 'KV002';
    END IF;
    IF OLD.den_ngay IS NOT NULL
       OR NEW.den_ngay IS NULL
       OR (NEW.id, NEW.bien_the_id, NEW.loai_gia, NEW.nhom_khach, NEW.so_tien, NEW.tu_ngay, NEW.nguoi_dat_id)
          IS DISTINCT FROM
          (OLD.id, OLD.bien_the_id, OLD.loai_gia, OLD.nhom_khach, OLD.so_tien, OLD.tu_ngay, OLD.nguoi_dat_id) THEN
        RAISE EXCEPTION 'Chỉ được đóng mức giá đang hiệu lực, không ghi đè số tiền' USING ERRCODE = 'KV002';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER gia_hieu_luc_chi_dong
    BEFORE UPDATE OR DELETE ON gia_hieu_luc
    FOR EACH ROW EXECUTE FUNCTION trg_gia_chi_dong();

-- ---------------------------------------------------------------------
-- Dòng đơn là bản chụp: chỉ cờ da_xuat được đổi (false -> true)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_dong_don_ban_chup() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Không được xóa dòng đơn' USING ERRCODE = 'KV002';
    END IF;
    IF (to_jsonb(NEW) - 'da_xuat') <> (to_jsonb(OLD) - 'da_xuat') OR (OLD.da_xuat AND NOT NEW.da_xuat) THEN
        RAISE EXCEPTION 'Dòng đơn là bản chụp giá, không được sửa' USING ERRCODE = 'KV002';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER dong_don_ban_chup
    BEFORE UPDATE OR DELETE ON dong_don
    FOR EACH ROW EXECUTE FUNCTION trg_dong_don_ban_chup();

-- ---------------------------------------------------------------------
-- Tự cập nhật cột tìm kiếm (không dấu + token kích thước "1800 1m8")
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION f_token_kich_thuoc(mm integer) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN mm IS NULL OR mm <= 0 THEN ''
        WHEN mm % 1000 = 0 THEN mm::text || ' ' || (mm / 1000)::text || 'm'
        WHEN mm % 100 = 0 THEN mm::text || ' ' || (mm / 1000)::text || 'm' || ((mm % 1000) / 100)::text
        ELSE mm::text
    END
$$;

CREATE OR REPLACE FUNCTION trg_bien_the_tim_kiem() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_mau text;
    v_loai text;
BEGIN
    SELECT m.ten, l.ten INTO v_mau, v_loai
    FROM mau_hang m JOIN loai_hang l ON l.id = m.loai_hang_id
    WHERE m.id = NEW.mau_hang_id;
    NEW.tim_kiem := f_chuan_hoa(concat_ws(' ',
        NEW.ma_noi_bo, NEW.ten_hien_thi, v_mau, v_loai, NEW.loai_go, NEW.mau_sac,
        f_token_kich_thuoc(NEW.dai_mm), f_token_kich_thuoc(NEW.rong_mm), f_token_kich_thuoc(NEW.cao_mm)));
    RETURN NEW;
END $$;

CREATE TRIGGER bien_the_tim_kiem
    BEFORE INSERT OR UPDATE ON bien_the
    FOR EACH ROW EXECUTE FUNCTION trg_bien_the_tim_kiem();

CREATE OR REPLACE FUNCTION trg_bo_san_pham_tim_kiem() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.tim_kiem := f_chuan_hoa(concat_ws(' ', NEW.ma, NEW.ten, NEW.mo_ta, 'bo'));
    RETURN NEW;
END $$;

CREATE TRIGGER bo_san_pham_tim_kiem
    BEFORE INSERT OR UPDATE ON bo_san_pham
    FOR EACH ROW EXECUTE FUNCTION trg_bo_san_pham_tim_kiem();

CREATE OR REPLACE FUNCTION trg_cap_nhat_luc() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.cap_nhat_luc := now();
    RETURN NEW;
END $$;

CREATE TRIGGER don_hang_cap_nhat_luc
    BEFORE UPDATE ON don_hang
    FOR EACH ROW EXECUTE FUNCTION trg_cap_nhat_luc();

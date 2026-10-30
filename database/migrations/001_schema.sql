-- =====================================================================
-- 001 — Lược đồ CSDL Hệ thống quản lý & bán hàng Nội thất Khanh Vân
-- Quy ước: tiền (VNĐ) dùng BIGINT, kích thước dùng INTEGER (mm),
-- hệ số dùng INTEGER phần nghìn (1200 = 1,2) để mọi phép tính là số nguyên.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- unaccent() chỉ là STABLE nên không dùng được trong index/cột sinh;
-- bọc lại với từ điển cố định để khai báo IMMUTABLE.
CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$;

CREATE OR REPLACE FUNCTION f_chuan_hoa(text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $$ SELECT regexp_replace(lower(f_unaccent($1)), '\s+', ' ', 'g') $$;

-- ---------------------------------------------------------------------
-- Tài khoản & thiết bị
-- ---------------------------------------------------------------------
CREATE TABLE tai_khoan (
    id             SERIAL PRIMARY KEY,
    ten_dang_nhap  TEXT        NOT NULL UNIQUE,
    ho_ten         TEXT        NOT NULL,
    vai_tro        TEXT        NOT NULL CHECK (vai_tro IN ('CHU', 'THO', 'QUAN_TRI')),
    mat_khau_hash  TEXT        NOT NULL,
    kich_hoat      BOOLEAN     NOT NULL DEFAULT TRUE,
    tao_luc        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE thiet_bi (
    id               SERIAL PRIMARY KEY,
    ten              TEXT        NOT NULL,
    loai             TEXT        NOT NULL CHECK (loai IN ('MAY_QUAY', 'DIEN_THOAI', 'MAY_NHAN_TIEN')),
    trang_thai       TEXT        NOT NULL DEFAULT 'CHO_GHEP'
                                 CHECK (trang_thai IN ('CHO_GHEP', 'HOAT_DONG', 'THU_HOI')),
    ma_ghep_hash     TEXT,
    ma_ghep_het_han  TIMESTAMPTZ,
    khoa_ky          TEXT,                     -- khóa HMAC cấp một lần khi ghép nối
    lan_bao_song     TIMESTAMPTZ,
    chu_so_huu_id    INT REFERENCES tai_khoan (id),
    tao_luc          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (trang_thai <> 'HOAT_DONG' OR khoa_ky IS NOT NULL)
);

-- ---------------------------------------------------------------------
-- Danh mục hàng hóa
-- ---------------------------------------------------------------------
CREATE TABLE loai_hang (
    id              SERIAL PRIMARY KEY,
    ma              TEXT  NOT NULL UNIQUE,
    ten             TEXT  NOT NULL,
    thuoc_tinh_mau  JSONB NOT NULL DEFAULT '{}'::jsonb,
    don_vi_tinh     TEXT  NOT NULL DEFAULT 'cái'
);

CREATE TABLE mau_hang (
    id            SERIAL PRIMARY KEY,
    loai_hang_id  INT         NOT NULL REFERENCES loai_hang (id),
    ten           TEXT        NOT NULL,
    anh_url       TEXT,
    mo_ta         TEXT,
    thuoc_tinh    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    tao_luc       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE he_so_go (
    loai_go           TEXT PRIMARY KEY,
    he_so_phan_nghin  INT  NOT NULL CHECK (he_so_phan_nghin > 0)
);

CREATE TABLE bien_the (
    id                   SERIAL PRIMARY KEY,
    mau_hang_id          INT         NOT NULL REFERENCES mau_hang (id),
    ma_noi_bo            TEXT        NOT NULL UNIQUE CHECK (ma_noi_bo ~ '^[A-Z0-9][A-Za-z0-9-]*$'),
    ten_hien_thi         TEXT        NOT NULL,
    loai_go              TEXT        REFERENCES he_so_go (loai_go),
    dai_mm               INT         CHECK (dai_mm >= 0),
    rong_mm              INT         CHECK (rong_mm >= 0),
    cao_mm               INT         CHECK (cao_mm >= 0),
    mau_sac              TEXT,
    dat_theo_kich_thuoc  BOOLEAN     NOT NULL DEFAULT FALSE,
    thuoc_tinh           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    ton_toi_thieu        INT         NOT NULL DEFAULT 0 CHECK (ton_toi_thieu >= 0),
    dang_ban             BOOLEAN     NOT NULL DEFAULT TRUE,
    tim_kiem             TEXT        NOT NULL DEFAULT '',   -- trigger 002 tự điền
    tao_luc              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX bien_the_mau_hang_idx ON bien_the (mau_hang_id);

-- Công thức tính giá cho biến thể đặt theo kích thước riêng (FR-02)
CREATE TABLE cong_thuc_gia (
    id                      SERIAL PRIMARY KEY,
    bien_the_id             INT    NOT NULL UNIQUE REFERENCES bien_the (id),
    kieu                    TEXT   NOT NULL CHECK (kieu IN ('THEO_CHIEU_DAI', 'THEO_DIEN_TICH', 'THEO_BAC')),
    don_gia                 BIGINT CHECK (don_gia >= 0),          -- đ/m hoặc đ/m²
    phu_phi                 BIGINT NOT NULL DEFAULT 0 CHECK (phu_phi >= 0),
    bac_gia                 JSONB  NOT NULL DEFAULT '[]'::jsonb,  -- [{"toi_da_mm":1600,"gia":7800000}, ...]
    kich_thuoc_min_mm       INT    NOT NULL DEFAULT 400 CHECK (kich_thuoc_min_mm >= 0),
    kich_thuoc_max_mm       INT    NOT NULL DEFAULT 3000 CHECK (kich_thuoc_max_mm >= kich_thuoc_min_mm),
    ty_le_gia_von_phan_nghin INT   NOT NULL DEFAULT 650 CHECK (ty_le_gia_von_phan_nghin BETWEEN 0 AND 1000),
    ty_le_gia_san_phan_nghin INT   NOT NULL DEFAULT 800 CHECK (ty_le_gia_san_phan_nghin BETWEEN 0 AND 1000),
    CHECK (kieu = 'THEO_BAC' OR don_gia IS NOT NULL),
    CHECK (kieu <> 'THEO_BAC' OR jsonb_array_length(bac_gia) > 0)
);

-- Bảng giá nhiều tầng: đổi giá = đóng mức cũ (den_ngay) + mở mức mới, không ghi đè
CREATE TABLE gia_hieu_luc (
    id            BIGSERIAL PRIMARY KEY,
    bien_the_id   INT         NOT NULL REFERENCES bien_the (id),
    loai_gia      TEXT        NOT NULL CHECK (loai_gia IN ('GIA_VON', 'GIA_NIEM_YET', 'GIA_SAN', 'GIA_NHOM_KHACH')),
    nhom_khach    TEXT,
    so_tien       BIGINT      NOT NULL CHECK (so_tien >= 0),
    tu_ngay       TIMESTAMPTZ NOT NULL DEFAULT now(),
    den_ngay      TIMESTAMPTZ,
    nguoi_dat_id  INT REFERENCES tai_khoan (id),
    ghi_chu       TEXT,
    CHECK (den_ngay IS NULL OR den_ngay >= tu_ngay),
    CHECK ((loai_gia = 'GIA_NHOM_KHACH') = (nhom_khach IS NOT NULL))
);
CREATE UNIQUE INDEX gia_hieu_luc_mot_muc_dang_mo
    ON gia_hieu_luc (bien_the_id, loai_gia, COALESCE(nhom_khach, ''))
    WHERE den_ngay IS NULL;

CREATE TABLE bo_san_pham (
    id            SERIAL PRIMARY KEY,
    ma            TEXT    NOT NULL UNIQUE CHECK (ma ~ '^[A-Z0-9][A-Za-z0-9-]*$'),
    ten           TEXT    NOT NULL,
    mo_ta         TEXT,
    gia_niem_yet  BIGINT  NOT NULL CHECK (gia_niem_yet >= 0),
    gia_san       BIGINT  NOT NULL CHECK (gia_san >= 0),
    dang_ban      BOOLEAN NOT NULL DEFAULT TRUE,
    tim_kiem      TEXT    NOT NULL DEFAULT '',
    CHECK (gia_san <= gia_niem_yet)
);

CREATE TABLE thanh_phan_bo (
    bo_san_pham_id  INT NOT NULL REFERENCES bo_san_pham (id),
    bien_the_id     INT NOT NULL REFERENCES bien_the (id),
    so_luong        INT NOT NULL CHECK (so_luong > 0),
    PRIMARY KEY (bo_san_pham_id, bien_the_id)
);

CREATE TABLE tu_dong_nghia (
    id            SERIAL PRIMARY KEY,
    tu_khoa       TEXT NOT NULL,
    tu_chuan      TEXT NOT NULL,
    tu_khoa_cn    TEXT GENERATED ALWAYS AS (f_chuan_hoa(tu_khoa)) STORED,
    tu_chuan_cn   TEXT GENERATED ALWAYS AS (f_chuan_hoa(tu_chuan)) STORED,
    UNIQUE (tu_khoa_cn)
);

-- ---------------------------------------------------------------------
-- Xưởng cung cấp & nhập kho
-- ---------------------------------------------------------------------
CREATE TABLE nha_cung_cap (
    id                   SERIAL PRIMARY KEY,
    ma                   TEXT   NOT NULL UNIQUE,
    ten                  TEXT   NOT NULL,
    lien_he              TEXT,
    so_dien_thoai        TEXT,
    loai_hang            TEXT,
    so_du_cong_no        BIGINT NOT NULL DEFAULT 0 CHECK (so_du_cong_no >= 0),
    han_thanh_toan_ngay  INT    NOT NULL DEFAULT 30 CHECK (han_thanh_toan_ngay >= 0)
);

CREATE TABLE ma_xuong (
    id               SERIAL PRIMARY KEY,
    bien_the_id      INT    NOT NULL REFERENCES bien_the (id),
    nha_cung_cap_id  INT    NOT NULL REFERENCES nha_cung_cap (id),
    ma_hang_xuong    TEXT   NOT NULL,
    gia_nhap         BIGINT NOT NULL CHECK (gia_nhap >= 0),
    so_ngay_giao     INT    NOT NULL DEFAULT 7 CHECK (so_ngay_giao >= 0),
    uu_tien          INT    NOT NULL DEFAULT 1 CHECK (uu_tien >= 1),
    UNIQUE (bien_the_id, nha_cung_cap_id)
);

CREATE TABLE phieu_nhap (
    id                SERIAL PRIMARY KEY,
    ma                TEXT        NOT NULL UNIQUE,
    nha_cung_cap_id   INT         NOT NULL REFERENCES nha_cung_cap (id),
    ngay_nhap         TIMESTAMPTZ NOT NULL DEFAULT now(),
    nguoi_lap_id      INT         NOT NULL REFERENCES tai_khoan (id),
    tong_tien         BIGINT      NOT NULL CHECK (tong_tien >= 0),
    anh_chung_tu_url  TEXT,
    ghi_chu           TEXT
);

CREATE TABLE lo_nhap (
    id               SERIAL PRIMARY KEY,
    phieu_nhap_id    INT    NOT NULL REFERENCES phieu_nhap (id),
    bien_the_id      INT    NOT NULL REFERENCES bien_the (id),
    so_luong         INT    NOT NULL CHECK (so_luong > 0),
    gia_von_don_vi   BIGINT NOT NULL CHECK (gia_von_don_vi >= 0)
);

CREATE TABLE chi_tra_xuong (
    id               SERIAL PRIMARY KEY,
    nha_cung_cap_id  INT         NOT NULL REFERENCES nha_cung_cap (id),
    so_tien          BIGINT      NOT NULL CHECK (so_tien > 0),
    nguoi_chi_id     INT         NOT NULL REFERENCES tai_khoan (id),
    ghi_chu          TEXT,
    thoi_diem        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Khách hàng, báo giá, đơn hàng
-- ---------------------------------------------------------------------
CREATE TABLE khach_hang (
    id             SERIAL PRIMARY KEY,
    ten            TEXT        NOT NULL,
    so_dien_thoai  TEXT,
    ma_so_thue     TEXT CHECK (ma_so_thue ~ '^[0-9]{10}(-?[0-9]{3})?$'),
    email          TEXT,
    dia_chi        TEXT,
    nhom_khach     TEXT,
    du_no          BIGINT      NOT NULL DEFAULT 0 CHECK (du_no >= 0),
    tao_luc        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bộ đếm sinh mã chứng từ theo ngày (KV261026001, PN26102601, ...)
CREATE TABLE bo_dem_ma (
    tien_to  TEXT NOT NULL,
    ngay     DATE NOT NULL,
    so       INT  NOT NULL CHECK (so > 0),
    PRIMARY KEY (tien_to, ngay)
);

CREATE TABLE bao_gia (
    id            SERIAL PRIMARY KEY,
    ma            TEXT        NOT NULL UNIQUE,
    khach_hang_id INT REFERENCES khach_hang (id),
    nguoi_lap_id  INT         NOT NULL REFERENCES tai_khoan (id),
    tong_tien     BIGINT      NOT NULL CHECK (tong_tien >= 0),
    ma_chia_se    TEXT        NOT NULL UNIQUE,
    tao_luc       TIMESTAMPTZ NOT NULL DEFAULT now(),
    het_han_luc   TIMESTAMPTZ NOT NULL,
    ghi_chu       TEXT,
    CHECK (het_han_luc > tao_luc)
);

CREATE TABLE dong_bao_gia (
    id              SERIAL PRIMARY KEY,
    bao_gia_id      INT    NOT NULL REFERENCES bao_gia (id),
    bien_the_id     INT REFERENCES bien_the (id),
    bo_san_pham_id  INT REFERENCES bo_san_pham (id),
    mo_ta           TEXT   NOT NULL,
    so_luong        INT    NOT NULL CHECK (so_luong > 0),
    don_gia_chup    BIGINT NOT NULL CHECK (don_gia_chup >= 0),
    kieu_cong_thuc  TEXT CHECK (kieu_cong_thuc IN ('THEO_CHIEU_DAI', 'THEO_DIEN_TICH', 'THEO_BAC')),
    tham_so         JSONB  NOT NULL DEFAULT '{}'::jsonb,
    thanh_tien      BIGINT NOT NULL CHECK (thanh_tien >= 0),
    CHECK (num_nonnulls(bien_the_id, bo_san_pham_id) = 1),
    CHECK (thanh_tien = don_gia_chup * so_luong)
);

CREATE TABLE don_hang (
    id               BIGSERIAL PRIMARY KEY,
    ma               TEXT        NOT NULL UNIQUE,
    khach_hang_id    INT REFERENCES khach_hang (id),
    bao_gia_id       INT REFERENCES bao_gia (id),
    nguoi_lap_id     INT         NOT NULL REFERENCES tai_khoan (id),
    kenh             TEXT        NOT NULL DEFAULT 'QUAY' CHECK (kenh IN ('QUAY', 'MOBILE', 'NGOAI_TUYEN')),
    trang_thai       TEXT        NOT NULL CHECK (trang_thai IN (
                         'CHO_DUYET_GIA', 'CHO_THANH_TOAN', 'CON_NO', 'DA_THANH_TOAN', 'HET_HAN', 'DA_HUY')),
    trang_thai_giao  TEXT        NOT NULL DEFAULT 'CHUA_GIAO' CHECK (trang_thai_giao IN (
                         'CHUA_GIAO', 'DA_GIAO', 'CHO_XUONG_GIAO', 'XUNG_DOT_TON')),
    tong_tien        BIGINT      NOT NULL CHECK (tong_tien >= 0),
    da_thu           BIGINT      NOT NULL DEFAULT 0 CHECK (da_thu >= 0),
    giam_tru         BIGINT      NOT NULL DEFAULT 0 CHECK (giam_tru >= 0),
    giu_cho_den      TIMESTAMPTZ,
    can_hoa_don      BOOLEAN     NOT NULL DEFAULT FALSE,
    idempotency_key  UUID UNIQUE,
    ghi_chu          TEXT,
    tao_luc          TIMESTAMPTZ NOT NULL DEFAULT now(),
    cap_nhat_luc     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (giam_tru <= tong_tien)
);
CREATE INDEX don_hang_trang_thai_idx ON don_hang (trang_thai, giu_cho_den);
CREATE INDEX don_hang_khach_idx ON don_hang (khach_hang_id);

-- Mỗi dòng đơn là bản chụp giá tại thời điểm chốt (không đổi theo bảng giá sau này)
CREATE TABLE dong_don (
    id                 BIGSERIAL PRIMARY KEY,
    don_hang_id        BIGINT  NOT NULL REFERENCES don_hang (id),
    bien_the_id        INT REFERENCES bien_the (id),
    bo_san_pham_id     INT REFERENCES bo_san_pham (id),
    mo_ta              TEXT    NOT NULL,
    so_luong           INT     NOT NULL CHECK (so_luong > 0),
    don_gia_ban        BIGINT  NOT NULL CHECK (don_gia_ban >= 0),
    gia_niem_yet_chup  BIGINT  NOT NULL CHECK (gia_niem_yet_chup >= 0),
    gia_san_chup       BIGINT  NOT NULL CHECK (gia_san_chup >= 0),
    gia_von_chup       BIGINT  NOT NULL CHECK (gia_von_chup >= 0),
    kieu_cong_thuc     TEXT CHECK (kieu_cong_thuc IN ('THEO_CHIEU_DAI', 'THEO_DIEN_TICH', 'THEO_BAC')),
    tham_so            JSONB   NOT NULL DEFAULT '{}'::jsonb,
    thanh_tien         BIGINT  NOT NULL CHECK (thanh_tien >= 0),
    dat_rieng          BOOLEAN NOT NULL DEFAULT FALSE,
    da_xuat            BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (num_nonnulls(bien_the_id, bo_san_pham_id) = 1),
    CHECK (thanh_tien = don_gia_ban * so_luong)
);
CREATE INDEX dong_don_don_idx ON dong_don (don_hang_id);

CREATE TABLE yeu_cau_duyet (
    id               SERIAL PRIMARY KEY,
    don_hang_id      BIGINT      NOT NULL REFERENCES don_hang (id),
    loai             TEXT        NOT NULL CHECK (loai IN ('BAN_DUOI_GIA_SAN')),
    noi_dung         JSONB       NOT NULL,
    trang_thai       TEXT        NOT NULL DEFAULT 'CHO_DUYET' CHECK (trang_thai IN ('CHO_DUYET', 'DA_DUYET', 'TU_CHOI')),
    nguoi_yeu_cau_id INT         NOT NULL REFERENCES tai_khoan (id),
    nguoi_duyet_id   INT REFERENCES tai_khoan (id),
    ly_do            TEXT,
    tao_luc          TIMESTAMPTZ NOT NULL DEFAULT now(),
    duyet_luc        TIMESTAMPTZ
);

-- ---------------------------------------------------------------------
-- Sổ cái tồn kho bất biến (chỉ INSERT — xem trigger ở 002)
-- Quy ước dấu: NHAP, TRA_HANG, GIU_CHO > 0; XUAT, NHA_CHO < 0; DIEU_CHINH ±
--   Tồn hiện có  = Σ(NHAP, TRA_HANG, DIEU_CHINH, XUAT)
--   Đang giữ chỗ = Σ(GIU_CHO, NHA_CHO)
--   Tồn khả dụng = Tồn hiện có − Đang giữ chỗ
-- ---------------------------------------------------------------------
CREATE TABLE so_cai_ton (
    id                  BIGSERIAL PRIMARY KEY,
    bien_the_id         INT         NOT NULL REFERENCES bien_the (id),
    loai                TEXT        NOT NULL CHECK (loai IN ('NHAP', 'GIU_CHO', 'NHA_CHO', 'XUAT', 'TRA_HANG', 'DIEU_CHINH')),
    so_luong            INT         NOT NULL CHECK (so_luong <> 0),
    don_hang_id         BIGINT REFERENCES don_hang (id),
    phieu_nhap_id       INT REFERENCES phieu_nhap (id),
    tham_chieu          TEXT,
    ly_do               TEXT,
    het_han_luc         TIMESTAMPTZ,
    nguoi_thuc_hien_id  INT REFERENCES tai_khoan (id),
    thoi_diem           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (CASE loai
               WHEN 'NHAP'     THEN so_luong > 0
               WHEN 'TRA_HANG' THEN so_luong > 0
               WHEN 'GIU_CHO'  THEN so_luong > 0
               WHEN 'XUAT'     THEN so_luong < 0
               WHEN 'NHA_CHO'  THEN so_luong < 0
               ELSE TRUE
           END),
    CHECK (loai <> 'DIEU_CHINH' OR ly_do IS NOT NULL),
    CHECK (loai NOT IN ('GIU_CHO', 'NHA_CHO') OR don_hang_id IS NOT NULL)
);
CREATE INDEX so_cai_ton_bien_the_idx ON so_cai_ton (bien_the_id, loai);
CREATE INDEX so_cai_ton_don_idx ON so_cai_ton (don_hang_id) WHERE don_hang_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- Thanh toán & đối soát
-- ---------------------------------------------------------------------
CREATE TABLE giao_dich_nh (
    id            BIGSERIAL PRIMARY KEY,
    nguon         TEXT        NOT NULL CHECK (nguon IN ('PAYOS', 'NAPAS', 'MAY_NHAN_TIEN')),
    ma_giao_dich  TEXT        NOT NULL,
    so_tien       BIGINT      NOT NULL CHECK (so_tien > 0),
    noi_dung      TEXT        NOT NULL DEFAULT '',
    ngan_hang     TEXT,
    thoi_diem_nh  TIMESTAMPTZ,
    ma_bam        CHAR(64)    NOT NULL UNIQUE,   -- chống ghi trùng khi webhook gửi lại
    thiet_bi_id   INT REFERENCES thiet_bi (id),
    don_hang_id   BIGINT REFERENCES don_hang (id),
    trang_thai    TEXT        NOT NULL DEFAULT 'CHUA_KHOP'
                              CHECK (trang_thai IN ('CHUA_KHOP', 'DA_KHOP', 'LECH_TIEN', 'DOI_SOAT')),
    ghi_chu       TEXT,
    du_lieu_goc   JSONB,
    nhan_luc      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE thanh_toan (
    id                 BIGSERIAL PRIMARY KEY,
    don_hang_id        BIGINT      NOT NULL REFERENCES don_hang (id),
    loai               TEXT        NOT NULL CHECK (loai IN ('COC', 'THANH_TOAN', 'THU_NO')),
    phuong_thuc        TEXT        NOT NULL CHECK (phuong_thuc IN ('TIEN_MAT', 'CHUYEN_KHOAN')),
    so_tien            BIGINT      NOT NULL CHECK (so_tien > 0),
    xac_nhan_tay       BOOLEAN     NOT NULL DEFAULT FALSE,
    giao_dich_nh_id    BIGINT UNIQUE REFERENCES giao_dich_nh (id),
    da_doi_soat        BOOLEAN     NOT NULL DEFAULT FALSE,
    nguoi_ghi_nhan_id  INT REFERENCES tai_khoan (id),
    thoi_diem          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (NOT xac_nhan_tay OR phuong_thuc = 'CHUYEN_KHOAN')
);
CREATE INDEX thanh_toan_don_idx ON thanh_toan (don_hang_id);

CREATE TABLE bang_chung_tien (
    id            BIGSERIAL PRIMARY KEY,
    thanh_toan_id BIGINT      NOT NULL REFERENCES thanh_toan (id),
    kieu          TEXT        NOT NULL CHECK (kieu IN ('BON_SO_CUOI', 'ANH_BIEN_LAI')),
    gia_tri       TEXT        NOT NULL,
    nguoi_tao_id  INT REFERENCES tai_khoan (id),
    tao_luc       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (kieu <> 'BON_SO_CUOI' OR gia_tri ~ '^[0-9]{4}$')
);

-- ---------------------------------------------------------------------
-- Phiếu in nội bộ & hóa đơn điện tử (hàng đợi Retry Queue)
-- ---------------------------------------------------------------------
CREATE TABLE phieu_ban_hang (
    id           SERIAL PRIMARY KEY,
    don_hang_id  BIGINT      NOT NULL UNIQUE REFERENCES don_hang (id),
    so_phieu     TEXT        NOT NULL UNIQUE,
    noi_dung     JSONB       NOT NULL,
    so_lan_in    INT         NOT NULL DEFAULT 0 CHECK (so_lan_in >= 0),
    tao_luc      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE hoa_don_dt (
    id                 SERIAL PRIMARY KEY,
    don_hang_id        BIGINT      NOT NULL UNIQUE REFERENCES don_hang (id),
    trang_thai         TEXT        NOT NULL CHECK (trang_thai IN ('CHUA_CAN', 'CHO_XUAT', 'DA_XUAT', 'LOI')),
    nha_cung_cap_hddt  TEXT        NOT NULL DEFAULT 'MOCK',
    ten_nguoi_mua      TEXT,
    ma_so_thue         TEXT,
    dia_chi            TEXT,
    email              TEXT,
    ky_hieu            TEXT,
    so_hoa_don         TEXT,
    link_pdf           TEXT,
    link_xml           TEXT,
    so_lan_thu         INT         NOT NULL DEFAULT 0 CHECK (so_lan_thu >= 0),
    lan_thu_tiep       TIMESTAMPTZ NOT NULL DEFAULT now(),
    loi_cuoi           TEXT,
    tao_luc            TIMESTAMPTZ NOT NULL DEFAULT now(),
    xuat_luc           TIMESTAMPTZ,
    CHECK (trang_thai <> 'DA_XUAT' OR so_hoa_don IS NOT NULL)
);
CREATE INDEX hoa_don_dt_hang_doi_idx ON hoa_don_dt (lan_thu_tiep) WHERE trang_thai = 'CHO_XUAT';

-- Hộp thư đi cho thông báo (Zalo OA / SMS / Email), Worker gửi bất đồng bộ
CREATE TABLE thong_bao (
    id             BIGSERIAL PRIMARY KEY,
    kenh           TEXT        NOT NULL CHECK (kenh IN ('ZALO', 'SMS', 'EMAIL')),
    nguoi_nhan     TEXT        NOT NULL,
    tieu_de        TEXT        NOT NULL,
    noi_dung       TEXT        NOT NULL,
    trang_thai     TEXT        NOT NULL DEFAULT 'CHO_GUI' CHECK (trang_thai IN ('CHO_GUI', 'DA_GUI', 'LOI')),
    so_lan_thu     INT         NOT NULL DEFAULT 0,
    lan_thu_tiep   TIMESTAMPTZ NOT NULL DEFAULT now(),
    loi_cuoi       TEXT,
    tao_luc        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Nhật ký thao tác (Audit Log) — chuỗi băm SHA-256, chỉ INSERT
-- ---------------------------------------------------------------------
CREATE TABLE nhat_ky (
    id                   BIGSERIAL PRIMARY KEY,
    thoi_diem            TIMESTAMPTZ NOT NULL DEFAULT now(),
    nguoi_thuc_hien_id   INT REFERENCES tai_khoan (id),
    ten_nguoi_thuc_hien  TEXT        NOT NULL,
    hanh_dong            TEXT        NOT NULL,
    thuc_the             TEXT        NOT NULL,
    thuc_the_id          TEXT,
    du_lieu_truoc        JSONB,
    du_lieu_sau          JSONB,
    thiet_bi_id          INT REFERENCES thiet_bi (id),
    prev_hash            CHAR(64)    NOT NULL,
    current_hash         CHAR(64)    NOT NULL UNIQUE
);
CREATE INDEX nhat_ky_thuc_the_idx ON nhat_ky (thuc_the, thuc_the_id);

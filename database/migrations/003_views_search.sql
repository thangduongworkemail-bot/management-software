-- =====================================================================
-- 003 — Chỉ mục tìm kiếm tiếng Việt & các view tính tồn kho / giá
-- =====================================================================

-- Trigram GIN hỗ trợ LIKE '%...%' và similarity() trên cột không dấu
CREATE INDEX bien_the_tim_kiem_trgm ON bien_the USING gin (tim_kiem gin_trgm_ops);
CREATE INDEX bo_san_pham_tim_kiem_trgm ON bo_san_pham USING gin (tim_kiem gin_trgm_ops);

-- Giá đang hiệu lực của từng biến thể
CREATE VIEW v_gia_hien_hanh AS
SELECT bien_the_id,
       max(so_tien) FILTER (WHERE loai_gia = 'GIA_VON')      AS gia_von,
       max(so_tien) FILTER (WHERE loai_gia = 'GIA_SAN')      AS gia_san,
       max(so_tien) FILTER (WHERE loai_gia = 'GIA_NIEM_YET') AS gia_niem_yet
FROM gia_hieu_luc
WHERE den_ngay IS NULL
GROUP BY bien_the_id;

-- Tồn kho tính hoàn toàn từ sổ cái
CREATE VIEW v_ton_kho AS
SELECT bt.id AS bien_the_id,
       COALESCE(sum(s.so_luong) FILTER (WHERE s.loai IN ('NHAP', 'TRA_HANG', 'DIEU_CHINH', 'XUAT')), 0)::int AS ton_hien_co,
       COALESCE(sum(s.so_luong) FILTER (WHERE s.loai IN ('GIU_CHO', 'NHA_CHO')), 0)::int                  AS dang_giu_cho,
       (COALESCE(sum(s.so_luong) FILTER (WHERE s.loai IN ('NHAP', 'TRA_HANG', 'DIEU_CHINH', 'XUAT')), 0)
        - COALESCE(sum(s.so_luong) FILTER (WHERE s.loai IN ('GIU_CHO', 'NHA_CHO')), 0))::int              AS ton_kha_dung
FROM bien_the bt
LEFT JOIN so_cai_ton s ON s.bien_the_id = bt.id
GROUP BY bt.id;

-- Tồn của bộ sản phẩm = thành phần thiếu nhiều nhất quyết định
CREATE VIEW v_ton_bo AS
SELECT tp.bo_san_pham_id,
       GREATEST(0, min(floor(t.ton_hien_co::numeric / tp.so_luong)))::int  AS ton_hien_co,
       GREATEST(0, min(floor(t.ton_kha_dung::numeric / tp.so_luong)))::int AS ton_kha_dung
FROM thanh_phan_bo tp
JOIN v_ton_kho t ON t.bien_the_id = tp.bien_the_id
GROUP BY tp.bo_san_pham_id;

-- Giá vốn của bộ = tổng giá vốn thành phần
CREATE VIEW v_gia_von_bo AS
SELECT tp.bo_san_pham_id,
       COALESCE(sum(g.gia_von * tp.so_luong), 0)::bigint AS gia_von
FROM thanh_phan_bo tp
LEFT JOIN v_gia_hien_hanh g ON g.bien_the_id = tp.bien_the_id
GROUP BY tp.bo_san_pham_id;

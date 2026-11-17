/**
 * Thu nhỏ ảnh chụp từ điện thoại (thường 3–10MB) trước khi tải lên: cạnh dài tối đa `canhMax` px, nén JPEG.
 * Trình duyệt không đọc được ảnh, hoặc bản nén không nhỏ hơn, thì trả lại file gốc.
 */
export async function thuNhoAnh(file, canhMax = 1600, chatLuong = 0.85) {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type) || typeof createImageBitmap !== 'function') return file
  let anh
  try {
    anh = await createImageBitmap(file, { imageOrientation: 'from-image' })
    const tiLe = Math.min(1, canhMax / Math.max(anh.width, anh.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(anh.width * tiLe)
    canvas.height = Math.round(anh.height * tiLe)
    const ctx = canvas.getContext('2d')
    ctx.fillStyle = '#FFFFFF'   // PNG nền trong suốt -> nền trắng thay vì đen khi chuyển JPEG
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(anh, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((xong) => canvas.toBlob(xong, 'image/jpeg', chatLuong))
    if (!blob || blob.size >= file.size) return file
    return new File([blob], `${file.name.replace(/\.[^.]+$/, '')}.jpg`, { type: 'image/jpeg' })
  } catch {
    return file
  } finally {
    anh?.close()
  }
}

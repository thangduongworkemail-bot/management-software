import { describe, expect, it } from 'vitest'
import { chuanHoaMayChu, noiUrl, urlWebSocket } from './may-chu'

describe('chuanHoaMayChu — địa chỉ máy chủ người dùng gõ trong app', () => {
  it.each([
    ['https://khanhvan.trycloudflare.com/', 'https://khanhvan.trycloudflare.com'],
    ['khanhvan.onrender.com', 'https://khanhvan.onrender.com'],
    ['  https://khanhvan.vn/api/  ', 'https://khanhvan.vn'],
    ['192.168.1.10:8000', 'http://192.168.1.10:8000'],
    ['10.0.0.5:8000/dang-nhap', 'http://10.0.0.5:8000'],
    ['172.20.1.2', 'http://172.20.1.2'],
    ['localhost:8000', 'http://localhost:8000'],
    ['may-quay:8000', 'http://may-quay:8000'],
    ['may-quay.local:8000', 'http://may-quay.local:8000'],
    ['http://khanhvan.vn', 'http://khanhvan.vn'],
    ['', ''],
  ])('%s -> %s', (vao, ra) => expect(chuanHoaMayChu(vao)).toBe(ra))

  it('từ chối địa chỉ hỏng hoặc giao thức lạ', () => {
    expect(() => chuanHoaMayChu('ftp://khanhvan.vn')).toThrow()
    expect(() => chuanHoaMayChu('https://')).toThrow()
  })
})

describe('noiUrl', () => {
  it('chỉ ghép vào đường dẫn tuyệt đối trên máy chủ', () => {
    expect(noiUrl('https://kv.vn', '/api/hang-hoa')).toBe('https://kv.vn/api/hang-hoa')
    expect(noiUrl('', '/files/a.jpg')).toBe('/files/a.jpg')
    expect(noiUrl('https://kv.vn', 'https://s3.amazonaws.com/a.jpg')).toBe('https://s3.amazonaws.com/a.jpg')
    expect(noiUrl('https://kv.vn', '//cdn.vn/a.jpg')).toBe('//cdn.vn/a.jpg')
    expect(noiUrl('https://kv.vn', 'data:image/png;base64,AA')).toBe('data:image/png;base64,AA')
    expect(noiUrl('https://kv.vn', null)).toBe(null)
  })
})

describe('urlWebSocket', () => {
  it('https -> wss, http -> ws, mã hóa token', () => {
    expect(urlWebSocket('https://kv.vn', 'a.b+c')).toBe('wss://kv.vn/ws?token=a.b%2Bc')
    expect(urlWebSocket('http://192.168.1.10:8000', 'x')).toBe('ws://192.168.1.10:8000/ws?token=x')
  })
})

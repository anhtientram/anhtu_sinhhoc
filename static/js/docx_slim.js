// Nén tối ưu hình ảnh bên trong file Word (.docx) ngay trên trình duyệt trước khi upload:
// - Chỉ giữ các thành phần importer cần (word/document.xml, word/styles.xml, word/_rels/document.xml.rels, word/media/*)
// - Thu nhỏ & chuyển ảnh PNG/BMP/JPEG nặng (>90KB) sang JPEG chất lượng 0.82 (nền trắng cho PNG trong suốt)
// - Không phụ thuộc thư viện ngoài; chịu lỗi CRC-32 cũ; nếu có bất kỳ ngoại lệ nào tự fallback về file gốc.

const _CRC_TABLE = (() => {
  const tbl = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    tbl[i] = c >>> 0;
  }
  return tbl;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) {
    c = _CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

async function inflateRaw(compressedBytes) {
  const ds = new DecompressionStream("deflate-raw");
  const writer = ds.writable.getWriter();
  writer.write(compressedBytes).catch(() => {});
  writer.close().catch(() => {});
  const resp = new Response(ds.readable);
  const buf = await resp.arrayBuffer();
  return new Uint8Array(buf);
}

function findEocdOffset(view, len) {
  const minOff = Math.max(0, len - 65557);
  for (let i = len - 22; i >= minOff; i--) {
    if (
      view.getUint8(i) === 0x50 &&
      view.getUint8(i + 1) === 0x4b &&
      view.getUint8(i + 2) === 0x05 &&
      view.getUint8(i + 3) === 0x06
    ) {
      return i;
    }
  }
  return -1;
}

function parseZipDirectory(buf) {
  const view = new DataView(buf);
  const len = buf.byteLength;
  const eocdOff = findEocdOffset(view, len);
  if (eocdOff < 0) return null;

  const entryCount = view.getUint16(eocdOff + 10, true);
  const cdSize = view.getUint32(eocdOff + 12, true);
  const cdOffset = view.getUint32(eocdOff + 16, true);
  if (entryCount === 0xffff || cdSize === 0xffffffff || cdOffset === 0xffffffff) {
    return null; // ZIP64 fallback to original
  }
  if (cdOffset + cdSize > len) return null;

  const decoder = new TextDecoder("utf-8");
  const entries = [];
  let ptr = cdOffset;
  for (let i = 0; i < entryCount && ptr + 46 <= len; i++) {
    if (view.getUint32(ptr, true) !== 0x02014b50) break;
    const method = view.getUint16(ptr + 10, true);
    const compSize = view.getUint32(ptr + 20, true);
    const nameLen = view.getUint16(ptr + 28, true);
    const extraLen = view.getUint16(ptr + 30, true);
    const commentLen = view.getUint16(ptr + 32, true);
    const localHeaderOffset = view.getUint32(ptr + 42, true);
    if (compSize === 0xffffffff || localHeaderOffset === 0xffffffff) return null;

    const nameBytes = new Uint8Array(buf, ptr + 46, nameLen);
    const name = decoder.decode(nameBytes);
    entries.push({ name, method, compSize, localHeaderOffset });
    ptr += 46 + nameLen + extraLen + commentLen;
  }
  return { view, buf, entries };
}

function getCompressedSlice(view, buf, entry) {
  const off = entry.localHeaderOffset;
  if (off + 30 > buf.byteLength || view.getUint32(off, true) !== 0x04034b50) {
    return null;
  }
  const fnameLen = view.getUint16(off + 26, true);
  const extraLen = view.getUint16(off + 28, true);
  const dataStart = off + 30 + fnameLen + extraLen;
  if (dataStart + entry.compSize > buf.byteLength) return null;
  return new Uint8Array(buf, dataStart, entry.compSize);
}

async function compressImageBytes(bytes) {
  let bitmap = null;
  try {
    bitmap = await createImageBitmap(new Blob([bytes]));
    const maxW = 1280;
    const maxH = 1600;
    let w = bitmap.width;
    let h = bitmap.height;
    if (w <= 0 || h <= 0) return bytes;

    const scale = Math.min(1, maxW / w, maxH / h);
    const tw = Math.max(1, Math.round(w * scale));
    const th = Math.max(1, Math.round(h * scale));

    const canvas = document.createElement("canvas");
    canvas.width = tw;
    canvas.height = th;
    const ctx = canvas.getContext("2d");
    if (!ctx) return bytes;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, tw, th);
    ctx.drawImage(bitmap, 0, 0, tw, th);

    const outBlob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.82));
    if (!outBlob || outBlob.size >= bytes.length) return bytes;
    return new Uint8Array(await outBlob.arrayBuffer());
  } catch {
    return bytes;
  } finally {
    try {
      bitmap?.close?.();
    } catch {}
  }
}

function buildStoredZip(items) {
  const encoder = new TextEncoder();
  const localParts = [];
  const cdParts = [];
  let offset = 0;

  for (const item of items) {
    const nameBytes = encoder.encode(item.name);
    const data = item.data;
    const crc = crc32(data);
    const size = data.length;

    const lh = new ArrayBuffer(30 + nameBytes.length);
    const lv = new DataView(lh);
    lv.setUint32(0, 0x04034b50, true);
    lv.setUint16(4, 20, true);
    lv.setUint16(6, 0x0800, true); // UTF-8
    lv.setUint16(8, 0, true); // Store
    lv.setUint16(10, 0, true);
    lv.setUint16(12, 0, true);
    lv.setUint32(14, crc, true);
    lv.setUint32(18, size, true);
    lv.setUint32(22, size, true);
    lv.setUint16(26, nameBytes.length, true);
    lv.setUint16(28, 0, true);
    new Uint8Array(lh, 30).set(nameBytes);

    localParts.push(new Uint8Array(lh), data);

    const ch = new ArrayBuffer(46 + nameBytes.length);
    const cv = new DataView(ch);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 20, true);
    cv.setUint16(8, 0x0800, true); // UTF-8
    cv.setUint16(10, 0, true); // Store
    cv.setUint16(12, 0, true);
    cv.setUint16(14, 0, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, size, true);
    cv.setUint32(24, size, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint16(30, 0, true);
    cv.setUint16(32, 0, true);
    cv.setUint16(34, 0, true);
    cv.setUint16(36, 0, true);
    cv.setUint32(38, 0, true);
    cv.setUint32(42, offset, true);
    new Uint8Array(ch, 46).set(nameBytes);

    cdParts.push(new Uint8Array(ch));
    offset += 30 + nameBytes.length + size;
  }

  let cdSize = 0;
  for (const p of cdParts) cdSize += p.length;

  const eocd = new ArrayBuffer(22);
  const ev = new DataView(eocd);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(4, 0, true);
  ev.setUint16(6, 0, true);
  ev.setUint16(8, items.length, true);
  ev.setUint16(10, items.length, true);
  ev.setUint32(12, cdSize, true);
  ev.setUint32(16, offset, true);
  ev.setUint16(20, 0, true);

  return new Blob([...localParts, ...cdParts, new Uint8Array(eocd)], {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
}

export async function slimDocxFile(file, onStage = null) {
  if (
    !file ||
    !String(file.name || "").toLowerCase().endsWith(".docx") ||
    file.size < 2 * 1024 * 1024 ||
    typeof DecompressionStream === "undefined" ||
    typeof createImageBitmap === "undefined"
  ) {
    return { file, savedBytes: 0, slimmed: false };
  }

  try {
    onStage?.("Đang tối ưu hình ảnh trong file Word trên máy bạn...");
    const buf = await file.arrayBuffer();
    const parsed = parseZipDirectory(buf);
    if (!parsed) return { file, savedBytes: 0, slimmed: false };

    const needed = new Set(["word/document.xml", "word/styles.xml", "word/_rels/document.xml.rels"]);
    const selected = parsed.entries.filter((e) => needed.has(e.name) || e.name.startsWith("word/media/"));
    if (!selected.some((e) => e.name === "word/document.xml")) {
      return { file, savedBytes: 0, slimmed: false };
    }

    const decodedItems = [];
    for (const entry of selected) {
      const slice = getCompressedSlice(parsed.view, parsed.buf, entry);
      if (!slice) return { file, savedBytes: 0, slimmed: false };
      let data;
      if (entry.method === 0) {
        data = slice;
      } else if (entry.method === 8) {
        data = await inflateRaw(slice);
      } else {
        return { file, savedBytes: 0, slimmed: false };
      }
      decodedItems.push({ name: entry.name, data });
    }

    const imgTargets = [];
    for (let i = 0; i < decodedItems.length; i++) {
      const it = decodedItems[i];
      if (
        it.name.startsWith("word/media/") &&
        it.data.length > 90 * 1024 &&
        /\.(png|jpe?g|webp|bmp)$/i.test(it.name)
      ) {
        imgTargets.push(i);
      }
    }

    if (imgTargets.length) {
      let done = 0;
      const batchSize = 6;
      for (let i = 0; i < imgTargets.length; i += batchSize) {
        const batch = imgTargets.slice(i, i + batchSize);
        await Promise.all(
          batch.map(async (idx) => {
            decodedItems[idx].data = await compressImageBytes(decodedItems[idx].data);
            done += 1;
            onStage?.(`Đang nén tối ưu ảnh (${done}/${imgTargets.length})...`);
          })
        );
      }
    }

    const slimBlob = buildStoredZip(decodedItems);
    if (slimBlob.size >= file.size * 0.92) {
      return { file, savedBytes: 0, slimmed: false };
    }
    const slimFile = new File([slimBlob], file.name, { type: file.type || slimBlob.type });
    return { file: slimFile, savedBytes: file.size - slimFile.size, slimmed: true };
  } catch {
    return { file, savedBytes: 0, slimmed: false };
  }
}

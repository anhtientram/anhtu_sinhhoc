// Tối ưu & cắt chuẩn hình ảnh bên trong file Word (.docx) ngay trên trình duyệt trước khi upload:
// - Tự động cắt đúng khung <a:srcRect l t r b> và xoay <a:xfrm rot> bằng HTML5 Canvas
//   (loại bỏ hoàn toàn chữ chụp màn hình thừa ngoài khung ảnh, hoạt động 100% trên mọi hệ điều hành & Wasmer Edge)
// - Chuyển đổi ảnh định dạng khó tương thích (BMP/TIFF/PNG lớn) sang JPEG/PNG chuẩn web đa trình duyệt & điện thoại
// - Chỉ giữ các thành phần importer cần (word/document.xml, word/styles.xml, word/_rels/document.xml.rels, word/media/*)
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

async function cropAndConvertImageBytes(bytes, crop = null, forceConvert = false) {
  let bitmap = null;
  try {
    bitmap = await createImageBitmap(new Blob([bytes]));
    const bw = bitmap.width;
    const bh = bitmap.height;
    if (bw <= 0 || bh <= 0) return null;

    let l = Math.max(0, Number(crop?.l || 0));
    let t = Math.max(0, Number(crop?.t || 0));
    let r = Math.max(0, Number(crop?.r || 0));
    let b = Math.max(0, Number(crop?.b || 0));
    const rot = ((Number(crop?.rot || 0) % 360) + 360) % 360;
    if (l + r >= 98000 || t + b >= 98000) {
      l = t = r = b = 0;
    }

    const sx = Math.max(0, Math.min(bw - 1, Math.round((bw * l) / 100000)));
    const sy = Math.max(0, Math.min(bh - 1, Math.round((bh * t) / 100000)));
    const sw = Math.max(1, Math.min(bw - sx, Math.round((bw * (100000 - l - r)) / 100000)));
    const sh = Math.max(1, Math.min(bh - sy, Math.round((bh * (100000 - t - b)) / 100000)));

    const maxW = 1280;
    const maxH = 1600;
    const swapDims = rot === 90 || rot === 270;
    const rawOutW = swapDims ? sh : sw;
    const rawOutH = swapDims ? sw : sh;
    const scale = Math.min(1, maxW / rawOutW, maxH / rawOutH);
    const outW = Math.max(1, Math.round(rawOutW * scale));
    const outH = Math.max(1, Math.round(rawOutH * scale));
    const drawW = Math.max(1, Math.round(sw * scale));
    const drawH = Math.max(1, Math.round(sh * scale));

    const canvas = document.createElement("canvas");
    canvas.width = outW;
    canvas.height = outH;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, outW, outH);

    ctx.save();
    ctx.translate(outW / 2, outH / 2);
    if (rot) ctx.rotate((rot * Math.PI) / 180);
    ctx.drawImage(bitmap, sx, sy, sw, sh, -drawW / 2, -drawH / 2, drawW, drawH);
    ctx.restore();

    const outBlob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.86));
    if (!outBlob) return null;
    if (!forceConvert && !crop && outBlob.size >= bytes.length) return bytes;
    return new Uint8Array(await outBlob.arrayBuffer());
  } catch {
    return null;
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

function normalizeMediaTarget(target) {
  let t = String(target || "").replace(/^\/+/, "");
  if (!t.startsWith("word/")) t = `word/${t}`;
  const parts = [];
  for (const seg of t.split("/")) {
    if (!seg || seg === ".") continue;
    if (seg === "..") parts.pop();
    else parts.push(seg);
  }
  return parts.join("/");
}

async function applyWordSrcRectCrops(decodedItems, onStage) {
  const docIdx = decodedItems.findIndex((it) => it.name === "word/document.xml");
  const relIdx = decodedItems.findIndex((it) => it.name === "word/_rels/document.xml.rels");
  if (docIdx < 0 || relIdx < 0 || typeof DOMParser === "undefined" || typeof XMLSerializer === "undefined") {
    return 0;
  }

  const decoder = new TextDecoder("utf-8");
  const encoder = new TextEncoder();
  const parser = new DOMParser();
  const docXml = parser.parseFromString(decoder.decode(decodedItems[docIdx].data), "application/xml");
  const relXml = parser.parseFromString(decoder.decode(decodedItems[relIdx].data), "application/xml");
  if (docXml.querySelector("parsererror") || relXml.querySelector("parsererror")) {
    return 0;
  }

  const relsRoot = relXml.documentElement;
  const relNs = relsRoot.namespaceURI || "http://schemas.openxmlformats.org/package/2006/relationships";
  const ridToMedia = new Map();
  const usedRids = new Set();
  for (const el of Array.from(relsRoot.children)) {
    if (el.localName !== "Relationship") continue;
    const id = el.getAttribute("Id") || "";
    const target = el.getAttribute("Target") || "";
    if (id) usedRids.add(id);
    if (id && target) {
      ridToMedia.set(id, normalizeMediaTarget(target));
    }
  }

  const mediaByName = new Map();
  for (const it of decodedItems) {
    if (it.name.startsWith("word/media/")) {
      mediaByName.set(it.name, it);
    }
  }

  // Tìm tất cả <a:blipFill> ngoài <mc:Fallback> có <a:srcRect> hoặc góc xoay <a:xfrm rot>
  const allElems = docXml.getElementsByTagName("*");
  const cropTasks = [];
  for (let i = 0; i < allElems.length; i++) {
    const el = allElems[i];
    if (el.localName !== "blipFill") continue;

    let anc = el.parentNode;
    let inFallback = false;
    let rotDeg = 0;
    while (anc && anc.nodeType === 1) {
      if (anc.localName === "Fallback") {
        inFallback = true;
        break;
      }
      if (anc.localName === "pic" && rotDeg === 0) {
        const subEls = anc.getElementsByTagName("*");
        for (let k = 0; k < subEls.length; k++) {
          if (subEls[k].localName === "xfrm" && subEls[k].getAttribute("rot")) {
            const rawRot = parseInt(subEls[k].getAttribute("rot"), 10);
            if (!Number.isNaN(rawRot)) {
              rotDeg = ((Math.round(rawRot / 60000) % 360) + 360) % 360;
            }
            break;
          }
        }
      }
      anc = anc.parentNode;
    }
    if (inFallback) continue;

    let blipEl = null;
    let srcRectEl = null;
    for (const ch of Array.from(el.children)) {
      if (ch.localName === "blip") blipEl = ch;
      else if (ch.localName === "srcRect") srcRectEl = ch;
    }
    if (!blipEl) continue;

    let embedAttrName = "";
    let embedAttrNs = null;
    let rid = "";
    for (const attr of Array.from(blipEl.attributes)) {
      if (attr.localName === "embed") {
        embedAttrName = attr.name;
        embedAttrNs = attr.namespaceURI;
        rid = attr.value || "";
        break;
      }
    }
    if (!rid || !ridToMedia.has(rid)) continue;

    const l = Math.max(0, parseInt(srcRectEl?.getAttribute("l") || "0", 10) || 0);
    const t = Math.max(0, parseInt(srcRectEl?.getAttribute("t") || "0", 10) || 0);
    const r = Math.max(0, parseInt(srcRectEl?.getAttribute("r") || "0", 10) || 0);
    const b = Math.max(0, parseInt(srcRectEl?.getAttribute("b") || "0", 10) || 0);

    if (l === 0 && t === 0 && r === 0 && b === 0 && rotDeg === 0) continue;
    const mediaPath = ridToMedia.get(rid);
    const mediaItem = mediaByName.get(mediaPath);
    if (!mediaItem || !mediaItem.data?.length) continue;

    cropTasks.push({ blipEl, srcRectEl, embedAttrName, embedAttrNs, rid, mediaPath, mediaItem, l, t, r, b, rot: rotDeg });
  }

  if (!cropTasks.length) return 0;

  const cropCache = new Map(); // key -> newRid
  let cropSeq = 1;
  let croppedCount = 0;

  for (let i = 0; i < cropTasks.length; i++) {
    const task = cropTasks[i];
    const cacheKey = `${task.mediaPath}|${task.l}|${task.t}|${task.r}|${task.b}|${task.rot}`;
    let newRid = cropCache.get(cacheKey);
    if (!newRid) {
      const croppedBytes = await cropAndConvertImageBytes(
        task.mediaItem.data,
        { l: task.l, t: task.t, r: task.r, b: task.b, rot: task.rot },
        true
      );
      if (!croppedBytes || croppedBytes.length < 100) continue;

      while (usedRids.has(`rIdCrop${cropSeq}`)) cropSeq += 1;
      newRid = `rIdCrop${cropSeq}`;
      usedRids.add(newRid);
      const newMediaRel = `media/crop_${cropSeq}.jpg`;
      const newMediaFull = `word/${newMediaRel}`;
      cropSeq += 1;

      decodedItems.push({ name: newMediaFull, data: croppedBytes });
      const relEl = relXml.createElementNS(relNs, "Relationship");
      relEl.setAttribute("Id", newRid);
      relEl.setAttribute(
        "Type",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
      );
      relEl.setAttribute("Target", newMediaRel);
      relsRoot.appendChild(relEl);
      cropCache.set(cacheKey, newRid);
      croppedCount += 1;
      onStage?.(`Đang cắt chuẩn khung hình ảnh Word (${croppedCount}/${cropTasks.length})...`);
    }

    if (task.embedAttrNs) {
      task.blipEl.setAttributeNS(task.embedAttrNs, task.embedAttrName, newRid);
    } else {
      task.blipEl.setAttribute(task.embedAttrName, newRid);
    }
    if (task.srcRectEl) {
      task.srcRectEl.removeAttribute("l");
      task.srcRectEl.removeAttribute("t");
      task.srcRectEl.removeAttribute("r");
      task.srcRectEl.removeAttribute("b");
    }
  }

  if (croppedCount > 0) {
    const serializer = new XMLSerializer();
    decodedItems[docIdx].data = encoder.encode(serializer.serializeToString(docXml));
    decodedItems[relIdx].data = encoder.encode(serializer.serializeToString(relXml));
  }
  return croppedCount;
}

export async function slimDocxFile(file, onStage = null) {
  if (
    !file ||
    !String(file.name || "").toLowerCase().endsWith(".docx") ||
    typeof DecompressionStream === "undefined" ||
    typeof createImageBitmap === "undefined"
  ) {
    return { file, savedBytes: 0, slimmed: false };
  }

  try {
    onStage?.("Đang kiểm tra & cắt chuẩn khung hình ảnh trong file Word...");
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

    // 1. Cắt chuẩn mọi ảnh có <a:srcRect> / xoay trong Word bằng Canvas để tuyệt đối không dính chữ thừa
    const croppedCount = await applyWordSrcRectCrops(decodedItems, onStage);

    // 2. Chuyển đổi định dạng ảnh khó tương thích (BMP/TIFF) & nén ảnh lớn > 90KB để đa trình duyệt/điện thoại hiển thị mượt
    const imgTargets = [];
    for (let i = 0; i < decodedItems.length; i++) {
      const it = decodedItems[i];
      if (!it.name.startsWith("word/media/")) continue;
      const isNonWeb = /\.(bmp|tiff?)$/i.test(it.name);
      const isHeavyWeb = it.data.length > 90 * 1024 && /\.(png|jpe?g|webp)$/i.test(it.name);
      if (isNonWeb || isHeavyWeb) {
        imgTargets.push({ idx: i, force: isNonWeb });
      }
    }

    let convertedCount = 0;
    if (imgTargets.length) {
      const batchSize = 6;
      for (let i = 0; i < imgTargets.length; i += batchSize) {
        const batch = imgTargets.slice(i, i + batchSize);
        await Promise.all(
          batch.map(async ({ idx, force }) => {
            const out = await cropAndConvertImageBytes(decodedItems[idx].data, null, force);
            if (out && out.length >= 100 && (force || out.length < decodedItems[idx].data.length)) {
              decodedItems[idx].data = out;
              convertedCount += 1;
            }
          })
        );
        onStage?.(`Đang chuẩn hoá hình ảnh (${Math.min(i + batchSize, imgTargets.length)}/${imgTargets.length})...`);
      }
    }

    // Nếu không cắt, không chuyển định dạng và file gốc nhỏ < 2MB -> giữ nguyên file gốc
    if (croppedCount === 0 && convertedCount === 0 && file.size < 2 * 1024 * 1024) {
      return { file, savedBytes: 0, slimmed: false };
    }

    const slimBlob = buildStoredZip(decodedItems);
    if (croppedCount === 0 && convertedCount === 0 && slimBlob.size >= file.size * 0.92) {
      return { file, savedBytes: 0, slimmed: false };
    }
    const slimFile = new File([slimBlob], file.name, { type: file.type || slimBlob.type });
    return { file: slimFile, savedBytes: Math.max(0, file.size - slimBlob.size), slimmed: true, croppedCount };
  } catch {
    return { file, savedBytes: 0, slimmed: false };
  }
}

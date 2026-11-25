import Foundation
import AppKit
import CoreGraphics

// Batch image cropper + rotator for Word <a:srcRect l t r b> + <a:xfrm rot>
// JSON jobs: [{"src": "...", "dst": "...", "l": 0, "t": 0, "r": 0, "b": 0, "rot": 0}, ...]
// rot is clockwise degrees (0, 90, 180, 270)
let args = CommandLine.arguments
if args.count < 2 {
    fputs("Usage: crop_img_bin <jobs.json>\n", stderr)
    exit(1)
}

guard let data = try? Data(contentsOf: URL(fileURLWithPath: args[1])),
      let jobs = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
    fputs("Invalid jobs JSON\n", stderr)
    exit(1)
}

func rotateCGImage(_ img: CGImage, clockwiseDegrees deg: Int) -> CGImage? {
    let norm = ((deg % 360) + 360) % 360
    if norm == 0 { return img }
    let w = img.width
    let h = img.height
    let swap = (norm == 90 || norm == 270)
    let outW = swap ? h : w
    let outH = swap ? w : h
    guard let cs = CGColorSpace(name: CGColorSpace.sRGB),
          let ctx = CGContext(data: nil, width: outW, height: outH, bitsPerComponent: 8, bytesPerRow: 0, space: cs, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
        return img
    }
    ctx.setFillColor(NSColor.white.cgColor)
    ctx.fill(CGRect(x: 0, y: 0, width: outW, height: outH))
    ctx.translateBy(x: CGFloat(outW) / 2.0, y: CGFloat(outH) / 2.0)
    // CoreGraphics rotates counter-clockwise for positive radians; clockwise = negative radians
    ctx.rotate(by: -CGFloat(norm) * .pi / 180.0)
    ctx.draw(img, in: CGRect(x: -CGFloat(w) / 2.0, y: -CGFloat(h) / 2.0, width: CGFloat(w), height: CGFloat(h)))
    return ctx.makeImage()
}

var okCount = 0
for job in jobs {
    guard let src = job["src"] as? String,
          let dst = job["dst"] as? String else { continue }
    let l = max(0.0, min(0.95, (job["l"] as? Double ?? 0.0) / 100000.0))
    let t = max(0.0, min(0.95, (job["t"] as? Double ?? 0.0) / 100000.0))
    let r = max(0.0, min(0.95, (job["r"] as? Double ?? 0.0) / 100000.0))
    let b = max(0.0, min(0.95, (job["b"] as? Double ?? 0.0) / 100000.0))
    let rot = job["rot"] as? Int ?? 0

    guard let imgData = try? Data(contentsOf: URL(fileURLWithPath: src)),
          let rep = NSBitmapImageRep(data: imgData),
          var cgImg = rep.cgImage else {
        try? FileManager.default.copyItem(atPath: src, toPath: dst)
        continue
    }

    if l > 0 || t > 0 || r > 0 || b > 0 {
        let w = Double(cgImg.width)
        let h = Double(cgImg.height)
        let x = Int(round(l * w))
        let y = Int(round(t * h))
        let cw = max(1, Int(round((1.0 - l - r) * w)))
        let ch = max(1, Int(round((1.0 - t - b) * h)))
        let rect = CGRect(x: x, y: y, width: min(cw, cgImg.width - x), height: min(ch, cgImg.height - y))
        if let cropped = cgImg.cropping(to: rect) {
            cgImg = cropped
        }
    }

    if rot != 0, let rotated = rotateCGImage(cgImg, clockwiseDegrees: rot) {
        cgImg = rotated
    }

    let outRep = NSBitmapImageRep(cgImage: cgImg)
    let isPng = dst.lowercased().hasSuffix(".png")
    let outData = isPng
        ? outRep.representation(using: .png, properties: [:])
        : outRep.representation(using: .jpeg, properties: [.compressionFactor: 0.90])
    if let d = outData {
        try? d.write(to: URL(fileURLWithPath: dst))
        okCount += 1
    }
}
print("CROPPED_ROTATED_OK \(okCount)/\(jobs.count)")

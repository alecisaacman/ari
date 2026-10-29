// codex-sheet: build a Codex pet sprite sheet from one cut-out photo per animation.
//
//   swift tools/ari-pet/codex-sheet.swift POSES_DIR OUT.png
//
// POSES_DIR holds transparent PNGs named for Codex's animations (idle, running-right,
// running-left, waving, jumping, failed, waiting, running, review), cut out with
// cutout.swift. The sheet is Codex's format: 8 columns x 9 rows of 192 x 208 cells,
// one animation per row. A photo can't move its own limbs, so each frame of a row is
// the pose with a little motion on top: breathing, a trotting bob, a jump arc, a tilt.
import AppKit
import CoreGraphics

let columns = 8, cellWidth = 192, cellHeight = 208
let rows: [(state: String, frames: Int)] = [
    ("idle", 6), ("running-right", 8), ("running-left", 8), ("waving", 4), ("jumping", 5),
    ("failed", 8), ("waiting", 6), ("running", 6), ("review", 6),
]
// The pet fits in this box, standing on the bottom of its cell, with room to move.
let fitWidth: CGFloat = 176, fitHeight: CGFloat = 184, floor: CGFloat = 6

struct Motion {
    var dx: CGFloat = 0, dy: CGFloat = 0, degrees: CGFloat = 0, sx: CGFloat = 1, sy: CGFloat = 1
}

func motion(_ state: String, _ index: Int, _ count: Int) -> Motion {
    let p = CGFloat(index) / CGFloat(count) * 2 * .pi
    let breathe = Motion(sx: 1 - 0.008 * sin(p), sy: 1 + 0.018 * sin(p))
    switch state {
    case "running-right", "running-left":
        let lean: CGFloat = state == "running-right" ? -1 : 1
        return Motion(dx: 2 * sin(p), dy: 5 * abs(sin(p)), degrees: lean * 2 * sin(p))
    case "waving":
        return Motion(dy: 1.5 * abs(sin(p)), degrees: 3 * sin(p))
    case "jumping":
        let arc: [CGFloat] = [0, 10, 16, 10, 0]
        return Motion(dy: arc[index % arc.count], sx: index == 0 ? 1.02 : 1, sy: index == 0 ? 0.97 : 1)
    case "failed":
        return Motion(dy: -1, sx: 1 - 0.006 * sin(p), sy: 1 + 0.012 * sin(p))
    case "waiting":
        var m = breathe
        m.degrees = 1.5 * sin(p)
        return m
    case "running":
        return Motion(dx: 3 * sin(2 * p), sx: 1 - 0.01 * sin(2 * p), sy: 1 + 0.02 * sin(2 * p))
    case "review":
        var m = breathe
        m.degrees = 2.5 * sin(p)
        return m
    default:
        return breathe
    }
}

let arguments = CommandLine.arguments
guard arguments.count == 3 else {
    print("usage: codex-sheet POSES_DIR OUT.png")
    exit(2)
}
let posesDir = URL(fileURLWithPath: arguments[1])
let width = columns * cellWidth, height = rows.count * cellHeight
guard let context = CGContext(
    data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
    space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
) else { exit(1) }
context.interpolationQuality = .high
context.clear(CGRect(x: 0, y: 0, width: width, height: height))

for (row, spec) in rows.enumerated() {
    let url = posesDir.appendingPathComponent("\(spec.state).png")
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        print("missing pose: \(spec.state)")
        exit(1)
    }
    let scale = min(fitWidth / CGFloat(image.width), fitHeight / CGFloat(image.height))
    let w = CGFloat(image.width) * scale, h = CGFloat(image.height) * scale
    for frame in 0..<spec.frames {
        let m = motion(spec.state, frame, spec.frames)
        // Core Graphics counts rows up from the bottom; Codex's first row is the top.
        let cellX = CGFloat(frame * cellWidth), cellY = CGFloat(height - (row + 1) * cellHeight)
        context.saveGState()
        context.clip(to: CGRect(x: cellX, y: cellY, width: CGFloat(cellWidth), height: CGFloat(cellHeight)))
        context.translateBy(x: cellX + CGFloat(cellWidth) / 2 + m.dx, y: cellY + floor + m.dy)
        context.rotate(by: m.degrees * .pi / 180)
        context.scaleBy(x: m.sx, y: m.sy)
        context.draw(image, in: CGRect(x: -w / 2, y: 0, width: w, height: h))
        context.restoreGState()
    }
}

guard let sheet = context.makeImage(),
      let png = NSBitmapImageRep(cgImage: sheet).representation(using: .png, properties: [:]) else { exit(1) }
try png.write(to: URL(fileURLWithPath: arguments[2]))
print("\(arguments[2]): \(width) x \(height)")

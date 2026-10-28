// cutout: lift the subject out of a photo onto a transparent background, using Apple's
// Vision subject lifting (the same feature as Copy Subject in Photos), trim it, and
// save it as a PNG at the original resolution (or scaled by SCALE). Every pose uses the
// same scale, so the dog stays the same size whether it's sitting or lying down.
//
//   swift tools/ari-pet/cutout.swift IN.png OUT.png [SCALE]
import AppKit
import CoreImage
import Vision

let arguments = CommandLine.arguments
guard arguments.count == 3 || arguments.count == 4 else {
    FileHandle.standardError.write("usage: cutout IN OUT [SCALE]\n".data(using: .utf8)!)
    exit(2)
}
let input = URL(fileURLWithPath: arguments[1])
let output = URL(fileURLWithPath: arguments[2])

guard let source = CIImage(contentsOf: input, options: [.applyOrientationProperty: true]) else {
    FileHandle.standardError.write("can't read \(input.path)\n".data(using: .utf8)!)
    exit(1)
}
let context = CIContext()
guard let cgSource = context.createCGImage(source, from: source.extent) else { exit(1) }

let request = VNGenerateForegroundInstanceMaskRequest()
let handler = VNImageRequestHandler(cgImage: cgSource)
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write("Vision failed: \(error)\n".data(using: .utf8)!)
    exit(1)
}
guard let result = request.results?.first, !result.allInstances.isEmpty else {
    FileHandle.standardError.write("no subject found in \(input.lastPathComponent)\n".data(using: .utf8)!)
    exit(1)
}
let buffer = try result.generateMaskedImage(ofInstances: result.allInstances, from: handler, croppedToInstancesExtent: true)
var lifted = CIImage(cvPixelBuffer: buffer)

let scale = arguments.count == 4 ? Double(arguments[3]) ?? 1 : 1
if scale != 1 {
    lifted = lifted.applyingFilter("CILanczosScaleTransform", parameters: [kCIInputScaleKey: scale, kCIInputAspectRatioKey: 1])
}
guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
      let png = context.pngRepresentation(of: lifted, format: .RGBA8, colorSpace: colorSpace) else { exit(1) }
try png.write(to: output)
print("\(output.lastPathComponent): \(Int(lifted.extent.width)) x \(Int(lifted.extent.height))")

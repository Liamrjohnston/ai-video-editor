// Reads every PNG in a folder with Apple's Vision text recognizer and prints
// one JSON object: { "frame.png": [ {text, conf, x0, y0, x1, y1}, ... ] }
// Boxes are in pixels, origin top-left. Used by check_side_crop.py.
// Usage: ocr_frames <folder>
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count == 2 else {
    FileHandle.standardError.write("usage: ocr_frames <folder>\n".data(using: .utf8)!)
    exit(2)
}
let folder = URL(fileURLWithPath: args[1])
let files = (try? FileManager.default.contentsOfDirectory(atPath: folder.path))?
    .filter { $0.hasSuffix(".png") }.sorted() ?? []

var out: [String: [[String: Any]]] = [:]
for name in files {
    let url = folder.appendingPathComponent(name)
    guard let img = NSImage(contentsOf: url),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let w = Double(cg.width), h = Double(cg.height)
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    req.minimumTextHeight = 0.006
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    try? handler.perform([req])
    var rows: [[String: Any]] = []
    for obs in req.results ?? [] {
        guard let cand = obs.topCandidates(1).first else { continue }
        let b = obs.boundingBox  // normalized, origin bottom-left
        rows.append([
            "text": cand.string,
            "conf": Double(cand.confidence),
            "x0": b.minX * w, "x1": b.maxX * w,
            "y0": (1 - b.maxY) * h, "y1": (1 - b.minY) * h,
        ])
    }
    out[name] = rows
}
let data = try JSONSerialization.data(withJSONObject: out, options: [.sortedKeys])
FileHandle.standardOutput.write(data)

// On-device evidence extraction using macOS Vision. No network requests.
// swiftc -module-cache-path /tmp/amas-swift-cache scripts/research/local_vision.swift -o data/research/local-vision
// data/research/local-vision FRAME_DIRECTORY OUTPUT_JSONL [stride]
// OCR text and image labels stay in the ignored output file. Stdout is counts only.
import Foundation
import Vision
import ImageIO

let input = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
let strideN = CommandLine.arguments.count > 3 ? Int(CommandLine.arguments[3])! : 1
let files = try FileManager.default.contentsOfDirectory(at: input, includingPropertiesForKeys: nil)
    .filter { $0.pathExtension.lowercased() == "jpg" }.sorted { $0.lastPathComponent < $1.lastPathComponent }
FileManager.default.createFile(atPath: output.path, contents: nil)
let stream = try FileHandle(forWritingTo: output)
var count = 0
for (index, url) in files.enumerated() where index % strideN == 0 {
    try autoreleasepool {
        let ocr = VNRecognizeTextRequest()
        ocr.recognitionLevel = .accurate
        ocr.usesLanguageCorrection = true
        ocr.recognitionLanguages = ["en-US", "ru-RU"]
        ocr.automaticallyDetectsLanguage = true
        let labels = VNClassifyImageRequest()
        labels.regionOfInterest = CGRect(x: 0.25, y: 0.05, width: 0.5, height: 0.9)
        var row: [String: Any] = ["file": url.lastPathComponent, "index": index]
        do {
            try VNImageRequestHandler(url: url).perform([ocr, labels])
            row["ocr"] = (ocr.results ?? []).compactMap { r -> [String: Any]? in
                guard let t = r.topCandidates(1).first else { return nil }
                return ["text": t.string, "confidence": t.confidence,
                        "box": [r.boundingBox.minX, r.boundingBox.minY, r.boundingBox.width, r.boundingBox.height]]
            }
            row["labels"] = (labels.results ?? []).prefix(10).map { ["label": $0.identifier, "confidence": $0.confidence] as [String: Any] }
        } catch {
            row["error"] = String(describing: error)
        }
        var line = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
        line.append(10)
        try stream.write(contentsOf: line)
    }
    count += 1
    if count % 25 == 0 { print("Processed \(count) local frames") }
}
try stream.close()
print("Saved \(count) local evidence rows")

// The Mac side of the iPhone Mirroring driver (box/drivers/iphone_mirroring.py), built by the box with
// `swiftc -O` into ~/.nextstep-box/. It reads one JSON request per line on stdin and answers one JSON
// line on stdout:
//   window                         where the iPhone Mirroring window is, and whether clicks are allowed
//   activate                       brings iPhone Mirroring to the front (clicks land on the window under them)
//   click   x y [hold_ms]          a tap (or a long press) at x,y in 0-999 of the window
//   drag    x1 y1 x2 y2 ms         a swipe
//   keys    [[code, [mods]], ...]  key presses for the iPhone; it gets key codes, not typed characters
//   shortcut code                  ⌘ + key for iPhone Mirroring itself (18 = ⌘1 Home, 19 = ⌘2, 20 = ⌘3 Spotlight)
//   ocr     path                   the words in a screenshot and where they are (Apple's text recognition)
// It needs Screen Recording (for the box's screenshots) and Accessibility (for clicks and keys) for the
// app that runs the box.

import AppKit
import ApplicationServices
import CoreGraphics
import Foundation
import Vision

let bundleID = "com.apple.ScreenContinuity"  // iPhone Mirroring
let source = CGEventSource(stateID: .hidSystemState)

func post(_ event: CGEvent?) { event?.post(tap: .cghidEventTap) }

func mirrorWindow() -> (id: Int, frame: CGRect)? {
    let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as? [[String: Any]] ?? []
    for w in list where (w[kCGWindowOwnerName as String] as? String) == "iPhone Mirroring"
        && (w[kCGWindowLayer as String] as? Int) == 0 {
        let b = w[kCGWindowBounds as String] as? [String: CGFloat] ?? [:]
        let frame = CGRect(x: b["X"] ?? 0, y: b["Y"] ?? 0, width: b["Width"] ?? 0, height: b["Height"] ?? 0)
        if frame.height > 300 { return (w[kCGWindowNumber as String] as? Int ?? 0, frame) }
    }
    return nil
}

func point(_ frame: CGRect, _ x: Double, _ y: Double) -> CGPoint {
    CGPoint(x: frame.minX + frame.width * CGFloat(x) / 1000, y: frame.minY + frame.height * CGFloat(y) / 1000)
}

func activate() {
    if NSWorkspace.shared.frontmostApplication?.bundleIdentifier == bundleID { return }
    NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).first?.activate()
    usleep(300_000)
}

func mouse(_ type: CGEventType, _ p: CGPoint) {
    post(CGEvent(mouseEventSource: source, mouseType: type, mouseCursorPosition: p, mouseButton: .left))
}

// Two kinds of key presses, found by trying:
// - keys passed on to the iPhone (letters, ⌘A, ⌘L...) only carry a modifier that is pressed as a key of
//   its own: as a flag on the letter it is lost ("H:" arrives as "h;", ⌘A as "a");
// - iPhone Mirroring's own shortcuts (⌘1 Home, ⌘2 app switcher, ⌘3 Spotlight) only work with ⌘ as a flag.
let modifierKeys: [(name: String, code: CGKeyCode, flag: CGEventFlags)] = [
    ("cmd", 55, .maskCommand), ("shift", 56, .maskShift), ("alt", 58, .maskAlternate), ("ctrl", 59, .maskControl)]

func modifier(_ code: CGKeyCode, _ held: CGEventFlags, down: Bool) {
    let e = CGEvent(keyboardEventSource: source, virtualKey: code, keyDown: down)
    e?.type = .flagsChanged
    e?.flags = held
    post(e)
    usleep(12_000)
}

func key(_ code: CGKeyCode, _ held: CGEventFlags) {
    for down in [true, false] {
        let e = CGEvent(keyboardEventSource: source, virtualKey: code, keyDown: down)
        e?.flags = held
        post(e)
        usleep(15_000)
    }
}

func press(_ code: CGKeyCode, _ mods: [String]) {
    var held = CGEventFlags()
    for m in modifierKeys where mods.contains(m.name) {
        held.insert(m.flag)
        modifier(m.code, held, down: true)
    }
    key(code, held)
    for m in modifierKeys.reversed() where mods.contains(m.name) {
        held.remove(m.flag)
        modifier(m.code, held, down: false)
    }
}

func handle(_ req: [String: Any]) -> [String: Any] {
    let cmd = req["cmd"] as? String ?? ""
    let num = { (k: String) -> Double in (req[k] as? NSNumber)?.doubleValue ?? 0 }
    if cmd == "ocr" {
        guard let path = req["path"] as? String, let img = NSImage(contentsOfFile: path),
              let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return ["ok": false, "error": "no_image"] }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        do { try VNImageRequestHandler(cgImage: cg).perform([request]) } catch { return ["ok": false, "error": "\(error)"] }
        let lines: [[String: Any]] = (request.results ?? []).compactMap { o in
            guard let c = o.topCandidates(1).first else { return nil }
            let b = o.boundingBox  // 0-1, origin bottom-left
            return ["text": c.string, "conf": c.confidence, "b": [b.minX, 1 - b.maxY, b.maxX, 1 - b.minY]]
        }
        return ["ok": true, "lines": lines]
    }
    guard let (id, frame) = mirrorWindow() else { return ["ok": false, "error": "no_iphone_mirroring_window"] }
    switch cmd {
    case "window":
        return ["ok": true, "id": id, "x": frame.minX, "y": frame.minY, "w": frame.width, "h": frame.height,
                "accessibility": AXIsProcessTrusted()]
    case "activate":
        activate()
        return ["ok": true]
    case "click":
        activate()
        let p = point(frame, num("x"), num("y"))
        mouse(.mouseMoved, p)
        usleep(40_000)
        mouse(.leftMouseDown, p)
        usleep(useconds_t(max(60, num("hold_ms")) * 1000))
        mouse(.leftMouseUp, p)
        return ["ok": true]
    case "drag":
        activate()
        let a = point(frame, num("x1"), num("y1")), b = point(frame, num("x2"), num("y2"))
        let steps = max(8, Int(num("ms") / 15))
        mouse(.mouseMoved, a)
        usleep(30_000)
        mouse(.leftMouseDown, a)
        for i in 1...steps {
            let f = CGFloat(i) / CGFloat(steps)
            usleep(useconds_t(num("ms") * 1000 / Double(steps)))
            mouse(.leftMouseDragged, CGPoint(x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f))
        }
        usleep(40_000)
        mouse(.leftMouseUp, b)
        return ["ok": true]
    case "keys":
        activate()
        for key in req["keys"] as? [[Any]] ?? [] {
            press(CGKeyCode((key.first as? NSNumber)?.intValue ?? 0), key.count > 1 ? key[1] as? [String] ?? [] : [])
            usleep(25_000)
        }
        return ["ok": true]
    case "shortcut":
        activate()
        key(CGKeyCode(num("code")), .maskCommand)
        return ["ok": true]
    default:
        return ["ok": false, "error": "unknown_cmd:\(cmd)"]
    }
}

setvbuf(stdout, nil, _IOLBF, 0)
for m in modifierKeys { modifier(m.code, [], down: false) }  // in case an earlier run left one down
while let line = readLine() {
    var res: [String: Any]
    if let data = line.data(using: .utf8), let req = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
        res = handle(req)
    } else {
        res = ["ok": false, "error": "bad_request"]
    }
    let out = (try? JSONSerialization.data(withJSONObject: res)) ?? Data("{\"ok\":false}".utf8)
    print(String(data: out, encoding: .utf8) ?? "{\"ok\":false}")
}

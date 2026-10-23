import AppKit
let app = NSApplication.shared
let notice = UpdateNotice(.available(PiggyRelease(version: "test", notes: "", url: URL(string: "https://example.com")!)))
func decorationBounds(scale: CGFloat) -> NSRect {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1280, pixelsHigh: 1280,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    let context = NSGraphicsContext(bitmapImageRep: bitmap)!
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = context
    context.cgContext.translateBy(x: 0, y: 1280)
    context.cgContext.scaleBy(x: scale, y: -scale)
    notice.drawPetDecoration(time: 0)
    context.flushGraphics(); NSGraphicsContext.restoreGraphicsState()
    var minX = 1280, minY = 1280, maxX = 0, maxY = 0
    for y in Int(300*scale)..<Int(460*scale) {
        for x in Int(330*scale)..<Int(490*scale) {
            if bitmap.colorAt(x: x, y: y)!.alphaComponent > 0.1 {
                minX = min(minX,x); maxX = max(maxX,x)
                minY = min(minY,y); maxY = max(maxY,y)
            }
        }
    }
    assert(maxX > minX)
    return NSRect(x: minX, y: minY, width: maxX-minX+1, height: maxY-minY+1)
}
let baseline = decorationBounds(scale: 1)
for scale: CGFloat in [0.5, 2] {
    let bounds = decorationBounds(scale: scale)
    assert(abs(bounds.width / scale - baseline.width) < 5)
    assert(abs(bounds.height / scale - baseline.height) < 5)
    assert(abs(bounds.midX / scale - baseline.midX) < 3)
    assert(abs(bounds.midY / scale - baseline.midY) < 3)
    let desktop = NSRect(x: 0, y: 0, width: 1440, height: 900)
    for edge in [DesktopEdge.left, .right, .top, .bottom] {
        let main = tailWindowFrame(edge: edge, petFrame: NSRect(x: 500, y: 400, width: 160, height: 140), desktopFrame: desktop,
            size: 68*scale, screenOverlap: 30*scale)
        let tails = familyTailRects(edge: edge, main: main, desktop: desktop, children: 3)
        assert(tails.count == 4 && tails[0].width == 68*scale)
        assert(tails.dropFirst().allSatisfy { $0.width == 32*scale && $0.height == 32*scale })
    }
}
assert(notice.petDecorationBounds != nil)
assert(UpdateNotice(.current).petDecorationBounds == nil)
print("PASS: bulb size and anchor scale with pet at 50%/100%/200%; main and child tails scale on all four edges")

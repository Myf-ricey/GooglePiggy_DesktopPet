import AppKit
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let suite = "GooglePiggy.AppearanceTests.\(UUID().uuidString)"
let defaults = UserDefaults(suiteName: suite)!
defer { defaults.removePersistentDomain(forName: suite) }
let appearance = PetAppearance(defaults: defaults)
assert(appearance.petScale == 1)
appearance.set("petScale", 1.75)
assert(PetAppearance(defaults: defaults).petScale == 1.75)
appearance.setColor("dialogColor", .systemBlue)
assert(appearance.dialogColor.usingColorSpace(.sRGB)!.blueComponent > 0.5)
appearance.reset()
assert(appearance.petScale == 1)
assert(appearance.customDialogColor == nil)
let selector = FamilySelector()
let node = FamilyNode(id: "test", parent: "", title: "测试任务与字体等比例缩放")
for scale: CGFloat in [0.5, 1, 2, 1] {
    selector.configure(scale: scale, color: .white, opacity: 0.75)
    selector.update([node], selected: "test", counts: [:])
    assert(abs(selector.panel.frame.width - 280 * scale) < 0.01)
    assert(abs(selector.panel.frame.height - 46 * scale) < 0.01)
    let scroll = selector.panel.contentView!.subviews[0] as! NSScrollView
    let document = scroll.documentView!
    let button = document.subviews[0] as! NSButton
    let rect = document.convert(button.frame, to: nil)
    assert(abs(rect.height - 32 * scale) < 0.01)
    let center = NSPoint(x: rect.midX, y: rect.midY)
    assert(button.bounds.contains(button.convert(center, from: nil)))
}
print("PASS: defaults, persistence, reset, scaled task layout and button hit testing")
// Preview toggles are independent and closing settings clears both.
let settings = AppearancePanel(appearance: appearance)
var previewState = (false, false)
settings.onPreview = { dialog, tasks, _ in previewState = (dialog, tasks) }
settings.show()
let settingsWindow = NSApp.windows.first { $0.title == "外观" }!
func buttons(in view: NSView) -> [NSButton] {
    (view as? NSButton).map { [$0] } ?? view.subviews.flatMap { buttons(in: $0) }
}
let controls = buttons(in: settingsWindow.contentView!)
let dialogToggle = controls.first { $0.title == "预览对话框" }!
let taskToggle = controls.first { $0.title == "预览任务栏" }!
dialogToggle.performClick(nil)
assert(previewState == (true, false))
taskToggle.performClick(nil)
assert(previewState == (true, true))
let reset = controls.first { $0.title == "恢复默认" }!
let originalFrame = settingsWindow.frame
appearance.setColor("dialogColor", .white)
appearance.set("buttonOpacity", 0.35)
assert(appearance.customDialogColor != nil)
reset.performClick(nil)
assert(appearance.number("buttonOpacity") == 1)
assert(appearance.customDialogColor == nil)
assert(dialogToggle.state == .on && taskToggle.state == .on)
assert(previewState == (true, true) && settingsWindow.frame == originalFrame)
dialogToggle.performClick(nil)
assert(previewState == (false, true))
reset.performClick(nil)
assert(dialogToggle.state == .off && taskToggle.state == .on)
assert(previewState == (false, true))
settingsWindow.close()
assert(previewState == (false, false))
print("PASS: independent preview checkboxes and close cleanup")
if let output = CommandLine.arguments.dropFirst().first {
    let settings = AppearancePanel(appearance: appearance)
    settings.show()
    RunLoop.current.run(until: Date().addingTimeInterval(0.1))
    let panel = NSApp.windows.first { $0.title == "外观" }!
    let view = panel.contentView!
    let image = view.bitmapImageRepForCachingDisplay(in: view.bounds)!
    view.cacheDisplay(in: view.bounds, to: image)
    try image.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: output))
    panel.close()
}

let previews = AppearancePreview()
previews.show(dialog: true, tasks: true)
let previewDialog = NSApp.windows.first { $0.title == "外观 · 对话框预览" }!
let previewTasks = NSApp.windows.first { $0.title == "外观 · 任务栏预览" }!
let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
for offset: CGFloat in [0, 100] {
    let dialog = NSRect(x: 400+offset, y: 500, width: 384, height: 194)
    let anchor = NSRect(x: 450+offset, y: 300, width: 168, height: 150)
    previews.position(dialogFrame: dialog, taskAnchor: anchor, screen: screen, visible: true, realDialogVisible: false)
    assert(previewDialog.frame == dialog)
    assert(previewTasks.frame.origin == familySelectorOrigin(anchor: anchor, size: previewTasks.frame.size, screen: screen, gap: PetAppearance.shared.taskGap))
    assert(previewDialog.isVisible && previewTasks.isVisible)
}
previews.position(dialogFrame: .zero, taskAnchor: .zero, screen: screen, visible: true, realDialogVisible: true)
assert(!previewDialog.isVisible)
previews.position(dialogFrame: nil, taskAnchor: nil, screen: nil, visible: false, realDialogVisible: false)
assert(!previewDialog.isVisible && !previewTasks.isVisible)
print("PASS: preview follows pet geometry, shares live task placement, yields to real dialogs and hides with pet")

// Render real dialogue pixels: a translucent background must not fade glyphs.
let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 640, pixelsHigh: 640,
    bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
    colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
let context = NSGraphicsContext(bitmapImageRep: bitmap)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = context
context.cgContext.translateBy(x: 0, y: 640)
context.cgContext.scaleBy(x: 1, y: -1)
let notice = UpdateNotice(.current)
notice.draw(time: 0, backgroundColor: .white, backgroundOpacity: 0.25)
context.flushGraphics()
NSGraphicsContext.restoreGraphicsState()
let backgroundAlpha = bitmap.colorAt(x: 300, y: 270)!.alphaComponent
assert(abs(backgroundAlpha - 0.25) < 0.02, "background alpha: \(backgroundAlpha)")
let glyphAlpha = (258..<530).flatMap { x in (206..<224).map { y in bitmap.colorAt(x: x, y: y)!.alphaComponent } }.max()!
assert(glyphAlpha > 0.95, "text alpha: \(glyphAlpha)")
selector.configure(scale: 1, color: .white, opacity: 0.25)
assert(selector.panel.alphaValue == 1)
assert(selector.panel.backgroundColor.alphaComponent == 0.25)
assert(previewDialog.alphaValue == 1)
print("PASS: dialogue background pixels are translucent, text pixels and window alpha remain opaque")

// The button setting must not affect either the background or glyph opacity.
func renderButton(_ opacity: CGFloat) -> NSBitmapImageRep {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 640, pixelsHigh: 640,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    let graphics = NSGraphicsContext(bitmapImageRep: rep)!
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = graphics
    graphics.cgContext.translateBy(x: 0, y: 640); graphics.cgContext.scaleBy(x: 1, y: -1)
    notice.draw(time: 0, backgroundColor: .white, backgroundOpacity: 0.25, buttonOpacity: opacity)
    graphics.flushGraphics(); NSGraphicsContext.restoreGraphicsState()
    return rep
}
let faintButton = renderButton(0.2), solidButton = renderButton(1)
assert(abs(faintButton.colorAt(x: 300, y: 270)!.alphaComponent - 0.25) < 0.02)
assert(abs(solidButton.colorAt(x: 300, y: 270)!.alphaComponent - 0.25) < 0.02)
assert(faintButton.colorAt(x: 280, y: 300)!.alphaComponent < 0.5)
assert(solidButton.colorAt(x: 280, y: 300)!.alphaComponent > 0.99)
let buttonTextAlpha = (385..<435).flatMap { x in (290..<313).map { y in faintButton.colorAt(x: x, y: y)!.alphaComponent } }.max()!
assert(buttonTextAlpha > 0.95)
print("PASS: independent button opacity, opaque button text and default reset")

appearance.set("dialogGap", -40)
appearance.set("taskGap", 80)
appearance.setColor("dialogTextColor", .red)
appearance.setColor("buttonTextColor", .blue)
let restoredAppearance = PetAppearance(defaults: defaults)
assert(restoredAppearance.dialogGap == -40 && restoredAppearance.taskGap == 80)
assert(restoredAppearance.dialogTextColor!.redComponent > 0.99)
assert(restoredAppearance.buttonTextColor!.blueComponent > 0.99)
let gapAnchor = NSRect(x: 400, y: 300, width: 160, height: 140)
assert(familySelectorOrigin(anchor: gapAnchor, size: NSSize(width: 280, height: 80), screen: screen, gap: 80).y == 520)
appearance.reset()
assert(appearance.dialogGap == 0 && appearance.taskGap == 8)
assert(appearance.dialogTextColor == nil && appearance.buttonTextColor == nil)
print("PASS: text colors and independent gaps persist and reset to original defaults")

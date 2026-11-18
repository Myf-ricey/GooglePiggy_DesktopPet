import AppKit

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let selector = FamilySelector()
let short = FamilyNode(id: "short", parent: "", title: "测试")
let long = FamilyNode(id: "long", parent: "", title: String(repeating: "混合标题测验 abc 🐷 ", count: 10))
let read = FamilyNode(id: "read", parent: "", title: "测试")
short.unread = true
short.resultCompletedAt = Date()

long.unread = true
long.resultCompletedAt = Date()

var dismissed: [String] = []
var selected: [String] = []
selector.onDismiss = { id, _ in dismissed.append(id) }
selector.onSelect = { selected.append($0) }
let panel = selector.panel
let scroll = panel.contentView!.subviews[0] as! NSScrollView
func button(_ id: String) -> NSButton {
    scroll.documentView!.subviews.compactMap { $0 as? NSButton }.first { $0.identifier?.rawValue == id }!
}
func send(_ type: NSEvent.EventType, in button: NSButton, x: CGFloat, y: CGFloat) {
    let position = button.convert(NSPoint(x: x, y: y), to: nil)
    let event = NSEvent.mouseEvent(with: type, location: position, modifierFlags: [],
        timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: panel.windowNumber,
        context: nil, eventNumber: 1, clickCount: 1, pressure: 1)!
    panel.sendEvent(event)
}
func rightClick(_ button: NSButton, x: CGFloat, y: CGFloat = 16) {
    send(.rightMouseDown, in: button, x: x, y: y)
    send(.rightMouseUp, in: button, x: x, y: y)
}
for scale: CGFloat in [0.5, 1, 2] {
    selector.configure(scale: scale, color: .black, opacity: 1)
    selector.update([short, long, read], selected: "read", counts: [:])
    panel.setFrameOrigin(NSPoint(x: 300, y: 400))
    panel.orderFrontRegardless()
    RunLoop.current.run(until: Date().addingTimeInterval(0.05))
    dismissed = []
    selected = []

    let shortButton = button("short")
    let longButton = button("long")
    rightClick(shortButton, x: 6)
    rightClick(shortButton, x: 13) // Include the gap between the dot and glyphs.
    rightClick(shortButton, x: 32)
    rightClick(longButton, x: 200)
    assert(dismissed == ["short", "short", "short", "long"], "scale \(scale): \(dismissed)")
    rightClick(shortButton, x: 44) // Just after the short title.
    rightClick(shortButton, x: 215)
    rightClick(shortButton, x: 6, y: 28) // Vertical row padding.
    rightClick(shortButton, x: 6, y: -1) // Gap between rows.
    rightClick(button("read"), x: 20)
    send(.rightMouseDown, in: shortButton, x: 6, y: 16)
    send(.rightMouseUp, in: shortButton, x: 45, y: 16)
    send(.rightMouseDown, in: shortButton, x: 45, y: 16)
    send(.rightMouseUp, in: shortButton, x: 6, y: 16)
    send(.rightMouseDown, in: shortButton, x: 6, y: 16)
    send(.rightMouseUp, in: longButton, x: 6, y: 16)
    assert(dismissed == ["short", "short", "short", "long"])
    assert(selected.isEmpty)
    button("read").performClick(nil)
    assert(selected.last == "read")
}
send(.rightMouseDown, in: button("short"), x: 6, y: 16)
short.resultCompletedAt = short.resultCompletedAt!.addingTimeInterval(1)
selector.update([short, long, read], selected: "read", counts: [:])
let beforeRefresh = dismissed
send(.rightMouseUp, in: button("short"), x: 6, y: 16)
assert(dismissed == beforeRefresh)

let many = (0..<9).map { index in FamilyNode(id: "row\(index)", parent: "", title: "测试 \(index)") }
for row in many {
    row.unread = true
    row.resultCompletedAt = Date()
}
selector.configure(scale: 1, color: .black, opacity: 1)
selector.update(many, selected: "", counts: [:])
let clip = scroll.contentView
clip.scroll(to: .zero)
scroll.reflectScrolledClipView(clip)
dismissed = []
let bottom = button("row8")
rightClick(bottom, x: 6)
assert(dismissed == ["row8"])
selector.update(Array(many.dropLast()), selected: "", counts: [:])
assert(clip.bounds.minY == 0, "dismissing a scrolled row should keep the bottom visible")
rightClick(button("row7"), x: 6)
assert(dismissed == ["row8", "row7"])
panel.orderOut(nil)
print("Passed native panel event dispatch at 50%, 100%, 200% and when scrolled")

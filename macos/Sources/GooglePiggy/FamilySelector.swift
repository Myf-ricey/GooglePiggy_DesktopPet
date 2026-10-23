import AppKit

final class FamilySelector: NSObject {
    let panel: NSPanel
    private let scroll = NSScrollView()
    // nil means never rendered; an empty task list legitimately has an empty signature.
    private var signature: String?
    private var appearanceScale: CGFloat = 1
    private var textColor: NSColor = .labelColor
    func configure(scale: CGFloat, color: NSColor, opacity: CGFloat) {
        if appearanceScale != scale { signature = nil; appearanceScale = scale }
        signature = nil
        let rgb = color.usingColorSpace(.sRGB)
        let light = rgb.map { ($0.redComponent + $0.greenComponent + $0.blueComponent) / 3 } ?? 1
        textColor = light < 0.45 ? .white : .black
        panel.backgroundColor = color.withAlphaComponent(opacity)
        panel.alphaValue = 1
    }
    var onSelect: ((String) -> Void)?
    override init() {
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 280, height: 100),
            styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        super.init()
        panel.isOpaque = false; panel.backgroundColor = .clear
        panel.hasShadow = true; panel.level = NSWindow.Level(rawValue: NSWindow.Level.floating.rawValue + 1); panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isReleasedWhenClosed = false
        scroll.hasVerticalScroller = true; scroll.drawsBackground = false
        let surface = NSView(frame: panel.contentView?.bounds ?? .zero)
        surface.autoresizingMask = [.width, .height]
        scroll.frame = surface.bounds; scroll.autoresizingMask = [.width, .height]
        surface.addSubview(scroll); panel.contentView = surface
    }
    func update(_ nodes: [FamilyNode], selected: String, counts: [String: Int]) {
        let sig = nodes.map { "\($0.id):\($0.title):\($0.unread):\(counts[$0.id] ?? 0)" }.joined() + selected
        guard sig != signature else { return }; signature = sig
        let height = CGFloat(max(1, min(nodes.count, 6))) * 34 + 12
        panel.setContentSize(NSSize(width: 280 * appearanceScale, height: height * appearanceScale))
        let document = NSView(frame: NSRect(x: 0, y: 0, width: 264, height: CGFloat(max(1, nodes.count))*34+12))
        if nodes.isEmpty {
            let label = NSTextField(labelWithString: "当前好像没有任务唔～")
            label.textColor = textColor
            label.frame = NSRect(x: 12, y: 12, width: 240, height: 20); document.addSubview(label)
        }
        for (i, node) in nodes.enumerated() {
            let button = NSButton(title: (node.unread ? "● " : (node.id == selected ? "✓ " : "   ")) + node.title, target: self, action: #selector(selectRow(_:)))
            button.contentTintColor = textColor
            if node.unread {
                let title = NSMutableAttributedString(string:button.title,attributes:[.font:NSFont.systemFont(ofSize:13),.foregroundColor:textColor])
                title.addAttribute(.foregroundColor,value:NSColor.systemBlue,range:NSRange(location:0,length:1))
                button.attributedTitle = title
            }
            button.identifier = NSUserInterfaceItemIdentifier(node.id)
            button.toolTip = "\(node.title) · \(counts[node.id] ?? 0) 个小助手"
            button.isBordered = false; button.alignment = .left; button.font = .systemFont(ofSize: 13)
            button.cell?.lineBreakMode = .byTruncatingTail
            button.frame = NSRect(x: 8, y: document.frame.height-CGFloat(i+1)*34-4, width: 248, height: 32)
            document.addSubview(button)
        }
        // AppKit scales both controls and their hit testing from logical points.
        document.setFrameSize(NSSize(width: 264 * appearanceScale, height: document.frame.height * appearanceScale))
        document.setBoundsSize(NSSize(width: 264, height: CGFloat(max(1, nodes.count))*34+12))
        scroll.documentView = document
        document.scroll(NSPoint(x: 0, y: document.bounds.height))
    }
    @objc private func selectRow(_ sender: NSButton) { if let id = sender.identifier?.rawValue { onSelect?(id) } }
}

// Shared by live tasks and appearance previews to keep placement identical.
func familySelectorOrigin(anchor: NSRect, size: NSSize, screen: NSRect, gap: CGFloat = 8) -> NSPoint {
    NSPoint(x: min(max(anchor.midX-size.width/2, screen.minX), screen.maxX-size.width),
            y: min(anchor.maxY+gap, screen.maxY-size.height))
}

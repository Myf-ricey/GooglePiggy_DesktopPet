import AppKit

final class FamilySelector: NSObject {
    let panel: NSPanel
    private let scroll = NSScrollView()
    // nil means never rendered; an empty task list legitimately has an empty signature.
    private var signature: String?
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
        let glass = NSVisualEffectView(frame:panel.contentView?.bounds ?? .zero)
        glass.material = .hudWindow; glass.blendingMode = .behindWindow; glass.state = .active
        glass.wantsLayer = true; glass.layer?.backgroundColor = NSColor.gray.withAlphaComponent(0.24).cgColor
        glass.autoresizingMask = [.width,.height]
        scroll.frame = glass.bounds; scroll.autoresizingMask = [.width,.height]
        glass.addSubview(scroll); panel.contentView = glass
    }
    func update(_ nodes: [FamilyNode], selected: String, counts: [String: Int]) {
        let sig = nodes.map { "\($0.id):\($0.title):\($0.unread):\(counts[$0.id] ?? 0)" }.joined() + selected
        guard sig != signature else { return }; signature = sig
        let height = CGFloat(max(1, min(nodes.count, 6))) * 34 + 12
        panel.setContentSize(NSSize(width: 280, height: height))
        let document = NSView(frame: NSRect(x: 0, y: 0, width: 264, height: CGFloat(max(1, nodes.count))*34+12))
        if nodes.isEmpty {
            let label = NSTextField(labelWithString: "当前好像没有任务唔～")
            label.frame = NSRect(x: 12, y: 12, width: 240, height: 20); document.addSubview(label)
        }
        for (i, node) in nodes.enumerated() {
            let button = NSButton(title: (node.unread ? "● " : (node.id == selected ? "✓ " : "   ")) + node.title, target: self, action: #selector(selectRow(_:)))
            if node.unread {
                let title = NSMutableAttributedString(string:button.title,attributes:[.font:NSFont.systemFont(ofSize:13),.foregroundColor:NSColor.labelColor])
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
        scroll.documentView = document
        document.scroll(NSPoint(x: 0, y: document.frame.height))
    }
    @objc private func selectRow(_ sender: NSButton) { if let id = sender.identifier?.rawValue { onSelect?(id) } }
}

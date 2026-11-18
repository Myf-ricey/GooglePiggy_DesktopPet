import AppKit
import CoreText

private final class FamilySelectorRow: NSButton {
    private let textLine: CTLine
    private let checkmark: CTLine?
    private let textOrigin: NSPoint
    private let unreadDot: NSRect
    private let dismissRect: NSRect
    private let dismiss: (() -> Void)?
    private var dismissPressed = false

    override var isFlipped: Bool { false }

    init(frame: NSRect, title: String, color: NSColor, unread: Bool, selected: Bool,
         dismiss: (() -> Void)?) {
        let font = NSFont.systemFont(ofSize: 13)
        let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: color]
        let singleLine = title.components(separatedBy: .newlines).joined(separator: " ")
        let fullLine = CTLineCreateWithAttributedString(NSAttributedString(string: singleLine, attributes: attributes))
        let ellipsis = CTLineCreateWithAttributedString(NSAttributedString(string: "…", attributes: attributes))
        // Every title begins after the same indicator column.
        let titleX: CGFloat = 15
        let availableWidth = frame.width - titleX
        if CTLineGetTypographicBounds(fullLine, nil, nil, nil) > availableWidth {
            textLine = CTLineCreateTruncatedLine(fullLine, availableWidth, .end, ellipsis) ?? ellipsis
        } else {
            textLine = fullLine
        }
        checkmark = selected && !unread
            ? CTLineCreateWithAttributedString(NSAttributedString(string: "✓", attributes: attributes))
            : nil
        let centerY = frame.height / 2
        textOrigin = NSPoint(x: titleX, y: centerY - (font.ascender + font.descender) / 2)
        unreadDot = unread ? NSRect(x: 1, y: centerY - 5, width: 10, height: 10) : .zero
        let glyphBounds = CTLineGetImageBounds(textLine, nil)
        let titleRect = glyphBounds.isEmpty ? .zero
            : glyphBounds.offsetBy(dx: textOrigin.x, dy: textOrigin.y)
        let rowBounds = NSRect(origin: .zero, size: frame.size)
        dismissRect = (titleRect.isEmpty ? unreadDot : unreadDot.union(titleRect)).intersection(rowBounds)
        self.dismiss = unread ? dismiss : nil
        super.init(frame: frame)
        self.title = title
        isBordered = false
    }

    required init?(coder: NSCoder) { nil }

    override func draw(_ dirtyRect: NSRect) {
        guard let context = NSGraphicsContext.current?.cgContext else { return }
        context.saveGState()
        context.clip(to: bounds)
        context.textMatrix = .identity
        if !unreadDot.isEmpty {
            context.setFillColor(NSColor.systemBlue.cgColor)
            context.fillEllipse(in: unreadDot)
        } else if let checkmark {
            context.textPosition = NSPoint(x: 1, y: textOrigin.y)
            CTLineDraw(checkmark, context)
        }
        context.textPosition = textOrigin
        CTLineDraw(textLine, context)
        context.restoreGState()
    }

    override func rightMouseDown(with event: NSEvent) {
        dismissPressed = dismiss != nil && containsDismissPoint(event)
    }

    override func rightMouseUp(with event: NSEvent) {
        let wasPressed = dismissPressed
        dismissPressed = false
        if wasPressed && containsDismissPoint(event) { dismiss?() }
    }

    private func containsDismissPoint(_ event: NSEvent) -> Bool {
        window?.isVisible == true
            && dismissRect.intersection(visibleRect).contains(convert(event.locationInWindow, from: nil))
    }
}

final class FamilySelector: NSObject {
    private struct Row: Equatable {
        let id: String
        let title: String
        let unread: Bool
        let selected: Bool
        let childCount: Int
        let completedAt: Date?
    }

    let panel: NSPanel
    private let scroll = NSScrollView()
    private var renderedRows: [Row]?
    private var appearanceScale: CGFloat = 1
    private var textColor: NSColor = .labelColor
    func configure(scale: CGFloat, color: NSColor, opacity: CGFloat, textColor customTextColor: NSColor? = nil) {
        appearanceScale = scale
        renderedRows = nil
        let rgb = color.usingColorSpace(.sRGB)
        let light = rgb.map { ($0.redComponent + $0.greenComponent + $0.blueComponent) / 3 } ?? 1
        textColor = (customTextColor ?? (light < 0.45 ? NSColor.white : NSColor.black)).withAlphaComponent(1)
        panel.backgroundColor = color.withAlphaComponent(opacity)
        panel.alphaValue = 1
    }
    var onSelect: ((String) -> Void)?
    var onDismiss: ((String, Date) -> Void)?
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
        let rows = nodes.map { node in
            Row(id: node.id, title: node.title, unread: node.unread, selected: node.id == selected,
                childCount: counts[node.id] ?? 0, completedAt: node.resultCompletedAt)
        }
        guard rows != renderedRows else { return }
        renderedRows = rows
        let clip = scroll.contentView
        let distanceFromTop = max(0, (scroll.documentView?.frame.maxY ?? 0) - clip.bounds.maxY)
        let height = CGFloat(max(1, min(nodes.count, 6))) * 34 + 12
        panel.setContentSize(NSSize(width: 280 * appearanceScale, height: height * appearanceScale))
        let document = NSView(frame: NSRect(x: 0, y: 0, width: 264, height: CGFloat(max(1, nodes.count))*34+12))
        if nodes.isEmpty {
            let label = NSTextField(labelWithString: "当前好像没有任务唔～")
            label.textColor = textColor
            label.frame = NSRect(x: 12, y: 12, width: 240, height: 20); document.addSubview(label)
        }
        for (i, row) in rows.enumerated() {
            let frame = NSRect(x: 8, y: document.frame.height - CGFloat(i + 1) * 34 - 5, width: 248, height: 32)
            let button = FamilySelectorRow(frame: frame, title: row.title, color: textColor,
                unread: row.unread, selected: row.selected, dismiss: { [weak self] in
                    if let completedAt = row.completedAt { self?.onDismiss?(row.id, completedAt) }
                })
            button.target = self
            button.action = #selector(selectRow(_:))
            button.identifier = NSUserInterfaceItemIdentifier(row.id)
            button.toolTip = "\(row.title) · \(row.childCount) 个小助手"
            document.addSubview(button)
        }
        // AppKit scales both controls and their hit testing from logical points.
        document.setFrameSize(NSSize(width: 264 * appearanceScale, height: document.frame.height * appearanceScale))
        document.setBoundsSize(NSSize(width: 264, height: CGFloat(max(1, nodes.count))*34+12))
        scroll.documentView = document
        clip.scroll(to: NSPoint(x: 0, y: max(0, document.frame.maxY - clip.bounds.height - distanceFromTop)))
        scroll.reflectScrolledClipView(clip)
    }
    @objc private func selectRow(_ sender: NSButton) { if let id = sender.identifier?.rawValue { onSelect?(id) } }
}

// Shared by live tasks and appearance previews to keep placement identical.
func familySelectorOrigin(anchor: NSRect, size: NSSize, screen: NSRect, gap: CGFloat = 8) -> NSPoint {
    NSPoint(x: min(max(anchor.midX-size.width/2, screen.minX), screen.maxX-size.width),
            y: min(anchor.maxY+gap, screen.maxY-size.height))
}

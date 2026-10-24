import AppKit

private final class DialogPreviewView: NSView {
    let notice = UpdateNotice(.current)
    override var isFlipped: Bool { true }
    override func draw(_ dirtyRect: NSRect) {
        notice.appearancePreview = true
        notice.draw(backgroundColor: PetAppearance.shared.customDialogColor, backgroundOpacity: PetAppearance.shared.number("dialogOpacity"), buttonOpacity: PetAppearance.shared.number("buttonOpacity"), textColor: PetAppearance.shared.dialogTextColor, buttonTextColor: PetAppearance.shared.buttonTextColor)
    }
}

// Preview windows use the production renderers without touching real task/read state.
final class AppearancePreview {
    private let dialogPanel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    private let dialogView = DialogPreviewView()
    private let tasks = FamilySelector()
    private var showDialog = false
    private var showTasks = false
    var previewsTasks: Bool { showTasks }
    var dialogLogicalBounds: NSRect { dialogView.notice.rect.insetBy(dx: -20, dy: -24) }
    private let samples: [FamilyNode] = {
        let working = FamilyNode(id: "appearance-preview-working", parent: "", title: "示例任务：正在处理你的请求")
        working.active = true
        let unread = FamilyNode(id: "appearance-preview-unread", parent: "", title: "示例任务：已完成，等待查看")
        unread.unread = true
        return [working, unread]
    }()
    init() {
        dialogPanel.title = "外观 · 对话框预览"
        tasks.panel.title = "外观 · 任务栏预览"
        dialogPanel.isOpaque = false; dialogPanel.backgroundColor = .clear
        dialogPanel.hasShadow = false; dialogPanel.level = .floating
        dialogPanel.hidesOnDeactivate = false; dialogPanel.isReleasedWhenClosed = false
        dialogPanel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        dialogPanel.contentView = dialogView
        dialogPanel.ignoresMouseEvents = true
        tasks.panel.ignoresMouseEvents = true
    }
    func show(dialog: Bool, tasks: Bool) {
        showDialog = dialog; showTasks = tasks; refresh()
    }
    func refresh() {
        let appearance = PetAppearance.shared
        let logical = dialogLogicalBounds
        let scale = appearance.dialogScale
        dialogPanel.setContentSize(NSSize(width: logical.width * scale, height: logical.height * scale))
        dialogView.frame = NSRect(origin: .zero, size: dialogPanel.frame.size)
        dialogView.bounds = logical
        dialogPanel.alphaValue = 1
        dialogView.needsDisplay = true
        tasks.configure(scale: appearance.taskScale, color: appearance.taskColor,
                        opacity: appearance.number("taskOpacity", fallback: 0.9), textColor: appearance.taskTextColor)
        tasks.update(samples, selected: samples[0].id, counts: [:])
    }
    func position(dialogFrame: NSRect?, taskAnchor: NSRect?, screen: NSRect?, visible: Bool, realDialogVisible: Bool) {
        if showDialog, visible, !realDialogVisible, let dialogFrame {
            dialogPanel.setFrame(dialogFrame, display: false)
            dialogPanel.orderFrontRegardless()
        } else { dialogPanel.orderOut(nil) }
        if showTasks, visible, let taskAnchor, let screen {
            tasks.panel.setFrameOrigin(familySelectorOrigin(anchor: taskAnchor, size: tasks.panel.frame.size, screen: screen, gap: PetAppearance.shared.taskGap))
            tasks.panel.orderFrontRegardless()
        } else { tasks.panel.orderOut(nil) }
    }
}

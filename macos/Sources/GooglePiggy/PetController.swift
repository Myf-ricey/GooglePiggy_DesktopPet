import AppKit
import Foundation

private let windowSize: CGFloat = 640
private let statusPollInterval: TimeInterval = 0.25
private let thinkingStaleInterval: TimeInterval = 45
private let permissionStaleInterval: TimeInterval = 620
private let heartbeatInterval: TimeInterval = 1
private let successEffectDuration: TimeInterval = 1.35
private let dragThreshold: CGFloat = 4
private let permissionBodyWidth: CGFloat = 280
private let permissionBodyHeight: CGFloat = 230
private enum EdgeTransition: Equatable {
    case hiding
    case revealing
}

private struct EdgeMotion {
    let start: NSPoint
    let target: NSPoint
    let startedAt: TimeInterval
    let completion: () -> Void
}

private struct EdgePlacement {
    let edge: DesktopEdge
    let edgeFrame: NSRect
    let revealFrame: NSRect
    let tailFrame: NSRect
}

private func permissionBodyText(_ detail: String) -> NSAttributedString {
    let paragraph = NSMutableParagraphStyle()
    paragraph.lineBreakMode = .byCharWrapping
    paragraph.lineSpacing = 3
    let attributes: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 14),
        .foregroundColor: NSColor(
            calibratedRed: 76 / 255,
            green: 67 / 255,
            blue: 70 / 255,
            alpha: 1
        ),
        .paragraphStyle: paragraph,
    ]
    return NSAttributedString(string: detail, attributes: attributes)
}

private func permissionBodyMeasuredHeight(_ detail: String) -> CGFloat {
    permissionBodyText(detail).boundingRect(
        with: NSSize(width: permissionBodyWidth, height: 1000),
        options: [.usesLineFragmentOrigin, .usesFontLeading]
    ).height
}

private struct FrameRecord: Decodable {
    let file: String
    let duration_ms: Int
    let visible_bounds: [Int]?
}

private struct AnimationRecord: Decodable {
    let label: String
    let source: String
    let frames: [FrameRecord]
    let loop_start: Int?
}

private struct AnimationManifest: Decodable {
    let format_version: Int
    let window_size: Int
    let animations: [String: AnimationRecord]
}

private struct VisualSnapshot {
    let transientKey: String?
    let transientOnce: Bool
    let frameIndex: Int
    let successEffectStarted: TimeInterval?
}

private final class ImageStore {
    private let cache = NSCache<NSString, NSImage>()
    private let resourceURL: URL

    init(resourceURL: URL) {
        self.resourceURL = resourceURL
        cache.countLimit = 80
    }

    func image(relativePath: String) -> NSImage? {
        let key = relativePath as NSString
        if let cached = cache.object(forKey: key) {
            return cached
        }
        let url = resourceURL.appendingPathComponent(relativePath)
        guard let image = NSImage(contentsOf: url) else {
            return nil
        }
        cache.setObject(image, forKey: key)
        return image
    }
}

final class PetView: NSView {
    unowned let controller: PetController

    init(frame: NSRect, controller: PetController) {
        self.controller = controller
        super.init(frame: frame)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var isFlipped: Bool {
        true
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        true
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        controller.drawCurrentFrame(in: bounds)
    }

    override func mouseDown(with event: NSEvent) {
        controller.handleMouseDown(
            point: convert(event.locationInWindow, from: nil)
        )
    }

    override func mouseDragged(with event: NSEvent) {
        controller.handleMouseDragged()
    }

    override func mouseUp(with event: NSEvent) {
        controller.handleMouseUp(
            point: convert(event.locationInWindow, from: nil)
        )
    }

    override func rightMouseDown(with event: NSEvent) {
        controller.showContextMenu(
            at: convert(event.locationInWindow, from: nil),
            in: self
        )
    }
}

final class TailView: NSView {
    unowned let controller: PetController

    init(frame: NSRect, controller: PetController) {
        self.controller = controller
        super.init(frame: frame)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var isFlipped: Bool {
        true
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        true
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        controller.drawEdgeTail(in: bounds)
    }

    override func mouseDown(with event: NSEvent) {
        controller.handleTailClick()
    }

    override func rightMouseDown(with event: NSEvent) {
        controller.showContextMenu(
            at: convert(event.locationInWindow, from: nil),
            in: self
        )
    }
}

final class PetController: NSObject, NSApplicationDelegate {
    private var manifest: AnimationManifest?
    private var imageStore: ImageStore?
    private var resourceURL: URL?
    private var window: NSPanel?
    private var petView: PetView?
    private var tailWindow: NSPanel?
    private var tailView: TailView?
    private var instanceLock: InstanceLock?
    private var animationTimer: Timer?
    private var edgeMotionTimer: Timer?
    private var isQuitting = false
    private let startupEdgePreview: DesktopEdge?

    private var leisure = LeisureRoutine()
    private var leisureTaskTurns: [String: String] = [:]
    private var leisureTasksInitialized = false
    private var sleepPreviewEpoch: TimeInterval = 0
    private let leisureLayerKeys: Set<String> = ["sleep_body", "sleep_z", "sleep_tail"]
    private var mode = "responsive"
    private var frameIndex = 0
    private var transientKey: String?
    private var transientOnce = false
    private var successEffectStarted: TimeInterval?

    private let threadAnimations = ThreadAnimationClock()
    private let families = FamilyStore()
    private let familySelector = FamilySelector()
    private var familyTimer: Timer?
    private var familyPollAt: TimeInterval = 0
    private var familyHoverUntil: TimeInterval = 0
    private var childPositions: [String: NSPoint] = [:]
    private var focusedChildID = ""
    private var selectedFamilyPayload: [String: Any]?
    private var bridgeToken = ""
    private var bridgeStatus = "idle"
    private var packingKey = "packing_01"
    private var packingCycle = 0
    private var lastStatusPoll: TimeInterval = 0
    private var lastHeartbeat: TimeInterval = 0

    private var permissionRequest: [String: Any]?
    private var permissionRequestID = ""
    private var permissionButtonDown: String?
    private var permissionBubbleDown = false

    private var mouseDown = false
    private var dragging = false
    private var nudgeFacesRight = false
    private var nudgeLastCursor: NSPoint?
    private var dragStartCursor: NSPoint?
    private var dragStartWindowOrigin: NSPoint?
    private var dragPrevious: VisualSnapshot?
    private var dragCanPlayFlat = false

    private var hiddenWorkTokens = Set<String>()
    private var familyRevealStarted: TimeInterval?
    private var dragAnimationStarted: TimeInterval = 0
    private var edgePlacement: EdgePlacement?
    private var edgeTransition: EdgeTransition?
    private var revealAfterHiding = false
    private var edgeMotion: EdgeMotion?

    private var currentKey: String {
        if permissionRequest != nil {
            return "question"
        }
        if let transientKey {
            return transientKey
        }
        if mode == "responsive" {
            if let position = threadAnimationPosition { return position.key }
            switch bridgeStatus {
            case "thinking": return manifest?.animations["reading"] != nil ? "reading" : "carrot"
            case "working": return "carrot"
            case "compacting": return packingKey
            case "interrupted": return "question"
            default:
                switch leisure.phase {
                case .entering: return "sleep_entry"
                case .sleeping: return "sleep_body"
                case .snacking: return "snack"
                case .waking: return "left"
                case .awake: return "idle"
                }
            }
        }
        if mode == "sleep_entry" {
            return leisureNow - sleepPreviewEpoch < sleepEntryDuration ? "sleep_entry" : "sleep_body"
        }
        return mode == "packing_random" ? packingKey : mode
    }

    private var selectedAnimationActor: String {
        if let node = families.nodes[focusedChildID], node.status == "permission" { return node.id }
        return families.selectedID
    }

    private var threadAnimationPosition: ThreadAnimationClock.Position? {
        guard mode == "responsive", transientKey == nil, permissionRequest == nil,
              let position = threadAnimations.position(id:selectedAnimationActor,now:leisureNow) else { return nil }
        // Physical interactions / leisure remain their own higher-priority track.
        if position.key == "idle", leisure.phase != .awake { return nil }
        return position
    }

    private func syncThreadAnimations() {
        let now=leisureNow
        for node in families.nodes.values {
            let state: String
            if !node.active, families.children(node.id).contains(where: { $0.active && !families.childIsPaused($0) }) {
                state="carrot"
            } else {
                switch node.status {
                case "thinking": state=manifest?.animations["reading"] != nil ? "reading" : "carrot"
                case "working": state="carrot"
                case "compacting": state="packing"
                case "interrupted", "permission", "error": state="question"
                case "success": state="jump"
                default: state="idle"
                }
            }
            threadAnimations.observe(id:node.id,turn:node.turn,state:state,now:now,
                                     age:max(0,Date().timeIntervalSince(node.changed)))
        }
        threadAnimations.retain(ids:Set(families.nodes.keys))
    }

    private var currentAnimation: AnimationRecord? {
        manifest?.animations[currentKey]
    }

    private var canHideAtDesktopEdge: Bool {
        canEnterEdgeHide(mode: mode, bridgeStatus: bridgeStatus, hasPermissionRequest: permissionRequest != nil, hasTransientAnimation: transientKey != nil) && edgePlacement == nil && edgeTransition == nil
    }

    private var currentWorkTokens: Set<String> {
        let nodes = [families.selected].compactMap { $0 } + families.children(families.selectedID)
        let working = nodes.filter { ["thinking", "working", "compacting", "permission"].contains($0.status) }
        if !nodes.isEmpty { return Set(working.map { $0.id + ":" + $0.turn }) }
        return ["thinking", "working", "compacting", "permission"].contains(bridgeStatus) ? ["bridge"] : []
    }

    private func familyBodyBounds() -> NSRect {
        var result = currentPetLocalBounds()
        let slots = [NSPoint(x:310,y:575), NSPoint(x:410,y:615), NSPoint(x:510,y:575)]
        for (i,node) in families.children(families.selectedID).prefix(3).enumerated() {
            let point = childPositions[node.id] ?? slots[i]
            result = result.union(NSRect(x:point.x-44,y:point.y-64,width:88,height:70))
        }
        return result
    }

    private func revealContentBounds() -> NSRect {
        // Reserve all three child slots, even if a new agent arrives after the reveal.
        currentContentLocalBounds().union(NSRect(x:258,y:400,width:310,height:230))
    }

    private var activityRequiresVisiblePet: Bool {
        ["thinking", "working", "compacting", "interrupted"].contains(bridgeStatus)
            || permissionRequest != nil
            || successEffectStarted != nil
    }

    private var permissionTextHeight: CGFloat {
        let summary = permissionRequest?["summary"] as? String ?? "Codex 正在请求权限"
        return min(permissionBodyHeight, max(22, ceil(permissionBodyMeasuredHeight(summary)) + 2))
    }

    private var permissionBubbleRect: NSRect {
        let height = 104 + permissionTextHeight
        // Keep the pointer anchored above the pig as the text grows upwards.
        return NSRect(x: 250, y: 348 - height, width: 320, height: height)
    }

    private var permissionButtons: [String: NSRect] {
        let rect = permissionBubbleRect
        return [
            "deny": NSRect(x: rect.minX + 20, y: rect.maxY - 48, width: 100, height: 32),
            "allow": NSRect(x: rect.maxX - 136, y: rect.maxY - 48, width: 116, height: 32),
        ]
    }

    init(startupEdgePreview: DesktopEdge? = nil) {
        self.startupEdgePreview = startupEdgePreview
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        instanceLock = InstanceLock()
        guard instanceLock != nil else {
            NSApp.terminate(nil)
            return
        }
        do {
            try loadResources()
            restartLeisureClock()
            createWindow()
            familySelector.onSelect = { [weak self] id in
                guard let self else { return }
                if let node = self.families.nodes[id], node.unread && !node.active {
                    guard let url = URL(string:"codex://threads/\(id)?hostId=local"), NSWorkspace.shared.open(url) else { return }
                    // Remove only after Codex confirms its actual read state.
                    self.familySelector.panel.orderOut(nil)
                    return
                }
                self.families.select(id); self.focusedChildID = ""
                self.bridgeToken = ""; self.transientKey = nil
                self.refreshFamilyState(force: true)
            }
            let timer = Timer(timeInterval: 0.02, repeats: true) { [weak self] _ in
                if let self, !self.mouseDown {
                    if self.currentKey == "left", self.leisure.phase != .waking { self.updateNudgeDirection(NSEvent.mouseLocation) }
                    else { self.nudgeLastCursor = NSEvent.mouseLocation }
                }
                self?.refreshFamilyState()
                self?.updateLeisure()
                self?.renderCurrent()
            }
            RunLoop.main.add(timer, forMode: .common); familyTimer = timer
            applyBridgePayload(readJSONDictionary(defaultStatusURL()) ?? [:])
            writeHeartbeat(force: true)
            renderCurrent()
            scheduleCurrent()
            if let edge = startupEdgePreview {
                DispatchQueue.main.async { [weak self] in
                    self?.refreshFamilyState(force: true)
                    self?.previewEdgeHide(edge)
                }
            }
        } catch {
            presentStartupError(error)
            NSApp.terminate(nil)
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(
        _ sender: NSApplication
    ) -> Bool {
        return false
    }

    private func loadResources() throws {
        guard let resources = Bundle.main.resourceURL else {
            throw NSError(
                domain: appBundleIdentifier,
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "App resources are missing."]
            )
        }
        let manifestURL = resources.appendingPathComponent(
            "animation-manifest.json"
        )
        let data = try Data(contentsOf: manifestURL)
        let decoded = try JSONDecoder().decode(AnimationManifest.self, from: data)
        threadAnimations.clips = decoded.animations.mapValues {
            ThreadAnimationClock.Clip(durations:$0.frames.map { Double($0.duration_ms)/1000 }, loopStart:$0.loop_start ?? 0)
        }
        guard
            decoded.format_version == 1,
            decoded.window_size == Int(windowSize),
            Set(decoded.animations.keys).filter({ !$0.hasPrefix("packing_") }).subtracting(["reading", "sleep_entry", "sleep_body", "sleep_z", "sleep_tail", "snack"])
                == Set([
                    "idle", "left", "carrot", "jump", "flat", "question",
                    "edge_reveal",
                ])
        else {
            throw NSError(
                domain: appBundleIdentifier,
                code: 3,
                userInfo: [
                    NSLocalizedDescriptionKey: "Animation manifest is invalid."
                ]
            )
        }
        for animation in decoded.animations.values where animation.frames.isEmpty {
            throw NSError(
                domain: appBundleIdentifier,
                code: 4,
                userInfo: [
                    NSLocalizedDescriptionKey: "An animation has no frames."
                ]
            )
        }
        for edge in DesktopEdge.allCases {
            let tailURL = resources.appendingPathComponent(
                "edge-tail/\(edge.rawValue).png"
            )
            guard NSImage(contentsOf: tailURL) != nil else {
                throw NSError(
                    domain: appBundleIdentifier,
                    code: 5,
                    userInfo: [
                        NSLocalizedDescriptionKey:
                            "Edge tail asset is missing: \(edge.rawValue)"
                    ]
                )
            }
        }
        resourceURL = resources
        manifest = decoded
        imageStore = ImageStore(resourceURL: resources)
    }

    private func createWindow() {
        let visibleFrame = NSScreen.main?.visibleFrame
            ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let origin = NSPoint(
            x: visibleFrame.maxX - windowSize - 36,
            y: visibleFrame.minY + 36
        )
        let panel = NSPanel(
            contentRect: NSRect(
                origin: origin,
                size: NSSize(width: windowSize, height: windowSize)
            ),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.title = appDisplayName
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.isMovableByWindowBackground = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.collectionBehavior = [
            .canJoinAllSpaces,
            .fullScreenAuxiliary,
        ]
        panel.isReleasedWhenClosed = false

        let view = PetView(
            frame: NSRect(x: 0, y: 0, width: windowSize, height: windowSize),
            controller: self
        )
        panel.contentView = view
        panel.orderFrontRegardless()
        window = panel
        petView = view

        let tailPanel = NSPanel(
            contentRect: NSRect(
                origin: .zero,
                size: NSSize(
                    width: EdgeHidePolicy.tailWindowSize,
                    height: EdgeHidePolicy.tailWindowSize
                )
            ),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        tailPanel.title = "\(appDisplayName) · 隐藏"
        tailPanel.isOpaque = false
        tailPanel.backgroundColor = .clear
        tailPanel.hasShadow = false
        // The tail is anchored to the physical display edge, including areas
        // occupied by the Dock/menu bar, so keep its small click target above
        // those system windows while the full pet remains at `.floating`.
        tailPanel.level = .statusBar
        tailPanel.hidesOnDeactivate = false
        tailPanel.becomesKeyOnlyIfNeeded = true
        tailPanel.collectionBehavior = [
            .canJoinAllSpaces,
            .fullScreenAuxiliary,
        ]
        tailPanel.isReleasedWhenClosed = false
        let edgeView = TailView(
            frame: NSRect(
                x: 0,
                y: 0,
                width: EdgeHidePolicy.tailWindowSize,
                height: EdgeHidePolicy.tailWindowSize
            ),
            controller: self
        )
        tailPanel.contentView = edgeView
        tailPanel.orderOut(nil)
        tailWindow = tailPanel
        tailView = edgeView
    }

    private func presentStartupError(_ error: Error) {
        let logURL = defaultStateDirectory().appendingPathComponent(
            "pig-pet-error.log"
        )
        try? "\(utcTimestamp())\n\(error)\n".write(
            to: logURL,
            atomically: true,
            encoding: .utf8
        )
        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = "猪猪桌宠启动失败"
        alert.informativeText = "请查看：\(logURL.path)"
        alert.runModal()
    }

    private func currentFrameRecord() -> FrameRecord? {
        if let position = threadAnimationPosition,
           let animation = manifest?.animations[position.key], animation.frames.indices.contains(position.index) {
            frameIndex = position.index
            return animation.frames[position.index]
        }
        if mode == "sleep_entry" {
            let elapsed = leisureNow - sleepPreviewEpoch
            return leisureLayer(currentKey, elapsed: currentKey == "sleep_entry" ? elapsed : elapsed - sleepEntryDuration,
                                loop: currentKey != "sleep_entry")
        }
        if mode == "responsive", leisure.phase == .sleeping, currentKey == "sleep_body" {
            return leisureLayer("sleep_body", elapsed: leisureNow - leisure.sleepEpoch)
        }
        guard let animation = currentAnimation, !animation.frames.isEmpty else {
            return nil
        }
        if frameIndex >= animation.frames.count {
            frameIndex = 0
        }
        return animation.frames[frameIndex]
    }

    private func currentPetLocalBounds() -> NSRect {
        guard
            let values = currentFrameRecord()?.visible_bounds,
            values.count == 4,
            values[2] > values[0],
            values[3] > values[1]
        else {
            // Compatibility fallback for locally cached pre-edge-hide manifests.
            return NSRect(x: 300, y: 375, width: 200, height: 210)
        }
        return NSRect(
            x: CGFloat(currentKey == "left" && nudgeFacesRight ? 820 - values[2] : values[0]),
            y: CGFloat(values[1]),
            width: CGFloat(values[2] - values[0]),
            height: CGFloat(values[3] - values[1])
        )
    }

    private func currentContentLocalBounds() -> NSRect {
        var result = currentPetLocalBounds()
        if permissionRequest != nil {
            // Include the bubble pointer so an automatic work reveal never
            // leaves an actionable permission prompt behind an edge.
            let bubbleWithPointer = NSRect(
                x: permissionBubbleRect.minX,
                y: permissionBubbleRect.minY,
                width: permissionBubbleRect.width,
                height: permissionBubbleRect.height + 25
            )
            result = result.union(bubbleWithPointer)
        }
        if !families.children(families.selectedID).isEmpty {
            result = result.union(NSRect(x: 260, y: 500, width: 305, height: 120))
        }
        return result
    }

    private func screenBounds(for localBounds: NSRect) -> NSRect? {
        guard let window else {
            return nil
        }
        // Animation metadata is top-left based; AppKit screen Y points upward.
        return NSRect(
            x: window.frame.minX + localBounds.minX,
            y: window.frame.maxY - localBounds.maxY,
            width: localBounds.width,
            height: localBounds.height
        )
    }

    private func bottomRevealDrop(for edge: DesktopEdge) -> CGFloat {
        guard edge == .bottom else {
            return 0
        }
        let petHeight = screenBounds(for: currentPetLocalBounds())?.height
            ?? currentPetLocalBounds().height
        return petHeight * EdgeHidePolicy.bottomRevealDropHeightMultiplier
    }

    private func settleRevealedWindow(for placement: EdgePlacement) {
        guard
            let window,
            let contentFrame = screenBounds(for: revealContentBounds())
        else {
            return
        }
        let correction = revealedDelta(
            edge: placement.edge,
            contentFrame: contentFrame,
            desktopFrame: placement.revealFrame,
            bottomDrop: 0
        )
        guard abs(correction.x) >= 0.5 || abs(correction.y) >= 0.5 else {
            return
        }
        window.setFrameOrigin(NSPoint(
            x: window.frame.origin.x + correction.x,
            y: window.frame.origin.y + correction.y
        ))
    }

    private func interactionScreen() -> NSScreen? {
        let cursor = NSEvent.mouseLocation
        if let underCursor = NSScreen.screens.first(where: {
            $0.frame.contains(cursor)
        }) {
            return underCursor
        }
        if let screen = window?.screen {
            return screen
        }
        guard let petFrame = screenBounds(for: currentPetLocalBounds()) else {
            return NSScreen.main
        }
        return NSScreen.screens.max(by: { lhs, rhs in
            let leftIntersection = lhs.frame.intersection(petFrame)
            let rightIntersection = rhs.frame.intersection(petFrame)
            let leftArea = leftIntersection.isNull
                ? 0 : leftIntersection.width * leftIntersection.height
            let rightArea = rightIntersection.isNull
                ? 0 : rightIntersection.width * rightIntersection.height
            return leftArea < rightArea
        }) ?? NSScreen.main
    }

    private func exposedEdges(
        of screen: NSScreen,
        near petFrame: NSRect
    ) -> Set<DesktopEdge> {
        let physicalFrame = screen.frame
        let probeOffset: CGFloat = 2
        let probeX = min(
            max(petFrame.midX, physicalFrame.minX + 1),
            physicalFrame.maxX - 1
        )
        let probeY = min(
            max(petFrame.midY, physicalFrame.minY + 1),
            physicalFrame.maxY - 1
        )
        let probes: [DesktopEdge: NSPoint] = [
            .left: NSPoint(
                x: physicalFrame.minX - probeOffset,
                y: probeY
            ),
            .right: NSPoint(
                x: physicalFrame.maxX + probeOffset,
                y: probeY
            ),
            .bottom: NSPoint(
                x: probeX,
                y: physicalFrame.minY - probeOffset
            ),
            .top: NSPoint(
                x: probeX,
                y: physicalFrame.maxY + probeOffset
            ),
        ]
        let otherFrames = NSScreen.screens.compactMap { candidate -> NSRect? in
            candidate === screen ? nil : candidate.frame.insetBy(dx: -1, dy: -1)
        }
        return Set(DesktopEdge.allCases.filter { edge in
            guard let probe = probes[edge] else {
                return false
            }
            return !otherFrames.contains(where: { $0.contains(probe) })
        })
    }

    private func stopEdgeMotion() {
        edgeMotionTimer?.invalidate()
        edgeMotionTimer = nil
        edgeMotion = nil
    }

    @discardableResult
    private func startEdgeMotion(
        to origin: NSPoint,
        completion: @escaping () -> Void
    ) -> Bool {
        guard let window else {
            return false
        }

        stopEdgeMotion()
        edgeMotion = EdgeMotion(
            start: window.frame.origin,
            target: origin,
            startedAt: ProcessInfo.processInfo.systemUptime,
            completion: completion
        )
        let timer = Timer(
            timeInterval: EdgeHidePolicy.motionFrameInterval,
            repeats: true
        ) { [weak self] _ in
            self?.advanceEdgeMotion()
        }
        RunLoop.main.add(timer, forMode: .common)
        edgeMotionTimer = timer
        return true
    }

    private func advanceEdgeMotion() {
        guard let motion = edgeMotion, let window else {
            stopEdgeMotion()
            return
        }
        let elapsed = ProcessInfo.processInfo.systemUptime - motion.startedAt
        let progress = min(
            1,
            max(0, elapsed / EdgeHidePolicy.transitionDuration)
        )
        let eased = edgeMotionEasedProgress(CGFloat(progress))
        let origin = NSPoint(
            x: motion.start.x
                + (motion.target.x - motion.start.x) * eased,
            y: motion.start.y
                + (motion.target.y - motion.start.y) * eased
        )
        window.setFrameOrigin(origin)
        guard progress >= 1 else {
            return
        }

        window.setFrameOrigin(motion.target)
        stopEdgeMotion()
        DispatchQueue.main.async(execute: motion.completion)
    }

    @discardableResult
    private func beginEdgeHideIfNeeded(
        forcedEdge: DesktopEdge? = nil,
        forcedScreen: NSScreen? = nil
    ) -> Bool {
        guard
            canHideAtDesktopEdge,
            let window,
            let petFrame = screenBounds(for: familyBodyBounds()),
            let screen = forcedScreen ?? interactionScreen()
        else {
            return false
        }
        let edgeFrame = screen.frame
        let revealFrame = screen.visibleFrame
        let allowedEdges = exposedEdges(of: screen, near: petFrame)
        let edge = forcedEdge ?? touchedDesktopEdge(
            petFrame: petFrame,
            desktopFrame: edgeFrame,
            allowedEdges: allowedEdges
        )
        guard let edge else {
            return false
        }

        let placement = EdgePlacement(
            edge: edge,
            edgeFrame: edgeFrame,
            revealFrame: revealFrame,
            tailFrame: tailWindowFrame(
                edge: edge,
                petFrame: petFrame,
                desktopFrame: edgeFrame
            )
        )
        hiddenWorkTokens = currentWorkTokens
        edgePlacement = placement
        edgeTransition = .hiding
        revealAfterHiding = false
        successEffectStarted = nil
        switchVisual("edge_reveal", once: true)

        guard let movingPetFrame = screenBounds(for: familyBodyBounds()) else {
            edgePlacement = nil
            edgeTransition = nil
            return false
        }
        let delta = offscreenDelta(
            edge: edge,
            petFrame: movingPetFrame,
            desktopFrame: edgeFrame
        )
        let target = NSPoint(
            x: window.frame.origin.x + delta.x,
            y: window.frame.origin.y + delta.y
        )
        guard startEdgeMotion(to: target, completion: { [weak self] in
            guard
                let self,
                self.edgeTransition == .hiding,
                self.edgePlacement?.edge == placement.edge
            else {
                return
            }
            self.edgeTransition = nil
            if self.revealAfterHiding {
                self.revealAfterHiding = false
                _ = self.beginEdgeReveal(playRevealAnimation: false)
                return
            }
            self.window?.orderOut(nil)
            self.updateFamilyTailFrame()
            self.tailView?.needsDisplay = true
            self.tailWindow?.orderFrontRegardless()
            self.writeHeartbeat(force: true)
        }) else {
            edgePlacement = nil
            edgeTransition = nil
            return false
        }
        return true
    }

    private func previewEdgeHide(_ edge: DesktopEdge) {
        guard
            canHideAtDesktopEdge,
            let screen = NSScreen.main,
            let window,
            let petFrame = screenBounds(for: currentPetLocalBounds())
        else {
            return
        }
        let frame = screen.frame
        var delta = NSPoint.zero
        switch edge {
        case .left:
            delta.x = frame.minX - petFrame.minX
            delta.y = frame.midY - petFrame.midY
        case .right:
            delta.x = frame.maxX - petFrame.maxX
            delta.y = frame.midY - petFrame.midY
        case .bottom:
            delta.x = frame.midX - petFrame.midX
            delta.y = frame.minY - petFrame.minY
        case .top:
            delta.x = frame.midX - petFrame.midX
            delta.y = frame.maxY - petFrame.maxY
        }
        window.setFrameOrigin(NSPoint(
            x: window.frame.origin.x + delta.x,
            y: window.frame.origin.y + delta.y
        ))
        _ = beginEdgeHideIfNeeded(
            forcedEdge: edge,
            forcedScreen: screen
        )
    }

    @discardableResult
    private func beginEdgeReveal(playRevealAnimation: Bool) -> Bool {
        guard let placement = edgePlacement else {
            return false
        }
        if edgeTransition == .hiding {
            revealAfterHiding = true
            return true
        }
        if edgeTransition == .revealing {
            return false
        }
        guard let window else {
            return false
        }

        familyRevealStarted = ProcessInfo.processInfo.systemUptime
        edgeTransition = .revealing
        revealAfterHiding = false
        tailWindow?.orderOut(nil)
        if playRevealAnimation {
            successEffectStarted = nil
            switchVisual("edge_reveal", once: true)
        }
        window.orderFrontRegardless()
        guard let contentFrame = screenBounds(for: revealContentBounds()) else {
            edgePlacement = nil
            edgeTransition = nil
            return false
        }
        let delta = revealedDelta(
            edge: placement.edge,
            contentFrame: contentFrame,
            desktopFrame: placement.revealFrame,
            bottomDrop: 0
        )
        let target = NSPoint(
            x: window.frame.origin.x + delta.x,
            y: window.frame.origin.y + delta.y
        )
        guard startEdgeMotion(to: target, completion: { [weak self] in
            guard let self, self.edgeTransition == .revealing else {
                return
            }
            _ = self.pollBridge(force: true)
            self.settleRevealedWindow(for: placement)
            self.edgePlacement = nil
            self.edgeTransition = nil
            self.revealAfterHiding = false
            self.renderCurrent()
            self.scheduleCurrent()
            self.writeHeartbeat(force: true)
        }) else {
            edgePlacement = nil
            edgeTransition = nil
            return false
        }
        return true
    }

    @discardableResult
    private func revealForActivityIfNeeded() -> Bool {
        guard edgePlacement != nil else { return false }
        let current = currentWorkTokens
        let started = !current.subtracting(hiddenWorkTokens).isEmpty
        hiddenWorkTokens = current
        guard started else { return false }
        return beginEdgeReveal(playRevealAnimation: true)
    }

    private var sleepEntryDuration: TimeInterval {
        Double(manifest?.animations["sleep_entry"]?.frames.reduce(0) { $0 + $1.duration_ms } ?? 6440) / 1000
    }

    private var leisureNow: TimeInterval { ProcessInfo.processInfo.systemUptime }

    private var leisureBlocked: Bool {
        permissionRequest != nil || dragging || edgePlacement != nil || edgeTransition != nil
            || transientKey != nil || activityRequiresVisiblePet
            || families.nodes.values.contains { $0.active && ["thinking", "working", "compacting", "permission"].contains($0.status) }
    }

    private func restartLeisureClock() {
        leisure.reset(now: leisureNow, interval: LeisureRoutine.interval { Double.random(in: 0..<1) },
                      choice: Double.random(in: 0..<1))
    }

    private func interruptLeisure(preserveDeadline: Bool = false) {
        guard leisure.phase != .awake else { return }
        if preserveDeadline || leisure.phase == .snacking { leisure.cancel() }
        else { restartLeisureClock() }
        frameIndex = 0
    }

    private func observeNewTasks() {
        var added = false
        for node in families.nodes.values {
            if leisureTasksInitialized,
               leisureTaskTurns[node.id] != node.turn,
               (!node.turn.isEmpty || node.active) { added = true }
            leisureTaskTurns[node.id] = node.turn
        }
        leisureTasksInitialized = true
        if added {
            let previous = currentKey
            restartLeisureClock()
            if previous != currentKey { frameIndex = 0; scheduleCurrent() }
        }
    }

    private func updateLeisure() {
        guard mode == "responsive" else { return }
        if transientKey == nil, successEffectStarted != nil, threadAnimationPosition?.key != "jump" {
            successEffectStarted = nil
        }
        if leisureBlocked && leisure.phase != .awake {
            interruptLeisure(); scheduleCurrent()
        }
        switch leisure.tick(now: leisureNow, eligible: !leisureBlocked && !mouseDown) {
        case .eat, .sleep: frameIndex = 0; renderCurrent(); scheduleCurrent()
        case .none: break
        }
    }

    private func startRest() {
        // Functional rest remains in responsive mode; it never suppresses Codex.
        guard !leisureBlocked else { return }
        mode = "responsive"; leisure.enter(); frameIndex = 0
        renderCurrent(); scheduleCurrent(); writeHeartbeat(force: true)
    }

    private func sleepClick() {
        let was = leisure.phase
        leisure.click(now: leisureNow, wake: Bool.random())
        if leisure.phase == .waking && was != .waking {
            nudgeFacesRight = false; frameIndex = 0; scheduleCurrent()
        }
        renderCurrent(); writeHeartbeat(force: true)
    }

    private func leisureLayer(_ key: String, elapsed: TimeInterval, loop: Bool = true) -> FrameRecord? {
        guard let animation = manifest?.animations[key], !animation.frames.isEmpty else { return nil }
        let duration = Double(animation.frames.reduce(0) { $0 + $1.duration_ms }) / 1000
        var remaining = loop ? max(0, elapsed).truncatingRemainder(dividingBy: duration) : min(max(0, elapsed), max(0,duration-0.001))
        for frame in animation.frames {
            remaining -= Double(frame.duration_ms) / 1000
            if remaining < 0 { return frame }
        }
        return animation.frames.last
    }

    private func drawSleepLayers(in bounds: NSRect) {
        let elapsed = mode == "sleep_entry" ? leisureNow - sleepPreviewEpoch - sleepEntryDuration : leisureNow - leisure.sleepEpoch
        let tailAge = mode == "responsive" ? leisure.tailEpoch.map { leisureNow - $0 } : nil
        let age = tailAge.flatMap { $0 < 1.44 ? $0 : nil } ?? 0
        for record in [leisureLayer("sleep_tail", elapsed: age, loop: false),
                       leisureLayer("sleep_z", elapsed: elapsed)].compactMap({ $0 }) {
            imageStore?.image(relativePath: record.file)?.draw(in: bounds, from: .zero,
                operation: .sourceOver, fraction: 1, respectFlipped: true,
                hints: [.interpolation: NSImageInterpolation.none])
        }
    }

    private func renderCurrent() {
        petView?.needsDisplay = true
    }

    private func scheduleCurrent() {
        animationTimer?.invalidate()
        guard let frame = currentFrameRecord() else {
            return
        }
        let interval = max(0.02, Double(frame.duration_ms) / 1000)
        let timer = Timer(
            timeInterval: interval,
            repeats: false
        ) { [weak self] _ in
            self?.advance()
        }
        RunLoop.main.add(timer, forMode: .common)
        animationTimer = timer
    }

    private func switchVisual(_ key: String?, once: Bool = false) {
        if key != nil { interruptLeisure() }
        transientKey = key
        transientOnce = once
        frameIndex = 0
        renderCurrent()
        scheduleCurrent()
    }

    private func advance() {
        writeHeartbeat()
        if pollBridge() {
            return
        }
        guard let animation = currentAnimation else {
            return
        }
        if threadAnimationPosition != nil {
            _ = currentFrameRecord();renderCurrent();scheduleCurrent();return
        }
        frameIndex += 1
        if frameIndex >= animation.frames.count, mode == "responsive", transientKey == nil {
            switch leisure.phase {
            case .entering: leisure.settled(now: leisureNow); frameIndex = 0
            case .snacking: leisure.finishSnack(); frameIndex = 0
            case .waking:
                if leisure.finishedWakeLoop() { restartLeisureClock() }
                frameIndex = 0
            default: break
            }
        }
        if frameIndex >= animation.frames.count {
            // The preview is isolated from functional sleep interactions.
            if mode == "sleep_entry" { frameIndex = animation.frames.count - 1 }
            // Polling continues on the held frame so a new prompt wakes it.
            else if mode == "responsive", transientKey == nil,
                permissionRequest == nil, bridgeStatus == "interrupted" {
                frameIndex = animation.frames.count - 1
            } else if (mode == "packing_random" || (mode == "responsive" && bridgeStatus == "compacting")), transientKey == nil {
                selectPackingAnimation()
                frameIndex = 0
            } else if currentKey == "reading", mode == "responsive" {
                // Repeat only the settled reading section, without picking
                // the book up again or jumping through the idle pose.
                frameIndex = animation.loop_start ?? 0
            } else {
                frameIndex = 0
            }
            if transientKey != nil, transientOnce {
                transientKey = nil
                transientOnce = false
                successEffectStarted = nil
            }
        }
        renderCurrent()
        scheduleCurrent()
    }

    private func statusAge() -> TimeInterval {
        if let time = selectedFamilyPayload?["received_at"] as? Double {
            return max(0, Date().timeIntervalSince1970-time)
        }
        guard
            let attributes = try? FileManager.default.attributesOfItem(
                atPath: defaultStatusURL().path
            ),
            let modified = attributes[.modificationDate] as? Date
        else {
            return .infinity
        }
        return max(0, Date().timeIntervalSince(modified))
    }

    private func selectPackingAnimation() {
        let keys = (manifest?.animations.keys.map { $0 } ?? [])
            .filter { $0.hasPrefix("packing_") }
        packingKey = keys.randomElement() ?? "carrot"
        packingCycle += 1
    }

    private func setBridgeStatus(_ status: String) -> Bool {
        let previousKey = currentKey
        if ["thinking", "working", "compacting", "interrupted"].contains(status) { interruptLeisure() }
        if status == "compacting", bridgeStatus != "compacting" { selectPackingAnimation() }
        bridgeStatus = ["thinking", "working", "compacting", "interrupted"].contains(status) ? status : "idle"
        if ["thinking", "working", "compacting", "interrupted"].contains(bridgeStatus), transientKey != nil {
            transientKey = nil
            transientOnce = false
            successEffectStarted = nil
        }
        if mode == "responsive", transientKey == nil, previousKey != currentKey {
            switchVisual(nil)
            return true
        }
        return false
    }

    private func clearPermissionRequest() -> Bool {
        let previousKey = currentKey
        permissionRequest = nil
        permissionRequestID = ""
        permissionButtonDown = nil
        permissionBubbleDown = false
        if previousKey == "question" {
            frameIndex = 0
            renderCurrent()
            scheduleCurrent()
            return true
        }
        return false
    }

    private func permissionRequestExpired(_ request: [String: Any]) -> Bool {
        guard
            let expiresAt = request["expires_at"] as? String,
            let expiry = parseTimestamp(expiresAt)
        else {
            return false
        }
        return Date() >= expiry
    }

    private func syncPermissionRequest(_ payload: [String: Any]) -> Bool {
        let requestID = payload["permission_request_id"] as? String ?? ""
        guard !requestID.isEmpty else {
            return clearPermissionRequest()
        }
        let responseURL = permissionDirectoryURL()
            .appendingPathComponent("\(requestID).response.json")
        if FileManager.default.fileExists(atPath: responseURL.path) {
            return clearPermissionRequest()
        }
        let requestURL = permissionDirectoryURL()
            .appendingPathComponent("\(requestID).request.json")
        guard
            let request = readJSONDictionary(requestURL),
            !permissionRequestExpired(request)
        else {
            return clearPermissionRequest()
        }
        let previousKey = currentKey
        interruptLeisure()
        permissionRequest = request
        permissionRequestID = requestID
        bridgeStatus = "idle"
        transientKey = nil
        transientOnce = false
        successEffectStarted = nil
        if previousKey != currentKey
            || frameIndex >= (currentAnimation?.frames.count ?? 0)
        {
            frameIndex = 0
            renderCurrent()
            scheduleCurrent()
            return true
        }
        renderCurrent()
        return false
    }

    @discardableResult
    private func applyBridgePayload(_ payload: [String: Any]) -> Bool {
        let token = payload["token"] as? String ?? ""
        let status = payload["status"] as? String ?? "idle"
        if token.isEmpty {
            _ = clearPermissionRequest()
            return setBridgeStatus("idle")
        }
        if status == "permission" {
            bridgeToken = token
            if statusAge() <= permissionStaleInterval {
                return syncPermissionRequest(payload)
            }
            _ = clearPermissionRequest()
            return setBridgeStatus("idle")
        }
        if token == bridgeToken {
            if permissionRequest != nil {
                return clearPermissionRequest()
            }
            if ["thinking", "working"].contains(bridgeStatus), ["thinking", "working"].contains(status),
                selectedFamilyPayload == nil, statusAge() > thinkingStaleInterval
            {
                return setBridgeStatus("idle")
            }
            return false
        }
        if families.nodes.isEmpty, ["thinking", "working"].contains(status),
           !["thinking", "working", "compacting"].contains(bridgeStatus) { restartLeisureClock() }
        bridgeToken = token
        _ = clearPermissionRequest()
        if status == "success", statusAge() > 3 { return setBridgeStatus("idle") }
        if status == "success", mode != "responsive" { return setBridgeStatus("idle") }
        if status == "success", families.nodes[selectedAnimationActor] != nil {
            bridgeStatus = "idle";transientKey = nil;transientOnce = false
            if let position = threadAnimationPosition, position.key == "jump" {
                successEffectStarted = leisureNow - position.elapsed
            } else { successEffectStarted = nil }
            renderCurrent();scheduleCurrent();return true
        }
        if status == "success" {
            bridgeStatus = "idle"
            successEffectStarted = ProcessInfo.processInfo.systemUptime
            switchVisual("jump", once: true)
            return true
        }
        if ["interrupted", "compacting"].contains(status) {
            return setBridgeStatus(status)
        }
        if ["thinking", "working"].contains(status), selectedFamilyPayload != nil || statusAge() <= thinkingStaleInterval {
            return setBridgeStatus(status)
        }
        return setBridgeStatus("idle")
    }

    private func pollBridge(force: Bool = false) -> Bool {
        if dragging {
            return false
        }
        let now = ProcessInfo.processInfo.systemUptime
        if !force, now - lastStatusPoll < statusPollInterval {
            return false
        }
        lastStatusPoll = now
        let visualChanged = applyBridgePayload(
            selectedFamilyPayload ?? readJSONDictionary(defaultStatusURL()) ?? [:]
        )
        let startedReveal = revealForActivityIfNeeded()
        return visualChanged || startedReveal
    }

    private func writeHeartbeat(force: Bool = false) {
        let now = ProcessInfo.processInfo.systemUptime
        if !force, now - lastHeartbeat < heartbeatInterval {
            return
        }
        lastHeartbeat = now
        _ = currentFrameRecord()
        var heartbeat: [String: Any] = [
            "app": appDisplayName,
            "pid": ProcessInfo.processInfo.processIdentifier,
            "updated_at": utcTimestamp(),
            "status_path": defaultStatusURL().path,
            "current_key": currentKey,
            "frame_index": frameIndex,
            "packing_cycle": packingCycle,
            "bridge_status": bridgeStatus,
            "nudge_facing": nudgeFacesRight ? "right" : "left",
            "family_tail_count": 1 + min(3, families.children(families.selectedID).count),
            "paused_children": families.children(families.selectedID).filter { families.childIsPaused($0) }.map { $0.id },
            "unread_families": families.roots.filter { $0.unread }.map { $0.id },
            "hidden_work_tokens": Array(hiddenWorkTokens).sorted(),
            "selected_family": families.selectedID,
            "families": families.roots.map { $0.id },
            "children": families.children(families.selectedID).map { $0.id },
            "leisure_phase": leisure.phase.rawValue,
            "sleep_in_seconds": max(0, leisure.deadline - now),
            "snack_in_seconds": leisure.snackTimes.map { max(0,$0-now) },
            "sleep_elapsed": leisure.phase == .sleeping ? now-leisure.sleepEpoch : 0,
            "tail_elapsed": leisure.tailEpoch.map { now-$0 } ?? -1,
            "wake_loops": leisure.wakeLoops,
            "mode": mode,
            "platform": "macOS",
        ]
        if let window {
            let frame = window.frame
            heartbeat["window_rect"] = [
                frame.minX, frame.minY, frame.maxX, frame.maxY,
            ]
            heartbeat["window_visible"] = window.isVisible
        }
        if let placement = edgePlacement {
            heartbeat["presentation"] = edgeTransition == .hiding
                ? "hiding"
                : edgeTransition == .revealing ? "revealing" : "hidden"
            heartbeat["hidden_edge"] = placement.edge.rawValue
        } else {
            heartbeat["presentation"] = "visible"
        }
        heartbeat["tail_visible"] = tailWindow?.isVisible == true
        if let tailWindow {
            let frame = tailWindow.frame
            heartbeat["tail_rect"] = [
                frame.minX, frame.minY, frame.maxX, frame.maxY,
            ]
        }
        try? writeJSONAtomic(heartbeat, to: heartbeatURL())
    }

    func drawCurrentFrame(in bounds: NSRect) {
        guard
            let record = currentFrameRecord(),
            let image = imageStore?.image(relativePath: record.file)
        else {
            return
        }
        NSGraphicsContext.saveGraphicsState()
        if currentKey == "left", nudgeFacesRight {
            let transform = NSAffineTransform()
            transform.translateX(by: 820, yBy: 0)
            transform.scaleX(by: -1, yBy: 1)
            transform.concat()
        }
        image.draw(
            in: bounds,
            from: .zero,
            operation: .sourceOver,
            fraction: 1,
            respectFlipped: true,
            hints: [.interpolation: NSImageInterpolation.none]
        )
        NSGraphicsContext.restoreGraphicsState()
        if currentKey == "sleep_body", mode == "responsive" || mode == "sleep_entry" { drawSleepLayers(in: bounds) }
        if currentKey == "jump", successEffectStarted != nil {
            drawSuccessEffects()
        }
        drawFamilyChildren()
        if permissionRequest != nil {
            drawPermissionBubble()
        }
    }

    private func refreshFamilyState(force: Bool = false) {
        let now = ProcessInfo.processInfo.systemUptime
        if force || now-familyPollAt > 0.20 {
            familyPollAt = now
            let previousFamily = families.selectedID
            families.poll()
            observeNewTasks()
            syncThreadAnimations()
            if families.selectedID != previousFamily {
                focusedChildID = ""; bridgeToken = ""; transientKey = nil
                transientOnce = false; successEffectStarted = nil; frameIndex = 0
            }
            let node = families.nodes[focusedChildID].flatMap { $0.status == "permission" ? $0 : nil } ?? families.selected
            selectedFamilyPayload = node?.payload ?? [:]
            if let node, !node.active,
                families.children(node.id).contains(where: { $0.active && !families.childIsPaused($0) }) {
                selectedFamilyPayload = ["status":"working", "token":"family-children-working-"+node.id,
                    "session_id":node.id,"received_at":Date().timeIntervalSince1970]
            }
            if !dragging, let payload = selectedFamilyPayload { _ = applyBridgePayload(payload) }
            _ = revealForActivityIfNeeded()
            if edgePlacement != nil && edgeTransition == nil { updateFamilyTailFrame() }
        }
        let nodes = families.roots
        familySelector.update(nodes, selected: families.selectedID,
            counts: Dictionary(uniqueKeysWithValues: nodes.map { ($0.id, families.children($0.id).count) }))
        guard let window, edgePlacement == nil, edgeTransition == nil else {
            familySelector.panel.orderOut(nil); return
        }
        // Position is anchored to the first idle pose, not the animated frame.
        // Keep hover coverage separate so feet and extended poses remain usable.
        let idle = manifest?.animations["idle"]?.frames.first?.visible_bounds ?? [334,436,486,570]
        let anchor = NSRect(x:CGFloat(idle[0]),y:CGFloat(idle[1]),
            width:CGFloat(idle[2]-idle[0]),height:CGFloat(idle[3]-idle[1])).insetBy(dx:-8,dy:-8)
        let hover = currentPetLocalBounds().union(anchor).insetBy(dx:-8,dy:-8)
        guard let anchorScreen = screenBounds(for:anchor),
            let headScreen = screenBounds(for:hover) else { return }
        let screen = window.screen?.visibleFrame ?? NSScreen.main!.visibleFrame
        let size = familySelector.panel.frame.size
        let origin = NSPoint(x: min(max(anchorScreen.midX-size.width/2, screen.minX), screen.maxX-size.width),
            y: min(anchorScreen.maxY+8, screen.maxY-size.height))
        familySelector.panel.setFrameOrigin(origin)
        let mouse = NSEvent.mouseLocation
        let corridor = headScreen.union(familySelector.panel.frame)
        if headScreen.contains(mouse) || (familySelector.panel.isVisible && corridor.contains(mouse)) {
            familyHoverUntil = now+0.4; familySelector.panel.orderFrontRegardless()
        } else if now > familyHoverUntil { familySelector.panel.orderOut(nil) }
    }

    private func drawFamilyChildren() {
        let nodes = Array(families.children(families.selectedID).prefix(3))
        let slots = [NSPoint(x: 310, y: 575), NSPoint(x: 410, y: 615), NSPoint(x: 510, y: 575)]
        for (index, node) in nodes.enumerated() {
            let target = slots[index], old = childPositions[node.id] ?? target
            let point = NSPoint(x: old.x+(target.x-old.x)*0.14, y: old.y+(target.y-old.y)*0.14)
            childPositions[node.id] = point
            let key: String
            let revealElapsed = familyRevealStarted.map { ProcessInfo.processInfo.systemUptime-$0 }
            let revealing = revealElapsed.map { $0 < 0.855 } ?? false
            if dragging { key = "left" }
            else if revealing { key = "edge_reveal" }
            else if families.childIsPaused(node) { key = "idle" }
            else if node.completion != nil { key = "jump" }
            else if ["permission", "error"].contains(node.status) { key = "question" }
            else { key = "carrot" }
            guard let animation = manifest?.animations[key], !animation.frames.isEmpty else { continue }
            let elapsed = dragging ? ProcessInfo.processInfo.systemUptime-dragAnimationStarted
                : (revealing ? (revealElapsed ?? 0) : max(0, Date().timeIntervalSince(node.completion ?? node.changed)))
            let duration = Double(animation.frames.reduce(0) { $0+$1.duration_ms })/1000
            let animationElapsed = key == "carrot" ? elapsed * 1.25 : elapsed
            var time = (node.completion != nil || key == "question") ? min(animationElapsed, max(0,duration-0.001)) : animationElapsed.truncatingRemainder(dividingBy: duration)
            var frame = animation.frames.last!
            for f in animation.frames { if time < Double(f.duration_ms)/1000 { frame = f; break }; time -= Double(f.duration_ms)/1000 }
            let opacity = (dragging || revealing || node.completion == nil) ? 1 : min(1, max(0, (duration+0.4-elapsed)/0.4))
            let scale: CGFloat = 0.48
            NSGraphicsContext.saveGraphicsState()
            let squeeze = NSAffineTransform()
            squeeze.translateX(by:point.x,yBy:0); squeeze.scaleX(by:0.85,yBy:1); squeeze.translateX(by:-point.x,yBy:0); squeeze.concat()
            if dragging && Int(elapsed / max(0.02,duration)) % 2 == 1 {
                let mirror = NSAffineTransform(); mirror.translateX(by: point.x*2, yBy: 0)
                mirror.scaleX(by: -1, yBy: 1); mirror.concat()
            }
            imageStore?.image(relativePath: frame.file)?.draw(
                in: NSRect(x: point.x-410*scale, y: point.y-570*scale, width: 640*scale, height: 640*scale),
                from: .zero, operation: .sourceOver, fraction: opacity, respectFlipped: true,
                hints: [.interpolation: NSImageInterpolation.high])
            NSGraphicsContext.restoreGraphicsState()
        }
        let extra = families.children(families.selectedID).count-3
        if extra > 0 { ("+\(extra)" as NSString).draw(at: NSPoint(x: 548, y: 565), withAttributes: [.font: NSFont.boldSystemFont(ofSize: 12), .foregroundColor: NSColor.gray]) }
    }

    private func currentFamilyTailRects() -> [NSRect] {
        guard let p = edgePlacement else { return [] }
        return familyTailRects(edge:p.edge,main:p.tailFrame,desktop:p.edgeFrame,
            children:families.children(families.selectedID).count)
    }

    private func updateFamilyTailFrame() {
        let rects = currentFamilyTailRects()
        guard let first = rects.first else { return }
        let frame = rects.dropFirst().reduce(first) { $0.union($1) }
        tailWindow?.setFrame(frame, display:true)
        tailView?.frame = NSRect(origin:.zero,size:frame.size)
        tailView?.needsDisplay = true
    }

    func drawEdgeTail(in bounds: NSRect) {
        guard let p = edgePlacement, let panel = tailWindow,
            let image = imageStore?.image(relativePath:"edge-tail/\(p.edge.rawValue).png") else { return }
        // Explicit clipping also keeps off-screen snapshot/render paths faithful.
        let visible = panel.frame.intersection(p.edgeFrame)
        NSGraphicsContext.saveGraphicsState()
        NSBezierPath(rect:NSRect(x:visible.minX-panel.frame.minX,y:panel.frame.maxY-visible.maxY,
            width:visible.width,height:visible.height)).addClip()
        for rect in currentFamilyTailRects() {
            image.draw(in:NSRect(x:rect.minX-panel.frame.minX,y:panel.frame.maxY-rect.maxY,
                width:rect.width,height:rect.height),from:.zero,operation:.sourceOver,
                fraction:1,respectFlipped:true,hints:[.interpolation:NSImageInterpolation.high])
        }
        NSGraphicsContext.restoreGraphicsState()
    }

    func handleTailClick() {
        _ = beginEdgeReveal(playRevealAnimation: true)
    }

    private func drawImage(
        _ relativePath: String,
        centeredAt center: NSPoint,
        width: CGFloat,
        opacity: CGFloat
    ) {
        guard
            width > 0,
            opacity > 0,
            let image = imageStore?.image(relativePath: relativePath)
        else {
            return
        }
        let ratio = image.size.height / max(1, image.size.width)
        let size = NSSize(width: width, height: width * ratio)
        let rect = NSRect(
            x: center.x - size.width / 2,
            y: center.y - size.height / 2,
            width: size.width,
            height: size.height
        )
        image.draw(
            in: rect,
            from: .zero,
            operation: .sourceOver,
            fraction: opacity,
            respectFlipped: true,
            hints: [.interpolation: NSImageInterpolation.high]
        )
    }

    private func drawSuccessEffects() {
        guard let started = successEffectStarted else {
            return
        }
        let elapsed = ProcessInfo.processInfo.systemUptime - started
        guard elapsed >= 0, elapsed <= successEffectDuration else {
            return
        }
        let progress = elapsed / successEffectDuration
        let fade = min(1, progress / 0.18)
            * min(1, (1 - progress) / 0.28)
        let dx: CGFloat = 182
        let dy: CGFloat = 180
        let fireworkSize = 34 + 28 * min(1, progress / 0.42)
        drawImage(
            "effects/firework.png",
            centeredAt: NSPoint(x: 300 + dx, y: 282 + dy),
            width: fireworkSize,
            opacity: fade * 0.82
        )

        let sparkles: [(CGFloat, CGFloat, CGFloat, Double)] = [
            (154 + dx, 266 + dy, 19, 0),
            (279 + dx, 235 + dy, 15, 0.13),
            (184 + dx, 224 + dy, 12, 0.26),
        ]
        for (x, y, baseSize, phase) in sparkles {
            let local = (progress - phase) / max(0.01, 1 - phase)
            guard local >= 0, local <= 1 else {
                continue
            }
            let pulse = sin(Double.pi * local)
            drawImage(
                "effects/sparkle.png",
                centeredAt: NSPoint(x: x, y: y),
                width: baseSize * (0.6 + 0.55 * pulse),
                opacity: fade * pulse
            )
        }
    }

    private func drawPermissionBubble() {
        guard let request = permissionRequest else {
            return
        }
        let rect = permissionBubbleRect
        let fill = NSColor(calibratedRed: 0.99, green: 0.975, blue: 0.955, alpha: 1)
        let ink = NSColor(calibratedRed: 0.27, green: 0.23, blue: 0.23, alpha: 1)
        let rose = NSColor(calibratedRed: 0.66, green: 0.39, blue: 0.43, alpha: 1)
        // A single closed contour keeps the speech tail's border continuous.
        let bubble = NSBezierPath()
        let radius: CGFloat = 20
        let control: CGFloat = radius * 0.55228475
        bubble.move(to: NSPoint(x: rect.minX + radius, y: rect.minY))
        bubble.line(to: NSPoint(x: rect.maxX - radius, y: rect.minY))
        bubble.curve(to: NSPoint(x: rect.maxX, y: rect.minY + radius), controlPoint1: NSPoint(x: rect.maxX - radius + control, y: rect.minY), controlPoint2: NSPoint(x: rect.maxX, y: rect.minY + radius - control))
        bubble.line(to: NSPoint(x: rect.maxX, y: rect.maxY - radius))
        bubble.curve(to: NSPoint(x: rect.maxX - radius, y: rect.maxY), controlPoint1: NSPoint(x: rect.maxX, y: rect.maxY - radius + control), controlPoint2: NSPoint(x: rect.maxX - radius + control, y: rect.maxY))
        bubble.line(to: NSPoint(x: 418, y: rect.maxY))
        bubble.curve(to: NSPoint(x: 410, y: rect.maxY + 10), controlPoint1: NSPoint(x: 415, y: rect.maxY + 4), controlPoint2: NSPoint(x: 412, y: rect.maxY + 10))
        bubble.curve(to: NSPoint(x: 402, y: rect.maxY), controlPoint1: NSPoint(x: 408, y: rect.maxY + 10), controlPoint2: NSPoint(x: 405, y: rect.maxY + 4))
        bubble.line(to: NSPoint(x: rect.minX + radius, y: rect.maxY))
        bubble.curve(to: NSPoint(x: rect.minX, y: rect.maxY - radius), controlPoint1: NSPoint(x: rect.minX + radius - control, y: rect.maxY), controlPoint2: NSPoint(x: rect.minX, y: rect.maxY - radius + control))
        bubble.line(to: NSPoint(x: rect.minX, y: rect.minY + radius))
        bubble.curve(to: NSPoint(x: rect.minX + radius, y: rect.minY), controlPoint1: NSPoint(x: rect.minX, y: rect.minY + radius - control), controlPoint2: NSPoint(x: rect.minX + radius - control, y: rect.minY))
        bubble.close()
        NSGraphicsContext.saveGraphicsState()
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.18)
        shadow.shadowBlurRadius = 16
        shadow.shadowOffset = NSSize(width: 0, height: -4)
        shadow.set()
        fill.setFill()
        bubble.fill()
        NSGraphicsContext.restoreGraphicsState()
        // The gradient and shadow follow the same complete silhouette.
        NSGraphicsContext.saveGraphicsState()
        bubble.addClip()
        let gradient = NSGradient(starting: fill, ending: NSColor(
            calibratedRed: 0.985, green: 0.90, blue: 0.92, alpha: 1
        ))!
        gradient.draw(
            from: NSPoint(x: rect.minX, y: rect.minY),
            to: NSPoint(x: rect.maxX, y: rect.maxY + 10),
            options: [.drawsBeforeStartingLocation, .drawsAfterEndingLocation]
        )
        NSGraphicsContext.restoreGraphicsState()
        NSColor(calibratedRed: 0.88, green: 0.59, blue: 0.67, alpha: 0.92).setStroke()
        bubble.lineWidth = 2
        bubble.stroke()

        let titleFont = NSFont.systemFont(ofSize: 11, weight: .medium)
        let titleOrigin = NSPoint(x: rect.minX + 34, y: rect.minY + 17)
        // Align the dot optically to the capital letters, rather than the line box.
        let titleCapCenter = titleOrigin.y + titleFont.ascender - titleFont.capHeight / 2
        rose.setFill()
        NSBezierPath(ovalIn: NSRect(x: rect.minX + 20, y: titleCapCenter - 3, width: 6, height: 6)).fill()
        ("CODEX · 需要你的确认" as NSString).draw(
            at: titleOrigin,
            withAttributes: [.font: titleFont, .foregroundColor: rose]
        )
        let summary = request["summary"] as? String ?? "Codex 正在请求权限"
        let bodyRect = NSRect(x: rect.minX + 20, y: rect.minY + 43, width: permissionBodyWidth, height: permissionTextHeight)
        NSGraphicsContext.saveGraphicsState()
        NSBezierPath(rect: bodyRect).addClip()
        permissionBodyText(summary).draw(with: bodyRect, options: [.usesLineFragmentOrigin, .usesFontLeading, .truncatesLastVisibleLine], context: nil)
        NSGraphicsContext.restoreGraphicsState()

        for (action, buttonRect) in permissionButtons {
            let pressed = permissionButtonDown == action
            let adjusted = buttonRect.offsetBy(dx: 0, dy: pressed ? 1 : 0)
            let isAllow = action == "allow"
            (isAllow ? rose : NSColor(calibratedRed: 0.94, green: 0.91, blue: 0.88, alpha: 1)).setFill()
            NSBezierPath(roundedRect: adjusted, xRadius: 10, yRadius: 10).fill()
            let label = isAllow ? "允许一次" : "拒绝"
            let attributes: [NSAttributedString.Key: Any] = [
                .font: NSFont.systemFont(ofSize: 13, weight: .medium),
                .foregroundColor: isAllow ? NSColor.white : ink,
            ]
            let size = (label as NSString).size(withAttributes: attributes)
            (label as NSString).draw(at: NSPoint(x: adjusted.midX - size.width / 2, y: adjusted.midY - size.height / 2), withAttributes: attributes)
        }
    }

    func handleMouseDown(point: NSPoint) {
        for node in families.children(families.selectedID).prefix(3) {
            if let center = childPositions[node.id], NSRect(x: center.x-45, y: center.y-70, width: 90, height: 76).contains(point), node.status == "permission" {
                focusedChildID = node.id; bridgeToken = ""; refreshFamilyState(force: true); return
            }
        }
        guard edgePlacement == nil, edgeTransition == nil else {
            return
        }
        if permissionRequest != nil {
            if let action = permissionButtons.first(where: {
                $0.value.contains(point)
            })?.key {
                permissionButtonDown = action
                permissionBubbleDown = true
                renderCurrent()
                return
            }
            if permissionBubbleRect.contains(point) {
                permissionBubbleDown = true
                return
            }
        }
        guard let window else {
            return
        }
        mouseDown = true
        dragging = false
        dragStartCursor = NSEvent.mouseLocation
        nudgeLastCursor = dragStartCursor
        dragStartWindowOrigin = window.frame.origin
        dragPrevious = VisualSnapshot(
            transientKey: transientKey,
            transientOnce: transientOnce,
            frameIndex: frameIndex,
            successEffectStarted: successEffectStarted
        )
        dragCanPlayFlat = mode == "responsive"
            && transientKey == nil
            && !["thinking", "working", "compacting", "interrupted"].contains(bridgeStatus)
    }

    private func updateNudgeDirection(_ cursor: NSPoint) {
        guard let previous = nudgeLastCursor else { nudgeLastCursor = cursor; return }
        let dx = cursor.x - previous.x
        // Accumulate small movements; vertical movement preserves the last facing.
        if abs(dx) >= 2 {
            nudgeFacesRight = dx > 0
            nudgeLastCursor = cursor
            if currentKey == "left" { renderCurrent() }
        }
    }

    func handleMouseDragged() {
        if permissionButtonDown != nil {
            renderCurrent()
            return
        }
        if permissionBubbleDown {
            return
        }
        guard
            mouseDown,
            let startCursor = dragStartCursor,
            let startOrigin = dragStartWindowOrigin,
            let window
        else {
            return
        }
        let cursor = NSEvent.mouseLocation
        updateNudgeDirection(cursor)
        let deltaX = cursor.x - startCursor.x
        let deltaY = cursor.y - startCursor.y
        if !dragging {
            guard
                abs(deltaX) >= dragThreshold || abs(deltaY) >= dragThreshold
            else {
                return
            }
            dragAnimationStarted = ProcessInfo.processInfo.systemUptime
            dragging = true
            if leisure.phase != .awake {
                // Dragging during the sleep-entry gesture only defers it;
                // it is not a new task and must not draw another idle interval.
                interruptLeisure(preserveDeadline: leisure.phase == .entering)
                dragPrevious = VisualSnapshot(transientKey: nil, transientOnce: false, frameIndex: 0, successEffectStarted: nil)
            }
            successEffectStarted = nil
            switchVisual("left")
        }
        window.setFrameOrigin(
            NSPoint(x: startOrigin.x + deltaX, y: startOrigin.y + deltaY)
        )
        if beginEdgeHideIfNeeded() {
            mouseDown = false; dragging = false
            dragStartCursor = nil; dragStartWindowOrigin = nil; dragPrevious = nil
        }
    }

    func handleMouseUp(point: NSPoint) {
        if permissionButtonDown != nil || permissionBubbleDown {
            let action = permissionButtonDown
            permissionButtonDown = nil
            permissionBubbleDown = false
            if let action, permissionButtons[action]?.contains(point) == true {
                writePermissionDecision(action)
            } else {
                renderCurrent()
            }
            return
        }
        guard mouseDown else {
            return
        }
        let wasDragging = dragging
        let previous = dragPrevious
        let canPlayFlat = dragCanPlayFlat
        mouseDown = false
        dragging = false
        dragStartCursor = nil
        dragStartWindowOrigin = nil
        dragPrevious = nil
        dragCanPlayFlat = false
        if wasDragging, let previous {
            transientKey = previous.transientKey
            transientOnce = previous.transientOnce
            frameIndex = previous.frameIndex
            successEffectStarted = previous.successEffectStarted
            _ = pollBridge(force: true)
            renderCurrent()
            scheduleCurrent()
            _ = beginEdgeHideIfNeeded()
            // Keep the original deadline while dragging; release immediately
            // starts a due sleep entry unless higher-priority work still owns it.
            updateLeisure()
        } else if mode == "responsive", leisure.phase == .entering || leisure.phase == .sleeping {
            sleepClick()
        } else if canPlayFlat && !activityRequiresVisiblePet && permissionRequest == nil {
            switchVisual("flat", once: true)
        }
    }

    private func writePermissionDecision(_ decision: String) {
        guard
            !permissionRequestID.isEmpty,
            decision == "allow" || decision == "deny"
        else {
            return
        }
        var response: [String: Any] = [
            "request_id": permissionRequestID,
            "decision": decision,
            "updated_at": utcTimestamp(),
            "source": "pig-pet",
        ]
        if decision == "deny" {
            response["message"] = "已在猪猪桌宠中拒绝该权限请求。"
        }
        let responseURL = permissionDirectoryURL()
            .appendingPathComponent("\(permissionRequestID).response.json")
        guard (try? writeJSONAtomic(response, to: responseURL)) != nil else {
            return
        }
        _ = clearPermissionRequest()
    }

    func showContextMenu(at point: NSPoint, in view: NSView) {
        let menu = NSMenu(title: appDisplayName)
        menu.autoenablesItems = false
        let entries: [(String, String)] = [
            ("状态互动（Codex）", "responsive"),
            ("休息模式", "rest"),
        ]
        for (label, modeValue) in entries {
            let item = NSMenuItem(
                title: label,
                action: #selector(selectMode(_:)),
                keyEquivalent: ""
            )
            item.target = self
            item.representedObject = modeValue
            item.state = modeValue == "rest" ? ((leisure.phase == .entering || leisure.phase == .sleeping) && mode == "responsive" ? .on : .off) : (mode == modeValue ? .on : .off)
            if modeValue == "rest" { item.isEnabled = !leisureBlocked }
            menu.addItem(item)
        }
        menu.addItem(.separator())
        let autostart = NSMenuItem(
            title: isAutostartEnabled() ? "关闭开机自启动" : "开启开机自启动",
            action: #selector(toggleAutostart(_:)),
            keyEquivalent: ""
        )
        autostart.target = self
        menu.addItem(autostart)
        let hookHelp = NSMenuItem(
            title: "Codex Hook 首次授权说明…",
            action: #selector(showCodexHookHelp(_:)),
            keyEquivalent: ""
        )
        hookHelp.target = self
        menu.addItem(hookHelp)
        menu.addItem(.separator())
        let quit = NSMenuItem(
            title: "退出猪猪桌宠",
            action: #selector(quitApplication(_:)),
            keyEquivalent: ""
        )
        quit.target = self
        menu.addItem(quit)
        menu.popUp(positioning: nil, at: point, in: view)
        restorePetWindowAfterMenuDismissal()
    }

    private func restorePetWindowAfterMenuDismissal() {
        guard !isQuitting, let window else {
            return
        }
        if edgePlacement != nil, edgeTransition == nil {
            window.orderOut(nil)
            tailWindow?.orderFrontRegardless()
            tailView?.needsDisplay = true
            writeHeartbeat(force: true)
            return
        }
        window.orderFrontRegardless()
        renderCurrent()
        scheduleCurrent()
        writeHeartbeat(force: true)
    }

    @objc private func selectMode(_ sender: NSMenuItem) {
        guard let selected = sender.representedObject as? String else {
            return
        }
        if selected == "rest" { startRest(); return }
        restartLeisureClock()
        mode = selected
        if selected == "sleep_entry" { sleepPreviewEpoch = leisureNow }
        if selected == "packing_random" { selectPackingAnimation() }
        transientKey = nil
        transientOnce = false
        successEffectStarted = nil
        frameIndex = 0
        _ = pollBridge(force: true)
        _ = beginEdgeReveal(playRevealAnimation: false)
        renderCurrent()
        scheduleCurrent()
    }

    @objc private func toggleAutostart(_ sender: NSMenuItem) {
        do {
            try setAutostart(!isAutostartEnabled())
        } catch {
            let alert = NSAlert()
            alert.alertStyle = .warning
            alert.messageText = "无法修改开机自启动"
            alert.informativeText = error.localizedDescription
            alert.runModal()
        }
    }

    @objc private func showCodexHookHelp(_ sender: NSMenuItem) {
        let alert = NSAlert()
        alert.alertStyle = .informational
        alert.messageText = "Codex Hook 首次需要手动信任"
        alert.informativeText = """
        打开“终端”，运行 codex；进入后输入 /hooks，选择 “Trust all and continue”。
        完成后退出终端版 Codex，并重启 Codex 桌面版。只重启而不信任，Hook 不会运行。
        """
        alert.runModal()
    }

    @objc private func quitApplication(_ sender: NSMenuItem) {
        isQuitting = true
        NSApp.terminate(nil)
    }
}

func runManifestSelfTest() throws {
    guard
        edgeMotionEasedProgress(0) == 0,
        abs(edgeMotionEasedProgress(0.5) - 0.5) < 0.0001,
        edgeMotionEasedProgress(1) == 1
    else {
        throw NSError(
            domain: appBundleIdentifier,
            code: 29,
            userInfo: [
                NSLocalizedDescriptionKey:
                    "Edge motion easing test failed."
            ]
        )
    }

    let desktopFixture = NSRect(x: 0, y: 0, width: 1000, height: 800)
    let safeFixture = NSRect(x: 0, y: 80, width: 1000, height: 680)
    guard
        touchedDesktopEdge(
            petFrame: NSRect(x: 300, y: 300, width: 150, height: 120),
            desktopFrame: desktopFixture
        ) == nil,
        canEnterEdgeHide(
            mode: "responsive",
            bridgeStatus: "idle",
            hasPermissionRequest: false,
            hasTransientAnimation: false
        ),
        canEnterEdgeHide(
            mode: "responsive",
            bridgeStatus: "thinking",
            hasPermissionRequest: false,
            hasTransientAnimation: false
        ),
        canEnterEdgeHide(
            mode: "responsive",
            bridgeStatus: "idle",
            hasPermissionRequest: true,
            hasTransientAnimation: false
        )
    else {
        throw NSError(
            domain: appBundleIdentifier,
            code: 25,
            userInfo: [
                NSLocalizedDescriptionKey: "Desktop edge contact test failed."
            ]
        )
    }

    let edgeFixtures: [(DesktopEdge, NSRect)] = [
        (.left, NSRect(x: -2, y: 300, width: 150, height: 120)),
        (.right, NSRect(x: 852, y: 300, width: 150, height: 120)),
        (.bottom, NSRect(x: 400, y: -2, width: 150, height: 120)),
        (.top, NSRect(x: 400, y: 682, width: 150, height: 120)),
    ]
    for (edge, contactFrame) in edgeFixtures {
        let hideDelta = offscreenDelta(
            edge: edge,
            petFrame: contactFrame,
            desktopFrame: desktopFixture
        )
        let hiddenFrame = contactFrame.offsetBy(
            dx: hideDelta.x,
            dy: hideDelta.y
        )
        let bottomDrop = edge == .bottom
            ? contactFrame.height
                * EdgeHidePolicy.bottomRevealDropHeightMultiplier
            : 0
        let revealDelta = revealedDelta(
            edge: edge,
            contentFrame: hiddenFrame,
            desktopFrame: safeFixture,
            bottomDrop: bottomDrop
        )
        let revealedFrame = hiddenFrame.offsetBy(
            dx: revealDelta.x,
            dy: revealDelta.y
        )
        let tailFixture = tailWindowFrame(
            edge: edge,
            petFrame: contactFrame,
            desktopFrame: desktopFixture
        )
        let hiddenCorrectly: Bool
        let revealedCorrectly: Bool
        let revealedContainmentCorrectly: Bool
        let tailAnchored: Bool
        switch edge {
        case .left:
            hiddenCorrectly = hiddenFrame.maxX
                <= desktopFixture.minX - EdgeHidePolicy.offscreenPadding
            revealedCorrectly = abs(
                revealedFrame.minX
                    - safeFixture.minX
                    - EdgeHidePolicy.revealClearance
            ) < 0.01
            revealedContainmentCorrectly = safeFixture.insetBy(
                dx: EdgeHidePolicy.revealClearance,
                dy: EdgeHidePolicy.revealClearance
            ).contains(revealedFrame)
            tailAnchored = tailFixture.minX
                == desktopFixture.minX - EdgeHidePolicy.tailScreenOverlap
        case .right:
            hiddenCorrectly = hiddenFrame.minX
                >= desktopFixture.maxX + EdgeHidePolicy.offscreenPadding
            revealedCorrectly = abs(
                safeFixture.maxX
                    - revealedFrame.maxX
                    - EdgeHidePolicy.revealClearance
            ) < 0.01
            revealedContainmentCorrectly = safeFixture.insetBy(
                dx: EdgeHidePolicy.revealClearance,
                dy: EdgeHidePolicy.revealClearance
            ).contains(revealedFrame)
            tailAnchored = tailFixture.maxX
                == desktopFixture.maxX + EdgeHidePolicy.tailScreenOverlap
        case .bottom:
            hiddenCorrectly = hiddenFrame.maxY
                <= desktopFixture.minY - EdgeHidePolicy.offscreenPadding
            revealedCorrectly = abs(
                revealedFrame.maxY
                    - safeFixture.minY
                    - EdgeHidePolicy.revealClearance
            ) < 0.01
            revealedContainmentCorrectly = desktopFixture.intersects(
                revealedFrame
            )
            tailAnchored = tailFixture.minY
                == desktopFixture.minY - EdgeHidePolicy.tailScreenOverlap
        case .top:
            hiddenCorrectly = hiddenFrame.minY
                >= desktopFixture.maxY + EdgeHidePolicy.offscreenPadding
            revealedCorrectly = abs(
                safeFixture.maxY
                    - revealedFrame.maxY
                    - EdgeHidePolicy.revealClearance
            ) < 0.01
            revealedContainmentCorrectly = safeFixture.insetBy(
                dx: EdgeHidePolicy.revealClearance,
                dy: EdgeHidePolicy.revealClearance
            ).contains(revealedFrame)
            tailAnchored = tailFixture.maxY
                == desktopFixture.maxY + EdgeHidePolicy.tailScreenOverlap
        }
        guard
            touchedDesktopEdge(
                petFrame: contactFrame,
                desktopFrame: desktopFixture
            ) == edge,
            hiddenCorrectly,
            revealedCorrectly,
            revealedContainmentCorrectly,
            tailAnchored,
            desktopFixture.intersects(tailFixture)
        else {
            throw NSError(
                domain: appBundleIdentifier,
                code: 26,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "Desktop edge placement test failed: \(edge.rawValue)"
                ]
            )
        }
    }

    let permissionFixture = """
    Codex 准备在“/Users/示例用户/Documents/桌宠猪 Window→Mac”中：修改“README-MAC.md”；修改“README.md”；修改“MACOS-PORTING.md”；修改“RELEASE-NOTES-v0.2.3.md”；修改“RELEASE-CHECKLIST.md”；修改“RELEASE-CHECKLIST-MAC.md”，是否允许？
    """
    let permissionHeight = permissionBodyMeasuredHeight(permissionFixture)
    guard permissionHeight >= 18, permissionHeight <= permissionBodyHeight else {
        throw NSError(
            domain: appBundleIdentifier,
            code: 24,
            userInfo: [
                NSLocalizedDescriptionKey:
                    "Permission text did not wrap into the available bubble height."
            ]
        )
    }

    guard let resources = Bundle.main.resourceURL else {
        throw NSError(domain: appBundleIdentifier, code: 20)
    }
    let data = try Data(
        contentsOf: resources.appendingPathComponent(
            "animation-manifest.json"
        )
    )
    let manifest = try JSONDecoder().decode(AnimationManifest.self, from: data)
    let expected: Set<String> = [
        "idle", "left", "carrot", "jump", "flat", "question",
        "edge_reveal",
    ]
    guard
        manifest.format_version == 1,
        manifest.window_size == 640,
        Set(manifest.animations.keys).filter({ !$0.hasPrefix("packing_") }).subtracting(["reading", "sleep_entry", "sleep_body", "sleep_z", "sleep_tail", "snack"]) == expected,
        manifest.animations["idle"]?.frames.count == 49,
        [8, 15, 30, 37, 47].contains(manifest.animations["left"]?.frames.count ?? 0),
        manifest.animations["carrot"]?.frames.count == 19,
        manifest.animations["jump"]?.frames.count == 61,
        manifest.animations["flat"]?.frames.count == 96,
        manifest.animations["question"]?.frames.count == 25,
        manifest.animations["edge_reveal"]?.frames.count == 19
    else {
        throw NSError(
            domain: appBundleIdentifier,
            code: 21,
            userInfo: [NSLocalizedDescriptionKey: "Animation parity test failed."]
        )
    }
    for animation in manifest.animations.values {
        for frame in animation.frames {
            let url = resources.appendingPathComponent(frame.file)
            guard
                frame.duration_ms >= 20,
                frame.visible_bounds?.count == 4,
                (frame.visible_bounds?[0] ?? -1) >= 0,
                (frame.visible_bounds?[1] ?? -1) >= 0,
                (frame.visible_bounds?[2] ?? 641) <= 640,
                (frame.visible_bounds?[3] ?? 641) <= 640,
                FileManager.default.fileExists(atPath: url.path),
                NSImage(contentsOf: url) != nil
            else {
                throw NSError(
                    domain: appBundleIdentifier,
                    code: 22,
                    userInfo: [
                        NSLocalizedDescriptionKey: "Frame validation failed: \(frame.file)"
                    ]
                )
            }
        }
    }
    let edgeRevealGIF = resources.appendingPathComponent(
        "animations/edge-reveal.gif"
    )
    let edgeRevealHeader = (try? Data(contentsOf: edgeRevealGIF).prefix(6))
        .flatMap { String(data: $0, encoding: .ascii) }
    guard edgeRevealHeader?.hasPrefix("GIF") == true else {
        throw NSError(
            domain: appBundleIdentifier,
            code: 28,
            userInfo: [
                NSLocalizedDescriptionKey: "Edge reveal GIF is missing."
            ]
        )
    }
    guard
        FileManager.default.fileExists(
            atPath: resources.appendingPathComponent(
                "effects/sparkle.png"
            ).path
        ),
        FileManager.default.fileExists(
            atPath: resources.appendingPathComponent(
                "effects/firework.png"
            ).path
        )
    else {
        throw NSError(
            domain: appBundleIdentifier,
            code: 23,
            userInfo: [NSLocalizedDescriptionKey: "Celebration effects are missing."]
        )
    }
    for edge in DesktopEdge.allCases {
        let tailURL = resources.appendingPathComponent(
            "edge-tail/\(edge.rawValue).png"
        )
        guard
            FileManager.default.fileExists(atPath: tailURL.path),
            let image = NSImage(contentsOf: tailURL),
            image.size == NSSize(
                width: EdgeHidePolicy.tailWindowSize,
                height: EdgeHidePolicy.tailWindowSize
            )
        else {
            throw NSError(
                domain: appBundleIdentifier,
                code: 27,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "Edge tail validation failed: \(edge.rawValue)"
                ]
            )
        }
    }
    print("macos_manifest_test=ok")
}

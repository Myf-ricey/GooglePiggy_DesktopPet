import AppKit
import Foundation

private let windowSize: CGFloat = 640
private let statusPollInterval: TimeInterval = 0.25
private let thinkingStaleInterval: TimeInterval = 45
private let permissionStaleInterval: TimeInterval = 620
private let heartbeatInterval: TimeInterval = 1
private let successEffectDuration: TimeInterval = 1.35
private let dragThreshold: CGFloat = 4
private let permissionBodyWidth: CGFloat = 260
private let permissionBodyHeight: CGFloat = 150
private enum EdgeTransition: Equatable {
    case hiding
    case revealing
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
    paragraph.maximumLineHeight = 20
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
    private var isQuitting = false
    private let startupEdgePreview: DesktopEdge?

    private var mode = "responsive"
    private var frameIndex = 0
    private var transientKey: String?
    private var transientOnce = false
    private var successEffectStarted: TimeInterval?

    private var bridgeToken = ""
    private var bridgeStatus = "idle"
    private var lastStatusPoll: TimeInterval = 0
    private var lastHeartbeat: TimeInterval = 0

    private var permissionRequest: [String: Any]?
    private var permissionRequestID = ""
    private var permissionButtonDown: String?
    private var permissionBubbleDown = false

    private var mouseDown = false
    private var dragging = false
    private var dragStartCursor: NSPoint?
    private var dragStartWindowOrigin: NSPoint?
    private var dragPrevious: VisualSnapshot?
    private var dragCanPlayFlat = false

    private var edgePlacement: EdgePlacement?
    private var edgeTransition: EdgeTransition?
    private var revealAfterHiding = false

    private var currentKey: String {
        if permissionRequest != nil {
            return "question"
        }
        if let transientKey {
            return transientKey
        }
        if mode == "responsive" {
            return bridgeStatus == "thinking" ? "carrot" : "idle"
        }
        return mode
    }

    private var currentAnimation: AnimationRecord? {
        manifest?.animations[currentKey]
    }

    private var canHideAtDesktopEdge: Bool {
        canEnterEdgeHide(
            mode: mode,
            bridgeStatus: bridgeStatus,
            hasPermissionRequest: permissionRequest != nil,
            hasTransientAnimation: transientKey != nil
        )
            && edgePlacement == nil
            && edgeTransition == nil
    }

    private var activityRequiresVisiblePet: Bool {
        bridgeStatus == "thinking"
            || permissionRequest != nil
            || successEffectStarted != nil
    }

    private var permissionBubbleRect: NSRect {
        NSRect(x: 262, y: 84, width: 296, height: 264)
    }

    private var permissionButtons: [String: NSRect] {
        [
            "allow": NSRect(x: 300, y: 300, width: 92, height: 32),
            "deny": NSRect(x: 428, y: 300, width: 92, height: 32),
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
            createWindow()
            applyBridgePayload(readJSONDictionary(defaultStatusURL()) ?? [:])
            writeHeartbeat(force: true)
            renderCurrent()
            scheduleCurrent()
            if let edge = startupEdgePreview {
                DispatchQueue.main.async { [weak self] in
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
        guard
            decoded.format_version == 1,
            decoded.window_size == Int(windowSize),
            Set(decoded.animations.keys)
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
            x: CGFloat(values[0]),
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
            let contentFrame = screenBounds(for: currentContentLocalBounds())
        else {
            return
        }
        let correction = revealedDelta(
            edge: placement.edge,
            contentFrame: contentFrame,
            desktopFrame: placement.revealFrame,
            bottomDrop: bottomRevealDrop(for: placement.edge)
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

    private func animateWindow(
        to origin: NSPoint,
        completion: @escaping () -> Void
    ) {
        guard let window else {
            completion()
            return
        }
        NSAnimationContext.runAnimationGroup { context in
            context.duration = EdgeHidePolicy.transitionDuration
            context.allowsImplicitAnimation = true
            window.animator().setFrameOrigin(origin)
        } completionHandler: {
            DispatchQueue.main.async(execute: completion)
        }
    }

    @discardableResult
    private func beginEdgeHideIfNeeded(
        forcedEdge: DesktopEdge? = nil,
        forcedScreen: NSScreen? = nil
    ) -> Bool {
        guard
            canHideAtDesktopEdge,
            let window,
            let petFrame = screenBounds(for: currentPetLocalBounds()),
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
        edgePlacement = placement
        edgeTransition = .hiding
        revealAfterHiding = false
        successEffectStarted = nil
        switchVisual("edge_reveal", once: true)

        guard let movingPetFrame = screenBounds(for: currentPetLocalBounds()) else {
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
        animateWindow(to: target) { [weak self] in
            guard
                let self,
                self.edgeTransition == .hiding,
                self.edgePlacement?.edge == placement.edge
            else {
                return
            }
            self.edgeTransition = nil
            if self.revealAfterHiding || self.activityRequiresVisiblePet {
                self.revealAfterHiding = false
                _ = self.beginEdgeReveal(playRevealAnimation: false)
                return
            }
            self.window?.orderOut(nil)
            self.tailWindow?.setFrame(placement.tailFrame, display: true)
            self.tailView?.needsDisplay = true
            self.tailWindow?.orderFrontRegardless()
            self.writeHeartbeat(force: true)
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

        edgeTransition = .revealing
        revealAfterHiding = false
        tailWindow?.orderOut(nil)
        if playRevealAnimation {
            successEffectStarted = nil
            switchVisual("edge_reveal", once: true)
        }
        window.orderFrontRegardless()
        guard let contentFrame = screenBounds(for: currentContentLocalBounds()) else {
            edgePlacement = nil
            edgeTransition = nil
            return false
        }
        let delta = revealedDelta(
            edge: placement.edge,
            contentFrame: contentFrame,
            desktopFrame: placement.revealFrame,
            bottomDrop: bottomRevealDrop(for: placement.edge)
        )
        let target = NSPoint(
            x: window.frame.origin.x + delta.x,
            y: window.frame.origin.y + delta.y
        )
        animateWindow(to: target) { [weak self] in
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
        }
        return true
    }

    @discardableResult
    private func revealForActivityIfNeeded() -> Bool {
        guard edgePlacement != nil, activityRequiresVisiblePet else {
            return false
        }
        return beginEdgeReveal(playRevealAnimation: false)
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
        frameIndex += 1
        if frameIndex >= animation.frames.count {
            frameIndex = 0
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

    private func setBridgeStatus(_ status: String) -> Bool {
        let previousKey = currentKey
        bridgeStatus = status == "thinking" ? "thinking" : "idle"
        if bridgeStatus == "thinking", transientKey == "jump" {
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
            if bridgeStatus == "thinking", status == "thinking",
                statusAge() > thinkingStaleInterval
            {
                return setBridgeStatus("idle")
            }
            return false
        }
        bridgeToken = token
        _ = clearPermissionRequest()
        if status == "success" {
            bridgeStatus = "idle"
            successEffectStarted = ProcessInfo.processInfo.systemUptime
            switchVisual("jump", once: true)
            return true
        }
        if status == "thinking", statusAge() <= thinkingStaleInterval {
            return setBridgeStatus("thinking")
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
            readJSONDictionary(defaultStatusURL()) ?? [:]
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
        var heartbeat: [String: Any] = [
            "app": appDisplayName,
            "pid": ProcessInfo.processInfo.processIdentifier,
            "updated_at": utcTimestamp(),
            "status_path": defaultStatusURL().path,
            "current_key": currentKey,
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
        image.draw(
            in: bounds,
            from: .zero,
            operation: .sourceOver,
            fraction: 1,
            respectFlipped: true,
            hints: [.interpolation: NSImageInterpolation.none]
        )
        if currentKey == "jump", successEffectStarted != nil {
            drawSuccessEffects()
        }
        if permissionRequest != nil {
            drawPermissionBubble()
        }
    }

    func drawEdgeTail(in bounds: NSRect) {
        guard
            let edge = edgePlacement?.edge,
            let image = imageStore?.image(
                relativePath: "edge-tail/\(edge.rawValue).png"
            )
        else {
            return
        }
        image.draw(
            in: bounds,
            from: .zero,
            operation: .sourceOver,
            fraction: 1,
            respectFlipped: true,
            hints: [.interpolation: NSImageInterpolation.high]
        )
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
        let shadowRect = rect.offsetBy(dx: 3, dy: 4)
        NSColor(calibratedWhite: 0, alpha: 0.32).setFill()
        NSBezierPath(roundedRect: shadowRect, xRadius: 18, yRadius: 18).fill()

        let pointerShadow = NSBezierPath()
        pointerShadow.move(to: NSPoint(x: 398, y: rect.maxY + 1))
        pointerShadow.line(to: NSPoint(x: 426, y: rect.maxY + 1))
        pointerShadow.line(to: NSPoint(x: 412, y: rect.maxY + 25))
        pointerShadow.close()
        NSColor(calibratedWhite: 0, alpha: 0.24).setFill()
        pointerShadow.fill()

        let fill = NSColor(
            calibratedRed: 1,
            green: 250 / 255,
            blue: 244 / 255,
            alpha: 0.95
        )
        fill.setFill()
        NSColor(
            calibratedRed: 236 / 255,
            green: 70 / 255,
            blue: 142 / 255,
            alpha: 0.92
        ).setStroke()
        let bubble = NSBezierPath(
            roundedRect: rect,
            xRadius: 18,
            yRadius: 18
        )
        bubble.lineWidth = 3
        bubble.fill()
        bubble.stroke()

        let pointer = NSBezierPath()
        pointer.move(to: NSPoint(x: 396, y: rect.maxY - 2))
        pointer.line(to: NSPoint(x: 424, y: rect.maxY - 2))
        pointer.line(to: NSPoint(x: 410, y: rect.maxY + 22))
        pointer.close()
        fill.setFill()
        pointer.fill()

        let titleAttributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 18, weight: .semibold),
            .foregroundColor: NSColor(
                calibratedRed: 48 / 255,
                green: 40 / 255,
                blue: 42 / 255,
                alpha: 1
            ),
        ]
        ("Codex 请求权限" as NSString).draw(
            at: NSPoint(x: rect.minX + 14, y: rect.minY + 12),
            withAttributes: titleAttributes
        )

        let summary = request["summary"] as? String
            ?? "Codex 正在请求权限"
        permissionBodyText(summary).draw(
            with: NSRect(
                x: rect.minX + 18,
                y: rect.minY + 43,
                width: permissionBodyWidth,
                height: permissionBodyHeight
            ),
            options: [.usesLineFragmentOrigin],
            context: nil
        )

        for (action, buttonRect) in permissionButtons {
            let pressed = permissionButtonDown == action
            let adjusted = buttonRect.offsetBy(dx: 0, dy: pressed ? 1 : 0)
            let isAllow = action == "allow"
            let buttonFill = isAllow
                ? NSColor(
                    calibratedRed: 94 / 255,
                    green: 199 / 255,
                    blue: 123 / 255,
                    alpha: 1
                )
                : NSColor(
                    calibratedRed: 1,
                    green: 237 / 255,
                    blue: 242 / 255,
                    alpha: 1
                )
            let buttonOutline = isAllow
                ? NSColor(
                    calibratedRed: 69 / 255,
                    green: 174 / 255,
                    blue: 99 / 255,
                    alpha: 1
                )
                : NSColor(
                    calibratedRed: 236 / 255,
                    green: 70 / 255,
                    blue: 142 / 255,
                    alpha: 0.9
                )
            buttonFill.setFill()
            buttonOutline.setStroke()
            let path = NSBezierPath(
                roundedRect: adjusted,
                xRadius: 16,
                yRadius: 16
            )
            path.lineWidth = 3
            path.fill()
            path.stroke()

            let label = isAllow ? "允许" : "拒绝"
            let labelColor = isAllow
                ? NSColor.white
                : NSColor(
                    calibratedRed: 198 / 255,
                    green: 47 / 255,
                    blue: 112 / 255,
                    alpha: 1
                )
            let attributes: [NSAttributedString.Key: Any] = [
                .font: NSFont.systemFont(ofSize: 15, weight: .semibold),
                .foregroundColor: labelColor,
            ]
            let size = (label as NSString).size(withAttributes: attributes)
            (label as NSString).draw(
                at: NSPoint(
                    x: adjusted.midX - size.width / 2,
                    y: adjusted.midY - size.height / 2
                ),
                withAttributes: attributes
            )
        }
    }

    func handleMouseDown(point: NSPoint) {
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
        dragStartWindowOrigin = window.frame.origin
        dragPrevious = VisualSnapshot(
            transientKey: transientKey,
            transientOnce: transientOnce,
            frameIndex: frameIndex,
            successEffectStarted: successEffectStarted
        )
        dragCanPlayFlat = mode == "responsive"
            && transientKey == nil
            && bridgeStatus != "thinking"
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
        let deltaX = cursor.x - startCursor.x
        let deltaY = cursor.y - startCursor.y
        if !dragging {
            guard
                abs(deltaX) >= dragThreshold || abs(deltaY) >= dragThreshold
            else {
                return
            }
            dragging = true
            successEffectStarted = nil
            switchVisual("left")
        }
        window.setFrameOrigin(
            NSPoint(x: startOrigin.x + deltaX, y: startOrigin.y + deltaY)
        )
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
        } else if canPlayFlat {
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
        let entries: [(String, String)] = [
            ("状态互动（Codex）", "responsive"),
            ("预览：呼吸待机", "idle"),
            ("预览：左拱", "left"),
            ("预览：猪追胡萝卜", "carrot"),
            ("预览：跳跳猪", "jump"),
            ("预览：躺平", "flat"),
            ("预览：疑问猪", "question"),
        ]
        for (label, modeValue) in entries {
            let item = NSMenuItem(
                title: label,
                action: #selector(selectMode(_:)),
                keyEquivalent: ""
            )
            item.target = self
            item.representedObject = modeValue
            item.state = mode == modeValue ? .on : .off
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
        mode = selected
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
        !canEnterEdgeHide(
            mode: "responsive",
            bridgeStatus: "thinking",
            hasPermissionRequest: false,
            hasTransientAnimation: false
        ),
        !canEnterEdgeHide(
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
        Set(manifest.animations.keys) == expected,
        manifest.animations["idle"]?.frames.count == 49,
        manifest.animations["left"]?.frames.count == 15,
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

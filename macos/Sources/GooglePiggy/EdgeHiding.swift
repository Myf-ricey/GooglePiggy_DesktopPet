import AppKit

/// Platform-neutral values used by the macOS implementation and documented for
/// the future Windows port. Values are logical screen points/pixels after DPI
/// scaling, not raw backing pixels.
enum EdgeHidePolicy {
    static let contactTolerance: CGFloat = 10
    static let revealClearance: CGFloat = 28
    static let offscreenPadding: CGFloat = 16
    static let transitionDuration: TimeInterval = 0.48
    static let tailWindowSize: CGFloat = 68
    /// Leaves about 23 pt of the rounded tail art visible on every edge.
    static let tailScreenOverlap: CGFloat = 30
    /// Bottom reveals finish one current non-transparent pet height lower.
    static let bottomRevealDropHeightMultiplier: CGFloat = 1
}

enum DesktopEdge: String, CaseIterable {
    case left
    case right
    case top
    case bottom
}

/// The shared state gate for entering edge-hidden mode.
func canEnterEdgeHide(
    mode: String,
    bridgeStatus: String,
    hasPermissionRequest: Bool,
    hasTransientAnimation: Bool
) -> Bool {
    mode == "responsive"
        && bridgeStatus == "idle"
        && !hasPermissionRequest
        && !hasTransientAnimation
}

// Windows port contract: all helpers below use screen coordinates with +Y
// upwards. `petFrame` is the non-transparent pixel bounds, never the 640px
// host window. The return values can be passed to the platform window mover.
func touchedDesktopEdge(
    petFrame: NSRect,
    desktopFrame: NSRect,
    allowedEdges: Set<DesktopEdge> = Set(DesktopEdge.allCases),
    tolerance: CGFloat = EdgeHidePolicy.contactTolerance
) -> DesktopEdge? {
    let overlapsVertically = petFrame.maxY >= desktopFrame.minY
        && petFrame.minY <= desktopFrame.maxY
    let overlapsHorizontally = petFrame.maxX >= desktopFrame.minX
        && petFrame.minX <= desktopFrame.maxX
    var candidates: [(DesktopEdge, CGFloat)] = []

    if allowedEdges.contains(.left), overlapsVertically,
        petFrame.minX <= desktopFrame.minX + tolerance
    {
        candidates.append((
            .left,
            max(0, petFrame.maxX - desktopFrame.minX)
        ))
    }
    if allowedEdges.contains(.right), overlapsVertically,
        petFrame.maxX >= desktopFrame.maxX - tolerance
    {
        candidates.append((
            .right,
            max(0, desktopFrame.maxX - petFrame.minX)
        ))
    }
    if allowedEdges.contains(.bottom), overlapsHorizontally,
        petFrame.minY <= desktopFrame.minY + tolerance
    {
        candidates.append((
            .bottom,
            max(0, petFrame.maxY - desktopFrame.minY)
        ))
    }
    if allowedEdges.contains(.top), overlapsHorizontally,
        petFrame.maxY >= desktopFrame.maxY - tolerance
    {
        candidates.append((
            .top,
            max(0, desktopFrame.maxY - petFrame.minY)
        ))
    }
    return candidates.min(by: { $0.1 < $1.1 })?.0
}

func offscreenDelta(
    edge: DesktopEdge,
    petFrame: NSRect,
    desktopFrame: NSRect,
    padding: CGFloat = EdgeHidePolicy.offscreenPadding
) -> NSPoint {
    switch edge {
    case .left:
        return NSPoint(
            x: desktopFrame.minX - petFrame.maxX - padding,
            y: 0
        )
    case .right:
        return NSPoint(
            x: desktopFrame.maxX - petFrame.minX + padding,
            y: 0
        )
    case .bottom:
        return NSPoint(
            x: 0,
            y: desktopFrame.minY - petFrame.maxY - padding
        )
    case .top:
        return NSPoint(
            x: 0,
            y: desktopFrame.maxY - petFrame.minY + padding
        )
    }
}

private func containmentShift(
    itemMin: CGFloat,
    itemMax: CGFloat,
    containerMin: CGFloat,
    containerMax: CGFloat,
    clearance: CGFloat
) -> CGFloat {
    let safeMin = containerMin + clearance
    let safeMax = containerMax - clearance
    if itemMax - itemMin > safeMax - safeMin {
        return (containerMin + containerMax - itemMin - itemMax) / 2
    }
    if itemMin < safeMin {
        return safeMin - itemMin
    }
    if itemMax > safeMax {
        return safeMax - itemMax
    }
    return 0
}

func revealedDelta(
    edge: DesktopEdge,
    contentFrame: NSRect,
    desktopFrame: NSRect,
    clearance: CGFloat = EdgeHidePolicy.revealClearance,
    bottomDrop: CGFloat = 0
) -> NSPoint {
    var delta = NSPoint.zero
    switch edge {
    case .left:
        delta.x = desktopFrame.minX + clearance - contentFrame.minX
    case .right:
        delta.x = desktopFrame.maxX - clearance - contentFrame.maxX
    case .bottom:
        delta.y = desktopFrame.minY
            + clearance
            - max(0, bottomDrop)
            - contentFrame.minY
    case .top:
        delta.y = desktopFrame.maxY - clearance - contentFrame.maxY
    }
    let shifted = contentFrame.offsetBy(dx: delta.x, dy: delta.y)
    switch edge {
    case .left, .right:
        delta.y += containmentShift(
            itemMin: shifted.minY,
            itemMax: shifted.maxY,
            containerMin: desktopFrame.minY,
            containerMax: desktopFrame.maxY,
            clearance: clearance
        )
    case .top, .bottom:
        delta.x += containmentShift(
            itemMin: shifted.minX,
            itemMax: shifted.maxX,
            containerMin: desktopFrame.minX,
            containerMax: desktopFrame.maxX,
            clearance: clearance
        )
    }
    return delta
}

/// Places the tail click target partly beyond the physical display. The overlap
/// makes the rounded rump look inserted into the edge instead of merely tangent
/// to it; Windows can reproduce this with an unclamped layered window.
func tailWindowFrame(
    edge: DesktopEdge,
    petFrame: NSRect,
    desktopFrame: NSRect,
    size: CGFloat = EdgeHidePolicy.tailWindowSize,
    screenOverlap: CGFloat = EdgeHidePolicy.tailScreenOverlap
) -> NSRect {
    let centeredX = min(
        max(petFrame.midX - size / 2, desktopFrame.minX),
        desktopFrame.maxX - size
    )
    let centeredY = min(
        max(petFrame.midY - size / 2, desktopFrame.minY),
        desktopFrame.maxY - size
    )
    switch edge {
    case .left:
        return NSRect(
            x: desktopFrame.minX - screenOverlap,
            y: centeredY,
            width: size,
            height: size
        )
    case .right:
        return NSRect(
            x: desktopFrame.maxX - size + screenOverlap,
            y: centeredY,
            width: size,
            height: size
        )
    case .bottom:
        return NSRect(
            x: centeredX,
            y: desktopFrame.minY - screenOverlap,
            width: size,
            height: size
        )
    case .top:
        return NSRect(
            x: centeredX,
            y: desktopFrame.maxY - size + screenOverlap,
            width: size,
            height: size
        )
    }
}

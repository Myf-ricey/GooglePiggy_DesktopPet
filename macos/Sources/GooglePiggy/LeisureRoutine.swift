import Foundation

/// Uses monotonic time. Polls never reroll the deadline; real new tasks do.
struct LeisureRoutine {
    enum Phase: String { case awake, snacking, entering, sleeping, waking }
    enum Action { case none, eat, sleep }
    private(set) var phase: Phase = .awake
    private(set) var deadline: TimeInterval = 0
    private(set) var began: TimeInterval = 0
    private(set) var snackTimes: [TimeInterval] = []
    private(set) var sleepEpoch: TimeInterval = 0
    private(set) var tailEpoch: TimeInterval?
    private(set) var wakeLoops = 0

    static func interval(random: () -> Double) -> TimeInterval {
        // 2 / Phi^-1(.75) = 2.965 minutes gives P(8..12) approximately .5.
        while true {
            let u = max(1e-12, min(1 - 1e-12, random()))
            let z = sqrt(-2 * log(u)) * cos(2 * .pi * random())
            let minutes = 10 + 2.965 * z
            if minutes >= 3 && minutes <= 30 { return minutes * 60 }
        }
    }
    mutating func reset(now: TimeInterval, interval: TimeInterval, choice: Double) {
        phase = .awake; began = now; deadline = now + interval
        tailEpoch = nil; wakeLoops = 0
        let fractions: [Double] = choice < 0.4 ? [2.0/3] : choice < 0.8 ? [1.0/3] : choice < 0.9 ? [1.0/3, 2.0/3] : []
        snackTimes = fractions.map { now + interval * $0 }
    }
    mutating func tick(now: TimeInterval, eligible: Bool) -> Action {
        guard phase == .awake else { return .none }
        // Never queue a late burst of snacks behind higher-priority work.
        let due = snackTimes.contains { $0 <= now }
        snackTimes.removeAll { $0 <= now }
        guard eligible else { return .none }
        if now >= deadline { enter(); return .sleep }
        if due { phase = .snacking; return .eat }
        return .none
    }
    mutating func enter() { phase = .entering; tailEpoch = nil; snackTimes = [] }
    mutating func settled(now: TimeInterval) { phase = .sleeping; sleepEpoch = now; tailEpoch = nil }
    mutating func finishSnack() { if phase == .snacking { phase = .awake } }
    mutating func cancel() { phase = .awake; tailEpoch = nil; wakeLoops = 0 }
    mutating func click(now: TimeInterval, wake: Bool) {
        guard phase == .entering || phase == .sleeping else { return }
        if wake { phase = .waking; wakeLoops = 0; tailEpoch = nil }
        else if phase == .sleeping, tailEpoch == nil || now - tailEpoch! >= 1.44 { tailEpoch = now }
    }
    mutating func finishedWakeLoop() -> Bool { wakeLoops += 1; return wakeLoops >= 2 }
}

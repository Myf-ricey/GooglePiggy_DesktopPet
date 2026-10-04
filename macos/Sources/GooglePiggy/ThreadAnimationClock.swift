import Foundation

/// Per-thread timelines advance with monotonic time even when not selected.
/// State changes pause a clip; returning within the same turn resumes it.
final class ThreadAnimationClock {
    struct Clip {
        let durations: [TimeInterval]
        let loopStart: Int
        var duration: TimeInterval { durations.reduce(0,+) }
        func frame(elapsed: TimeInterval, hold: Bool = false) -> Int {
            guard !durations.isEmpty else { return 0 }
            let total = duration
            let start = min(max(0,loopStart),durations.count-1)
            let intro = durations.prefix(start).reduce(0,+)
            var time = max(0,elapsed)
            var first = 0
            if time >= total {
                if hold { return durations.count-1 }
                time = (time-intro).truncatingRemainder(dividingBy:max(0.001,total-intro))
                first = start
            }
            for (i,ms) in durations.enumerated().dropFirst(first) { time -= ms; if time < -1e-9 { return i } }
            return durations.count-1
        }
    }
    struct Position { let key: String; let index: Int; let elapsed: TimeInterval }
    private struct Track {
        var turn: String
        var state: String
        var epoch: TimeInterval
        var carried: [String:TimeInterval] = [:]
        var packing: [(String,TimeInterval)] = []
    }
    private var tracks: [String:Track] = [:]
    var clips: [String:Clip] = [:]
    func observe(id: String, turn: String, state: String, now: TimeInterval, age: TimeInterval) {
        let changedAt = now-max(0,age)
        guard var track = tracks[id], track.turn == turn else {
            tracks[id] = Track(turn:turn,state:state,epoch:changedAt);return
        }
        guard track.state != state else { return } // Polls/tool updates never restart.
        let transition = max(track.epoch,min(now,changedAt))
        track.carried[track.state,default:0] += transition-track.epoch
        track.state=state;track.epoch=transition;tracks[id]=track
    }
    func retain(ids: Set<String>) { tracks=tracks.filter { ids.contains($0.key) } }
    func position(id: String, now: TimeInterval) -> Position? {
        guard var track=tracks[id] else { return nil }
        let elapsed=track.carried[track.state,default:0]+max(0,now-track.epoch)
        var key=track.state;var clipTime=elapsed
        if key == "packing" {
            let keys=clips.keys.filter { $0.hasPrefix("packing_") }.sorted()
            guard !keys.isEmpty else { return nil }
            if track.packing.isEmpty { track.packing.append((keys.randomElement()!,0)) }
            while let last=track.packing.last, let clip=clips[last.0], elapsed >= last.1+clip.duration {
                track.packing.append((keys.randomElement()!,last.1+max(0.02,clip.duration)))
            }
            if let current=track.packing.last { key=current.0;clipTime=elapsed-current.1 }
            tracks[id]=track
        }
        guard let clip=clips[key] else { return nil }
        if key == "jump", elapsed >= clip.duration { return nil }
        return Position(key:key,index:clip.frame(elapsed:clipTime,hold:key == "question" || key == "jump"),elapsed:elapsed)
    }
}

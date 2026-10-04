import Foundation
var seed: UInt64 = 87193
func random() -> Double {
    seed = seed &* 6364136223846793005 &+ 1442695040888963407
    return Double(seed >> 11) / Double(UInt64(1) << 53)
}
var samples = [Double]()
for _ in 0..<100000 { samples.append(LeisureRoutine.interval(random: random)/60) }
let mean = samples.reduce(0,+)/Double(samples.count)
let central = Double(samples.filter { $0 >= 8 && $0 <= 12 }.count)/Double(samples.count)
assert(samples.allSatisfy { $0 >= 3 && $0 <= 30 })
assert(abs(mean-10)<0.15 && abs(central-0.5)<0.015)
for (choice,expected) in [(0.0,[400.0]),(0.399,[400.0]),(0.4,[200.0]),(0.799,[200.0]),(0.8,[200.0,400.0]),(0.899,[200.0,400.0]),(0.9,[]),(0.999,[])] {
 var r=LeisureRoutine();r.reset(now:0,interval:600,choice:choice);assert(r.snackTimes==expected)
}
var r=LeisureRoutine();r.reset(now:0,interval:600,choice:0.85)
assert(r.tick(now:200,eligible:true) == .eat)
r.cancel();assert(r.deadline==600) // Click-flat cancels eating without postponing sleep.
assert(r.tick(now:400,eligible:false) == .none && r.snackTimes.isEmpty)
assert(r.tick(now:700,eligible:false) == .none && r.phase == .awake)
assert(r.tick(now:701,eligible:true) == .sleep)
r.settled(now:708);r.click(now:710,wake:false)
assert(r.phase == .sleeping && r.sleepEpoch==708 && r.tailEpoch==710)
r.click(now:710.5,wake:false);assert(r.tailEpoch==710) // No tail restart/jump.
r.click(now:712,wake:false);assert(r.tailEpoch==712 && r.sleepEpoch==708)
r.click(now:712.1,wake:true);assert(r.phase == .waking)
assert(!r.finishedWakeLoop());assert(r.finishedWakeLoop())
r.reset(now:715,interval:600,choice:0.5);assert(r.deadline==1315 && r.snackTimes==[915])
r.enter();r.reset(now:800,interval:600,choice:0.95);assert(r.phase == .awake && r.deadline==1400)
print("PASS: truncated Gaussian bounds, mean \(mean), P(8–12)=\(central); four snack plans; priority blocking; flat preserves deadline; independent tail/ZZZ; exactly two wake loops; new-task reset")

import Foundation
let clock=ThreadAnimationClock()
clock.clips=["reading":.init(durations:[0.4,0.6,0.2,0.3],loopStart:2),"carrot":.init(durations:[0.1,0.2],loopStart:0),"question":.init(durations:[0.2,0.2],loopStart:0),"jump":.init(durations:[0.2,0.2],loopStart:0),"packing_01":.init(durations:[0.2,0.3],loopStart:0),"packing_02":.init(durations:[0.3,0.3],loopStart:0)]
clock.observe(id:"A",turn:"1",state:"reading",now:0,age:0)
clock.observe(id:"B",turn:"1",state:"reading",now:0.5,age:0)
assert(clock.position(id:"A",now:0.8)!.index==1)
assert(clock.position(id:"B",now:0.8)!.index==0)
assert(clock.position(id:"A",now:4.05)!.index==2) // Hidden A passed the intro and advanced loops.
for now in stride(from:1.0,to:10.0,by:0.07) { assert(clock.position(id:"A",now:now)!.index>=2) }
clock.observe(id:"A",turn:"1",state:"reading",now:9,age:0) // Duplicate status cannot reset.
assert(clock.position(id:"A",now:9)!.index>=2)
clock.observe(id:"A",turn:"1",state:"carrot",now:10,age:0)
clock.observe(id:"A",turn:"1",state:"reading",now:11,age:0)
assert(clock.position(id:"A",now:11)!.index>=2) // Return from tool work keeps the book out.
clock.observe(id:"A",turn:"2",state:"reading",now:12,age:0)
assert(clock.position(id:"A",now:12)!.index==0) // A new turn has a fresh intro.
clock.observe(id:"B",turn:"1",state:"jump",now:13,age:0)
assert(clock.position(id:"B",now:13.1)!.key=="jump")
assert(clock.position(id:"B",now:14)==nil) // Hidden completion is not replayed.
clock.observe(id:"C",turn:"1",state:"question",now:5,age:3)
assert(clock.position(id:"C",now:5)!.index==1)
clock.observe(id:"D",turn:"1",state:"packing",now:0,age:0)
let packing=clock.position(id:"D",now:30)!
assert(packing.key.hasPrefix("packing_"))
assert(clock.position(id:"D",now:30)!.key==packing.key)
print("PASS per-thread timelines: independent epochs, background progress, one-time reading intro, duplicate polls, same-turn resume, new-turn reset, expired completion, hold-last question, packing continuity")

import AppKit
let desktop = NSRect(x:0,y:0,width:1440,height:900)
let safe = NSRect(x:0,y:50,width:1440,height:825)
// Reserve the third child and the lower middle child at every edge.
let family = NSRect(x:258,y:10,width:310,height:230)
for edge in DesktopEdge.allCases {
    let delta = revealedDelta(edge:edge,contentFrame:family,desktopFrame:safe,bottomDrop:0)
    let revealed = family.offsetBy(dx:delta.x,dy:delta.y)
    assert(safe.insetBy(dx:EdgeHidePolicy.revealClearance,dy:EdgeHidePolicy.revealClearance).contains(revealed))
}
let parent = NSRect(x:1150,y:400,width:150,height:120)
let thirdChild = NSRect(x:1380,y:400,width:60,height:60)
assert(touchedDesktopEdge(petFrame:parent,desktopFrame:desktop)==nil)
assert(touchedDesktopEdge(petFrame:parent.union(thirdChild),desktopFrame:desktop) == .right)
for status in ["idle","thinking","working","compacting","interrupted"] {
    assert(canEnterEdgeHide(mode:"responsive",bridgeStatus:status,hasPermissionRequest:false,hasTransientAnimation:true))
}
print("family edge geometry and working-hide policy: passed")
for edge in DesktopEdge.allCases {
    let main = tailWindowFrame(edge:edge,petFrame:NSRect(x:500,y:300,width:150,height:120),desktopFrame:desktop)
    for count in 0...3 {
        let tails = familyTailRects(edge:edge,main:main,desktop:desktop,children:count)
        assert(tails.count == count+1)
        for (index,tail) in tails.enumerated() {
            let overlap = EdgeHidePolicy.tailScreenOverlap * (index == 0 ? 1 : 32/EdgeHidePolicy.tailWindowSize)
            switch edge {
            case .bottom: assert(abs(tail.minY-(desktop.minY-overlap))<0.01)
            case .top: assert(abs(tail.maxY-(desktop.maxY+overlap))<0.01)
            case .left: assert(abs(tail.minX-(desktop.minX-overlap))<0.01)
            case .right: assert(abs(tail.maxX-(desktop.maxX+overlap))<0.01)
            }
            if index > 0 {
                if edge == .bottom || edge == .top { assert(tail.minX > tails[index-1].maxX) }
                else { assert(tail.maxY < tails[index-1].minY) }
            }
        }
    }
}
print("all edges: original overlap preserved; 0–3 tails ordered without overlap")

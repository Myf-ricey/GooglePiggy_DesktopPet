#!/usr/bin/env python3
"""Compile a test-only controller extension into an isolated bundle."""
from pathlib import Path
import subprocess,shutil,os,json
root=Path(__file__).resolve().parents[1];out=root/'output/native-leisure';src=root/'macos/Sources/GooglePiggy'
test=out/'test-sources';test.mkdir(parents=True,exist_ok=True)
code=(src/'PetController.swift').read_text()
code+='''
extension PetController {
    func runLeisureIntegrationTests() throws {
        try loadResources()
        selectedFamilyPayload = [:]
        restartLeisureClock()
        startRest()
        assert(mode == "responsive" && leisure.phase == .entering && currentKey == "sleep_entry")
        for _ in 0..<(manifest!.animations["sleep_entry"]!.frames.count) { advance() }
        assert(leisure.phase == .sleeping && currentKey == "sleep_body")
        var woke = 0, stayed = 0
        for _ in 0..<200 {
            leisure.settled(now: leisureNow-1)
            let epoch = leisure.sleepEpoch
            frameIndex = 24
            sleepClick()
            if leisure.phase == .waking { woke += 1; assert(currentKey == "left" && !nudgeFacesRight) }
            else { stayed += 1; assert(leisure.phase == .sleeping && leisure.sleepEpoch == epoch && frameIndex == 24 && leisure.tailEpoch != nil) }
        }
        assert(woke > 60 && stayed > 60)
        leisure.settled(now: leisureNow)
        leisure.click(now: leisureNow, wake: true);frameIndex=0
        let count=manifest!.animations["left"]!.frames.count
        for _ in 0..<count { advance() }
        assert(leisure.phase == .waking && leisure.wakeLoops == 1)
        for _ in 0..<count { advance() }
        assert(leisure.phase == .awake && currentKey == "idle" && leisure.deadline > leisureNow+179)
        // Click-flat cancels eating but never restarts this cycle's deadline.
        leisure.reset(now:leisureNow-201,interval:600,choice:0.5)
        updateLeisure(); assert(currentKey == "snack")
        let deadline=leisure.deadline
        mouseDown=true;dragging=false;dragCanPlayFlat=true
        handleMouseUp(point:.zero)
        assert(currentKey == "flat" && leisure.phase == .awake && leisure.deadline == deadline)
        for _ in 0..<manifest!.animations["flat"]!.frames.count { advance() }
        assert(currentKey == "idle" && leisure.deadline == deadline)
        for status in ["thinking","working","compacting","interrupted"] {
            bridgeStatus="idle";transientKey=nil;leisure.settled(now:leisureNow)
            _=applyBridgePayload(["status":status,"token":UUID().uuidString])
            assert(leisure.phase == .awake && currentKey != "sleep_body" && currentKey != "snack")
            leisure.reset(now:leisureNow-601,interval:600,choice:0.95)
            updateLeisure();assert(leisure.phase == .awake)
        }
        // New tasks cancel sleep even if they arrive outside the selected family.
        bridgeStatus="idle";transientKey=nil
        leisureTasksInitialized=true;leisure.settled(now:leisureNow)
        let node=FamilyNode(id:"test-new-task",parent:"",title:"test")
        node.turn="new-turn";node.active=true;node.status="working";families.nodes[node.id]=node
        observeNewTasks();assert(leisure.phase == .awake && leisure.deadline > leisureNow+179)
        let stable=leisure.deadline;observeNewTasks();assert(leisure.deadline==stable)
        families.nodes.removeAll()
        // Higher-priority transient animations prevent both snack and sleep.
        for key in ["left","flat","jump","edge_reveal"] {
            transientKey=key
            leisure.reset(now:leisureNow-601,interval:600,choice:0.85)
            updateLeisure();assert(currentKey==key && leisure.phase == .awake)
        }
        // Crossing the deadline during drag keeps the same deadline and
        // starts sleeping on mouse-up, rather than drawing a new interval.
        transientKey=nil;bridgeStatus="idle"
        leisure.reset(now:leisureNow-601,interval:600,choice:0.95)
        let dragDeadline=leisure.deadline
        dragging=true;mouseDown=true;transientKey="left"
        dragPrevious=VisualSnapshot(transientKey:nil,transientOnce:false,frameIndex:0,successEffectStarted:nil)
        updateLeisure()
        assert(leisure.phase == .awake && leisure.deadline == dragDeadline && currentKey == "left")
        handleMouseUp(point:.zero)
        assert(leisure.phase == .entering && leisure.deadline == dragDeadline && currentKey == "sleep_entry")
        interruptLeisure(preserveDeadline:true)
        assert(leisure.phase == .awake && leisure.deadline == dragDeadline)
        updateLeisure();assert(leisure.phase == .entering && leisure.deadline == dragDeadline)
        // A real task arriving before mouse-up still wins over overdue sleep.
        restartLeisureClock();dragging=true;mouseDown=true;transientKey="left"
        dragPrevious=VisualSnapshot(transientKey:nil,transientOnce:false,frameIndex:0,successEffectStarted:nil)
        selectedFamilyPayload=["status":"working","token":"drag-release-new-task"]
        handleMouseUp(point:.zero)
        assert(leisure.phase == .awake && bridgeStatus == "working" && currentKey == "carrot")
        selectedFamilyPayload=[:];bridgeStatus="idle"
        transientKey=nil;leisure.reset(now:leisureNow,interval:600,choice:0.95)
        mode="sleep_entry";sleepPreviewEpoch=leisureNow-sleepEntryDuration-1
        assert(currentKey=="sleep_body" && leisure.phase == .awake)
        let previewFrame=currentFrameRecord()!;assert(previewFrame.file.contains("sleep_body"))
        // Switching families uses their own timelines, not the global index.
        mode="responsive";transientKey=nil;permissionRequest=nil;bridgeStatus="thinking"
        restartLeisureClock();families.nodes.removeAll()
        let a=FamilyNode(id:"clock-A",parent:"",title:"A")
        a.turn="a1";a.status="thinking";a.active=true;a.changed=Date().addingTimeInterval(-8)
        a.payload=["session_id":a.id,"status":"thinking","token":"a-token"]
        let b=FamilyNode(id:"clock-B",parent:"",title:"B")
        b.turn="b1";b.status="thinking";b.active=true;b.changed=Date().addingTimeInterval(-0.2)
        b.payload=["session_id":b.id,"status":"thinking","token":"b-token"]
        families.nodes=[a.id:a,b.id:b];syncThreadAnimations()
        let intro=manifest!.animations["reading"]!.loop_start!
        families.selectedID=a.id;selectedFamilyPayload=a.payload;bridgeToken="";frameIndex=0
        _=applyBridgePayload(a.payload);_=currentFrameRecord()
        assert(currentKey=="reading" && frameIndex>=intro)
        families.selectedID=b.id;selectedFamilyPayload=b.payload;bridgeToken="";frameIndex=0
        _=applyBridgePayload(b.payload);_=currentFrameRecord()
        assert(currentKey=="reading" && frameIndex<intro)
        families.selectedID=a.id;selectedFamilyPayload=a.payload;bridgeToken="";frameIndex=0
        _=applyBridgePayload(a.payload);_=currentFrameRecord()
        assert(currentKey=="reading" && frameIndex>=intro)
        a.turn="a2";a.changed=Date();syncThreadAnimations();_=currentFrameRecord()
        assert(frameIndex<intro)
        a.turn="a-completed";a.status="success";a.changed=Date().addingTimeInterval(-5);syncThreadAnimations()
        selectedFamilyPayload=["session_id":a.id,"status":"success","token":"done","received_at":Date().timeIntervalSince1970-5]
        bridgeToken="";_=applyBridgePayload(selectedFamilyPayload!);successEffectStarted=leisureNow-5
        updateLeisure();assert(currentKey=="idle" && successEffectStarted==nil)
        print("PASS native thread switching: A resumes reading loop, B has independent intro, A new turn restarts, expired completion does not replay or block sleep")
        animationTimer?.invalidate();window?.orderOut(nil)
        print("PASS native: rest entry; 200 clicks wake=\\(woke) tail=\\(stayed); independent Z clock; two wake loops; snack click interruption; Codex priorities; new-task detection; no repeated reset; drag deadline preserved and release starts sleep; real task wins on release; preview isolation")
    }
}
'''
(test/'PetController.swift').write_text(code)
(test/'main.swift').write_text('import AppKit\nlet app=NSApplication.shared\napp.setActivationPolicy(.accessory)\nlet controller=PetController()\ntry controller.runLeisureIntegrationTests()\n')
app=out/'Leisure Integration Test.app';shutil.copytree(root/'build/macos/GooglePiggy.app',app,dirs_exist_ok=True)
exe=app/'Contents/MacOS/GooglePiggy'
files=[p for p in src.glob('*.swift') if p.name not in ['main.swift','PetController.swift']]+[test/'PetController.swift',test/'main.swift']
subprocess.run(['swiftc','-swift-version','5','-framework','AppKit','-framework','Foundation',*map(str,files),'-o',str(exe)],check=True)
subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True,capture_output=True)
state=out/'integration-state';state.mkdir(exist_ok=True)
result=subprocess.run([str(exe)],env=dict(os.environ,GOOGLEPIGGY_STATE_DIR=str(state)),text=True,capture_output=True,timeout=90)
(out/'integration-test.log').write_text(result.stdout+result.stderr)
print(result.stdout);print(result.stderr[-3000:] if result.returncode else '')
assert result.returncode==0,result.returncode

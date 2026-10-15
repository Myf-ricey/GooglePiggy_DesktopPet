import AppKit
import ImageIO
import UniformTypeIdentifiers
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
let output = root.appendingPathComponent("build/update-preview")
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let manifest = try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent("assets/macos-resources/animation-manifest.json"))) as! [String:Any]
let animations = manifest["animations"] as! [String:[String:Any]]
let frames = animations["idle"]!["frames"] as! [[String:Any]]
let images = frames.map { NSImage(contentsOf:root.appendingPathComponent("assets/macos-resources/" + ($0["file"] as! String)))! }
images.forEach { $0.cacheMode = .never }
let demoRelease = PiggyRelease(version:"0.5.0",notes:"• 新增启动检查与手动检查更新\n• 发光小灯泡，及时告诉你新版消息\n• 优化猪猪的互动体验",url:URL(string:"https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases")!)
final class Preview: NSView {
    var notice = UpdateNotice(.available(demoRelease),current:"0.4.0")
    var time: Double = 0
    override var isFlipped: Bool { true }
    override func draw(_ dirtyRect: NSRect) {
        NSColor(calibratedRed:0.96,green:0.96,blue:0.94,alpha:1).setFill(); bounds.fill()
        ("猪猪桌宠  /  macOS 更新提示预览" as NSString).draw(at:NSPoint(x:28,y:25),withAttributes:[.font:NSFont.systemFont(ofSize:13,weight:.medium),.foregroundColor:NSColor(calibratedWhite:0.45,alpha:1)])
        NSGraphicsContext.saveGraphicsState()
        let t = NSAffineTransform();t.translateX(by:-170,yBy:-60);t.concat()
        NSImage(contentsOf: root.appendingPathComponent("assets/macos-resources/" + (frames[Int(time*12)%frames.count]["file"] as! String)))!.draw(in:NSRect(x:0,y:0,width:640,height:640),from:.zero,operation:.sourceOver,fraction:1,respectFlipped:true,hints:[.interpolation:NSImageInterpolation.none])
        notice.draw(time:time)
        NSGraphicsContext.restoreGraphicsState()
    }
    override func mouseDown(with event:NSEvent) {
        let p=convert(event.locationInWindow,from:nil);let local=NSPoint(x:p.x+170,y:p.y+60)
        notice.pressed=notice.buttons.first(where:{$0.value.contains(local)})?.key;needsDisplay=true
    }
    override func mouseUp(with event:NSEvent) {
        let p=convert(event.locationInWindow,from:nil);let local=NSPoint(x:p.x+170,y:p.y+60)
        if let action=notice.pressed,notice.buttons[action]?.contains(local)==true {
            notice = UpdateNotice(notice.release == nil ? .available(demoRelease) : .current,current:"0.4.0")
        }
        notice.pressed=nil;needsDisplay=true
    }
}
let view=Preview(frame:NSRect(x:0,y:0,width:480,height:550))
let panel=NSPanel(contentRect:view.bounds,styleMask:[.titled,.closable],backing:.buffered,defer:false)
panel.title="猪猪更新预览 · 演示版本 0.5.0";panel.contentView=view
func snapshot() -> NSBitmapImageRep {
    let rep = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:960,pixelsHigh:1100,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    NSGraphicsContext.saveGraphicsState()
    let context=NSGraphicsContext(bitmapImageRep:rep)!
    NSGraphicsContext.current=context
    context.cgContext.translateBy(x:0,y:1100)
    context.cgContext.scaleBy(x:2,y:-2)
    NSGraphicsContext.current=NSGraphicsContext(cgContext:context.cgContext,flipped:true)
    view.draw(view.bounds)
    NSGraphicsContext.restoreGraphicsState()
    return rep
}
for (name,result) in [("available",UpdateResult.available(demoRelease)),("current",.current),("error",.failed)] {
    view.notice=UpdateNotice(result,current:"0.4.0");view.time=0.4
    try snapshot().representation(using:.png,properties:[:])!.write(to:output.appendingPathComponent(name+".png"))
}
view.notice=UpdateNotice(.available(demoRelease),current:"0.4.0")
let destination=CGImageDestinationCreateWithURL(output.appendingPathComponent("update-preview.gif") as CFURL,UTType.gif.identifier as CFString,48,nil)!
CGImageDestinationSetProperties(destination,[kCGImagePropertyGIFDictionary:[kCGImagePropertyGIFLoopCount:0]] as CFDictionary)
for i in 0..<48 {
    view.time=Double(i)/20
    CGImageDestinationAddImage(destination,snapshot().cgImage!,[kCGImagePropertyGIFDictionary:[kCGImagePropertyGIFDelayTime:0.05]] as CFDictionary)
}
assert(CGImageDestinationFinalize(destination))
print("preview_render=ok")
if CommandLine.arguments.contains("--live") {
    panel.center();panel.makeKeyAndOrderFront(nil);app.activate(ignoringOtherApps:true)
    let timer=Timer.scheduledTimer(withTimeInterval:0.05,repeats:true) { _ in view.time += 0.05;view.needsDisplay=true }
    RunLoop.main.add(timer,forMode:.common)
    app.run()
}

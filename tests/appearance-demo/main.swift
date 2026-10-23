// Native playback recording harness. Uses the production controller and controls,
// with an isolated bundle ID/state directory and only synthetic preview content.
import AppKit
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let controller = PetController()
app.delegate = controller
let backdrop = NSPanel(contentRect: NSRect(x:80,y:100,width:1500,height:900),styleMask:[.borderless,.nonactivatingPanel],backing:.buffered,defer:false)
backdrop.backgroundColor = NSColor(srgbRed:0.15,green:0.18,blue:0.23,alpha:1)
backdrop.level = NSWindow.Level(rawValue: NSWindow.Level.floating.rawValue+2)
backdrop.isReleasedWhenClosed = false
let caption = NSTextField(labelWithString:"macOS 26.5 · candidate 0.5.6 (11) · native playback test")
caption.textColor = .white; caption.font = .systemFont(ofSize:22,weight:.medium)
caption.frame = NSRect(x:30,y:840,width:1440,height:40)
backdrop.contentView?.addSubview(caption)
func descendants(_ v:NSView) -> [NSView] { [v]+v.subviews.flatMap(descendants) }
func controls() -> [NSView] { app.windows.filter { $0.title == "外观" }.compactMap(\.contentView).flatMap(descendants) }
func slider(_ key:String,_ value:Double) {
    guard let control = controls().compactMap({$0 as? NSSlider}).first(where:{$0.identifier?.rawValue == key}) else { fatalError(key) }
    control.doubleValue = value; control.sendAction(control.action,to:control.target)
}
func color(_ key:String,_ value:NSColor) {
    let control = controls().compactMap({$0 as? NSColorWell}).first(where:{$0.identifier?.rawValue == key})!
    control.color = value; control.sendAction(control.action,to:control.target)
}
func mode(_ key:String) {
    let item = NSMenuItem(); item.representedObject = key
    controller.perform(NSSelectorFromString("selectMode:"),with:item)
}
func scene(_ delay:Double,_ label:String,_ work:@escaping ()->Void) {
    DispatchQueue.main.asyncAfter(deadline:.now()+delay) {
        caption.stringValue = "macOS 26.5 · 0.5.6 (11) · Fixture · " + label
        work()
        for window in app.windows where window !== backdrop {
            window.level = NSWindow.Level(rawValue:NSWindow.Level.floating.rawValue+3)
        }
    }
}
scene(1,"Default gradient / preview at pet position") {
    PetAppearance.shared.reset()
    backdrop.orderFrontRegardless()
    let pet = app.windows.first { $0.title == appDisplayName }!
    pet.setFrameOrigin(NSPoint(x:50,y:180))
    controller.perform(NSSelectorFromString("showAppearance:"),with:NSMenuItem())
    app.windows.first { $0.title == "外观" }!.setFrameOrigin(NSPoint(x:1040,y:240))
    for button in controls().compactMap({$0 as? NSButton}) where ["预览对话框","预览任务栏"].contains(button.title) { button.performClick(nil) }
}
scene(7,"Pet 50% / bulb follows pet; dialogue remains 100%") {
    controls().compactMap({$0 as? NSButton}).first(where:{$0.title == "预览任务栏"})!.performClick(nil)
    slider("petScale",0.5)
}
scene(12,"Pet 150% / bulb follows pet; dialogue remains 100%") { slider("petScale",1.5) }
scene(17,"Independent background/button alpha; opaque coloured text") {
    controls().compactMap({$0 as? NSButton}).first(where:{$0.title == "预览任务栏"})!.performClick(nil)
    slider("petScale",1); slider("dialogOpacity",0.35);slider("buttonOpacity",0.7)
    color("dialogColor",.darkGray);color("dialogTextColor",.white);color("buttonTextColor",.yellow)
}
scene(22,"Independent dialogue/task gaps and sizes") {
    slider("dialogGap",50);slider("taskGap",30);slider("dialogScale",1.2);slider("taskScale",1.2)
}
scene(27,"Reset original gradient; both preview checkboxes stay enabled") {
    controls().compactMap({$0 as? NSButton}).first(where:{$0.title == "恢复默认"})!.performClick(nil)
}
scene(31,"Sleep body / tail / Z use the pet coordinate system") { mode("sleep_body") }
scene(35,"Reading animation / original RGBA frames") { mode("reading") }
DispatchQueue.main.asyncAfter(deadline:.now()+40) { app.terminate(nil) }
app.run()

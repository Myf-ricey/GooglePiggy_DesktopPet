import Foundation
func row(_ tag:String, _ prerelease:Bool=false, _ url:String="https://github.com/Myf-ricey/GooglePiggy_DesktopPet/releases/tag/test") -> [String:Any] {
    ["tag_name":tag,"draft":false,"prerelease":prerelease,"html_url":url,"assets":[["name":"GooglePiggy-macos-universal.zip","size":123]],"body":"- 新增检查更新\n- 优化互动"]
}
assert(UpdateChecker.newer("0.4.10",than:"0.4.9"))
assert(!UpdateChecker.newer("0.4.0",than:"0.4"))
assert(!UpdateChecker.newer("0.3.9",than:"0.4.0"))
assert(!UpdateChecker.newer("0.5-beta",than:"0.4.0"))
assert(UpdateChecker.version("0..5") == nil)
assert(UpdateChecker.parse([row("v0.4.2-windows"),row("v0.4.0-macos")]).map(\.version) == ["0.4.0"])
assert(UpdateChecker.parse([row("v0.5.0-macos",true)]).isEmpty)
assert(UpdateChecker.parse([row("v0.5.0-macos",false,"https://evil.example/download")]).isEmpty)
var empty=row("v0.5.0-macos");empty["assets"]=[] as [[String:Any]]
assert(UpdateChecker.parse([empty]).isEmpty)
let notice=UpdateNotice(.available(PiggyRelease(version:"0.5.0",notes:"新增功能",url:URL(string:"https://github.com")!)))
assert(notice.buttons.count == 2)
assert(UpdateNotice(.current).buttons.count == 1)
assert(UpdateNotice(.failed).release == nil)
print("update_checks=12_passed")

final class FixtureProtocol: URLProtocol {
    static var status = 200
    static var payload: [[String:Any]] = []
    override class func canInit(with request:URLRequest) -> Bool { true }
    override class func canonicalRequest(for request:URLRequest) -> URLRequest { request }
    override func startLoading() {
        client?.urlProtocol(self,didReceive:HTTPURLResponse(url:request.url!,statusCode:Self.status,httpVersion:nil,headerFields:nil)!,cacheStoragePolicy:.notAllowed)
        client?.urlProtocol(self,didLoad:try! JSONSerialization.data(withJSONObject:Self.payload))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
let config = URLSessionConfiguration.ephemeral
config.protocolClasses = [FixtureProtocol.self]
let checker = UpdateChecker(session:URLSession(configuration:config))
func check(_ manual:Bool, expected:String, promote:Bool=false) {
    var done=false
    checker.check(manual:manual) { result,requested in
        let name:String
        switch result { case .available: name="available";case .current:name="current";case .failed:name="failed" }
        assert(name == expected)
        assert(requested == (manual || promote))
        assert(Thread.isMainThread)
        done=true
    }
    if promote { checker.check(manual:true) { _,_ in fatalError("Concurrent check was not coalesced") } }
    let deadline=Date().addingTimeInterval(3)
    while !done && Date() < deadline { RunLoop.current.run(until:Date().addingTimeInterval(0.01)) }
    assert(done && !checker.checking)
}
FixtureProtocol.payload=[row("v\(UpdateChecker.currentVersion)-macos"),row("v99.0.0-windows")]
check(false,expected:"current")
check(true,expected:"current")
FixtureProtocol.payload=[row("v99.0.0-macos"),row("v\(UpdateChecker.currentVersion)-macos")]
check(false,expected:"available")
check(false,expected:"available",promote:true)
FixtureProtocol.status=403
check(false,expected:"failed")
check(true,expected:"failed")
print("update_network_cases=6_passed")
let releaseFile = URL(fileURLWithPath:"build/update-preview/releases.json")
if let data=try? Data(contentsOf:releaseFile),let rows=try? JSONSerialization.jsonObject(with:data) as? [[String:Any]] {
    let releases=UpdateChecker.parse(rows)
    assert(!releases.isEmpty)
    print("live_release_parse=" + releases.map(\.version).joined(separator:","))
}

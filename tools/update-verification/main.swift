import CryptoKit
import Foundation
// Public-key-only release validation: never accesses Keychain or private keys.
let args=CommandLine.arguments
let info=try PropertyListSerialization.propertyList(from:Data(contentsOf:URL(fileURLWithPath:args[1])),format:nil) as! [String:Any]
let key=try Curve25519.Signing.PublicKey(rawRepresentation:Data(base64Encoded:info["SUPublicEDKey"] as! String)!)
let feed=try Data(contentsOf:URL(fileURLWithPath:args[2]))
let xml=String(data:feed,encoding:.utf8)!
let footer=xml.components(separatedBy:"<!-- sparkle-signatures:").last!
let signature=footer.components(separatedBy:"edSignature: ")[1].components(separatedBy:.newlines)[0]
let length=Int(footer.components(separatedBy:"length: ")[1].components(separatedBy:.newlines)[0])!
assert(key.isValidSignature(Data(base64Encoded:signature)!,for:Data(feed.prefix(length))),"Appcast signature invalid")
let document=try XMLDocument(data:feed)
let enclosure=try document.nodes(forXPath:"/rss/channel/item/enclosure").first as! XMLElement
let archive=try Data(contentsOf:URL(fileURLWithPath:args[3]))
assert(archive.count == Int(enclosure.attribute(forName:"length")!.stringValue!)!)
let archiveSignature=enclosure.attribute(forName:"sparkle:edSignature")!.stringValue!
assert(key.isValidSignature(Data(base64Encoded:archiveSignature)!,for:archive),"Archive signature invalid")
print("public_key_only_verification=feed_and_archive_passed")

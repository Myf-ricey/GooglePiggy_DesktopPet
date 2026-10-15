import CryptoKit
import Foundation
let key = Curve25519.Signing.PrivateKey()
let path = CommandLine.arguments[1]
FileManager.default.createFile(atPath: path, contents: Data(key.rawRepresentation.base64EncodedString().utf8), attributes: [.posixPermissions: 0o600])
print(key.publicKey.rawRepresentation.base64EncodedString())

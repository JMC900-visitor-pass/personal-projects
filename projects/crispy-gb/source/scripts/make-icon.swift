import AppKit
let destination = CommandLine.arguments[1]
let image = NSImage(size: NSSize(width: 1024, height: 1024))
image.lockFocus()
NSColor(calibratedRed: 0.035, green: 0.065, blue: 0.095, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 24, y: 24, width: 976, height: 976), xRadius: 210, yRadius: 210).fill()
NSColor(calibratedRed: 0.24, green: 0.86, blue: 0.67, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 145, y: 265, width: 734, height: 495), xRadius: 120, yRadius: 120).fill()
NSColor(calibratedRed: 0.07, green: 0.18, blue: 0.2, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 335, y: 350, width: 354, height: 335), xRadius: 30, yRadius: 30).fill()
NSColor(calibratedRed: 0.52, green: 0.98, blue: 0.78, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 365, y: 385, width: 294, height: 265), xRadius: 12, yRadius: 12).fill()
NSColor(calibratedRed: 0.07, green: 0.18, blue: 0.2, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 212, y: 455, width: 38, height: 135), xRadius: 5, yRadius: 5).fill()
NSBezierPath(roundedRect: NSRect(x: 165, y: 504, width: 132, height: 38), xRadius: 5, yRadius: 5).fill()
NSBezierPath(ovalIn: NSRect(x: 730, y: 480, width: 65, height: 65)).fill()
NSBezierPath(ovalIn: NSRect(x: 795, y: 535, width: 65, height: 65)).fill()
let lettering = "GB" as NSString
let letteringAttributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.monospacedSystemFont(ofSize: 130, weight: .heavy),
    .foregroundColor: NSColor(calibratedRed: 0.07, green: 0.18, blue: 0.2, alpha: 1)
]
let letteringSize = lettering.size(withAttributes: letteringAttributes)
lettering.draw(at: NSPoint(x: 512 - letteringSize.width / 2, y: 515 - letteringSize.height / 2), withAttributes: letteringAttributes)
image.unlockFocus()
let rep = NSBitmapImageRep(data: image.tiffRepresentation!)!
try rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: destination))

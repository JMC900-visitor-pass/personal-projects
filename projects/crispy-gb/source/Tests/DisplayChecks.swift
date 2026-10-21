import Foundation

@main struct DisplayChecks {
    static func main() throws {
        for game in [CGSize(width: 160,height: 144), CGSize(width: 240,height: 160)] {
            for screen in [CGSize(width: 1920,height:1080), CGSize(width:2560,height:1600), CGSize(width:5120,height:2160), CGSize(width:600,height:900)] {
                let fit = PlaybackLayout.viewport(screen:screen,game:game,mode:0)
                let fill = PlaybackLayout.viewport(screen:screen,game:game,mode:2)
                precondition(FillGeometry.viewport(screen:screen,game:game,percent:0) == fit)
                precondition(FillGeometry.viewport(screen:screen,game:game,percent:1) == fill)
                var last = CGSize.zero
                for p in stride(from:0.0,through:1.0,by:0.1) {
                    let r = FillGeometry.viewport(screen:screen,game:game,percent:p)
                    precondition(abs(r.width/r.height-game.width/game.height)<1e-8)
                    let c = FillGeometry.crop(screen:screen,game:game,percent:p)
                    precondition(c.width >= last.width-1e-8 && c.height >= last.height-1e-8); last = c
                    let safe = FillGeometry.safeZone(game:game,percent:p)
                    for ratio in [16.0/9,16.0/10,21.0/9] {
                        let crop = FillGeometry.crop(screen:CGSize(width:ratio*1000,height:1000),game:game,percent:p)
                        precondition(safe.minX >= crop.width-1e-8 && safe.minY >= crop.height-1e-8)
                        precondition(safe.maxX <= game.width-crop.width+1e-8 && safe.maxY <= game.height-crop.height+1e-8)
                    }
                }
            }
        }
        let example = ##"{"fitMode":"fill","fillPercent":0.72,"colour":{"rgbShift":[0,0,0],"gamma":1.1,"saturation":1.15,"scanline":{"on":true,"intensity":0.15,"colour":"#1a1a2e"}},"filter":"crt","aspectLock":"4:3"}"##
        let display = try JSONDecoder().decode(DisplaySettings.self,from:Data(example.utf8))
        precondition(display.colour.brightness == 1 && display.colour.contrast == 1 && display.presets.count == 3)
        var settings = SessionSettings(display: display)
        settings.display.presets[2] = .crispy
        settings.controls.overrides = ["A":"kb.z","Start":"ctrl.start"]
        let restored = try JSONDecoder().decode(SessionSettings.self,from:JSONEncoder().encode(settings))
        precondition(restored == settings)
        let malformed = try JSONDecoder().decode(DisplaySettings.self,from:Data(#"{"fillPercent":42,"colour":{"rgbShift":[999],"gamma":-1},"presets":[]}"#.utf8))
        precondition(malformed.fillPercent == 1 && malformed.colour.rgbShift == [255,0,0] && malformed.colour.gamma == 0 && malformed.presets.count == 3)
        var timing = PlaybackTiming()
        let first = timing.frames(elapsed:1.0/60,fps:60,speed:1)
        precondition(first == 1); timing.reset()
        precondition(timing.frames(elapsed:0,fps:60,speed:1) == 0)
        print("PASS: fit/fill endpoints, continuous crop, native aspect, common-ratio safe zone, partial schema defaults, presets/control roundtrip, validation, timing reset")
    }
}

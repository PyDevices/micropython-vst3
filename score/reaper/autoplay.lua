--[[
One-shot autoplay for the Perihelion project.

launch.sh copies this file to Scripts/__startup.lua right before starting
REAPER with the project. It deletes itself immediately - a leftover
__startup.lua would hijack the next interactive REAPER session - then gives
the sixteen MicroPython sidecars a moment to come up and starts playback
from the top.
]]

local info = debug.getinfo(1, "S")
local self_path = info.source:sub(2)
os.remove(self_path)

local started = reaper.time_precise()
local fired = false

local function tick()
    if not fired and reaper.time_precise() - started >= 6.0 then
        fired = true
        reaper.SetEditCurPos(0.0, false, false)
        reaper.Main_OnCommand(1007, 0) -- Transport: Play
        return
    end
    reaper.defer(tick)
end

tick()

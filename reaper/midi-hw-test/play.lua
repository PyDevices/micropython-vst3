--[[
One-shot autoplay for the MIDI hardware-output test project. Self-deletes
immediately - a leftover __startup.lua would hijack the next interactive
REAPER session - waits MPVST_MIDIHW_DELAY seconds (default 3, enough for
REAPER's window and MIDI subsystem to settle; there is no sidecar to boot,
unlike the soundtrack pieces' autoplay.lua), then plays from the top. Stops
the transport one second after the project's own length has elapsed
(read from the project itself, not hardcoded, so this stays correct if
build_project.py's note count/tempo ever changes) and leaves REAPER open.

Platform-neutral: no environment this script touches is Windows- or
Linux-specific. `run-midi-hw-test.sh` is what differs by platform.
]]

local info = debug.getinfo(1, "S")
os.remove(info.source:sub(2))

local DELAY = tonumber(os.getenv("MPVST_MIDIHW_DELAY") or "3")

local started = reaper.time_precise()
local fired = false
local stopped = false
local stop_at = nil

local function tick()
    local elapsed = reaper.time_precise() - started
    if not fired and elapsed >= DELAY then
        fired = true
        reaper.SetEditCurPos(0.0, false, false)
        reaper.Main_OnCommand(1007, 0) -- Transport: Play
        stop_at = elapsed + reaper.GetProjectLength(0) + 1.0
    end
    if fired and not stopped and elapsed >= stop_at then
        stopped = true
        reaper.Main_OnCommand(1016, 0) -- Transport: Stop
        return -- one-shot; project stays open, REAPER is not quit
    end
    if not stopped then
        reaper.defer(tick)
    end
end

tick()

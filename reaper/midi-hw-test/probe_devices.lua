--[[
One-shot, read-only probe: list the hardware MIDI input/output devices
this REAPER install currently sees (name + index, the index build_project.py
needs), and confirm the transport actually advances in real wall-clock time
under Play - not just during an offline render, which is REAPER's normal
mode in this repo's other headless tooling.

Never touches a track's MIDI Hardware Output, never presses a note: the
scratch project it runs against is empty. Self-deletes and quits like every
other startup hook in this repo. Platform-neutral - reads MPVST_PROBE_REPORT
and nothing else host-specific.
]]

local info = debug.getinfo(1, "S")
os.remove(info.source:sub(2))

local REPORT = os.getenv("MPVST_PROBE_REPORT")
local report = io.open(REPORT, "w")

local function emit(line)
    report:write(line .. "\n")
    report:flush()
end

local function quit()
    emit("DONE")
    report:close()
    reaper.Main_OnCommand(40004, 0)
end

emit("BEGIN")
emit("INFO reaper_version " .. reaper.GetAppVersion())

emit("INFO num_midi_outputs " .. reaper.GetNumMIDIOutputs())
for i = 0, 31 do
    local present, name = reaper.GetMIDIOutputName(i, "")
    if present then
        emit(string.format("MIDIOUT_DEV %d name=%s", i, name))
    end
end

emit("INFO num_midi_inputs " .. reaper.GetNumMIDIInputs())
for i = 0, 31 do
    local present, name = reaper.GetMIDIInputName(i, "")
    if present then
        emit(string.format("MIDIIN_DEV %d name=%s", i, name))
    end
end

-- Realtime check: does the transport actually move forward in wall-clock
-- time under Play with the currently configured audio device (no render)?
-- The project behind this script is empty (no items, no MIDI hardware
-- output configured), so nothing can sound even if Play does work.
local phase = 0
local wall_start = nil

local function driver()
    if phase == 0 then
        reaper.SetEditCurPos(0.0, false, false)
        reaper.Main_OnCommand(1007, 0) -- Transport: Play
        wall_start = reaper.time_precise()
        phase = 1
        reaper.defer(driver)
        return
    elseif phase == 1 then
        local elapsed = reaper.time_precise() - wall_start
        if elapsed >= 3.0 then
            local pos = reaper.GetPlayPosition()
            emit(string.format("INFO realtime_check wall=%.3f playpos=%.3f",
                                elapsed, pos))
            if pos > elapsed * 0.5 then
                emit("PASS realtime_playback_advances")
            else
                emit("FAIL realtime_playback_stalled")
            end
            reaper.Main_OnCommand(1016, 0) -- Transport: Stop
            phase = 2
        end
        reaper.defer(driver)
        return
    end
    quit()
end

driver()

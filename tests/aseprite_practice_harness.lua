-- Real sprites/transactions, controlled clipboard and alerts. Run only in batch mode.
local root = app.params.root
local base = app.params.repo
local scenario = app.params.scenario
local target = app.params.target
local sprite = app.open(target)
assert(sprite and app.activeSprite == sprite)
local original = sprite.cels[1] and sprite.cels[1].image:getPixel(0, 0)
local original_count = #sprite.cels
local alerts, console = {}, {}
local function read(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end
local clipboard = assert(read(root .. "/test_clipboard.txt"))
local env = setmetatable({
    app = setmetatable({clipboard = {text = clipboard}, alert = function(msg) table.insert(alerts, msg) end}, {__index = app}),
    print = function(...) table.insert(console, {...}) end,
}, {__index = _G})

local exercise = tonumber(scenario:match("^copy_frame_(%d)"))
if exercise then
    app.activeFrame = sprite.frames[exercise]
    app.activeLayer = sprite.layers[1]
end
if scenario:match("_deleted$") then assert(os.remove(target)) end
if scenario:match("_no_settings$") then
    assert(os.remove(root .. "/Ase-PS-Bridge/bridge_settings.json"))
end
if scenario:match("_stat_false$") then
    env.app.fs = setmetatable({isFile = function(path)
        if path:lower():match("copy practice%.aseprite$") then return false end
        return app.fs.isFile(path)
    end}, {__index = app.fs})
elseif scenario:match("_denied$") then
    env.io = setmetatable({open = function(path, mode)
        if path:match("practice_copy%.json$") then error("denied") end
        return io.open(path, mode)
    end}, {__index = io})
end
local script = (scenario == "copy" or exercise) and "aseprite_copy.lua" or "aseprite_paste.lua"
assert(loadfile(base .. "/scripts/" .. script, "t", env))()
assert(#console == 0, "successful shortcuts must not open a console")
local alert = type(alerts[1]) == "table" and alerts[1].text or alerts[1]
if exercise then
    assert(#app.fs.listFiles(root .. "/jobs") == 0, "practice is isolated from the regular inbox")
    local output = app.fs.filePath(target) .. "/copies"
    local expected = scenario:match("_stale$") and "practice"
        or scenario:match("_deleted$") and "missing"
        or scenario:match("_denied$") and "access"
    if expected or exercise == 2 then
        local diagnostic = json.decode(assert(read(root .. "/Ase-PS-Bridge/logs/aseprite_copy_diagnostic.json")))
        assert(diagnostic.code == (expected or "blank"))
        assert(#alerts == 1 and not app.fs.isDirectory(output))
    end
    if exercise == 2 then
        assert(#alerts == 1 and alert:match("frame 1 or 3"))
        assert(not app.fs.isDirectory(output))
    elseif not expected then
        assert(#alerts == 0, tostring(alert))
        local dirs = app.fs.listFiles(output)
        assert(#dirs == 1)
        local report = json.decode(assert(read(output .. "/" .. app.fs.fileName(dirs[1]) .. "/status_done.json")))
        assert(report.practice_frame == exercise and report.layer_count == 1)
        assert(report.practice_token == string.rep("1", 32))
    end
elseif scenario == "copy" then
    assert(#alerts == 0, tostring(alert))
    local dirs = app.fs.listFiles(root .. "/jobs")
    assert(#dirs == 1 and read(root .. "/jobs/" .. app.fs.fileName(dirs[1]) .. "/status_done.json"))
elseif scenario == "practice" or scenario == "ordinary" then
    assert(#alerts == 0, tostring(alert))
    assert(#sprite.layers == 1 and #sprite.frames == 1 and #sprite.cels == 1)
    local cel = sprite.cels[1]
    assert(cel.position.x == 13 and cel.position.y == 14)
    assert(cel.image.width == 6 and cel.image.height == 4)
    assert(app.pixelColor.rgbaR(cel.image:getPixel(0, 0)) == 116)
    if scenario == "practice" then
        assert(read(root .. "/job/aseprite_paste_done.txt") == string.rep("a", 32))
    else
        assert(not read(root .. "/job/aseprite_paste_done.txt"))
    end
else
    assert(#alerts == 1 and #sprite.cels == original_count and #sprite.frames == 1 and #sprite.layers == 1,
           tostring(alert) .. ": cel count " .. #sprite.cels)
    assert(original == (sprite.cels[1] and sprite.cels[1].image:getPixel(0, 0)))
    assert(not read(root .. "/job/aseprite_paste_done.txt"))
end
local result = assert(io.open(root .. "/passed.txt", "w"))
result:write("pass")
result:close()

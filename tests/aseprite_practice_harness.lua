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

local script = scenario == "copy" and "aseprite_copy.lua" or "aseprite_paste.lua"
assert(loadfile(base .. "/scripts/" .. script, "t", env))()
assert(#console == 0, "successful shortcuts must not open a console")
local alert = type(alerts[1]) == "table" and alerts[1].text or alerts[1]
if scenario == "copy" then
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

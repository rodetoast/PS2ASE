-- scripts/aseprite_paste.lua
-- Ase-PS Bridge Pro - Paste Action (Aseprite)

local function isJsonContainer(value)
    return type(value) == "table" or type(value) == "userdata"
end

local function decodeJson(str)
    if type(str) ~= "string" or not str:match("^%s*{") or type(json) ~= "table" or not json.decode then return nil end
    local ok, obj = pcall(json.decode, str)
    if ok and isJsonContainer(obj) then return obj end
end

local function readText(path)
    local file = io.open(path, "r")
    if not file then return nil end
    local value = file:read("*a")
    file:close()
    return value
end

local prefs = decodeJson(readText((os.getenv("APPDATA") or "") .. "/Ase-PS-Bridge/bridge_settings.json")) or {}
local notices = {
    ko = {"붙여넣을 문서를 열어 주세요.", "사용할 수 있는 복사본이 없습니다. Photoshop에서 다시 복사해 주세요.",
          "복사본 파일이 없거나 손상되었습니다. Photoshop에서 다시 복사해 주세요.",
          "가이드에서 연습 복사본을 먼저 준비해 주세요."},
    en = {"Open a destination document first.", "No usable copy. Copy again from Photoshop.",
          "The copy files are missing or damaged. Copy again from Photoshop.",
          "Prepare the practice copy in the setup guide first."},
    ja = {"貼り付け先のドキュメントを開いてください。", "使えるコピーがありません。Photoshop からコピーし直してください。",
          "コピーのファイルが見つからないか破損しています。Photoshop からコピーし直してください。",
          "初期設定ガイドで練習用のコピーを準備してください。"}
}

-- [표준 변환 정책 1] Bridge 백분율(0~100) -> Aseprite 스케일(0~255)
local function opacityPercentToAse255(value)
    local n = tonumber(value)
    if n == nil then n = 100 end
    
    if n <= 0 then return 0 end
    if n >= 100 then return 255 end
    
    -- 소수점 이하 오차(254.999...)를 안전하게 255로 반올림(+0.5 후 버림)
    return math.floor(n * 255 / 100 + 0.5)
end

local function showMessage(index)
    app.alert({ title="Photoshop ↔ Aseprite", text=(notices[prefs.language] or notices.en)[index] })
end

local spr = app.activeSprite
if not spr then
    showMessage(1)
    return
end

local function normalizePath(path)
    return path:gsub("\\", "/"):lower()
end

local filename = normalizePath(spr.filename or "")
local basename = filename:match("[^/]+$") or ""
local exercise = filename:match("/ps2ase%-paste%-(%x+)/paste practice%.png$")
local guideTarget = (exercise and #exercise == 32) or basename:match("^ps2ase%-paste%-%x+%.png$") ~= nil
local payload
local guideCount
if guideTarget then
    payload = decodeJson(readText(spr.filename .. ".ps2ase.json"))
    guideCount = payload and (payload.guide_layer_count or 1)
    local guideSize = guideCount == 1 and 32 or guideCount == 4 and 300
    if not payload or type(payload.guide_target) ~= "string" or normalizePath(payload.guide_target) ~= filename
        or payload.source_app ~= "photoshop" or type(payload.guide_nonce) ~= "string"
        or not payload.guide_nonce:match("^%x+$") or #payload.guide_nonce ~= 32
        or type(payload.guide_expires) ~= "number" or payload.guide_expires < os.time()
        or not guideSize or spr.width ~= guideSize or spr.height ~= guideSize then
        return showMessage(4)
    end
else
    local clipboardText = app.clipboard and app.clipboard.text or ""
    if type(clipboardText) ~= "string" or clipboardText == "" then
        local handle = io.popen("powershell.exe -NoProfile -Command \"Get-Clipboard\"")
        if handle then
            clipboardText = handle:read("*a")
            handle:close()
        end
    end
    payload = decodeJson(clipboardText)
end
if not payload or payload.signature ~= "ase_ps_bridge_payload" or (not guideTarget and payload.guide_target) then
    return showMessage(2)
end

local jobPath = payload.job_path
if type(jobPath) ~= "string" or jobPath == "" or jobPath:find("%z") then return showMessage(2) end

local metadata = decodeJson(readText(jobPath .. "/metadata.json"))
local elementsList, images, count = {}, {}, 0
local valid = pcall(function()
    local elements = metadata and (metadata.elements or metadata.layers)
    assert(isJsonContainer(elements) and #elements > 0)
    local frameMode = metadata.frame_mode or "normal"
    assert(frameMode == "normal" or frameMode == "folder_frames" or frameMode == "layer_frames")
    for i = 1, #elements do
        local el = elements[i]
        assert(isJsonContainer(el))
        elementsList[i] = el
        if frameMode ~= "normal" then
            local index = tonumber(el.frame_index)
            assert(index and index >= 0 and index < #elements and index == math.floor(index))
        end
        if el.type ~= "group" then
            local file = el.file
            assert(type(file) == "string" and file:match("^layers/[^/\\:%c]+%.png$"))
            local img = Image{ fromFile = jobPath .. "/" .. file }
            assert(img and img.width > 0 and img.height > 0)
            images[el] = img
            count = count + 1
        end
    end
end)
if not valid or count == 0 then return showMessage(3) end
if guideTarget and (count ~= guideCount or (metadata.frame_mode or "normal") ~= "normal") then return showMessage(4) end

local function recordGuidePaste()
    if not guideTarget then return end
    local f = io.open(jobPath .. "/aseprite_paste_done.txt", "w")
    if not f then return end
    f:write(payload.guide_nonce)
    f:close()
end

local function pasteTransaction(action)
    local ok = pcall(app.transaction, action)
    if not ok then showMessage(3) end
    return ok
end

-- Debug Logger
local function writeLog(msg)
    local f = io.open(jobPath .. "/debug_ase_paste.log", "a")
    if f then
        f:write(msg .. "\n")
        f:close()
    end
end
os.remove(jobPath .. "/debug_ase_paste.log")
writeLog("=== Aseprite Paste Debug Log ===")

local alignMode = "center"
if isJsonContainer(payload.settings) and payload.settings.align_mode then
    alignMode = payload.settings.align_mode
end

local frameMode = metadata.frame_mode or "normal"
if frameMode == "layer_frames" then
    local framesMap = {}
    local frameIndices = {}
    for i = 1, #elementsList do
        local el = elementsList[i]
        local frameIndex = tonumber(el.frame_index) or 0
        if not framesMap[frameIndex] then
            framesMap[frameIndex] = {}
            table.insert(frameIndices, frameIndex)
        end
        table.insert(framesMap[frameIndex], el)
    end

    table.sort(frameIndices)

    local function calculateLayerOffset(frameElements)
        local minX, minY, maxX, maxY
        for i = 1, #frameElements do
            local el = frameElements[i]
            if el.type ~= "group" and el.visible ~= false then
                local cx = tonumber(el.x) or 0
                local cy = tonumber(el.y) or 0
                local cRight = cx + (tonumber(el.width) or 0)
                local cBottom = cy + (tonumber(el.height) or 0)

                if not minX or cx < minX then minX = cx end
                if not minY or cy < minY then minY = cy end
                if not maxX or cRight > maxX then maxX = cRight end
                if not maxY or cBottom > maxY then maxY = cBottom end
            end
        end

        local offsetX, offsetY = 0, 0
        if minX ~= nil and alignMode ~= "absolute" then
            local contentWidth = maxX - minX
            local contentHeight = maxY - minY
            offsetX = math.floor((spr.width - contentWidth) / 2) - minX
            if alignMode == "ground_line" then
                offsetY = (math.floor(spr.height / 2) - contentHeight) - minY
            else
                offsetY = math.floor((spr.height - contentHeight) / 2) - minY
            end
        end
        return offsetX, offsetY
    end

    local importedCount = 0
    local startFrameNumber = (app.activeFrame and app.activeFrame.frameNumber) or 1

    if not pasteTransaction(function()
        local targetLayer = app.activeLayer
        if not targetLayer or targetLayer.isGroup then
            targetLayer = spr:newLayer()
        end

        for _, frameIndex in ipairs(frameIndices) do
            local frameElements = framesMap[frameIndex]
            local targetFrameNumber = startFrameNumber + frameIndex
            while #spr.frames < targetFrameNumber do
                spr:newFrame()
            end
            local targetFrame = spr.frames[targetFrameNumber]
            local offsetX, offsetY = calculateLayerOffset(frameElements)

            for i = 1, #frameElements do
                local el = frameElements[i]
                if el.type ~= "group" then
                    local importedImage = images[el]
                    do
                        if importedImage then
                            local existingCel = targetLayer:cel(targetFrame.frameNumber)
                            if existingCel then spr:deleteCel(existingCel) end

                            local finalX = (tonumber(el.x) or 0) + offsetX
                            local finalY = (tonumber(el.y) or 0) + offsetY
                            if alignMode == "absolute" then
                                finalX = tonumber(el.x) or 0
                                finalY = tonumber(el.y) or 0
                            end

                            local newCel = spr:newCel(targetLayer, targetFrame, importedImage, Point(finalX, finalY))
                            newCel.opacity = opacityPercentToAse255(el.opacity)
                            importedCount = importedCount + 1
                            break
                        end
                    end
                end
            end
        end
    end) then return end

    app.refresh()

    if importedCount == 0 then showMessage(3) end
    return
end

if frameMode == "folder_frames" then
    local framesMap = {}
    local frameIndices = {}
    for i = 1, #elementsList do
        local el = elementsList[i]
        local frameIndex = tonumber(el.frame_index) or 0
        if not framesMap[frameIndex] then
            framesMap[frameIndex] = {}
            table.insert(frameIndices, frameIndex)
        end
        table.insert(framesMap[frameIndex], el)
    end

    table.sort(frameIndices)

    local function calculateOffset(frameElements)
        local minX, minY, maxX, maxY
        for i = 1, #frameElements do
            local el = frameElements[i]
            if el.type ~= "group" and el.visible ~= false then
                local cx = tonumber(el.x) or 0
                local cy = tonumber(el.y) or 0
                local cRight = cx + (tonumber(el.width) or 0)
                local cBottom = cy + (tonumber(el.height) or 0)

                if not minX or cx < minX then minX = cx end
                if not minY or cy < minY then minY = cy end
                if not maxX or cRight > maxX then maxX = cRight end
                if not maxY or cBottom > maxY then maxY = cBottom end
            end
        end

        local offsetX, offsetY = 0, 0
        if minX ~= nil and alignMode ~= "absolute" then
            local contentWidth = maxX - minX
            local contentHeight = maxY - minY
            offsetX = math.floor((spr.width - contentWidth) / 2) - minX
            if alignMode == "ground_line" then
                offsetY = (math.floor(spr.height / 2) - contentHeight) - minY
            else
                offsetY = math.floor((spr.height - contentHeight) / 2) - minY
            end
        end
        return offsetX, offsetY
    end

    local importedCount = 0
    local startFrameNumber = (app.activeFrame and app.activeFrame.frameNumber) or 1

    local framePixelRows = {}
    local maxRowCount = 0

    local function flattenPixelRows(frameElements)
        local treeMap = {}
        for i = 1, #frameElements do
            local el = frameElements[i]
            local pId = el.parent_id or "root"
            if not treeMap[pId] then treeMap[pId] = {} end
            table.insert(treeMap[pId], el)
        end

        for pId, children in pairs(treeMap) do
            table.sort(children, function(a, b)
                local idxA = tonumber(a.index) or 0
                local idxB = tonumber(b.index) or 0
                return idxA > idxB
            end)
        end

        local rows = {}
        local function walk(parentId)
            local children = treeMap[parentId]
            if not children then return end
            for i = 1, #children do
                local el = children[i]
                if el.type == "group" then
                    walk(el.id)
                else
                    table.insert(rows, el)
                end
            end
        end

        walk("root")
        return rows
    end

    for _, frameIndex in ipairs(frameIndices) do
        local rows = flattenPixelRows(framesMap[frameIndex])
        framePixelRows[frameIndex] = rows
        if #rows > maxRowCount then maxRowCount = #rows end
    end

    if not pasteTransaction(function()
        local flatLayers = {}
        local function collectFlat(layersCollection)
            for _, l in ipairs(layersCollection) do
                if not l.isGroup then table.insert(flatLayers, l) end
                if l.isGroup then collectFlat(l.layers) end
            end
        end
        collectFlat(spr.layers)

        local activeIdx = #flatLayers + 1
        if app.activeLayer and not app.activeLayer.isGroup then
            for i, l in ipairs(flatLayers) do
                if l == app.activeLayer then
                    activeIdx = i
                    break
                end
            end
        end

        local targetLayers = {}
        local firstFrameRows = framePixelRows[frameIndices[1]] or {}
        local insertAnchor = app.activeLayer

        local function placeBelowAnchor(layer, anchor)
            if not layer or not anchor then return end
            pcall(function()
                if layer.parent ~= anchor.parent then
                    layer.parent = anchor.parent
                end
                if anchor.stackIndex then
                    layer.stackIndex = anchor.stackIndex
                end
            end)
        end

        for rowIndex = 1, maxRowCount do
            local targetLayer = flatLayers[activeIdx - rowIndex + 1]
            if not targetLayer then
                targetLayer = spr:newLayer()
                local nameSource = firstFrameRows[rowIndex]
                targetLayer.name = (nameSource and nameSource.name) or ("Frame Row " .. tostring(rowIndex))
                placeBelowAnchor(targetLayer, insertAnchor)
            end
            insertAnchor = targetLayer
            targetLayers[rowIndex] = targetLayer
        end

        for _, frameIndex in ipairs(frameIndices) do
            local frameElements = framesMap[frameIndex]
            local rows = framePixelRows[frameIndex] or {}
            local targetFrameNumber = startFrameNumber + frameIndex
            while #spr.frames < targetFrameNumber do
                spr:newEmptyFrame()
            end
            local targetFrame = spr.frames[targetFrameNumber]
            local offsetX, offsetY = calculateOffset(frameElements)

            for rowIndex = 1, maxRowCount do
                local targetLayer = targetLayers[rowIndex]
                if targetLayer then
                    local oldCel = targetLayer:cel(targetFrame.frameNumber)
                    if oldCel then spr:deleteCel(oldCel) end
                end
            end

            for rowIndex = 1, #rows do
                local el = rows[rowIndex]
                local targetLayer = targetLayers[rowIndex]
                local importedImage = images[el]
                do
                    if importedImage and targetLayer then
                        local existingCel = targetLayer:cel(targetFrame.frameNumber)
                        if existingCel then spr:deleteCel(existingCel) end

                        local finalX = (tonumber(el.x) or 0) + offsetX
                        local finalY = (tonumber(el.y) or 0) + offsetY
                        if alignMode == "absolute" then
                            finalX = tonumber(el.x) or 0
                            finalY = tonumber(el.y) or 0
                        end

                        local newCel = spr:newCel(targetLayer, targetFrame, importedImage, Point(finalX, finalY))
                        newCel.opacity = opacityPercentToAse255(el.opacity)
                        importedCount = importedCount + 1
                    end
                end
            end
        end
    end) then return end

    app.refresh()

    if importedCount == 0 then showMessage(3) end
    return
end

local hasGroup = false
for i = 1, #elementsList do
    if elementsList[i].type == "group" then
        hasGroup = true
        break
    end
end

local minX, minY, maxX, maxY
for i = 1, #elementsList do
    local el = elementsList[i]
    if el.type ~= "group" and el.visible ~= false then
        local cx = tonumber(el.x) or 0
        local cy = tonumber(el.y) or 0
        local cRight = cx + (tonumber(el.width) or 0)
        local cBottom = cy + (tonumber(el.height) or 0)

        if not minX or cx < minX then minX = cx end
        if not minY or cy < minY then minY = cy end
        if not maxX or cRight > maxX then maxX = cRight end
        if not maxY or cBottom > maxY then maxY = cBottom end
    end
end

if minX == nil then
    for i = 1, #elementsList do
        local el = elementsList[i]
        if el.type ~= "group" then
            local cx = tonumber(el.x) or 0
            local cy = tonumber(el.y) or 0
            local cRight = cx + (tonumber(el.width) or 0)
            local cBottom = cy + (tonumber(el.height) or 0)

            if not minX or cx < minX then minX = cx end
            if not minY or cy < minY then minY = cy end
            if not maxX or cRight > maxX then maxX = cRight end
            if not maxY or cBottom > maxY then maxY = cBottom end
        end
    end
end

local offsetX, offsetY = 0, 0
if minX ~= nil and alignMode ~= "absolute" then
    local contentWidth = maxX - minX
    local contentHeight = maxY - minY
    local psCanvasW = (metadata.canvas_size and metadata.canvas_size.w) or contentWidth
    local psCanvasH = (metadata.canvas_size and metadata.canvas_size.h) or contentHeight
    
    offsetX = math.floor((spr.width - contentWidth) / 2) - minX
    if alignMode == "ground_line" then
        offsetY = (math.floor(spr.height / 2) - contentHeight) - minY
    else
        offsetY = math.floor((spr.height - contentHeight) / 2) - minY
    end
end

local importedCount = 0
local frame = app.activeFrame or 1

if not pasteTransaction(function()

    if not hasGroup then
        -- [분기 1] Flat Overwrite
        local flatLayers = {}
        local function collectFlat(layersCollection)
            for _, l in ipairs(layersCollection) do
                if not l.isGroup then table.insert(flatLayers, l) end
                if l.isGroup then collectFlat(l.layers) end
            end
        end
        collectFlat(spr.layers)

        local targetLayers = {}
        local activeIdx = #flatLayers
        if app.activeLayer and not app.activeLayer.isGroup then
            for i, l in ipairs(flatLayers) do
                if l == app.activeLayer then
                    activeIdx = i
                    break
                end
            end
        end

        local bottomIdx = activeIdx - #elementsList + 1
        if bottomIdx < 1 then bottomIdx = 1 end

        for i = 1, #elementsList do
            local l = flatLayers[bottomIdx + i - 1]
            if l then table.insert(targetLayers, l) end
        end

        for i = 1, #elementsList do
            local el = elementsList[i]
            local targetLayer = targetLayers[i]
            
            if not targetLayer then
                targetLayer = spr:newLayer()
            end
            
            local img = images[el]
            do
                if img then
                    -- Opacity 적용 및 디버그 로깅
                    local originalOpacity = el.opacity
                    local targetOpacity = opacityPercentToAse255(originalOpacity)
                    
                    local existingCel = targetLayer:cel(frame.frameNumber)
                    if existingCel then spr:deleteCel(existingCel) end
                    
                    local finalX = (tonumber(el.x) or 0) + offsetX
                    local finalY = (tonumber(el.y) or 0) + offsetY
                    if alignMode == "absolute" then
                        finalX = tonumber(el.x) or 0
                        finalY = tonumber(el.y) or 0
                    end
                    
                    local newCel = spr:newCel(targetLayer, frame, img, Point(finalX, finalY))
                    newCel.opacity = targetOpacity
                    writeLog(string.format("[Flat Layer %d] Name: %s | Opacity: raw %s -> converted %s -> applied to cel", i, el.name, tostring(originalOpacity), tostring(targetOpacity)))
                    
                    importedCount = importedCount + 1
                end
            end
        end

    else
        -- [분기 2] Hierarchy Reconstruct
        local treeMap = {}
        for i = 1, #elementsList do
            local el = elementsList[i]
            local pId = el.parent_id or "root"
            if not treeMap[pId] then treeMap[pId] = {} end
            table.insert(treeMap[pId], el)
        end

        for pId, children in pairs(treeMap) do
            table.sort(children, function(a, b)
                local idxA = tonumber(a.index) or 0
                local idxB = tonumber(b.index) or 0
                return idxA < idxB
            end)
        end

        local function buildHierarchy(parentId, targetParentObj)
            local children = treeMap[parentId]
            if not children then return end
            
            for i = 1, #children do
                local el = children[i]
                local newObj = nil
                
                if el.type == "group" then
                    newObj = spr:newGroup()
                    newObj.name = el.name
                    
                    -- Opacity 적용 및 디버그 로깅 (Group)
                    local originalOpacity = el.opacity
                    local targetOpacity = opacityPercentToAse255(originalOpacity)
                    newObj.opacity = targetOpacity
                    writeLog(string.format("[Hierarchy Group] Name: %s | Opacity (Bridge JSON 0-100): %s -> Aseprite (0-255): %s", el.name, tostring(originalOpacity), tostring(targetOpacity)))
                    
                    if targetParentObj ~= spr then newObj.parent = targetParentObj end
                    buildHierarchy(el.id, newObj)
                else
                    local importedImage = images[el]
                    do
                        if importedImage then
                            newObj = spr:newLayer()
                            newObj.name = el.name or "Layer"
                            
                            -- Opacity 적용 및 디버그 로깅 (Layer)
                            local originalOpacity = el.opacity
                            local targetOpacity = opacityPercentToAse255(originalOpacity)
                            
                            if targetParentObj ~= spr then newObj.parent = targetParentObj end
                            
                            local finalX = (tonumber(el.x) or 0) + offsetX
                            local finalY = (tonumber(el.y) or 0) + offsetY
                            if alignMode == "absolute" then
                                finalX = tonumber(el.x) or 0
                                finalY = tonumber(el.y) or 0
                            end
                            
                            local newCel = spr:newCel(newObj, frame, importedImage, Point(finalX, finalY))
                            newCel.opacity = targetOpacity
                            writeLog(string.format("[Hierarchy Layer] Name: %s | Opacity: raw %s -> converted %s -> applied to cel", el.name, tostring(originalOpacity), tostring(targetOpacity)))
                            
                            importedCount = importedCount + 1
                        end
                    end
                end
            end
        end

        buildHierarchy("root", spr)
    end
end) then return end

app.refresh()

if importedCount > 0 and (not guideTarget or importedCount == guideCount) then
    recordGuidePaste()
else
    showMessage(3)
end

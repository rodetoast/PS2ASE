-- scripts/aseprite_paste.lua
-- Ase-PS Bridge Pro - Paste Action (Aseprite)

local function decodeJson(str)
    if type(json) == "table" and json.decode then return json.decode(str) end
    local obj = {}
    obj.signature = str:match('"signature"%s*:%s*"([^"]+)"')
    obj.job_path = str:match('"job_path"%s*:%s*"([^"]+)"')
    return obj
end

-- [표준 변환 정책 1] Bridge 백분율(0~100) -> Aseprite 스케일(0~255)
local function opacityPercentToAse255(value)
    local n = tonumber(value)
    if n == nil then n = 100 end
    
    if n <= 0 then return 0 end
    if n >= 100 then return 255 end
    
    -- 소수점 이하 오차(254.999...)를 안전하게 255로 반올림(+0.5 후 버림)
    return math.floor(n * 255 / 100 + 0.5)
end

local function showMessage(msg)
    app.alert({ title="Bridge Paste", text=msg, buttons={"OK"} })
end

local spr = app.activeSprite
if not spr then
    showMessage("붙여넣기할 활성 문서가 없습니다. 새 문서를 열고 실행해주세요.")
    return
end

local clipboardText = ""
if app.clipboard and app.clipboard.text then
    clipboardText = app.clipboard.text
end

if not clipboardText or clipboardText == "" then
    local handle = io.popen("powershell.exe -NoProfile -Command \"Get-Clipboard\"")
    if handle then
        clipboardText = handle:read("*a")
        handle:close()
    end
end

if not clipboardText or clipboardText:match("^%s*$") then
    showMessage("클립보드가 비어있습니다. 포토샵에서 복사를 먼저 실행해주세요.")
    return
end

local payload = decodeJson(clipboardText)
if not payload or payload.signature ~= "ase_ps_bridge_payload" then return end

local jobPath = payload.job_path
if not jobPath then return end

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

local metaFile = io.open(jobPath .. "/metadata.json", "r")
if not metaFile then
    showMessage("임시 전송 데이터가 삭제되었거나 만료되었습니다.")
    return
end
local metaContent = metaFile:read("*all")
metaFile:close()

local metadata = nil
if type(json) == "table" and json.decode then
    metadata = json.decode(metaContent)
end

if not metadata then
    showMessage("메타데이터 파싱 실패.")
    return
end

local elementsList = metadata.elements or metadata.layers
if not elementsList or #elementsList == 0 then
    showMessage("붙여넣을 데이터가 없습니다.")
    return
end

local alignMode = "center"
if payload.settings and payload.settings.align_mode then
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

    app.transaction(function()
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
                    local fullImagePath = jobPath .. "/" .. el.file
                    local imgFile = io.open(fullImagePath, "rb")
                    if imgFile then
                        imgFile:close()
                        local importedImage = Image{ fromFile = fullImagePath }
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
    end)

    app.refresh()

    if importedCount > 0 then
        if app.statusBar then
            app.statusBar.text = importedCount .. "개 프레임 붙여넣기 완료"
        else
            print(importedCount .. "개 프레임 붙여넣기 완료")
        end
    else
        showMessage("레이어 프레임을 생성하지 못했습니다. 전송 데이터가 손상되었을 수 있습니다.")
    end
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

    app.transaction(function()
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
                local fullImagePath = jobPath .. "/" .. el.file
                local imgFile = io.open(fullImagePath, "rb")
                if imgFile then
                    imgFile:close()
                    local importedImage = Image{ fromFile = fullImagePath }
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
    end)

    app.refresh()

    if importedCount > 0 then
        if app.statusBar then
            app.statusBar.text = importedCount .. "개 항목 붙여넣기 완료"
        else
            print(importedCount .. "개 항목 붙여넣기 완료")
        end
    else
        showMessage("레이어를 생성하지 못했습니다. 전송 데이터가 손상되었을 수 있습니다.")
    end
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

app.transaction(function()

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
            
            local fullImagePath = jobPath .. "/" .. el.file
            local imgFile = io.open(fullImagePath, "rb")
            if imgFile then
                imgFile:close()
                local img = Image{ fromFile = fullImagePath }
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
                    local fullImagePath = jobPath .. "/" .. el.file
                    local imgFile = io.open(fullImagePath, "rb")
                    if imgFile then
                        imgFile:close()
                        local importedImage = Image{ fromFile = fullImagePath }
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
end)

app.refresh()

if importedCount > 0 then
    if app.statusBar then
        app.statusBar.text = importedCount .. "개 항목 붙여넣기 완료"
    else
        print(importedCount .. "개 항목 붙여넣기 완료")
    end
else
    showMessage("레이어를 생성하지 못했습니다. 전송 데이터가 손상되었을 수 있습니다.")
end

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
    local opened, file, reason = pcall(function()
        local handle, message = io.open(path, "rb")
        return handle, message
    end)
    if not opened then return nil, "access" end
    if not file then
        reason = tostring(reason or ""):lower()
        return nil, reason:find("permission", 1, true) and "access" or "missing"
    end
    local ok, value = pcall(file.read, file, "*a")
    pcall(file.close, file)
    if ok then return value end
    return nil, "access"
end

local profile = (os.getenv("APPDATA") or "") .. "/Ase-PS-Bridge"
local prefs = decodeJson(readText(profile .. "/bridge_settings.json")) or {}
local notices = {
    ko = {"붙여넣을 문서를 열어 주세요.", "사용할 수 있는 복사본이 없습니다. Photoshop에서 다시 복사해 주세요.",
          "복사본 파일이 없거나 손상되었습니다. Photoshop에서 다시 복사해 주세요."},
    en = {"Open a destination document first.", "No usable copy. Copy again from Photoshop.",
          "The copy files are missing or damaged. Copy again from Photoshop."},
    ja = {"貼り付け先のドキュメントを開いてください。", "使えるコピーがありません。Photoshop からコピーし直してください。",
          "コピーのファイルが見つからないか破損しています。Photoshop からコピーし直してください。"}
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

local practiceNotices = {
    ko = {
        ended = "이 연습 탭의 세션이 끝났습니다. 일반 붙여넣기는 작업 문서에서 사용하고, 연습하려면 가이드에서 새 문서를 열어 주세요.",
        expired = "연습 복사본이 만료됐습니다. 가이드에서 Photoshop 연습 레이어를 다시 복사해 주세요.",
        button_expired = "버튼 요청이 만료됐습니다. 가이드에서 ‘결과가 오지 않나요?’를 열고 F4를 다시 누르거나, 붙여넣기 버튼을 다시 눌러 주세요.",
        access = "연습 파일을 읽을 수 없습니다. Aseprite의 스크립트 파일 접근 안내를 확인하고 다시 시도해 주세요.",
        wrong_target = "현재 탭은 이 요청의 연습 문서가 아닙니다. 가이드에서 연 연습 탭을 선택해 주세요.",
        wrong_canvas = "연습 캔버스 크기가 바뀌었습니다. 가이드에서 만든 원래 연습 문서를 다시 열어 주세요.",
        choose_cel = "연습 문서의 첫 프레임에서 일반 레이어의 셀을 선택해 주세요.",
        invalid_copy = "연습 복사본을 사용할 수 없습니다. Photoshop에서 연습 레이어를 모두 선택하고 가이드에서 다시 복사해 주세요.",
    },
    en = {
        ended = "This practice tab’s session has ended. Paste into a work document, or open a fresh practice document from the guide.",
        expired = "The practice copy expired. Copy the Photoshop practice layers again from the guide.",
        button_expired = "The button request expired. Open ‘No result yet?’ in the guide and press F4 again, or retry the paste button.",
        access = "The practice file could not be read. Check Aseprite’s script file access prompt and try again.",
        wrong_target = "This is not the tab for this request. Select the practice tab opened from the guide.",
        wrong_canvas = "The practice canvas size changed. Reopen the original practice document from the guide.",
        choose_cel = "Select a cel on a regular layer in frame 1 of the practice document.",
        invalid_copy = "This practice copy cannot be used. Select all practice layers in Photoshop and copy again from the guide.",
    },
    ja = {
        ended = "この練習タブのセッションは終了しました。作業用の文書に貼り付けるか、ガイドから新しい練習文書を開いてください。",
        expired = "練習用コピーの期限が切れました。ガイドから Photoshop の練習レイヤーを再度コピーしてください。",
        button_expired = "ボタンの要求が期限切れです。ガイドの「結果が届かない場合」を開いて F4 を押すか、貼り付けボタンを押し直してください。",
        access = "練習ファイルを読めません。Aseprite のスクリプトのファイルアクセス許可を確認してください。",
        wrong_target = "この要求の練習タブではありません。ガイドで開いた練習タブを選んでください。",
        wrong_canvas = "練習用キャンバスのサイズが変わりました。ガイドから元の練習文書を開き直してください。",
        choose_cel = "練習文書のフレーム 1 で通常レイヤーのセルを選択してください。",
        invalid_copy = "練習用コピーを使えません。Photoshop で練習レイヤーをすべて選択してコピーし直してください。",
    },
}

local function normalizePath(path)
    return app.fs.normalizePath(path):gsub("\\", "/"):lower()
end

local spr = app.activeSprite
local filename = normalizePath(spr and spr.filename or "")
local basename = filename:match("[^/]+$") or ""
local exercise = filename:match("/ps2ase%-paste%-(%x+)/paste practice%.png$")
local guideTarget = basename == "paste practice.png" or basename:match("^ps2ase%-paste%-%x+%.png$") ~= nil

local function reject(code, message, fields)
    pcall(function()
        local f = io.open(profile .. "/logs/aseprite_paste_diagnostic.json", "w")
        if not f then return end
        fields = fields or {}
        fields.code, fields.document, fields.session = code, filename, exercise
        fields.width, fields.height = spr and spr.width, spr and spr.height
        local script = debug and debug.getinfo and debug.getinfo(1, "S")
        fields.script = script and script.source
        f:write(json.encode(fields))
        f:close()
    end)
    app.alert({title="Photoshop ↔ Aseprite", text=(practiceNotices[prefs.language] or practiceNotices.en)[message]})
end

local function isNonce(value)
    return type(value) == "string" and #value == 32 and value:match("^%x+$") ~= nil
end

local requestPath = profile .. "/guide_paste_request.json"
local request
if app.fs.isFile(requestPath) then
    local data, err = readText(requestPath)
    if err == "access" then return reject("request_access", "access") end
    request = decodeJson(data)
    if data and not request then return reject("request_json", "invalid_copy") end
    if request and type(request.expires) ~= "number" then return reject("request_expiry", "invalid_copy") end
    if request and request.expires < os.time() then
        if guideTarget and type(request.target) == "string" and normalizePath(request.target) == filename then
            return reject("button_expired", "button_expired")
        end
        request = nil
    end
end
if request and (not guideTarget or type(request.target) ~= "string" or normalizePath(request.target) ~= filename) then
    return reject("button_wrong_target", "wrong_target")
end
if not spr then return showMessage(1) end

local payload
local guideCount
if guideTarget then
    local data, err = readText(spr.filename .. ".ps2ase.json")
    if not data then return reject("sidecar_" .. (err or "missing"), err == "access" and "access" or "ended") end
    payload = decodeJson(data)
    if not payload then return reject("sidecar_json", "invalid_copy") end
    if type(payload.guide_target) ~= "string" or normalizePath(payload.guide_target) ~= filename then
        return reject("target_mismatch", "wrong_target", {expected = payload.guide_target, path_equal = false})
    end
    if not isNonce(payload.guide_session) or not isNonce(exercise) or payload.guide_session ~= exercise then
        return reject("session_mismatch", "ended")
    end
    if payload.source_app ~= "photoshop" or not isNonce(payload.guide_nonce)
        or type(payload.guide_expires) ~= "number" then
        return reject("sidecar_contract", "invalid_copy")
    end
    if payload.guide_expires < os.time() then return reject("expired", "expired", {expires = payload.guide_expires}) end
    if request and request.nonce ~= payload.guide_nonce then return reject("request_stale", "invalid_copy") end
    guideCount = payload.guide_layer_count
    local guideSize = guideCount == 1 and 32 or guideCount == 4 and 300
    if not guideSize then return reject("layer_count_contract", "invalid_copy", {expected_count = guideCount}) end
    if spr.width ~= guideSize or spr.height ~= guideSize then
        return reject("canvas_mismatch", "wrong_canvas", {expected_size = guideSize})
    end
    if not app.activeFrame or app.activeFrame.frameNumber ~= 1 or not app.activeLayer or app.activeLayer.isGroup then
        return reject("cel_selection", "choose_cel")
    end
else
    local clipboardText = app.clipboard and app.clipboard.text or ""
    if type(clipboardText) ~= "string" or clipboardText == "" then
        local opened, handle = pcall(function()
            local pipe = io.popen("powershell.exe -NoProfile -Command \"Get-Clipboard\"")
            return pipe
        end)
        if opened and handle then
            clipboardText = handle:read("*a")
            handle:close()
        end
    end
    payload = decodeJson(clipboardText)
end
if not payload or payload.signature ~= "ase_ps_bridge_payload" or (not guideTarget and payload.guide_target) then
    if guideTarget then return reject("signature", "invalid_copy") end
    return showMessage(2)
end

local jobPath = payload.job_path
if type(jobPath) ~= "string" or jobPath == "" or jobPath:find("%z") then
    if guideTarget then return reject("job_path", "invalid_copy") end
    return showMessage(2)
end
if guideTarget and normalizePath(jobPath) ~= filename:match("^(.*)/ps2ase%-paste%-") .. "/guide_" .. payload.guide_nonce then
    return reject("job_scope", "invalid_copy")
end

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
if not valid or count == 0 then
    if guideTarget then return reject("copy_files", "invalid_copy") end
    return showMessage(3)
end
if guideTarget and (count ~= guideCount or (metadata.frame_mode or "normal") ~= "normal") then
    return reject("metadata_mismatch", "invalid_copy", {expected_count = guideCount, actual_count = count,
                  frame_mode = metadata.frame_mode or "normal"})
end

local function recordGuidePaste()
    if not guideTarget then return end
    pcall(function()
        local f = io.open(jobPath .. "/aseprite_paste_done.txt", "w")
        if not f then return end
        f:write(json.encode({nonce = payload.guide_nonce, method = request and "button" or "shortcut"}))
        f:close()
    end)
end

local function pasteTransaction(action)
    local ok = pcall(app.transaction, action)
    if not ok then showMessage(3) end
    return ok
end

-- Debug Logger
local function writeLog(msg)
    pcall(function()
        local f = io.open(jobPath .. "/debug_ase_paste.log", "a")
        if not f then return end
        f:write(msg .. "\n")
        f:close()
    end)
end
pcall(function() os.remove(jobPath .. "/debug_ase_paste.log") end)
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
elseif guideTarget then
    reject("import_count", "invalid_copy", {expected_count = guideCount, actual_count = importedCount})
else
    showMessage(3)
end

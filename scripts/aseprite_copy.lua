-- scripts/aseprite_copy.lua
-- Ase-PS Bridge Pro - Copy Action (Aseprite to Bridge)

local function encodeJson(obj)
    -- Aseprite 내장 json.encode 지원 시 사용
    if type(json) == "table" and json.encode then
        return json.encode(obj)
    end
    
    -- Fallback: 매우 단순화된 수동 JSON 직렬화 (단일 뎁스 테이블용)
    local function escapeStr(s)
        return '"' .. tostring(s):gsub('"', '\\"') .. '"'
    end
    
    local parts = {}
    table.insert(parts, "{")
    
    local firstKey = true
    for k, v in pairs(obj) do
        if not firstKey then table.insert(parts, ",") end
        firstKey = false
        
        table.insert(parts, escapeStr(k) .. ":")
        
        if type(v) == "table" then
            if #v > 0 or next(v) == nil then
                -- Array
                table.insert(parts, "[")
                for i, item in ipairs(v) do
                    if i > 1 then table.insert(parts, ",") end
                    if type(item) == "table" then
                        table.insert(parts, encodeJson(item)) -- 재귀
                    else
                        table.insert(parts, encodeJson(item)) -- 이 코드는 객체 배열 처리용으로 작성됨
                    end
                end
                table.insert(parts, "]")
            else
                -- Dict (canvas_size 등)
                table.insert(parts, "{")
                local firstSub = true
                for subK, subV in pairs(v) do
                    if not firstSub then table.insert(parts, ",") end
                    firstSub = false
                    table.insert(parts, escapeStr(subK) .. ":" .. tostring(subV))
                end
                table.insert(parts, "}")
            end
        elseif type(v) == "string" then
            table.insert(parts, escapeStr(v))
        elseif type(v) == "boolean" then
            table.insert(parts, v and "true" or "false")
        else
            table.insert(parts, tostring(v))
        end
    end
    table.insert(parts, "}")
    return table.concat(parts)
end

local spr = app.activeSprite
if not spr then
    return app.alert("복사할 활성 문서가 없습니다.")
end

-- 1. 선택된 레이어 및 그룹(폴더) 수집
-- Aseprite의 app.range.layers는 선택된 레이어들의 배열입니다.
-- 기존에는 폴더를 무시했지만, 이제 폴더도 계층 구조 복원을 위해 수집 대상에 포함합니다.
local selLayers = {}
local hasSelection = false

if app.range and app.range.layers then
    for _, l in ipairs(app.range.layers) do
        hasSelection = true
    end
end

if hasSelection then
    -- 전체 레이어를 순회하며 선택된 것들을 Bottom->Top 고정 순서로 수집
    -- (Aseprite의 layers 컬렉션은 폴더 내외를 구분하지 않고 플랫하게 가져올 수 있는 속성이 아니라
    -- 최상위 레이어부터 시작하는 트리입니다. spr.layers를 재귀 순회하며 선택 여부를 판단해야 합니다.)
    local function collectSelected(layersCollection)
        for _, l in ipairs(layersCollection) do
            local isSelected = false
            for _, selL in ipairs(app.range.layers) do
                if l == selL then isSelected = true break end
            end
            if isSelected and not l.isReference then
                table.insert(selLayers, l)
            end
            if l.isGroup then
                collectSelected(l.layers)
            end
        end
    end
    collectSelected(spr.layers)
else
    -- 단일 선택
    if app.activeLayer and not app.activeLayer.isReference then
        table.insert(selLayers, app.activeLayer)
    else
        return app.alert("복사할 레이어/그룹을 선택해주세요 (레퍼런스 제외).")
    end
end

if #selLayers == 0 then
    return app.alert("선택된 영역에 유효한 레이어나 그룹이 없습니다.")
end

local frame = app.activeFrame or 1

-- Verify guide copies against the active session, independently of the regular Bridge inbox.
local function normalized(path)
    local normalizedPath = app.fs.normalizePath(path):gsub("\\", "/")
    return (normalizedPath:gsub("[A-Z]", function(letter) return string.char(letter:byte() + 32) end))
end

local function readJson(path)
    local opened, file, reason = pcall(io.open, path, "rb")
    if not opened then return nil, "access_denied" end
    if not file then
        reason = tostring(reason or "unreadable")
        return nil, reason:lower():find("permission denied", 1, true) and "access_denied" or reason
    end
    local raw = file:read("*a")
    file:close()
    if type(json) ~= "table" or not json.decode then return nil, "json_unavailable" end
    local ok, parsed = pcall(json.decode, raw)
    if ok and (type(parsed) == "userdata" or type(parsed) == "table") then return parsed end
    return nil, "invalid_json"
end

local filename = spr.filename or ""
local documentName = app.fs.fileName(filename)
local folder = app.fs.filePath(filename)
local exerciseToken = app.fs.fileName(folder):lower():match("^ps2ase%-copy%-(%x+)$")
local exercise = documentName:lower() == "copy practice.aseprite" or exerciseToken ~= nil
local appdata = os.getenv("APPDATA")
local profile = appdata and app.fs.joinPath(appdata, "Ase-PS-Bridge")
local settingsPath = profile and app.fs.joinPath(profile, "bridge_settings.json")
local settings, settingsError
if settingsPath then settings, settingsError = readJson(settingsPath) end
local copyMessages = {
    ko = {
        settings = "Bridge 설정을 읽을 수 없습니다. Bridge를 열거나 다시 시작한 뒤 복사해 주세요.",
        output = "Bridge의 복사 저장 위치가 설정되지 않았습니다. Bridge를 다시 시작한 뒤 복사해 주세요.",
        practice = "현재 가이드가 준비한 연습 파일이 아닙니다. 가이드에서 새 연습 파일을 열고 다시 복사해 주세요.",
        missing = "이 연습 파일을 디스크에서 읽을 수 없습니다. 가이드에서 새 파일을 준비해 다시 열어 주세요.",
        access = "연습 파일에 접근할 수 없습니다. 스크립트 사용을 허용했는지 확인하고 가이드에서 연습 파일을 다시 열어 주세요.",
        blank = "이 프레임에는 복사할 픽셀이 없습니다. 연습 파일의 1번 또는 3번 프레임에서 그림이 있는 셀을 선택하고 다시 복사하세요.",
        selection = "선택한 프레임에서 그림이 있는 셀을 선택하고 다시 복사하세요.",
        write = "복사 파일을 저장할 수 없습니다. Bridge의 저장 위치와 파일 접근 권한을 확인해 주세요.",
    },
    en = {
        settings = "Bridge settings could not be read. Open or restart Bridge, then copy again.",
        output = "Bridge has no copy destination configured. Restart Bridge, then copy again.",
        practice = "This is not the current practice file. Open a fresh file from the guide and copy again.",
        missing = "The practice file cannot be read from disk. Prepare a new file in the guide and reopen it.",
        access = "The script cannot access the practice file. Check script permission and reopen the file from the guide.",
        blank = "There are no pixels to copy here. Select a painted cel in frame 1 or 3 and copy again.",
        selection = "Select a painted cel in the active frame and copy again.",
        write = "Could not save the copy. Check the Bridge output folder and file access permissions.",
    },
    ja = {
        settings = "Bridge の設定を読み込めません。Bridge を開くか再起動してからコピーしてください。",
        output = "Bridge のコピー先が設定されていません。Bridge を再起動してからコピーしてください。",
        practice = "現在の練習ファイルではありません。ガイドから新しいファイルを開いてコピーしてください。",
        missing = "練習ファイルをディスクから読み込めません。ガイドで新しいファイルを用意して開き直してください。",
        access = "スクリプトが練習ファイルにアクセスできません。許可を確認してガイドから開き直してください。",
        blank = "コピーできるピクセルがありません。フレーム 1 または 3 の絵があるセルを選び、もう一度コピーしてください。",
        selection = "現在のフレームで絵があるセルを選び、もう一度コピーしてください。",
        write = "コピーを保存できません。保存先とファイルのアクセス権限を確認してください。",
    }
}
local windowsKorean = os.getenv("LANG") and os.getenv("LANG"):lower():match("^ko")
local messages = copyMessages[settings and settings.language] or (windowsKorean and copyMessages.ko or copyMessages.en)
local baseTempPath = settings and settings.active_temp_path
local probeExists, nativeExists
local scriptSource = debug and debug.getinfo and debug.getinfo(1, "S").source or ""

local function reject(code, reason)
    -- Logging is best-effort and must not replace the actionable error.
    pcall(function()
        if not profile or not app.fs.isDirectory(app.fs.joinPath(profile, "logs")) then return end
        local report = app.fs.joinPath(profile, "logs", "aseprite_copy_diagnostic.json")
        local file = io.open(report, "w")
        if not file then return end
        file:write(encodeJson({ code = code, reason = reason or "", document = filename,
                               normalized_document = normalized(filename), token = exerciseToken or "",
                               host_is_file = nativeExists, readable = probeExists,
                               script = scriptSource, profile = profile, settings = settingsPath or "",
                               settings_status = settings and "read" or (settingsError or "missing_appdata"),
                               active_temp_path = type(baseTempPath) == "string" and baseTempPath or "",
                               host_version = tostring(app.version) }))
        file:close()
    end)
    return app.alert(messages[code])
end

if exercise then
    if not exerciseToken or #exerciseToken ~= 32 or documentName:lower() ~= "copy practice.aseprite" then
        return reject("practice", "document_identity")
    end
    local closedMarker = app.fs.filePath(folder) .. ".ps2ase-copy-" .. exerciseToken .. ".closed"
    if app.fs.isFile(closedMarker) then return reject("practice", "session_closed") end
    local session, sessionError = readJson(app.fs.joinPath(folder, "practice_copy.json"))
    if not session then
        return reject(sessionError == "access_denied" and "access" or "practice", sessionError)
    end
    if session.token ~= exerciseToken or type(session.document) ~= "string"
        or normalized(session.document) ~= normalized(filename) then
        return reject("practice", "session_mismatch")
    end
    local expected = app.fs.normalizePath(session.document)
    local statOK, exists = pcall(function() return app.fs.isFile(filename) or app.fs.isFile(expected) end)
    nativeExists = statOK and exists == true
    if not nativeExists then
        local opened, file, reason = pcall(io.open, expected, "rb")
        probeExists = opened and file ~= nil
        if probeExists then file:close() end
        local denied = not opened or tostring(reason):lower():find("permission denied", 1, true)
        if not probeExists then return reject(denied and "access" or "missing", "document_stat") end
    end
    baseTempPath = app.fs.joinPath(folder, "copies")
elseif not settings then
    return reject("settings", settingsError)
elseif type(baseTempPath) ~= "string" or baseTempPath == "" then
    return reject("output", "active_temp_path_missing")
end
local timestamp = os.date("%Y%m%d_%H%M%S")
local jobDirName, jobPath
repeat
    jobDirName = (exercise and "copy_" or ("bridge_job_" .. timestamp .. "_")) .. math.random(1000, 99999999)
    jobPath = app.fs.joinPath(baseTempPath, jobDirName)
until not app.fs.isDirectory(jobPath)
local layersPath = app.fs.joinPath(jobPath, "layers")

-- 3. 재귀적 스캔 및 추출 (Bottom -> Top 순서로 index 부여)
local elementsList = {}
local idCounter = 0
local extractedPixCount = 0
local exportFailed = false

-- 객체의 고유 ID를 기억하기 위한 캐시 (부모 ID 찾기용)
local idCache = {}

local function traverseItems(items, parentId)
    local localIndex = 0
    
    -- Aseprite는 Bottom -> Top 정방향 순회
    for i = 1, #items do
        if exportFailed then return end
        local item = items[i]
        
        -- 현재 item이 사용자가 선택한 selLayers에 포함되는지 확인
        -- (그룹 전체를 선택했을 때는 자식들도 다 추출해야 하므로 논리가 복잡해집니다.
        -- 직관적이고 완벽한 재구성을 위해, Aseprite에서는 "선택된 항목"을 루트로 삼아 파고들거나,
        -- 단순히 selLayers에 포함된 것들의 계층을 구성합니다.)
        local isTarget = false
        for _, sel in ipairs(selLayers) do
            if item == sel then isTarget = true break end
        end
        
        -- 부모가 복사 대상이거나, 나 자신이 복사 대상일 때만 처리 (부분 선택 지원)
        if isTarget then
            local currentId = "item_" .. idCounter
            idCounter = idCounter + 1
            idCache[item] = currentId
            
            if item.isGroup then
                -- 폴더 처리
                table.insert(elementsList, {
                    id = currentId,
                    type = "group",
                    name = item.name,
                    parent_id = parentId,
                    index = localIndex,
                    opacity = math.floor(((tonumber(item.opacity) or 255) / 255) * 100 + 0.5),
                    visible = item.isVisible
                })
                localIndex = localIndex + 1
                
                -- 자식 순회 (재귀)
                traverseItems(item.layers, currentId)
                
            else
                -- 일반 픽셀 레이어 처리
                local cel = item:cel(frame.frameNumber)
                if cel and cel.image and not cel.image:isEmpty() then
                    if extractedPixCount == 0 then
                        app.fs.makeAllDirectories(jobPath)
                        if not app.fs.isDirectory(layersPath) then app.fs.makeDirectory(layersPath) end
                        if not app.fs.isDirectory(layersPath) then
                            exportFailed = true
                            return
                        end
                    end
                    local bounds = cel.bounds
                    
                    local croppedImg = Image(bounds.width, bounds.height, spr.colorMode)
                    croppedImg:clear()
                    croppedImg:drawImage(cel.image, 0, 0)
                    
                    local fileName = "layer_" .. extractedPixCount .. ".png"
                    local fullPngPath = app.fs.joinPath(layersPath, fileName)
                    
                    croppedImg:saveAs(fullPngPath)
                    if not app.fs.isFile(fullPngPath) then
                        exportFailed = true
                        return
                    end
                    
                    table.insert(elementsList, {
                        id = currentId,
                        type = "layer",
                        name = item.name,
                        parent_id = parentId,
                        index = localIndex,
                        x = bounds.x,
                        y = bounds.y,
                        width = bounds.width,
                        height = bounds.height,
                        opacity = math.floor(((tonumber(item.opacity) or 255) / 255) * 100 + 0.5),
                        visible = item.isVisible,
                        file = "layers/" .. fileName
                    })
                    
                    localIndex = localIndex + 1
                    extractedPixCount = extractedPixCount + 1
                end
            end
        elseif item.isGroup then
            -- 나 자신은 선택되지 않았지만, 내 자식 중에 선택된 것이 있을 수 있으므로 파고듦
            -- 이 경우 나는 출력되지 않지만 자식들은 내 위쪽 부모(parentId)에 붙게 됨
            traverseItems(item.layers, parentId)
        end
    end
end

-- 4. 최상단부터 순회 시작
traverseItems(spr.layers, nil)

if exportFailed then return reject("write", "layer_export") end
if extractedPixCount == 0 then
    return reject(exercise and "blank" or "selection", "no_pixels")
end

-- 5. 메타데이터 구성 (v1.1 스키마)
local metadata = {
    version = "1.1",
    job_id = jobDirName,
    source_app = "aseprite",
    target_app = "photoshop",
    timestamp = timestamp,
    document_name = documentName ~= "" and documentName or "Untitled",
    canvas_size = { w = spr.width, h = spr.height },
    element_count = #elementsList,
    elements = elementsList,
    -- 하위 호환성을 위한 임시 레이어 배열
    layer_count = extractedPixCount,
    layers = {}
}

for i = 1, #elementsList do
    if elementsList[i].type == "layer" then
        table.insert(metadata.layers, elementsList[i])
    end
end

local metaFile = io.open(jobPath .. "/metadata.json", "w")
if metaFile then
    metaFile:write(encodeJson(metadata))
    metaFile:close()
end

-- 6. Python Daemon용 트리거 파일 생성
local payload = {
    signature = "ase_ps_bridge_payload",
    version = "1.1",
    job_id = jobDirName,
    source_app = "aseprite",
    target_app = "photoshop",
    job_path = jobPath,
    summary = {
        layer_count = extractedPixCount,
        element_count = #elementsList,
        document_name = metadata.document_name
    },
    timestamp = timestamp
}

local triggerFile = io.open(jobPath .. "/trigger_copy.json", "w")
if triggerFile then
    triggerFile:write(encodeJson(payload))
    triggerFile:close()
end

local doneData = {
    job_id = jobDirName,
    status = "done",
    layer_count = extractedPixCount,
    element_count = #elementsList,
    timestamp = timestamp
}
if exercise then
    doneData.practice_token = exerciseToken
    doneData.practice_path = filename
    doneData.practice_frame = frame.frameNumber
end

local doneFile = io.open(jobPath .. "/status_done.json", "w")
if doneFile then
    doneFile:write(encodeJson(doneData))
    doneFile:close()
end

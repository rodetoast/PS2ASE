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

-- Guide copies live next to their own exercise rather than in the Bridge clipboard inbox.
local filename = spr.filename or ""
local documentName = app.fs.fileName(filename)
local folder = app.fs.filePath(filename)
local exerciseToken = app.fs.fileName(folder):lower():match("^ps2ase%-copy%-(%x+)$")
local exercise = exerciseToken and #exerciseToken == 32 and documentName:lower() == "copy practice.aseprite"
local settings = nil
local appdata = os.getenv("APPDATA")
if appdata and type(json) == "table" then
    local f = io.open(appdata .. "/Ase-PS-Bridge/bridge_settings.json", "r")
    if f then
        local ok, decoded = pcall(json.decode, f:read("*a"))
        f:close()
        if ok and (type(decoded) == "userdata" or type(decoded) == "table") then settings = decoded end
    end
end
local copyMessages = {
    ko = {"먼저 Bridge를 열어 주세요. 복사 결과를 받을 위치가 아직 설정되지 않았습니다.",
          "이 프레임에는 복사할 픽셀이 없습니다. 연습 파일의 1번 또는 3번 프레임에서 그림이 있는 셀을 선택하고 다시 복사하세요.",
          "선택한 프레임에서 그림이 있는 셀을 선택하고 다시 복사하세요.",
          "복사 파일을 저장할 수 없습니다. Bridge의 저장 위치와 파일 접근 권한을 확인해 주세요."},
    en = {"Open Bridge first so there is a place to receive copies.",
          "There are no pixels to copy here. Select a painted cel in frame 1 or 3 and copy again.",
          "Select a painted cel in the active frame and copy again.",
          "Could not save the copy. Check the Bridge output folder and file access permissions."},
    ja = {"先に Bridge を起動してコピー結果の保存先を準備してください。",
          "コピーできるピクセルがありません。フレーム 1 または 3 の絵があるセルを選び、もう一度コピーしてください。",
          "現在のフレームで絵があるセルを選び、もう一度コピーしてください。",
          "コピーを保存できません。保存先とファイルのアクセス権限を確認してください。"}
}
local messages = copyMessages[settings and settings.language] or copyMessages.en
local baseTempPath = settings and settings.active_temp_path
if exercise then
    if not app.fs.isFile(filename) then return app.alert(messages[1]) end
    baseTempPath = app.fs.joinPath(folder, "copies")
end
if type(baseTempPath) ~= "string" or baseTempPath == "" then return app.alert(messages[1]) end
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

if exportFailed then return app.alert(messages[4]) end
if extractedPixCount == 0 then
    return app.alert(messages[exercise and 2 or 3])
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

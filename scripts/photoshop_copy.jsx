// scripts/photoshop_copy.jsx
// Ase-PS Bridge Pro - Copy Action (Photoshop to Bridge)
// 지원: Layer/Group 계층(Tree) 구조 완벽 전송 및 파일 시스템 기반 상태 통신

// ==========================================
// [동적 변수 주입 영역] 
// 파이썬 데몬(Bridge UI)이 실행 시점에 아래 변수들을 실제 값으로 치환하여 
// 이 스크립트를 감싸는 래퍼(Wrapper) 스크립트를 생성합니다.
// ==========================================
var JOB_PATH = "REPLACE_ME_JOB_PATH";
var ALIGN_MODE = "REPLACE_ME_ALIGN_MODE"; // Copy 시점에서는 당장 안 쓰지만 미래 확장을 위해 보존
var FRAME_MODE = "REPLACE_ME_FRAME_MODE";

#target photoshop
app.preferences.rulerUnits = Units.PIXELS;

function main() {
    if (app.documents.length === 0) {
        writeStatusError("복사할 활성 문서가 없습니다. 문서를 열고 실행해주세요.");
        return;
    }
    var originalDoc = app.activeDocument;

    // Job 폴더 경로 (파이썬이 만들어둔 폴더를 그대로 사용)
    var jobFolder = new Folder(JOB_PATH);
    if (!jobFolder.exists) {
        writeStatusError("지정된 Job 폴더가 존재하지 않습니다: " + JOB_PATH);
        return;
    }

    var layersFolder = new Folder(jobFolder + "/layers");
    if (!layersFolder.exists) layersFolder.create();

    if (FRAME_MODE === "folder_frames") {
        runFolderFramesCopy(originalDoc, jobFolder, layersFolder);
        return;
    }

    runNormalCopy(originalDoc, jobFolder, layersFolder);
}

function runNormalCopy(originalDoc, jobFolder, layersFolder) {
    // 1. 선택된 레이어/폴더들을 새로운 임시 문서로 복제 (안전한 추출)
    try {
        var desc = new ActionDescriptor();
        var ref = new ActionReference();
        ref.putClass(charIDToTypeID("Dcmn"));
        desc.putReference(charIDToTypeID("null"), ref);
        desc.putString(charIDToTypeID("Nm  "), "TempBridgeDoc");
        var ref2 = new ActionReference();
        ref2.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        desc.putReference(charIDToTypeID("Usng"), ref2);
        executeAction(charIDToTypeID("Mk  "), desc, DialogModes.NO);
    } catch (e) {
        writeStatusError("선택된 레이어나 그룹이 없습니다. 전송할 대상을 선택한 후 다시 실행해주세요.\n(원본 에러: " + e.toString() + ")");
        return;
    }

    var tempDoc = app.activeDocument;
    
    // 개별 레이어의 bounds는 마스크/이펙트로 인해 부정확하므로 문서 전체를 Trim
    try {
        tempDoc.trim(TrimType.TRANSPARENT);
    } catch(e) {
        writeStatusError("추출 가능한 픽셀 레이어가 없거나 완전히 투명합니다.");
        tempDoc.close(SaveOptions.DONOTSAVECHANGES);
        app.activeDocument = originalDoc;
        return;
    }

    var contentW = tempDoc.width.as("px");
    var contentH = tempDoc.height.as("px");

    var elementsList = [];
    var idCounter = 0;
    var extractedPixCount = 0;

    // 2. 재귀적 스캔 및 추출 함수
    function traverseItems(items, parentId) {
        var localIndex = 0;
        for (var i = items.length - 1; i >= 0; i--) {
            var item = items[i];
            var currentId = "item_" + idCounter++;
            
            if (item.typename === "LayerSet") {
                elementsList.push({
                    id: currentId,
                    type: "group",
                    name: item.name,
                    parent_id: parentId,
                    index: localIndex++,
                    opacity: Math.round(item.opacity),
                    visible: item.visible
                });
                traverseItems(item.layers, currentId);
            } else if (item.typename === "ArtLayer") {
                if (item.bounds[2].as("px") - item.bounds[0].as("px") <= 0) continue;
                
                var fileName = "layer_" + extractedPixCount + ".png";
                var pngPath = layersFolder + "/" + fileName;
                
                exportLayerAsPNG(tempDoc, item, pngPath, contentW, contentH);
                
                elementsList.push({
                    id: currentId,
                    type: "layer",
                    name: item.name,
                    parent_id: parentId,
                    index: localIndex++,
                    x: 0,
                    y: 0,
                    width: contentW,
                    height: contentH,
                    opacity: Math.round(item.opacity),
                    visible: item.visible,
                    file: "layers/" + fileName
                });
                extractedPixCount++;
            }
        }
    }

    // 3. 추출 실행
    traverseItems(tempDoc.layers, null);

    tempDoc.close(SaveOptions.DONOTSAVECHANGES);
    app.activeDocument = originalDoc;

    if (elementsList.length === 0) {
        writeStatusError("추출 가능한 그룹이나 픽셀 레이어가 없습니다.");
        return;
    }

    // 4. 메타데이터 구성 (v1.1 스키마)
    var timestamp = getFormattedDate();
    var metadata = {
        "version": "1.1",
        "job_id": jobFolder.name,
        "source_app": "photoshop",
        "target_app": "aseprite",
        "timestamp": timestamp,
        "document_name": originalDoc.name,
        "canvas_size": { "w": originalDoc.width.as("px"), "h": originalDoc.height.as("px") },
        "element_count": elementsList.length,
        "elements": elementsList,
        "layer_count": extractedPixCount,
        "layers": []
    };
    
    for (var k = 0; k < elementsList.length; k++) {
        if (elementsList[k].type === "layer") metadata.layers.push(elementsList[k]);
    }

    saveJSON(jobFolder + "/metadata.json", metadata);

    // 5. 트리거 및 완료 상태 파일 생성 (파이썬 데몬 폴링용)
    var payload = {
        "signature": "ase_ps_bridge_payload",
        "version": "1.1",
        "job_id": jobFolder.name,
        "source_app": "photoshop",
        "target_app": "aseprite",
        "job_path": jobFolder.fsName.replace(/\\/g, "/"),
        "summary": {
            "layer_count": extractedPixCount,
            "element_count": elementsList.length,
            "document_name": originalDoc.name
        },
        "settings": {
            "align_mode": ALIGN_MODE
        },
        "timestamp": timestamp
    };
    saveJSON(jobFolder + "/trigger_copy.json", payload);

    // 성공 상태 파일 생성
    var doneData = {
        "job_id": jobFolder.name,
        "status": "success",
        "layer_count": extractedPixCount,
        "element_count": elementsList.length,
        "timestamp": timestamp
    };
    saveJSON(jobFolder + "/status_done.json", doneData);
}

function runFolderFramesCopy(originalDoc, jobFolder, layersFolder) {
    var selectedIds = getSelectedLayerIds();
    if (selectedIds.length === 0) {
        writeStatusError("Folder → Frames 모드에서는 top-level 폴더 안의 레이어 또는 그룹을 선택해야 합니다.");
        return;
    }

    var selectedMap = {};
    for (var i = 0; i < selectedIds.length; i++) {
        selectedMap[selectedIds[i]] = true;
    }

    var frameGroups = [];
    for (var t = 0; t < originalDoc.layers.length; t++) {
        var topItem = originalDoc.layers[t];
        if (topItem.typename !== "LayerSet") {
            continue;
        }

        var folderSelected = false;
        if (selectedMap[topItem.id]) {
            folderSelected = true;
            delete selectedMap[topItem.id];
        }

        var childSelectionIds = [];
        collectSelectedIdsInFolder(topItem.layers, selectedMap, childSelectionIds);

        if (folderSelected || childSelectionIds.length > 0) {
            frameGroups.push({
                folder: topItem,
                ids: childSelectionIds.length > 0 ? childSelectionIds : [topItem.id]
            });
        }
    }

    for (var key in selectedMap) {
        if (selectedMap.hasOwnProperty(key)) {
            writeStatusError("Folder → Frames 모드에서는 선택 항목이 모두 top-level 폴더 안에 있어야 합니다. 폴더 밖 레이어 선택을 해제해 주세요.");
            return;
        }
    }

    if (frameGroups.length === 0) {
        writeStatusError("Folder → Frames 모드에서 선택된 레이어가 들어있는 top-level 폴더를 찾지 못했습니다.");
        return;
    }

    var elementsList = [];
    var idCounter = 0;
    var extractedPixCount = 0;

    function traverseFrameItems(doc, items, parentId, frameIndex, contentW, contentH) {
        var localIndex = 0;
        for (var i = items.length - 1; i >= 0; i--) {
            var item = items[i];
            var currentId = "item_" + idCounter++;

            if (item.typename === "LayerSet") {
                elementsList.push({
                    id: currentId,
                    type: "group",
                    name: item.name,
                    parent_id: parentId,
                    index: localIndex++,
                    frame_index: frameIndex,
                    opacity: Math.round(item.opacity),
                    visible: item.visible
                });
                traverseFrameItems(doc, item.layers, currentId, frameIndex, contentW, contentH);
            } else if (item.typename === "ArtLayer") {
                if (item.bounds[2].as("px") - item.bounds[0].as("px") <= 0) continue;

                var fileName = "layer_" + extractedPixCount + ".png";
                var pngPath = layersFolder + "/" + fileName;

                exportLayerAsPNG(doc, item, pngPath, contentW, contentH);

                elementsList.push({
                    id: currentId,
                    type: "layer",
                    name: item.name,
                    parent_id: parentId,
                    index: localIndex++,
                    frame_index: frameIndex,
                    x: 0,
                    y: 0,
                    width: contentW,
                    height: contentH,
                    opacity: Math.round(item.opacity),
                    visible: item.visible,
                    file: "layers/" + fileName
                });
                extractedPixCount++;
            }
        }
    }

    for (var f = 0; f < frameGroups.length; f++) {
        app.activeDocument = originalDoc;
        selectLayerIds(frameGroups[f].ids);

        try {
            var desc = new ActionDescriptor();
            var ref = new ActionReference();
            ref.putClass(charIDToTypeID("Dcmn"));
            desc.putReference(charIDToTypeID("null"), ref);
            desc.putString(charIDToTypeID("Nm  "), "TempBridgeFrameDoc");
            var ref2 = new ActionReference();
            ref2.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
            desc.putReference(charIDToTypeID("Usng"), ref2);
            executeAction(charIDToTypeID("Mk  "), desc, DialogModes.NO);
        } catch (dupErr) {
            writeStatusError("선택된 폴더를 임시 문서로 복제하지 못했습니다.\n(원본 에러: " + dupErr.toString() + ")");
            app.activeDocument = originalDoc;
            return;
        }

        var tempDoc = app.activeDocument;
        try {
            tempDoc.trim(TrimType.TRANSPARENT);
        } catch(trimErr) {
            tempDoc.close(SaveOptions.DONOTSAVECHANGES);
            app.activeDocument = originalDoc;
            writeStatusError("Folder → Frames 모드에서 추출 가능한 픽셀이 없는 선택이 있습니다: " + frameGroups[f].folder.name);
            return;
        }

        var contentW = tempDoc.width.as("px");
        var contentH = tempDoc.height.as("px");

        if (tempDoc.layers.length === 1 && tempDoc.layers[0].typename === "LayerSet" && tempDoc.layers[0].name === frameGroups[f].folder.name) {
            traverseFrameItems(tempDoc, tempDoc.layers[0].layers, null, f, contentW, contentH);
        } else {
            traverseFrameItems(tempDoc, tempDoc.layers, null, f, contentW, contentH);
        }

        tempDoc.close(SaveOptions.DONOTSAVECHANGES);
        app.activeDocument = originalDoc;
    }

    if (elementsList.length === 0) {
        writeStatusError("Folder → Frames 모드에서 추출 가능한 그룹이나 픽셀 레이어가 없습니다.");
        return;
    }

    var timestamp = getFormattedDate();
    var metadata = {
        "version": "1.1",
        "job_id": jobFolder.name,
        "source_app": "photoshop",
        "target_app": "aseprite",
        "timestamp": timestamp,
        "document_name": originalDoc.name,
        "canvas_size": { "w": originalDoc.width.as("px"), "h": originalDoc.height.as("px") },
        "frame_mode": "folder_frames",
        "element_count": elementsList.length,
        "elements": elementsList,
        "layer_count": extractedPixCount,
        "layers": []
    };

    for (var k = 0; k < elementsList.length; k++) {
        if (elementsList[k].type === "layer") metadata.layers.push(elementsList[k]);
    }

    saveJSON(jobFolder + "/metadata.json", metadata);

    var payload = {
        "signature": "ase_ps_bridge_payload",
        "version": "1.1",
        "job_id": jobFolder.name,
        "source_app": "photoshop",
        "target_app": "aseprite",
        "job_path": jobFolder.fsName.replace(/\\/g, "/"),
        "summary": {
            "layer_count": extractedPixCount,
            "element_count": elementsList.length,
            "document_name": originalDoc.name
        },
        "settings": {
            "align_mode": ALIGN_MODE
        },
        "timestamp": timestamp
    };
    saveJSON(jobFolder + "/trigger_copy.json", payload);

    var doneData = {
        "job_id": jobFolder.name,
        "status": "success",
        "layer_count": extractedPixCount,
        "element_count": elementsList.length,
        "timestamp": timestamp
    };
    saveJSON(jobFolder + "/status_done.json", doneData);
}

// ==========================================
// Helper Functions
// ==========================================
function writeStatusError(errorMsg) {
    try {
        var errFile = new File(JOB_PATH + "/status_error.txt");
        errFile.encoding = "UTF-8";
        errFile.open("w");
        errFile.write(errorMsg);
        errFile.close();
    } catch(e) {
        alert("치명적 에러: 상태 파일을 쓸 수 없습니다.\n" + errorMsg);
    }
}

function getSelectedLayerIds() {
    var ids = [];
    var idKey = stringIDToTypeID("targetLayersIDs");

    try {
        var ref = new ActionReference();
        ref.putProperty(stringIDToTypeID("property"), idKey);
        ref.putEnumerated(charIDToTypeID("Dcmn"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        var desc = executeActionGet(ref);
        if (desc.hasKey(idKey)) {
            var list = desc.getList(idKey);
            for (var i = 0; i < list.count; i++) {
                ids.push(list.getReference(i).getIdentifier());
            }
            return ids;
        }
    } catch(e) {}

    try {
        var activeRef = new ActionReference();
        activeRef.putProperty(charIDToTypeID("Prpr"), stringIDToTypeID("layerID"));
        activeRef.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        var activeDesc = executeActionGet(activeRef);
        ids.push(activeDesc.getInteger(stringIDToTypeID("layerID")));
    } catch(singleErr) {}

    return ids;
}

function collectSelectedIdsInFolder(items, selectedMap, outIds) {
    for (var i = 0; i < items.length; i++) {
        var item = items[i];
        if (selectedMap[item.id]) {
            outIds.push(item.id);
            delete selectedMap[item.id];
            if (item.typename === "LayerSet") {
                consumeSelectedIdsInFolder(item.layers, selectedMap);
            }
            continue;
        }
        if (item.typename === "LayerSet") {
            collectSelectedIdsInFolder(item.layers, selectedMap, outIds);
        }
    }
}

function consumeSelectedIdsInFolder(items, selectedMap) {
    for (var i = 0; i < items.length; i++) {
        var item = items[i];
        if (selectedMap[item.id]) {
            delete selectedMap[item.id];
        }
        if (item.typename === "LayerSet") {
            consumeSelectedIdsInFolder(item.layers, selectedMap);
        }
    }
}

function selectLayerById(layerId, addToSelection) {
    var desc = new ActionDescriptor();
    var ref = new ActionReference();
    ref.putIdentifier(charIDToTypeID("Lyr "), layerId);
    desc.putReference(charIDToTypeID("null"), ref);
    if (addToSelection) {
        desc.putEnumerated(
            stringIDToTypeID("selectionModifier"),
            stringIDToTypeID("selectionModifierType"),
            stringIDToTypeID("addToSelection")
        );
    }
    desc.putBoolean(charIDToTypeID("MkVs"), false);
    executeAction(charIDToTypeID("slct"), desc, DialogModes.NO);
}

function selectLayerIds(layerIds) {
    if (!layerIds || layerIds.length === 0) return;
    selectLayerById(layerIds[0], false);
    for (var i = 1; i < layerIds.length; i++) {
        selectLayerById(layerIds[i], true);
    }
}

function exportLayerAsPNG(doc, layer, fullPath, w, h) {
    var exportDoc = app.documents.add(w, h, doc.resolution, "ExportTemp", NewDocumentMode.RGB, DocumentFill.TRANSPARENT);
    app.activeDocument = doc;
    layer.duplicate(exportDoc, ElementPlacement.PLACEATBEGINNING);
    app.activeDocument = exportDoc;
    var saveFile = new File(fullPath);
    var pngOptions = new PNGSaveOptions();
    pngOptions.compression = 0;
    pngOptions.interlaced = false;
    exportDoc.saveAs(saveFile, pngOptions, true, Extension.LOWERCASE);
    exportDoc.close(SaveOptions.DONOTSAVECHANGES);
    app.activeDocument = doc;
}

function getFormattedDate() {
    var d = new Date();
    var pad = function(n) { return n < 10 ? '0' + n : n; };
    return d.getFullYear().toString() + pad(d.getMonth() + 1) + pad(d.getDate()) + "_" + 
           pad(d.getHours()) + pad(d.getMinutes()) + pad(d.getSeconds());
}

function saveJSON(path, obj) {
    var file = new File(path);
    file.encoding = "UTF-8";
    file.open("w");
    file.write(customStringify(obj));
    file.close();
}

function customStringify(obj) {
    if (obj === null) return "null";
    if (typeof obj === "string") return '"' + obj.replace(/"/g, '\\"') + '"';
    if (typeof obj === "number" || typeof obj === "boolean") return obj.toString();
    if (obj instanceof Array) {
        var arr = [];
        for (var i = 0; i < obj.length; i++) arr.push(customStringify(obj[i]));
        return "[" + arr.join(",") + "]";
    }
    if (typeof obj === "object") {
        var props = [];
        for (var key in obj) {
            if (obj.hasOwnProperty(key)) {
                props.push('"' + key + '":' + customStringify(obj[key]));
            }
        }
        return "{" + props.join(",") + "}";
    }
    return '""';
}

// 스크립트 실행 시작 (전체 예외 처리)
try {
    main();
} catch(globalError) {
    writeStatusError("포토샵 스크립트 전역 에러 발생:\n" + globalError.toString());
}

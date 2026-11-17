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
var DIAGNOSTICS_PATH = "REPLACE_ME_DIAGNOSTICS_PATH";
var ATTEMPT_TOKEN = "REPLACE_ME_ATTEMPT_TOKEN";
var DEBUG_ENABLED = "REPLACE_ME_DEBUG_ENABLED" === true;

#target photoshop
app.preferences.rulerUnits = Units.PIXELS;

function main() {
    traceCopy("PHOTOSHOP_COPY_STARTED", {version: app.version, frame_mode: FRAME_MODE,
        active_document: diagnosticDocument()});
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

    if (FRAME_MODE === "layer_frames") {
        runLayerFramesCopy(originalDoc, jobFolder, layersFolder);
        return;
    }

    runNormalCopy(originalDoc, jobFolder, layersFolder);
}

function runNormalCopy(originalDoc, jobFolder, layersFolder) {
    var selectionBefore = diagnosticSelectionSnapshot();
    traceCopy("NORMAL_SELECTION_CAPTURED", {source_document: diagnosticDocument(originalDoc),
        selection: selectionBefore, layers: diagnosticLayers(originalDoc, selectionBefore.ids)});
    // 1. 선택된 레이어/폴더들을 새로운 임시 문서로 복제 (안전한 추출)
    traceCopy("NORMAL_DUPLICATION_STARTED", {source_document: diagnosticDocument(originalDoc),
        active_document: diagnosticDocument(), selection: diagnosticSelectionSnapshot()});
    var normalState = null;
    try {
        normalState = captureCopyDocuments(originalDoc, "TempBridgeDoc");
        var desc = new ActionDescriptor();
        var ref = new ActionReference();
        ref.putClass(charIDToTypeID("Dcmn"));
        desc.putReference(charIDToTypeID("null"), ref);
        desc.putString(charIDToTypeID("Nm  "), "TempBridgeDoc");
        var ref2 = new ActionReference();
        ref2.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        desc.putReference(charIDToTypeID("Usng"), ref2);
        traceCopy("NORMAL_MAKE_CONTEXT", diagnosticNormalCommandContext(originalDoc));
        var duplicationStarted = new Date().getTime();
        normalState.creationAttempted = true;
        try { executeAction(charIDToTypeID("Mk  "), desc, DialogModes.NO); }
        finally { traceDuration("temporary_document_make", duplicationStarted); }
    } catch (e) {
        traceCopy("NORMAL_DUPLICATION_FAILED", {error: diagnosticError(e),
            active_document: diagnosticDocument(), selection: diagnosticSelectionSnapshot(),
            command_context: diagnosticNormalCommandContext(originalDoc, true)});
        writeStatusError("선택된 레이어/그룹의 임시 문서 복제에 실패했습니다.\n(원본 에러: " + e.toString() + ")", e);
        cleanupNormalCopy(originalDoc, null, selectionBefore, normalState);
        return;
    }

    var tempDoc = null;
    try {
        tempDoc = claimCopyTemporary(normalState, app.activeDocument);
    } catch (identityError) {
        writeStatusError("Normal copy temporary document verification failed: " + identityError.toString(), identityError);
        cleanupNormalCopy(originalDoc, null, selectionBefore, normalState);
        return;
    }
    traceCopy("NORMAL_DUPLICATION_COMPLETED", {source_document: diagnosticDocument(originalDoc),
        temporary_document: diagnosticDocument(tempDoc), layers: diagnosticLayers(tempDoc),
        selection: diagnosticSelectionSnapshot()});
    var contentW;
    var contentH;
    var normalClean = false;

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
                var itemBounds = item.bounds;
                if (itemBounds[2].as("px") - itemBounds[0].as("px") <= 0) continue;
                
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

    try {
        // Bounds are diagnostic only; retain the existing composite Trim/export algorithm.
        traceCopy("NORMAL_TRIM_STARTED", {temporary_document: diagnosticDocument(tempDoc),
            alpha_measurement: "not_verified_before_export"});
        try {
            var trimStarted = new Date().getTime();
            try { tempDoc.trim(TrimType.TRANSPARENT); }
            finally { traceDuration("trim", trimStarted); }
        } catch (trimError) {
            traceCopy("NORMAL_TRIM_FAILED", {function_name: "runNormalCopy", stage: "trim",
                error: diagnosticError(trimError), temporary_document: diagnosticDocument(tempDoc),
                layers: diagnosticLayers(tempDoc), alpha_measurement: "unverified_trim_exception"});
            writeStatusError("임시 문서의 픽셀 영역을 판정하지 못했습니다 (Trim 실패).\n(원본 에러: " + trimError.toString() + ")", trimError);
            return;
        }
        contentW = tempDoc.width.as("px");
        contentH = tempDoc.height.as("px");
        traceCopy("NORMAL_TRIM_COMPLETED", {temporary_document: diagnosticDocument(tempDoc),
            width: contentW, height: contentH, layers: diagnosticLayers(tempDoc)});
        traceCopy("NORMAL_EXTRACTION_STARTED", {temporary_document: diagnosticDocument(tempDoc)});
        traverseItems(tempDoc.layers, null);
        traceCopy("NORMAL_EXTRACTION_COMPLETED", {pixel_count: extractedPixCount, element_count: elementsList.length});
    } catch (extractError) {
        traceCopy("NORMAL_EXTRACTION_FAILED", {function_name: "runNormalCopy", stage: "export",
            error: diagnosticError(extractError), active_document: diagnosticDocument()});
        throw extractError;
    } finally {
        normalClean = cleanupNormalCopy(originalDoc, tempDoc, selectionBefore, normalState);
    }

    if (!normalClean) {
        writeStatusError("Normal copy cleanup failed. Select the original document before retrying.");
        return;
    }

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
    traceCopy("FOLDER_SELECTION_READ", {selected_ids: selectedIds, source_document: diagnosticDocument(originalDoc)});
    if (selectedIds.length === 0) {
        writeStatusError("Folder → Frames 모드에서는 top-level 폴더 안의 레이어 또는 그룹을 선택해야 합니다.");
        return;
    }

    var selectedMap = {};
    for (var i = 0; i < selectedIds.length; i++) {
        selectedMap[selectedIds[i]] = true;
    }

    var collectionStarted = new Date().getTime();
    // Snapshot only structural fields, before selection/document changes; never reuse across jobs.
    var selectionTree = captureSelectionTree(originalDoc.layers);
    traceDuration("source_tree_capture", collectionStarted);
    var frameGroups = [];
    collectDirectSelectedFolders(selectionTree, selectedMap, frameGroups);
    traceCopy("DIRECT_FOLDERS_COLLECTED", {count: frameGroups.length});

    if (frameGroups.length === 0) {
        for (var t = 0; t < selectionTree.length; t++) {
            var topItem = selectionTree[t];
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
                    folder: topItem.source,
                    ids: childSelectionIds.length > 0 ? childSelectionIds : [topItem.id]
                });
            }
        }
    }
    traceDuration("frame_container_collection", collectionStarted);

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

    for (var diagnosticIndex = 0; diagnosticIndex < frameGroups.length; diagnosticIndex++) {
        traceCopy("FRAME_CONTAINER_COLLECTED", {frame_index: diagnosticIndex,
            folder: diagnosticFolder(frameGroups[diagnosticIndex].folder),
            selected_ids: frameGroups[diagnosticIndex].ids});
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
                var itemBounds = item.bounds;
                if (itemBounds[2].as("px") - itemBounds[0].as("px") <= 0) continue;

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
        var frameState = null;
        var frameSucceeded = false;
        var frameClean = false;
        try {
            frameState = captureCopyDocuments(originalDoc, "TempBridgeFrameDoc");
            app.activeDocument = originalDoc;
            selectLayerIds(frameGroups[f].ids);
            traceCopy("FOLDER_DUPLICATION_STARTED", {frame_index: f,
                folder: diagnosticFolder(frameGroups[f].folder), source_document: diagnosticDocument(originalDoc),
                active_document: diagnosticDocument(), selected_ids: diagnosticSelection()});

            try {
                var desc = new ActionDescriptor();
                var ref = new ActionReference();
                ref.putClass(charIDToTypeID("Dcmn"));
                desc.putReference(charIDToTypeID("null"), ref);
                desc.putString(charIDToTypeID("Nm  "), "TempBridgeFrameDoc");
                var ref2 = new ActionReference();
                ref2.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
                desc.putReference(charIDToTypeID("Usng"), ref2);
                var duplicationStarted = new Date().getTime();
                frameState.creationAttempted = true;
                try { executeAction(charIDToTypeID("Mk  "), desc, DialogModes.NO); }
                finally { traceDuration("temporary_document_make", duplicationStarted); }
            } catch (dupErr) {
                traceCopy("FOLDER_DUPLICATION_FAILED", {frame_index: f,
                    folder: diagnosticFolder(frameGroups[f].folder), error: diagnosticError(dupErr),
                    source_document: diagnosticDocument(originalDoc), active_document: diagnosticDocument(),
                    selected_ids: diagnosticSelection()});
                writeStatusError("선택된 폴더를 임시 문서로 복제하지 못했습니다.\n(원본 에러: " + dupErr.toString() + ")", dupErr);
                return;
            }

            var tempDoc = claimCopyTemporary(frameState, app.activeDocument);
            traceCopy("FOLDER_DUPLICATION_COMPLETED", {frame_index: f, source_document: diagnosticDocument(originalDoc),
                active_document: diagnosticDocument(), temporary_document_created: tempDoc.id !== originalDoc.id});
            try {
                var trimStarted = new Date().getTime();
                try { tempDoc.trim(TrimType.TRANSPARENT); }
                finally { traceDuration("trim", trimStarted); }
            } catch(trimErr) {
                writeStatusError("Folder → Frames 모드에서 추출 가능한 픽셀이 없는 선택이 있습니다: " + frameGroups[f].folder.name + "\n" + trimErr.toString(), trimErr);
                return;
            }

            var contentW = tempDoc.width.as("px");
            var contentH = tempDoc.height.as("px");

            if (tempDoc.layers.length === 1 && tempDoc.layers[0].typename === "LayerSet" && tempDoc.layers[0].name === frameGroups[f].folder.name) {
                traverseFrameItems(tempDoc, tempDoc.layers[0].layers, null, f, contentW, contentH);
            } else {
                traverseFrameItems(tempDoc, tempDoc.layers, null, f, contentW, contentH);
            }

            frameSucceeded = true;
        } catch (frameError) {
            traceCopy("FOLDER_FRAME_FAILED", {frame_index: f, error: diagnosticError(frameError)});
            writeStatusError("Folder -> Frames copy failed: " + frameError.toString(), frameError);
            return;
        } finally {
            frameClean = finishCopyDocuments(frameState, "FOLDER_FRAME");
            if (!frameClean && frameSucceeded) {
                writeStatusError("Folder -> Frames cleanup failed. Select the original document before retrying.");
            }
        }
        if (!frameClean) return;
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

function runLayerFramesCopy(originalDoc, jobFolder, layersFolder) {
    var selectedIds = getSelectedLayerIds();
    if (selectedIds.length === 0) {
        writeStatusError("Layer → Frames 모드에서는 Photoshop 픽셀 레이어를 선택해야 합니다.");
        return;
    }

    var selectedMap = {};
    for (var i = 0; i < selectedIds.length; i++) {
        selectedMap[selectedIds[i]] = true;
    }

    var selectedLayers = [];
    var selectedGroupName = null;

    function collectSelectedPixelLayers(items) {
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            if (selectedMap[item.id]) {
                delete selectedMap[item.id];
                if (item.typename === "LayerSet") {
                    selectedGroupName = item.name;
                    consumeSelectedIdsInFolder(item.layers, selectedMap);
                } else if (item.typename === "ArtLayer") {
                    if (item.kind && item.kind !== LayerKind.NORMAL) {
                        writeStatusError("Layer → Frames 모드에서는 픽셀 레이어만 선택할 수 있습니다: " + item.name);
                        return false;
                    }
                    selectedLayers.push(item);
                }
                continue;
            }
            if (item.typename === "LayerSet") {
                if (collectSelectedPixelLayers(item.layers) === false) return false;
            }
        }
        return true;
    }

    var collectionStarted = new Date().getTime();
    var collected = collectSelectedPixelLayers(originalDoc.layers);
    traceDuration("selected_pixel_tree", collectionStarted);
    if (collected === false) {
        return;
    }

    if (selectedGroupName !== null) {
        writeStatusError("Layer → Frames 모드에서는 폴더/그룹을 선택할 수 없습니다. 픽셀 레이어만 선택해 주세요: " + selectedGroupName);
        return;
    }

    for (var key in selectedMap) {
        if (selectedMap.hasOwnProperty(key)) {
            writeStatusError("Layer → Frames 모드에서 선택 항목을 확인하지 못했습니다. 픽셀 레이어만 선택해 주세요.");
            return;
        }
    }

    if (selectedLayers.length === 0) {
        writeStatusError("Layer → Frames 모드에서 선택된 픽셀 레이어가 없습니다.");
        return;
    }

    var elementsList = [];
    var extractedPixCount = 0;

    for (var f = 0; f < selectedLayers.length; f++) {
        var frameState = null;
        var frameSucceeded = false;
        var frameClean = false;
        try {
            frameState = captureCopyDocuments(originalDoc, "TempBridgeLayerFrameDoc");
            app.activeDocument = originalDoc;
            selectLayerById(selectedLayers[f].id, false);

            try {
                var desc = new ActionDescriptor();
                var ref = new ActionReference();
                ref.putClass(charIDToTypeID("Dcmn"));
                desc.putReference(charIDToTypeID("null"), ref);
                desc.putString(charIDToTypeID("Nm  "), "TempBridgeLayerFrameDoc");
                var ref2 = new ActionReference();
                ref2.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
                desc.putReference(charIDToTypeID("Usng"), ref2);
                var duplicationStarted = new Date().getTime();
                frameState.creationAttempted = true;
                try { executeAction(charIDToTypeID("Mk  "), desc, DialogModes.NO); }
                finally { traceDuration("temporary_document_make", duplicationStarted); }
            } catch (dupErr) {
                traceCopy("LAYER_DUPLICATION_FAILED", {frame_index: f, error: diagnosticError(dupErr),
                    source_document: diagnosticDocument(originalDoc), active_document: diagnosticDocument()});
                writeStatusError("선택된 레이어를 임시 문서로 복제하지 못했습니다.\n(원본 에러: " + dupErr.toString() + ")", dupErr);
                return;
            }

            var tempDoc = claimCopyTemporary(frameState, app.activeDocument);
            try {
                var trimStarted = new Date().getTime();
                try { tempDoc.trim(TrimType.TRANSPARENT); }
                finally { traceDuration("trim", trimStarted); }
            } catch(trimErr) {
                writeStatusError("Layer → Frames 모드에서 추출 가능한 픽셀이 없는 레이어가 있습니다: " + selectedLayers[f].name + "\n" + trimErr.toString(), trimErr);
                return;
            }

            var contentW = tempDoc.width.as("px");
            var contentH = tempDoc.height.as("px");
            var exportLayer = findFirstArtLayer(tempDoc.layers);
            if (!exportLayer) {
                writeStatusError("Layer → Frames 모드에서 복제된 픽셀 레이어를 찾지 못했습니다: " + selectedLayers[f].name);
                return;
            }

            var fileName = "layer_" + extractedPixCount + ".png";
            var pngPath = layersFolder + "/" + fileName;
            exportLayerAsPNG(tempDoc, exportLayer, pngPath, contentW, contentH);

            elementsList.push({
                id: "item_" + f,
                type: "layer",
                name: selectedLayers[f].name,
                parent_id: null,
                index: 0,
                frame_index: f,
                x: 0,
                y: 0,
                width: contentW,
                height: contentH,
                opacity: Math.round(selectedLayers[f].opacity),
                visible: selectedLayers[f].visible,
                file: "layers/" + fileName
            });
            extractedPixCount++;

            frameSucceeded = true;
        } catch (frameError) {
            traceCopy("LAYER_FRAME_FAILED", {frame_index: f, error: diagnosticError(frameError)});
            writeStatusError("Layer -> Frames copy failed: " + frameError.toString(), frameError);
            return;
        } finally {
            frameClean = finishCopyDocuments(frameState, "LAYER_FRAME");
            if (!frameClean && frameSucceeded) {
                writeStatusError("Layer -> Frames cleanup failed. Select the original document before retrying.");
            }
        }
        if (!frameClean) return;
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
        "frame_mode": "layer_frames",
        "element_count": elementsList.length,
        "elements": elementsList,
        "layer_count": extractedPixCount,
        "layers": []
    };

    for (var k = 0; k < elementsList.length; k++) {
        metadata.layers.push(elementsList[k]);
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
function traceCopy(state, details) {
    try {
        if (DIAGNOSTICS_PATH.indexOf("REPLACE_ME") !== -1) return;
        var file = new File(DIAGNOSTICS_PATH);
        if (file.exists && file.length > 1048576) return;
        file.encoding = "UTF-8";
        if (!file.open("a")) return;
        file.writeln(diagnosticEncode({attempt: ATTEMPT_TOKEN, timestamp_ms: new Date().getTime(),
            state: state, details: details}));
        file.close();
    } catch (ignoredDiagnosticError) {}
}

function traceDuration(stage, started) {
    traceCopy("COPY_STAGE_TIMING", {stage: stage, elapsed_ms: new Date().getTime() - started});
}

function copyDocumentId(doc) {
    var id = doc.id;
    if (typeof id !== "number" || !isFinite(id) || id <= 0) {
        throw new Error("Cannot verify Photoshop document identity.");
    }
    return id;
}

function openCopyDocuments() {
    var count = app.documents.length;
    if (typeof count !== "number" || count < 1) throw new Error("Cannot verify open Photoshop documents.");
    var documents = [];
    for (var i = 0; i < count; i++) {
        var doc = app.documents[i];
        documents.push({doc: doc, id: copyDocumentId(doc)});
    }
    return documents;
}

function captureCopyDocuments(source, expectedName) {
    var state = {source: source, sourceId: copyDocumentId(source), before: openCopyDocuments(),
        expectedName: expectedName, creationAttempted: false, owned: null};
    var found = false;
    for (var i = 0; i < state.before.length; i++) {
        if (state.before[i].id === state.sourceId) found = true;
    }
    if (!found) throw new Error("Source Photoshop document is not open.");
    return state;
}

function claimCopyTemporary(state, candidate) {
    var id = copyDocumentId(candidate);
    if (candidate === state.source || id === state.sourceId) throw new Error("No new temporary document was created.");
    for (var i = 0; i < state.before.length; i++) {
        if (candidate === state.before[i].doc || id === state.before[i].id) {
            throw new Error("Refusing to use a pre-existing user document as a temporary document.");
        }
    }
    var after = openCopyDocuments();
    var created = [];
    for (var a = 0; a < after.length; a++) {
        var existed = false;
        for (var b = 0; b < state.before.length; b++) {
            if (after[a].id === state.before[b].id) existed = true;
        }
        if (!existed) created.push(after[a]);
    }
    // A changed active document alone is not ownership: require one new, correctly named document.
    if (created.length !== 1 || created[0].id !== id || candidate.name !== state.expectedName) {
        throw new Error("Cannot prove ownership of the temporary Photoshop document.");
    }
    state.owned = {doc: candidate, id: id};
    return candidate;
}

function finishCopyDocuments(state, prefix) {
    if (!state) return false;
    var ok = true;
    if (!state.owned && state.creationAttempted) {
        // A command can throw after creating a document. Adopt only the same verifiable result.
        try { claimCopyTemporary(state, app.activeDocument); }
        catch (unverified) {
            ok = false;
            traceCopy(prefix + "_TEMP_UNVERIFIED", {error: diagnosticError(unverified)});
        }
    }
    if (state.owned) {
        try {
            var owned = state.owned;
            if (owned.doc === state.source || copyDocumentId(owned.doc) !== owned.id || owned.id === state.sourceId) {
                throw new Error("Temporary document identity changed; refusing to close it.");
            }
            for (var i = 0; i < state.before.length; i++) {
                if (owned.doc === state.before[i].doc || owned.id === state.before[i].id) {
                    throw new Error("Refusing to close a pre-existing user document.");
                }
            }
            owned.doc.close(SaveOptions.DONOTSAVECHANGES);
            traceCopy(prefix + "_TEMP_CLOSED", {temporary_document_id: owned.id});
        } catch (closeError) {
            ok = false;
            traceCopy(prefix + "_TEMP_CLOSE_FAILED", {error: diagnosticError(closeError)});
        }
    }
    try {
        if (copyDocumentId(state.source) !== state.sourceId) throw new Error("Source document identity changed.");
        app.activeDocument = state.source;
        if (copyDocumentId(app.activeDocument) !== state.sourceId) throw new Error("Source activation was not restored.");
        var restored = {source_document_id: state.sourceId};
        if (state.selectionBefore) {
            restored.source_document = diagnosticDocument(state.source);
            restored.selection_before = state.selectionBefore;
            restored.selection_after = diagnosticSelectionSnapshot();
        }
        traceCopy(prefix + "_SOURCE_RESTORED", restored);
    } catch (restoreError) {
        ok = false;
        traceCopy(prefix + "_SOURCE_RESTORE_FAILED", {error: diagnosticError(restoreError)});
    }
    return ok;
}

function captureSelectionTree(items) {
    var result = [];
    for (var i = 0, count = items.length; i < count; i++) {
        var item = items[i];
        var node = {id: item.id, typename: item.typename, source: item};
        if (node.typename === "LayerSet") node.layers = captureSelectionTree(item.layers);
        result.push(node);
    }
    return result;
}

function diagnosticEncode(value) {
    if (value === null || typeof value === "undefined") return "null";
    if (typeof value === "string") {
        return '"' + value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')
            .replace(/[\x00-\x1f]/g, function(c) {
                return "\\u" + ("000" + c.charCodeAt(0).toString(16)).slice(-4);
            }) + '"';
    }
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    var parts = [];
    var key;
    if (value instanceof Array) {
        for (key = 0; key < value.length; key++) parts.push(diagnosticEncode(value[key]));
        return "[" + parts.join(",") + "]";
    }
    for (key in value) if (value.hasOwnProperty(key)) parts.push(diagnosticEncode(key) + ":" + diagnosticEncode(value[key]));
    return "{" + parts.join(",") + "}";
}

function diagnosticDocument(doc) {
    var info = {};
    try { doc = doc || app.activeDocument; } catch (ignoredDoc) { return {unavailable: true}; }
    try { info.id = doc.id; } catch (ignoredId) {}
    try { info.layer_count = doc.layers.length; } catch (ignoredCount) {}
    try { info.width = doc.width.as("px"); info.height = doc.height.as("px"); } catch (ignoredSize) {}
    try { info.mode = String(doc.mode); info.bits = String(doc.bitsPerChannel); } catch (ignoredMode) {}
    return info;
}

function diagnosticSelectionSnapshot() {
    var info = {};
    try {
        info.ids = getSelectedLayerIds(info);
        info.count = info.ids.length;
    } catch (ignored) { info.ids = []; info.unavailable = true; }
    return info;
}

function diagnosticNormalCommandContext(doc, forceDetail) {
    var info = {command: "Mk  ", create_class: "Dcmn", using_reference: "Lyr / Ordn / Trgt",
        dialog_argument: "DialogModes.NO", source_document: diagnosticDocument(doc),
        active_document: diagnosticDocument(), selection: diagnosticSelectionSnapshot()};
    try {
        info.active_layer_id = doc.activeLayer.id;
        info.active_layer_type = doc.activeLayer.typename;
    } catch (ignoredLayer) { info.active_layer_unavailable = true; }
    if (!DEBUG_ENABLED && !forceDetail) return info;
    try { info.application_display_dialogs = String(app.displayDialogs); } catch (ignoredDialogs) {}
    try { info.document_count = app.documents.length; } catch (ignoredDocuments) {}
    try { info.history_count = doc.historyStates.length; } catch (ignoredHistory) {}
    try { info.document_saved = doc.saved; } catch (ignoredSaved) {}
    try {
        var channels = doc.activeChannels;
        info.active_channel_count = channels.length;
        info.active_channel_kinds = [];
        for (var i = 0; i < channels.length; i++) info.active_channel_kinds.push(String(channels[i].kind));
    } catch (ignoredChannels) { info.active_channels_unavailable = true; }
    return info;
}

function diagnosticLayers(doc, selectedIds) {
    if (!DEBUG_ENABLED) return [];
    var started = new Date().getTime();
    var result = [];
    var selected = {};
    if (selectedIds) for (var s = 0; s < selectedIds.length; s++) selected[selectedIds[s]] = true;
    function visit(items, depth, selectedParent) {
        for (var i = 0; i < items.length && result.length < 128; i++) {
            try {
                var item = items[i];
                var include = !selectedIds || selectedParent || selected[item.id];
                if (include) {
                    var detail = {id: item.id, type: item.typename, depth: depth, ui_index: i};
                    try { detail.kind = String(item.kind); } catch (ignoredKind) {}
                    try { detail.visible = item.visible; detail.opacity = item.opacity; } catch (ignoredVisible) {}
                    try {
                        var bounds = item.bounds;
                        detail.bounds = [bounds[0].as("px"), bounds[1].as("px"),
                            bounds[2].as("px"), bounds[3].as("px")];
                    } catch (ignoredBounds) {}
                    result.push(detail);
                }
                if (item.typename === "LayerSet" && depth < 20) visit(item.layers, depth + 1, include);
            } catch (ignoredLayer) {}
        }
    }
    try { visit(doc.layers, 0, false); } catch (ignoredTree) {}
    traceDuration("diagnostic_layer_tree", started);
    return result;
}

function cleanupNormalCopy(originalDoc, tempDoc, selectionBefore, state) {
    if (state) {
        state.selectionBefore = selectionBefore;
        return finishCopyDocuments(state, "NORMAL");
    }
    if (tempDoc) {
        traceCopy("NORMAL_TEMP_UNVERIFIED", {reason: "No ownership snapshot; document left open."});
    }
    try {
        app.activeDocument = originalDoc;
        traceCopy("NORMAL_SOURCE_RESTORED", {source_document: diagnosticDocument(originalDoc),
            selection_before: selectionBefore, selection_after: diagnosticSelectionSnapshot()});
    } catch (restoreError) {
        traceCopy("NORMAL_SOURCE_RESTORE_FAILED", {error: diagnosticError(restoreError)});
    }
    return false;
}

function diagnosticSelection() {
    try { return getSelectedLayerIds(); }
    catch (ignored) { return []; }
}

function diagnosticLayerId(layer) {
    try { return layer.id; } catch (ignored) { return null; }
}

function diagnosticFolder(folder) {
    if (!DEBUG_ENABLED) return {id: diagnosticLayerId(folder)};
    try {
        var chain = [];
        var item = folder;
        while (item && item.typename === "LayerSet") {
            chain.push(item.id);
            item = item.parent;
        }
        return {id: folder.id, depth: chain.length, ancestor_ids: chain,
            type: folder.typename, child_count: folder.layers.length};
    } catch (ignored) { return {unavailable: true}; }
}

function diagnosticError(error) {
    var info = {};
    if (!error) return info;
    try { info.number = error.number; } catch (ignoredNumber) {}
    try { info.message = error.message; } catch (ignoredMessage) {}
    try { info.line = error.line; } catch (ignoredLine) {}
    try { info.file = new File(error.fileName).name; } catch (ignoredFile) {}
    return info;
}

function writeStatusError(errorMsg, errorObject) {
    traceCopy("FAILED", {message: errorMsg, error: diagnosticError(errorObject),
        active_document: diagnosticDocument()});
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

function getSelectedLayerIds(diagnosticInfo) {
    var started = new Date().getTime();
    try { return readSelectedLayerIds(diagnosticInfo); }
    finally { traceDuration("selected_layer_ids", started); }
}

function readSelectedLayerIds(diagnosticInfo) {
    var ids = [];
    var idKey = stringIDToTypeID("targetLayersIDs");

    try {
        var ref = new ActionReference();
        ref.putProperty(stringIDToTypeID("property"), idKey);
        ref.putEnumerated(charIDToTypeID("Dcmn"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        var desc = executeActionGet(ref);
        if (desc.hasKey(idKey)) {
            var list = desc.getList(idKey);
            if (diagnosticInfo) diagnosticInfo.method = "targetLayersIDs";
            for (var i = 0; i < list.count; i++) {
                ids.push(list.getReference(i).getIdentifier());
            }
            return ids;
        }
    } catch(e) {
        if (diagnosticInfo) diagnosticInfo.primary_error = diagnosticError(e);
    }

    try {
        var activeRef = new ActionReference();
        activeRef.putProperty(charIDToTypeID("Prpr"), stringIDToTypeID("layerID"));
        activeRef.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        var activeDesc = executeActionGet(activeRef);
        ids.push(activeDesc.getInteger(stringIDToTypeID("layerID")));
        if (diagnosticInfo) diagnosticInfo.method = "active_layer_fallback";
    } catch(singleErr) {
        if (diagnosticInfo) diagnosticInfo.fallback_error = diagnosticError(singleErr);
    }

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

function collectDirectSelectedFolders(items, selectedMap, frameGroups) {
    for (var i = 0; i < items.length; i++) {
        var item = items[i];
        if (item.typename !== "LayerSet") {
            continue;
        }

        if (selectedMap[item.id]) {
            delete selectedMap[item.id];
            consumeSelectedIdsInFolder(item.layers, selectedMap);
            frameGroups.push({
                folder: item.source || item,
                ids: [item.id]
            });
            continue;
        }

        collectDirectSelectedFolders(item.layers, selectedMap, frameGroups);
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

function findFirstArtLayer(items) {
    for (var i = 0; i < items.length; i++) {
        var item = items[i];
        if (item.typename === "ArtLayer") {
            return item;
        }
        if (item.typename === "LayerSet") {
            var found = findFirstArtLayer(item.layers);
            if (found) return found;
        }
    }
    return null;
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
    var exportStarted = new Date().getTime();
    traceCopy("PNG_EXPORT_STARTED", {source_document: diagnosticDocument(doc), layer_id: diagnosticLayerId(layer),
        width: w, height: h});
    var exportDoc = null;
    var exportState = null;
    var exportFailure = null;
    var exportStage = "create_export_document";
    try {
        exportState = captureCopyDocuments(doc, "ExportTemp");
        var stageStarted = new Date().getTime();
        exportState.creationAttempted = true;
        var candidate = app.documents.add(w, h, doc.resolution, "ExportTemp", NewDocumentMode.RGB, DocumentFill.TRANSPARENT);
        exportDoc = claimCopyTemporary(exportState, candidate);
        traceDuration("png_document_create", stageStarted);
        traceCopy("PNG_TEMP_CREATED", {temporary_document: diagnosticDocument(exportDoc)});
        app.activeDocument = doc;
        exportStage = "duplicate_layer";
        stageStarted = new Date().getTime();
        layer.duplicate(exportDoc, ElementPlacement.PLACEATBEGINNING);
        traceDuration("png_layer_duplicate", stageStarted);
        app.activeDocument = exportDoc;
        var saveFile = new File(fullPath);
        var pngOptions = new PNGSaveOptions();
        pngOptions.compression = 0;
        pngOptions.interlaced = false;
        exportStage = "save_png";
        stageStarted = new Date().getTime();
        exportDoc.saveAs(saveFile, pngOptions, true, Extension.LOWERCASE);
        traceDuration("png_save", stageStarted);
        traceCopy("PNG_EXPORTED", {temporary_document: diagnosticDocument(exportDoc),
            width: w, height: h, file: saveFile.name});
    } catch (exportError) {
        exportFailure = exportError;
        traceCopy("PNG_EXPORT_FAILED", {function_name: "exportLayerAsPNG", stage: exportStage,
            error: diagnosticError(exportError), active_document: diagnosticDocument()});
        throw exportError;
    } finally {
        var exportClean = finishCopyDocuments(exportState, "PNG");
        traceDuration("png_export_including_cleanup", exportStarted);
        if (!exportClean && !exportFailure) throw new Error("PNG temporary document cleanup failed.");
    }
}

function getFormattedDate() {
    var d = new Date();
    var pad = function(n) { return n < 10 ? '0' + n : n; };
    return d.getFullYear().toString() + pad(d.getMonth() + 1) + pad(d.getDate()) + "_" + 
           pad(d.getHours()) + pad(d.getMinutes()) + pad(d.getSeconds());
}

function saveJSON(path, obj) {
    var started = new Date().getTime();
    var file = new File(path);
    file.encoding = "UTF-8";
    file.open("w");
    file.write(customStringify(obj));
    file.close();
    if (/metadata\.json$/.test(String(path))) {
        traceDuration("metadata_write", started);
        traceCopy("METADATA_CREATED", {frame_mode: FRAME_MODE, element_count: obj.element_count,
            layer_count: obj.layer_count});
    }
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
var copyStarted = new Date().getTime();
try {
    main();
} catch(globalError) {
    writeStatusError("포토샵 스크립트 전역 에러 발생:\n" + globalError.toString(), globalError);
} finally {
    traceDuration("jsx_total", copyStarted);
}

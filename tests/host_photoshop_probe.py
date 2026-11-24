"""Opt-in real-host probe. Only creates/closes its own synthetic documents.

Run in a dedicated process with --output outside the source tree. Aseprite
runs in batch in a separate process; no existing editor window is controlled.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prog-id', default='Photoshop.Application.210')
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--aseprite', type=Path, required=True)
    parser.add_argument('--cli', action='store_true', help='Use the production CLI worker instead of COM for copy/paste')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ['APPDATA'] = str(out / 'profile')
    root = Path(__file__).resolve().parents[1]
    from PIL import Image
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    ps = win32com.client.Dispatch(args.prog_id)
    assert str(ps.Path).rstrip('\\/').lower() == str(args.exe.parent).lower()
    assert str(ps.Version).split('.')[0] == '28'
    spec = importlib.util.spec_from_file_location('bridge_host_probe', root / 'bridge_ui.py')
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    report = {'host': str(ps.Version), 'cases': []}

    def js(code):
        return ps.DoJavaScript(code)

    def execute(template, job, mode='normal'):
        if args.cli:
            worker=bridge.PhotoshopCLIWorker(str(template),str(args.exe),job.name,str(job.parent),'absolute',mode,'en')
            # Human warning approval is outside measured script time. Product timeout is unchanged.
            worker.RESPONSE_TIMEOUT=120
            worker.log.connect(lambda message: print(message,flush=True))
            worker.run()
            assert worker.outcome and worker.outcome[0],worker.outcome
        else:
            body=template.read_text(encoding='utf-8')
            for key,value in {'JOB_PATH':str(job),'ALIGN_MODE':'absolute','FRAME_MODE':mode,
                              'DIAGNOSTICS_PATH':str(job/'events.jsonl'),'ATTEMPT_TOKEN':'host-probe'}.items():
                body=body.replace('"REPLACE_ME_'+key+'"',json.dumps(value))
            body=body.replace('"REPLACE_ME_DEBUG_ENABLED"','false')
            path=job/'body.jsx';path.write_text(body,encoding='utf-8')
            ps.DoJavaScriptFile(str(path))

    before = js('var r=[];for(var i=0;i<app.documents.length;i++)r.push(app.documents[i].id);r.join(",");')
    old_units = str(js('app.preferences.rulerUnits.toString();'))
    assert old_units.startswith('Units.') and old_units.split('.')[-1].isalpha()
    source = None
    try:
        names = ['A', 'B', 'C', 'D']
        for i, name in enumerate(names):
            image = Image.new('RGBA', (64, 64))
            for x in range(4 + i * 3, 12 + i * 3):
                for y in range(5 + i * 4, 14 + i * 4):
                    image.putpixel((x, y), ((255 if i % 2 == 0 else 0), (255 if i == 1 else 0), (255 if i >= 2 else 0), 128 if i == 1 else 255))
            image.save(out / (name + '.png'))
        files = json.dumps([str(out / (n + '.png')) for n in names])
        result = js(r'''
var __spProbe = {ids:[], groups:[], oldUnits:app.preferences.rulerUnits};
app.preferences.rulerUnits=Units.PIXELS;
__spProbe.doc=app.documents.add(64,64,72,'Southpaw Synthetic Compatibility',NewDocumentMode.RGB,DocumentFill.TRANSPARENT);
var rootGroup=__spProbe.doc.layerSets.add(); rootGroup.name='Nested Root';
var groups=[];
for(var k=1;k>=0;k--){var g=rootGroup.layerSets.add();g.name='Frame '+k;groups[k]=g;}
__spProbe.groups=[groups[0].id,groups[1].id];
var paths=FILES;
for(var k=3;k>=0;k--){
 var img=app.open(new File(paths[k]));
 var layer=img.activeLayer.duplicate(__spProbe.doc,ElementPlacement.PLACEATBEGINNING);
 img.close(SaveOptions.DONOTSAVECHANGES);
 app.activeDocument=__spProbe.doc;layer.name=['A','B','C','D'][k];
 layer.move(groups[k==3?1:0],ElementPlacement.INSIDE);__spProbe.ids[k]=layer.id;
}
app.activeDocument=__spProbe.doc;
__spProbe.doc.id+'|'+__spProbe.ids.join(',')+'|'+__spProbe.groups.join(',');
'''.replace('FILES', files))
        source = int(result.split('|')[0])
        layers = [int(x) for x in result.split('|')[1].split(',')]
        groups = [int(x) for x in result.split('|')[2].split(',')]
        js('var d=app.activeDocument;if(d.id!='+str(source)+')throw Error("Source mismatch");d.saveAs(new File('+json.dumps(str(out/'source.psd'))+'),new PhotoshopSaveOptions(),true,Extension.LOWERCASE);')

        def select(ids):
            js(r'''var source=null;for(var j=0;j<app.documents.length;j++)if(app.documents[j].id==SOURCE)source=app.documents[j];
if(!source)throw Error('Synthetic source missing');app.activeDocument=source;var ids=IDS;
for(var i=0;i<ids.length;i++){var d=new ActionDescriptor(),r=new ActionReference();
r.putIdentifier(charIDToTypeID('Lyr '),ids[i]);d.putReference(charIDToTypeID('null'),r);
if(i)d.putEnumerated(stringIDToTypeID('selectionModifier'),stringIDToTypeID('selectionModifierType'),stringIDToTypeID('addToSelection'));
d.putBoolean(charIDToTypeID('MkVs'),false);executeAction(charIDToTypeID('slct'),d,DialogModes.NO);}'''.replace('IDS', json.dumps(ids)).replace('SOURCE',str(source)))

        for mode in ('normal', 'folder_frames', 'layer_frames'):
            job = out / mode
            job.mkdir()
            select(layers if mode == 'layer_frames' else groups)
            start = time.perf_counter()
            execute(root/'scripts/photoshop_copy.jsx',job,mode)
            assert not (job/'status_error.txt').exists(), (job/'status_error.txt').read_text(encoding='utf-8') if (job/'status_error.txt').exists() else ''
            assert (job/'status_done.json').is_file()
            metadata = json.loads((job/'metadata.json').read_text(encoding='utf-8-sig'))
            pixels = [e for e in metadata['elements'] if e['type']=='layer']
            assert len(pixels)==4, pixels
            for el in pixels:
                actual=Image.open(job/el['file']).convert('RGBA')
                original=Image.open(out/(el['name']+'.png')).convert('RGBA')
                assert actual.crop(actual.getbbox()).tobytes()==original.crop(original.getbbox()).tobytes()
            by_frame = {}
            for e in pixels:
                by_frame.setdefault(e.get('frame_index',0), []).append(e['name'])
            if mode=='folder_frames':
                assert set(by_frame)=={0,1} and set(by_frame[0])=={'A','B','C'} and by_frame[1]==['D'], by_frame
            if mode=='layer_frames':
                assert [by_frame[i] for i in range(4)]==[[n] for n in names], by_frame
            assert int(js('app.activeDocument.id;'))==source
            case={'mode':mode,'copy_seconds':round(time.perf_counter()-start,3),'frames':by_frame,'alignments':[]}

            for alignment in ('absolute','center','ground_line'):
                payload=json.loads((job/'trigger_copy.json').read_text(encoding='utf-8-sig'))
                payload['settings']={'align_mode':alignment}
                lua = '''local spr=Sprite(128,128,ColorMode.RGB)
spr.layers[1].name='Target'
if spr.layers[1]:cel(1) then spr:deleteCel(spr.layers[1]:cel(1)) end
app.activeFrame=spr.frames[1];app.activeLayer=spr.layers[1]
local hostApp=app
local proxy=setmetatable({clipboard={text=PAYLOAD}}, {__index=hostApp,__newindex=function(_,k,v)hostApp[k]=v end})
local env=setmetatable({app=proxy},{__index=_G})
assert(loadfile(SCRIPT,'t',env))()
local result={width=spr.width,height=spr.height,frames=#spr.frames,layers={}}
local function scan(items)
 for _,l in ipairs(items) do
  if l.isGroup then scan(l.layers) else
   local item={name=l.name,cels={}}
   for _,cel in ipairs(l.cels) do
    local path=PREFIX..'_'..tostring(#result.layers+1)..'_'..cel.frame.frameNumber..'.png'
    cel.image:saveAs(path)
    table.insert(item.cels,{frame=cel.frame.frameNumber,x=cel.position.x,y=cel.position.y,opacity=cel.opacity,file=path})
   end
   table.insert(result.layers,item)
  end
 end
end
scan(spr.layers)
local f=assert(io.open(RESULT,'w'));f:write(json.encode(result));f:close()
spr:saveAs(ASEFILE)
'''
                result_path=job/(alignment+'.json')
                values={'PAYLOAD':json.dumps(json.dumps(payload)), 'SCRIPT':json.dumps(str(root/'scripts/aseprite_paste.lua')),
                        'PREFIX':json.dumps(str(job/alignment)), 'RESULT':json.dumps(str(result_path)),
                        'ASEFILE':json.dumps(str(job/(alignment+'.aseprite')))}
                for key,value in values.items():lua=lua.replace(key,value)
                lua_path=job/(alignment+'.lua');lua_path.write_text(lua,encoding='utf-8')
                proc=subprocess.run([str(args.aseprite),'--batch','--script',str(lua_path)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
                assert proc.returncode==0 and result_path.is_file(),proc.stdout+proc.stderr
                pasted=json.loads(result_path.read_text())
                cels=[c for l in pasted['layers'] for c in l['cels']]
                assert len(cels)==4,(mode,alignment,pasted)
                assert pasted['frames']==(4 if mode=='layer_frames' else 2 if mode=='folder_frames' else 1)
                if mode=='layer_frames':assert len(pasted['layers'])==1
                if mode=='folder_frames':
                    assert len(pasted['layers'])==3
                    assert [len(l['cels']) for l in pasted['layers']]==[1,1,2],pasted
                matched_names={}
                for cel in cels:
                    actual=Image.open(cel['file']).convert('RGBA')
                    candidates=[e for e in pixels if (e.get('frame_index',0)+1)==cel['frame']]
                    matches=[e for e in candidates if actual.size==Image.open(job/e['file']).size and actual.tobytes()==Image.open(job/e['file']).convert('RGBA').tobytes()]
                    assert len(matches)==1,(mode,cel)
                    el=matches[0]
                    matched_names[cel['file']]=el['name']
                    frame_pixels=[e for e in pixels if e.get('frame_index',0)==el.get('frame_index',0)]
                    minx=min(e['x'] for e in frame_pixels);miny=min(e['y'] for e in frame_pixels)
                    maxx=max(e['x']+e['width'] for e in frame_pixels);maxy=max(e['y']+e['height'] for e in frame_pixels)
                    ox=0 if alignment=='absolute' else (128-(maxx-minx))//2-minx
                    oy=0 if alignment=='absolute' else ((64-(maxy-miny)) if alignment=='ground_line' else (128-(maxy-miny))//2)-miny
                    assert (cel['x'],cel['y'])==(el['x']+ox,el['y']+oy)
                    assert cel['opacity']==int(el['opacity']*255/100+0.5)
                rows=[{c['frame']:matched_names[c['file']] for c in layer['cels']} for layer in reversed(pasted['layers']) if layer['cels']]
                if mode=='folder_frames':assert rows==[{1:'A',2:'D'},{1:'B'},{1:'C'}],rows
                if mode=='normal':assert rows==[{1:'A'},{1:'B'},{1:'C'},{1:'D'}],rows
                case['alignments'].append({'alignment':alignment,'pixel_exact':True,'cels':len(cels)})
            report['cases'].append(case)

        # Reverse direction uses the real installed Aseprite host, not mocked metadata.
        reverse=out/'ase-copy';reverse.mkdir()
        settings=out/'profile'/'Ase-PS-Bridge'/'bridge_settings.json'
        settings.write_text(json.dumps({'active_temp_path':str(reverse)}),encoding='utf-8')
        lua='''local spr=app.open(ASEFILE)
local rows={}
local function collect(items)for _,l in ipairs(items)do if l.isGroup then collect(l.layers) else table.insert(rows,l) end end end
collect(spr.layers);app.range.layers=rows;app.activeFrame=spr.frames[1]
assert(loadfile(SCRIPT))()
'''.replace('ASEFILE',json.dumps(str(out/'normal'/'absolute.aseprite'))).replace('SCRIPT',json.dumps(str(root/'scripts/aseprite_copy.lua')))
        path=out/'reverse.lua';path.write_text(lua,encoding='utf-8')
        proc=subprocess.run([str(args.aseprite),'--batch','--script',str(path)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        jobs=list(reverse.glob('bridge_job_*'))
        assert proc.returncode==0 and len(jobs)==1,proc.stdout+proc.stderr
        job=jobs[0]
        reverse_meta=json.loads((job/'metadata.json').read_text(encoding='utf-8-sig'))
        reverse_source=int(js("app.documents.add(128,128,72,'Southpaw Reverse Synthetic',NewDocumentMode.RGB,DocumentFill.TRANSPARENT).id;"))
        try:
            execute(root/'scripts/photoshop_paste.jsx',job)
            assert (job/'status_done.json').is_file() and not (job/'status_error.txt').exists()
            # Render each imported layer onto a full-canvas temporary document.
            js(r'''
var src=app.activeDocument;if(src.id!=SOURCE)throw Error('Reverse source mismatch');
var names=NAMES;var paths=PATHS;
function exportItems(items){for(var i=0;i<items.length;i++){
 var l=items[i];if(l.typename=='LayerSet'){exportItems(l.layers);continue;}
 var k=-1;for(var j=0;j<names.length;j++)if(names[j]==l.name)k=j;
 if(k<0)continue;
 var tmp=app.documents.add(128,128,72,'Southpaw Reverse Export',NewDocumentMode.RGB,DocumentFill.TRANSPARENT);
 try{app.activeDocument=src;l.duplicate(tmp,ElementPlacement.PLACEATBEGINNING);app.activeDocument=tmp;
 var options=new PNGSaveOptions();tmp.saveAs(new File(paths[k]),options,true,Extension.LOWERCASE);}
 finally{tmp.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=src;}
}}
exportItems(src.layers);
'''.replace('SOURCE',str(reverse_source)).replace('NAMES',json.dumps(names)).replace('PATHS',json.dumps([str(out/('reverse-'+n+'.png')) for n in names])))
            for el in reverse_meta['elements']:
                if el['type']!='layer':continue
                expected=Image.new('RGBA',(128,128))
                expected.alpha_composite(Image.open(job/el['file']).convert('RGBA'),(el['x'],el['y']))
                actual=Image.open(out/('reverse-'+el['name']+'.png')).convert('RGBA')
                assert actual.getchannel('A').tobytes()==expected.getchannel('A').tobytes(),el['name']
                black=Image.new('RGBA',actual.size,(0,0,0,255))
                assert Image.alpha_composite(black,actual).tobytes()==Image.alpha_composite(black,expected).tobytes(),el['name']
            report['reverse']={'layers':reverse_meta['layer_count'],'alpha_and_rendered_pixels_exact':True,
                               'transparent_rgb_ignored':True,'canvas':[128,128]}
        finally:
            js('for(var i=0;i<app.documents.length;i++)if(app.documents[i].id=='+str(reverse_source)+'){app.documents[i].close(SaveOptions.DONOTSAVECHANGES);break;}')
    finally:
        if source is not None:
            js('for(var i=0;i<app.documents.length;i++){var d=app.documents[i];if(d.id=='+str(source)+'){d.close(SaveOptions.DONOTSAVECHANGES);break;}}app.preferences.rulerUnits='+old_units+';')
        after=js('var r=[];for(var i=0;i<app.documents.length;i++)r.push(app.documents[i].id);r.join(",");')
        report['user_document_ids_unchanged']=before==after
        report['transport']='production-cli' if args.cli else 'version-specific-com'
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        pythoncom.CoUninitialize()
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()

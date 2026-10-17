/* Ward slot V2: isolated, deterministic tests. No DB, network or browser calls. */
/*
 * [LOCAL ADAPTATION] 交付版本的源码断言写的是**压缩写法**（无空格），本仓库格式化后
 * 源码为 `intersectObjects(slotTargets, false)` / `editorActive ? editorState : null`。
 * 三处源码正则改为容忍空格，断言语义（真实瓦片射线 / 槽位编辑器接入既有沙盘）不变；
 * 其余 19 项运行时断言原样保留。见 docs/WARD_SLOT_SANDBOX_V2_INTEGRATION.md。
 */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const root=path.join(__dirname,'src','modules','ward-map');
const cache=new Map();
function load(file){
 file=path.resolve(file);if(cache.has(file))return cache.get(file).exports;
 const mod={exports:{}};cache.set(file,mod);
 const raw=fs.readFileSync(file,'utf8');
 const compiled=ts.transpileModule(raw,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 const req=(name)=>name.startsWith('.')?load(path.resolve(path.dirname(file),name+'.ts')):require(name);
 new Function('module','exports','require',compiled)(mod,mod.exports,req);
 return mod.exports;
}
const ed=load(path.join(root,'editor.ts')),layout=load(path.join(root,'scene-layout.ts')),grid=load(path.join(root,'slot-grid.ts'));
const room=(id,code,floor=1)=>({ward_id:id,code,name:code,department_id:1,department_name:'模拟病区',building:'A',floor,bed_count:2,simulated_position:{x:0,z:0}});
const bed=(id,code,wardId,slot,status='AVAILABLE')=>({id,code,ward_id:wardId,ward_code:`R${wardId}`,ward_name:'模拟病房',department_id:1,department_name:'模拟病区',building:'A',floor:1,bed_type:'GENERAL',is_isolation:false,status,simulated_position:{x:0,z:0},scene_slot:slot,scene_rotation:0,patient:null,state_warning:null});
const rooms=[room(1,'101'),room(2,'102')],real=[bed(41,'A-01',1,0),bed(42,'A-02',1,2,'OCCUPIED'),bed(43,'A-03',2,0)];
let pass=0;function check(label,fn){fn();pass++;process.stdout.write('PASS '+label+'\n')}
let state=ed.initialEditor(rooms,real);
const sceneRoom=layout.createHospitalPlan(rooms,real).floors[0].rooms.find(r=>r.room.ward_id===1);
check('floor provides fixed twelve or more slots',()=>assert.ok(grid.floorSlotCount(sceneRoom)>=12));
check('occupied ground tiles distinguish actual beds',()=>assert.equal(grid.listFloorSlots(sceneRoom,state).filter(s=>s.occupancy==='real').length,2));
check('floor empty tiles are clickable slot IDs',()=>assert.equal(grid.listFloorSlots(sceneRoom,state).find(s=>s.slot===1).label,'101 · S02'));
check('cannot place on a real bed',()=>assert.equal(grid.slotIntent(state,rooms,{wardId:1,slot:0,rotation:0},'add',null).ok,false));
check('can place on vacant bed slot',()=>assert.equal(grid.slotIntent(state,rooms,{wardId:1,slot:1,rotation:0},'add',null).ok,true));
const before=layout.createHospitalPlan(rooms,real).bedLocations;
state=ed.addDraft(state,rooms,1,1,'SIM-001');const draft=state.items.find(i=>i.synthetic);
check('new bed is an isolated negative-ID draft',()=>assert.ok(draft.bed.id<0));
check('existing bed coordinates remain fixed',()=>{const after=ed.editorLayout(rooms,state).bedLocations;for(const b of real)assert.deepEqual(after[b.id],before[b.id])});
check('ground tile and draft-bed placement align exactly',()=>{
 const slot=grid.listFloorSlots(sceneRoom,state).find(s=>s.slot===1),actual=ed.editorLayout(rooms,state).floors[0].beds.find(b=>b.bed.id===draft.bed.id);
 assert.equal(actual.x,slot.x);assert.equal(actual.z,slot.z);
});
check('cannot overlay another draft or a real bed',()=>assert.throws(()=>ed.addDraft(state,rooms,1,1,'SIM-002'),/已有床位/));
check('real bed cannot be deleted using the slot tool',()=>assert.equal(grid.slotIntent(state,rooms,{wardId:1,slot:0,rotation:0},'remove',null).ok,false));
check('draft can move to an empty slot',()=>{state=ed.moveDraft(state,rooms,draft.key,{wardId:1,slot:4,rotation:90});assert.equal(state.items.find(i=>i.key===draft.key).pose.slot,4)});
check('moving over a real bed is blocked',()=>assert.equal(grid.slotIntent(state,rooms,{wardId:1,slot:2,rotation:90},'move',draft.bed.id).ok,false));
check('room identity preserved when moving to another room',()=>{state=ed.moveDraft(state,rooms,draft.key,{wardId:2,slot:1,rotation:0});assert.equal(state.items.find(i=>i.key===draft.key).pose.wardId,2)});
check('supply delta contains exactly one virtual bed',()=>assert.equal(ed.supplyDelta(state,real).added.length,1));
check('one-click remove changes only the draft',()=>{state=ed.removeDraft(state,draft.key);assert.equal(state.items.filter(i=>i.synthetic).length,0);assert.equal(state.items.filter(i=>!i.synthetic).length,3)});
check('undo restores and redo removes',()=>{state=ed.undo(state);assert.equal(state.items.some(i=>i.key===draft.key),true);state=ed.redo(state);assert.equal(state.items.some(i=>i.key===draft.key),false)});
check('slot positions stable across repeated layout runs',()=>assert.deepEqual(layout.createHospitalPlan(rooms,real),layout.createHospitalPlan([...rooms],real)));
const scenePath=path.join(__dirname,'src','components','WardScene3D.vue');const viewPath=path.join(__dirname,'src','views','WardMapView.vue');
check('real three.js floor mesh pick targets',()=>{const s=fs.readFileSync(scenePath,'utf8');assert.match(s,/intersectObjects\(\s*slotTargets\s*,\s*false\s*\)/);assert.match(s,/buildFloorSlots\(\s*f\s*,\s*layer\s*\)/);assert.doesNotMatch(s,/function previewPlacement\(/)});
check('slot editor wired to existing simulation',()=>{const s=fs.readFileSync(viewPath,'utf8');assert.match(s,/WardSlotEditor/);assert.match(s,/editorActive\s*\?\s*editorState\s*:\s*null/);assert.match(s,/@edit-place="onEditPlace"/)});
console.log(`WARD_SLOT_SANDBOX_V2 ${pass}/${pass} PASS`);

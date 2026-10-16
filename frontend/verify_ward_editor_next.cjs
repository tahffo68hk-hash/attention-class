/** Pure TS editor and scene geometry runtime checks, no browser/WebGL claims. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const ts=require('typescript'),base=path.resolve(__dirname,'src/modules/ward-map');
function load(file,cache=new Map()){
 const filename=path.join(base,file+'.ts');if(cache.has(filename))return cache.get(filename).exports;
 const js=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 const m=new Module(filename,module);m.filename=filename;m.paths=module.paths;cache.set(filename,m);
 m.require=name=>name.startsWith('./')?load(name.slice(2),cache):require(name);
 m._compile(js,filename);return m.exports;
}
const E=load('editor'),S=load('scene-layout');let tested=0;
const okay=(condition,description)=>{assert(condition,description);tested++};
const room=(id,building='A')=>({ward_id:id,code:String(id),name:`病房${id}`,department_id:1,department_name:'模拟内科',building,floor:1,bed_count:2,simulated_position:{x:0,z:0}});
const bed=(id,ward=1,slot=null)=>({id,code:`BED-${id}`,status:'AVAILABLE',bed_type:'NORMAL',is_isolation:false,ward_id:ward,ward_code:String(ward),ward_name:`病房${ward}`,department_id:1,department_name:'模拟内科',building:'A',floor:1,scene_slot:slot,scene_rotation:0,patient:null,state_warning:null,simulated_position:{x:0,z:0}});
const rooms=[room(1),room(2)],real=[bed(10,1,3),bed(11,1,0),bed(12,2,1)];
let s=E.initialEditor(rooms,real);
okay(s.items.length===3,'all real beds included');
okay(s.items.find(i=>i.bed.id===10).pose.slot===3,'persisted slot used');
okay(s.items.find(i=>i.bed.id===11).pose.slot===0,'another persisted slot used');
okay(E.validatePose(s,rooms,'new',{wardId:1,slot:3,rotation:0})?.includes('已有床位'),'collision against REAL bed');
try{E.addDraft(s,rooms,1,3,'SIM-001');throw Error('accepted illegal position')}catch(e){okay(String(e).includes('已有床位'),'real-vs-draft blocked')}
const initial=S.createHospitalPlan(rooms,E.editorBeds(s));
s=E.addDraft(s,rooms,1,4,'SIM-001');
const added=s.items.find(i=>i.synthetic);okay(added.bed.id<0,'virtual bed stays negative');
okay(E.validatePose(s,rooms,'another',{wardId:1,slot:4,rotation:0})?.includes('已有床位'),'draft-vs-draft blocked');
const withNew=E.editorLayout(rooms,s);
for(const id of [10,11,12])okay(JSON.stringify(initial.bedLocations[id])===JSON.stringify(withNew.bedLocations[id]),`existing real bed ${id} did not shift`);
const delta=E.supplyDelta(s,real);okay(delta.added.length===1&&delta.removed.length===0,'new synthetic supply computed');
let moved=E.moveDraft(s,rooms,added.key,{wardId:1,slot:6,rotation:90});
okay(moved.items.find(i=>i.key===added.key).pose.rotation===90,'rotate persisted in state');
const beforeMove=E.editorLayout(rooms,s),afterMove=E.editorLayout(rooms,moved);
okay(JSON.stringify(beforeMove.bedLocations[added.bed.id])!==JSON.stringify(afterMove.bedLocations[added.bed.id]),'moved draft changes location');
for(const id of [10,11,12])okay(JSON.stringify(beforeMove.bedLocations[id])===JSON.stringify(afterMove.bedLocations[id]),`real bed ${id} not displaced by draft move`);
moved=E.undo(moved);okay(moved.items.find(i=>i.key===added.key).pose.slot===4,'undo returns position');
moved=E.redo(moved);okay(moved.items.find(i=>i.key===added.key).pose.slot===6,'redo reapplies position');
moved=E.removeDraft(moved,added.key);okay(E.supplyDelta(moved,real).added.length===0,'removed synthetic supply');
moved=E.removeDraft(moved,'bed:11');okay(E.supplyDelta(moved,real).removed.includes(11),'simulated removal from available real supply');
okay(E.roomSlots(rooms[0],12)===12,'room capacity stable at 12');
const scene=fs.readFileSync(path.join(__dirname,'src/components/WardScene3D.vue'),'utf8');
for(const clause of ['edit-place','pointerup','ensureGhost','raycaster.ray.intersectPlane','ghostMaterial.color.set',"props.editorOccupied?.some"]){okay(scene.includes(clause),`interactive scene contains ${clause}`)}
for(const file of ['WardScene3D.vue','WardBedEditor.vue','WardBedManager.vue']){
 const src=fs.readFileSync(path.join(__dirname,'src/components',file),'utf8');
 const script=src.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)?.[1];
 okay(Boolean(script)&&ts.createSourceFile(file,script,ts.ScriptTarget.Latest,true,ts.ScriptKind.TS).parseDiagnostics.length===0,`${file} TS AST`);
}
console.log(`WARD_EDITOR_NEXT=${tested}/${tested} PASS (static+TS runtime, not browser)`);

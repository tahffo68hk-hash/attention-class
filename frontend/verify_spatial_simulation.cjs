/* Deterministic geometry assertions against real TypeScript layout implementation. */
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),Module=require('module');
const ts=require('typescript');
function load(name){const source=fs.readFileSync(path.join(__dirname,'src/modules/ward-map',name),'utf8');
 const out=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},reportDiagnostics:true});
 assert(!(out.diagnostics||[]).some(d=>d.category===ts.DiagnosticCategory.Error),`${name} TS parse`);
 const m=new Module(name,module);m.filename=name;m.paths=module.paths;
 // scene-layout 现在运行时依赖 slot-grid.ts：Node 不解析 `.ts`，补相对模块的转译加载。
 m.require=s=>s.startsWith('./')?load(`${s.slice(2)}.ts`):require(s);
 m._compile(out.outputText,name);return m.exports}
const {demoSnapshot}=load('demo.ts'),{createHospitalPlan,FLOOR_HEIGHT}=load('scene-layout.ts');
const data=demoSnapshot(),plan=createHospitalPlan(data.rooms,data.beds);
assert.equal(data.beds.length,44);assert.equal(plan.bedLocations&&Object.keys(plan.bedLocations).length,44);
const pair=(a,b)=>Math.hypot(a.x-b.x,a.z-b.z);
for(const f of plan.floors){
 assert.equal(f.corridorWidth,4.5);
 const corridorLeft=f.corridorZ-f.corridorWidth/2,corridorRight=f.corridorZ+f.corridorWidth/2;
 const occupied=[];
 for(const r of f.rooms){
  assert(r.x>=0&&r.z>=0&&r.x+r.width<=f.width+.001&&r.z+r.depth<=f.depth+.001);
  assert(r.side==='north'?r.z+r.depth<=corridorLeft+.001:r.z>=corridorRight-.001);
  for(const other of occupied) assert(!((r.x<other.x+other.width-.01)&&(r.x+r.width>other.x+.01)&&(r.z<other.z+other.depth-.01)&&(r.z+r.depth>other.z+.01)),'room overlap');
  occupied.push(r);
 }
 for(const bed of f.beds){
  const r=f.rooms.find(r=>r.room.ward_id===bed.bed.ward_id);assert(r,'room assignment');
  assert(bed.x-1>r.x&&bed.x+1.4<r.x+r.width,'bed/cabinet avoids side wall');
  assert(bed.z-1.45>r.z&&bed.z+1.45<r.z+r.depth,'bed avoids front/back wall');
  assert(bed.z<corridorLeft-1||bed.z>corridorRight+1,'no bed in corridor');
  assert.equal(bed.orientation,r.side==='north'?0:Math.PI);
  for(const b of f.beds){if(b.bed.id!==bed.bed.id)assert(pair(bed,b)>2.2,'no intersecting beds')}
 }
}
const stable=createHospitalPlan([...data.rooms].reverse(),[...data.beds].reverse());
assert.deepEqual(stable.bedLocations,plan.bedLocations,'stable regardless of API order');
assert.equal(new Set(Object.keys(plan.bedLocations)).size,data.beds.length);
for(const building of plan.buildings){assert(building.floors.length>=1);
 for(const f of building.floors){assert.equal(f.width,building.width);assert.equal(f.depth,building.depth);assert.equal(f.corridorZ,building.floors[0].corridorZ)}
 for(let i=1;i<building.floors.length;i++)assert.equal(building.floors[i].index*FLOOR_HEIGHT-building.floors[i-1].index*FLOOR_HEIGHT,FLOOR_HEIGHT)
}
console.log(`SPATIAL_LAYOUT: PASS (${plan.floors.length} floors, ${data.beds.length} uniquely placed beds, 0 overlaps, corridor & wall clearance, deterministic refresh)`);
for(const name of ['scene-layout.ts','sandbox.ts'])load(name);
console.log('SANDBOX_CONTRACT_TS: PASS');

<script setup lang="ts">
import {computed,ref,watch,onMounted,onBeforeUnmount} from 'vue';
// 本地适配：模块引用改走 `@/` 别名（本仓库路径约定），逻辑与交付版本一致。
import type {WardBed,WardRoom} from '@/modules/ward-map/types';
import {createHospitalPlan} from '@/modules/ward-map/scene-layout';
import {initialEditor,addDraft,moveDraft,removeDraft,undo,redo,
 type EditorState,type EditPose,type Rotation} from '@/modules/ward-map/editor';
import {listFloorSlots,slotIntent,type FloorSlot} from '@/modules/ward-map/slot-grid';

type Tool='select'|'add'|'move'|'remove';
const props=defineProps<{beds:WardBed[];rooms:WardRoom[];active:boolean;selectedId:number|null}>();
const emit=defineEmits<{
 (e:'change',state:EditorState|null):void;
 (e:'intent',tool:Tool,roomId:number,rotation:Rotation):void;
 (e:'close'):void;
 (e:'locate',bedId:number):void;
}>();
const state=ref<EditorState>(initialEditor(props.rooms,props.beds));
const roomId=ref(props.rooms[0]?.ward_id??0);
const rotation=ref<Rotation>(0);
const tool=ref<Tool>('select');
const nextNumber=ref(1);
const error=ref('');
const notice=ref('');
const selected=computed(()=>state.value.items.find(i=>i.bed.id===props.selectedId)??null);
const room=computed(()=>props.rooms.find(r=>r.ward_id===roomId.value));
const plan=computed(()=>createHospitalPlan(props.rooms,state.value.items.map(i=>i.bed),
 Object.fromEntries(state.value.items.map(i=>[i.bed.id,i.pose]))));
const currentSceneRoom=computed(()=>plan.value.floors.flatMap(f=>f.rooms).find(r=>r.room.ward_id===roomId.value));
const tiles=computed(()=>currentSceneRoom.value?listFloorSlots(currentSceneRoom.value,state.value):[]);
const freeCount=computed(()=>tiles.value.filter(t=>t.available).length);
const drafts=computed(()=>state.value.items.filter(i=>i.synthetic));
const realCount=computed(()=>state.value.items.filter(i=>!i.synthetic).length);

function update(next:EditorState,tip:string){state.value=next;error.value='';notice.value=tip;emit('change',next)}
function run(operation:()=>EditorState,message:string){
 try{update(operation(),message)}catch(e){error.value=(e as Error).message;notice.value=''}
}
function code(){
 let result='';do{result=`SIM-${String(nextNumber.value++).padStart(3,'0')}`}
 while(state.value.items.some(i=>i.bed.code===result));return result;
}
function setTool(next:Tool){tool.value=next;error.value='';notice.value=next==='add'?'选择地面空槽位放下模拟床位':next==='move'?'先选择模拟床，再点击目标空槽位':next==='remove'?'点击青色模拟床槽位即可移除':'查看当前病房槽位';}
function chooseTile(tile:FloorSlot){
 if(tool.value==='select'){
  if(tile.bedId!==null)emit('locate',tile.bedId);
  else notice.value=`${tile.label} · 空槽位`;
  return;
 }
 const pose:EditPose={wardId:tile.wardId,slot:tile.slot,rotation:rotation.value};
 applySlot(pose);
}
function applySlot(pose:EditPose,overrideId:number|null=null){
 const currentId=overrideId??props.selectedId;
 const intent=slotIntent(state.value,props.rooms,pose,tool.value==='select'?'add':tool.value,currentId);
 if(!intent.ok){error.value=intent.message;notice.value='';return}
 if(tool.value==='add'){
  const generated=code();run(()=>addDraft(state.value,props.rooms,pose.wardId,pose.slot,generated,pose.rotation),`${generated} 已放置到 S${pose.slot+1}`);
 }else if(tool.value==='move'){
  const item=state.value.items.find(i=>i.bed.id===currentId);
  if(!item?.synthetic){error.value='只能移动模拟床位';return}
  run(()=>moveDraft(state.value,props.rooms,item.key,pose),`已移动至 S${pose.slot+1}`);
 }else if(tool.value==='remove'){
  const item=state.value.items.find(i=>i.bed.id===intent.targetId);
  if(!item?.synthetic){error.value='只能移除模拟床位';return}
  run(()=>removeDraft(state.value,item.key),`已移除 ${item.bed.code}`);
 }
}
function placeFromScene(pose:EditPose,bedId:number|null){roomId.value=pose.wardId;applySlot(pose,tool.value==='move'?bedId:null)}
function cancel(){setTool('select')}
onMounted(()=>window.addEventListener('keydown',onGlobalKey));
onBeforeUnmount(()=>window.removeEventListener('keydown',onGlobalKey));
function onGlobalKey(e:KeyboardEvent){if(props.active&&e.key==='Escape'&&tool.value!=='select'){e.preventDefault();cancel()}}
function onKey(e:KeyboardEvent){
 if(e.key==='Escape'){e.preventDefault();cancel()}
 else if(e.key.toLowerCase()==='r'&&!['INPUT','TEXTAREA','SELECT'].includes((e.target as HTMLElement).tagName)){
  e.preventDefault();rotation.value=((rotation.value+90)%360) as Rotation;
 }
}
function reset(){nextNumber.value=1;update(initialEditor(props.rooms,props.beds),'已重置模拟草稿');setTool('select')}
function history(direction:'undo'|'redo'){
 const next=direction==='undo'?undo(state.value):redo(state.value);
 update(next,direction==='undo'?'已撤销':'已重做');
}
watch(()=>props.active,active=>{
 if(active){nextNumber.value=1;state.value=initialEditor(props.rooms,props.beds);roomId.value=props.rooms[0]?.ward_id??0;setTool('select');emit('change',state.value)}
});
watch(()=>props.beds,beds=>{
 if(props.active&&!state.value.history.length){state.value=initialEditor(props.rooms,beds);emit('change',state.value)}
});
watch([tool,roomId,rotation],()=>emit('intent',tool.value,roomId.value,rotation.value));
watch(()=>props.selectedId,id=>{
 const item=state.value.items.find(i=>i.bed.id===id);
 if(item&&tool.value==='move'&&item.synthetic)roomId.value=item.pose.wardId;
});
defineExpose({placeFromScene,cancel});
</script>

<template>
 <section v-if="active" class="slot-editor" aria-label="固定槽位式调度沙盘" @keydown="onKey" @contextmenu.prevent="cancel">
  <div class="slot-heading"><div><strong>槽位式沙盘</strong><small>固定地面槽位 · 左键放置 / 移除 · 仅模拟，不写数据库</small></div><button type="button" @click="emit('close')">退出沙盘</button></div>
  <div class="slot-toolbar" role="group" aria-label="选择沙盘工具">
   <button v-for="t in [{id:'select',name:'查看'},{id:'add',name:'＋ 放置'},{id:'move',name:'↔ 移动'},{id:'remove',name:'− 移除'}]" :key="t.id" type="button" :aria-pressed="tool===t.id" :class="{'slot-current':tool===t.id}" @click="setTool(t.id as Tool)">{{t.name}}</button>
   <button type="button" :disabled="!state.history.length" @click="history('undo')">↶ 撤销</button>
   <button type="button" :disabled="!state.future.length" @click="history('redo')">↷ 重做</button>
   <button type="button" @click="reset">重置</button>
  </div>
  <div class="slot-controls">
   <label>病房 <select v-model.number="roomId"><option v-for="r in rooms" :key="r.ward_id" :value="r.ward_id">{{r.code}} · {{r.name}}</option></select></label>
   <label>床头朝向 <select v-model.number="rotation"><option v-for="degree in [0,90,180,270]" :key="degree" :value="degree">{{degree}}°</option></select></label>
   <span class="slot-stat">{{realCount}} 正式床 · {{drafts.length}} 模拟床 · 当前病房 {{freeCount}} 空槽</span>
  </div>
  <p class="slot-explain" role="status">{{notice||'地面有固定 S01、S02 等槽位；悬停预览、左键操作，Esc / 右键取消工具。'}}</p>
  <div class="slot-room-head"><strong>{{room?.code}} · {{room?.name}}</strong><span>固定槽位（与 3D 地面一一对应）</span></div>
  <div class="slot-tiles" role="group" :aria-label="`${room?.name??'病房'} 床位槽位`">
   <button v-for="tile in tiles" :key="`${tile.wardId}:${tile.slot}`" type="button" class="slot-tile"
     :class="[`slot-${tile.occupancy}`,{'slot-target':tool==='select'?false:slotIntent(state,rooms,{wardId:tile.wardId,slot:tile.slot,rotation},tool,selectedId).ok}]"
     :title="`${tile.label} · ${tile.occupancy==='empty'?'空槽':tile.occupancy==='real'?'正式床位':'模拟床位'}`"
     @click="chooseTile(tile)"><strong>S{{String(tile.slot+1).padStart(2,'0')}}</strong><small>{{tile.occupancy==='empty'?'空槽':tile.occupancy==='real'?'正式占用':'模拟占用'}}</small></button>
  </div>
  <div class="slot-legend"><span>◇ 空槽位</span><span>■ 正式占用</span><span>▣ 模拟占用</span><span>绿色边框=当前工具可操作</span></div>
  <p v-if="tool==='move'" class="slot-explain">{{selected?.synthetic?`当前选中 ${selected.bed.code}，点击目标空槽位完成移动`:'请先点击 3D 中的一张模拟床，或在下方选择模拟床'}}</p>
  <div v-if="tool==='move'" class="slot-draft-list"><button v-for="d in drafts" :key="d.key" type="button" :aria-pressed="d.bed.id===selectedId" @click="emit('locate',d.bed.id)">{{d.bed.code}} · S{{d.pose.slot+1}}</button></div>
  <p v-if="error" class="slot-error" role="alert">{{error}}</p>
  <small class="slot-boundary">正式床位不可通过本工具删除或移动。模拟供给变化须点“重新计算调度”后才更新优化结果；布局非真实医院 BIM。</small>
 </section>
</template>
<style scoped>
.slot-editor{display:grid;gap:12px;border:1px solid var(--wm-stroke,#c9dbe5);border-radius:12px;padding:14px;margin:12px 0;background:var(--surface,var(--wm-surface,#fff));color:inherit}
.slot-heading,.slot-toolbar,.slot-controls,.slot-room-head,.slot-legend,.slot-draft-list{display:flex;align-items:center;flex-wrap:wrap;gap:8px}
.slot-heading,.slot-room-head{justify-content:space-between}.slot-heading>div{display:grid;gap:4px}.slot-heading small,.slot-boundary,.slot-explain,.slot-room-head span,.slot-stat,.slot-legend{font-size:12px;color:var(--wm-muted,#66788a)}
.slot-heading button,.slot-toolbar button,.slot-draft-list button{border:1px solid var(--wm-stroke,#c9dbe5);background:transparent;color:inherit;border-radius:7px;padding:8px 10px;cursor:pointer}
.slot-toolbar .slot-current{border-color:#37a6a0;background:rgba(42,166,159,.14);font-weight:700}.slot-toolbar button:disabled{opacity:.35;cursor:not-allowed}
.slot-controls label{display:flex;align-items:center;gap:6px;font-size:12px}.slot-controls select{border:1px solid var(--wm-stroke,#c9dbe5);background:var(--surface,#fff);color:inherit;border-radius:6px;padding:7px}
.slot-tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;max-width:470px}
.slot-tile{display:grid;gap:2px;text-align:left;min-height:52px;padding:8px;border-radius:6px;border:1px solid var(--wm-stroke,#becdd8);color:inherit;background:rgba(120,145,160,.065);cursor:pointer}
.slot-tile small{font-size:11px;opacity:.8}.slot-real{background:rgba(110,125,145,.13)}.slot-draft{background:rgba(21,164,175,.18);border-color:#19a6b0}
.slot-target{outline:2px solid #36b783;outline-offset:-2px}.slot-tile:focus-visible{outline:3px solid #d5a02b;outline-offset:1px}
.slot-error{color:#c34141;font-size:12px}.slot-boundary{line-height:1.55}
@media(max-width:640px){.slot-controls{align-items:stretch;flex-direction:column}.slot-tiles{max-width:none}}
</style>

/**
 * 三维模拟编辑器 —— **纯函数模型**，只操作内存草稿。
 *
 * 边界（务必保持）：
 * - 坐标是**展示槽位**（房间网格吸附位），不是医疗评分坐标，也不参与推荐评分；
 * - 合成床位 id 一律为**负数**，绝不可译成正式床位 id 传给创建/预占接口；
 * - 这里没有任何 HTTP/DB 调用：草稿只活在本页内存，刷新即失。
 */
import type {WardBed,WardRoom} from './types';
import {createHospitalPlan, type HospitalPlan} from './scene-layout';

export type Rotation = 0 | 90 | 180 | 270;
export interface EditPose {wardId:number;slot:number;rotation:Rotation}
export interface EditedBed {key:string;bed:WardBed;pose:EditPose;synthetic:boolean}
export interface EditorState {items:EditedBed[];history:EditedBed[][];future:EditedBed[][]}

const clone=(a:EditedBed[]):EditedBed[]=>a.map(x=>({...x,pose:{...x.pose},bed:{...x.bed}}));
const byBed=(a:WardBed,b:WardBed)=>a.code.localeCompare(b.code,'zh-CN',{numeric:true})||a.id-b.id;

export function roomSlots(_room:WardRoom,bedCount=0):number {
  // 固定 12 槽位起步；仅在确有必要时按 3 的倍数增长 ——
  // 自动扩张几何尺寸会把已有床位整体挪位，因此容量增长必须保守。
  return Math.max(12,Math.ceil(Math.max(1,bedCount)/3)*3)
}

export function initialEditor(rooms:WardRoom[],beds:WardBed[]):EditorState {
  const items:EditedBed[]=[];
  for(const room of rooms){
    const taken=new Set<number>();
    const list=beds.filter(b=>b.ward_id===room.ward_id).sort(byBed);
    // 持久化槽位优先；缺失/重复的历史槽位按床号顺序确定性补位。
    for(const bed of list){
      const stored=bed.scene_slot;
      if(stored===null||stored===undefined||!Number.isInteger(stored)||stored<0||taken.has(stored))continue;
      taken.add(stored);
      items.push({key:`bed:${bed.id}`,bed,pose:{wardId:room.ward_id,slot:stored,rotation:(bed.scene_rotation??0) as Rotation},synthetic:false});
    }
    for(const bed of list){
      if(items.some(i=>i.bed.id===bed.id))continue;
      let slot=0;while(taken.has(slot))slot++;
      taken.add(slot);
      items.push({key:`bed:${bed.id}`,bed,pose:{wardId:room.ward_id,slot,rotation:0},synthetic:false});
    }
  }
  return {items,history:[],future:[]};
}

export function validatePose(state:EditorState,rooms:WardRoom[],key:string,pose:EditPose):string|null {
  const room=rooms.find(r=>r.ward_id===pose.wardId);if(!room)return '病房不存在';
  // 容量以「病房床位数」与「当前草稿占用数」的较大者为准，真实床与草稿床统一判据。
  const initialCapacity=Math.max(room.bed_count,state.items.filter(i=>i.pose.wardId===room.ward_id).length);
  if(!Number.isInteger(pose.slot)||pose.slot<0||pose.slot>=roomSlots(room,initialCapacity))return '超出病房合法床位槽位';
  if(![0,90,180,270].includes(pose.rotation))return '旋转角度不合法';
  if(state.items.some(i=>i.key!==key&&i.pose.wardId===pose.wardId&&i.pose.slot===pose.slot))return '该槽位已有床位（含正式床位）';
  return null;
}

function commit(state:EditorState,items:EditedBed[]):EditorState {return {items,history:[...state.history.slice(-49),clone(state.items)],future:[]}}

export function addDraft(state:EditorState,rooms:WardRoom[],roomId:number,slot:number,bedCode:string,rotation:Rotation=0):EditorState{
  const code=bedCode.trim();
  if(!code||state.items.some(i=>i.bed.code.toLocaleLowerCase()===code.toLocaleLowerCase()))throw new Error('模拟床号为空或重复');
  const room=rooms.find(r=>r.ward_id===roomId);if(!room)throw new Error('找不到病房');
  const key=`draft:${code}`;const pose:EditPose={wardId:roomId,slot,rotation};
  const reason=validatePose(state,rooms,key,pose);if(reason)throw new Error(reason);
  const sample=state.items.find(i=>i.pose.wardId===roomId)?.bed??state.items[0]?.bed;
  if(!sample)throw new Error('当前场景没有床位模板');
  // 负数 id：保证合成床永远不会与真实床位 id 空间冲突。
  const id=Math.min(0,...state.items.map(i=>i.bed.id))-1;
  const bed:WardBed={...sample,id,code,status:'AVAILABLE',ward_id:roomId,ward_code:room.code,
    ward_name:room.name,department_id:room.department_id,department_name:room.department_name,
    building:room.building,floor:room.floor,patient:null,state_warning:null,
    scene_slot:slot,scene_rotation:rotation};
  return commit(state,[...state.items,{key,bed,pose,synthetic:true}]);
}

export function moveDraft(state:EditorState,rooms:WardRoom[],key:string,pose:EditPose):EditorState {
  const target=state.items.find(i=>i.key===key);if(!target)throw new Error('床位不存在');
  const reason=validatePose(state,rooms,key,pose);if(reason)throw new Error(reason);
  // 位置没变就不写历史，避免「点了按钮但没动」也占一个撤销步。
  if(target.pose.wardId===pose.wardId&&target.pose.slot===pose.slot&&target.pose.rotation===pose.rotation)return state;
  const room=rooms.find(r=>r.ward_id===pose.wardId)!;
  return commit(state,state.items.map(i=>i.key===key?{...i,pose,bed:{...i.bed,
    ward_id:room.ward_id,ward_code:room.code,ward_name:room.name,building:room.building,
    floor:room.floor,department_id:room.department_id,department_name:room.department_name,
    scene_slot:pose.slot,scene_rotation:pose.rotation}}:i));
}

export function removeDraft(state:EditorState,key:string):EditorState {if(!state.items.some(i=>i.key===key))throw new Error('床位不存在');return commit(state,state.items.filter(i=>i.key!==key))}
export function undo(state:EditorState):EditorState {if(!state.history.length)return state;return {items:clone(state.history[state.history.length-1]!),history:state.history.slice(0,-1),future:[clone(state.items),...state.future]}}
export function redo(state:EditorState):EditorState {if(!state.future.length)return state;return {items:clone(state.future[0]),history:[...state.history,clone(state.items)],future:state.future.slice(1)}}
export function editorBeds(state:EditorState):WardBed[]{return state.items.map(i=>i.bed)}
export function editorLayout(rooms:WardRoom[],state:EditorState):HospitalPlan {
  return createHospitalPlan(rooms,editorBeds(state),Object.fromEntries(state.items.map(i=>[i.bed.id,i.pose])));
}

/** 相对**不可变真实快照**计算模拟供给增减：新增（负 id 草稿）与临时移除（真实空闲床）。 */
export function supplyDelta(state:EditorState,realBeds:WardBed[]){
  const realIds=new Set(realBeds.map(b=>b.id)),keptIds=new Set(state.items.map(i=>i.bed.id));
  const removed=realBeds.filter(b=>!keptIds.has(b.id)&&b.status==='AVAILABLE').map(b=>b.id);
  const added=state.items.filter(i=>i.synthetic&&!realIds.has(i.bed.id));
  return {removed,added};
}

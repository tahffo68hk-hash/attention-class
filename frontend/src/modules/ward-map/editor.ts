/** Sandbox-only editor. Coordinates are display slots, NOT medical scoring coordinates. */
import type {WardBed,WardRoom} from './types';
import {createHospitalPlan, type HospitalPlan} from './scene-layout';
export interface EditPose {wardId:number;slot:number;rotation:0|90|180|270}
export interface EditedBed {key:string;bed:WardBed;pose:EditPose;synthetic:boolean}
export interface EditorState {items:EditedBed[];history:EditedBed[][];future:EditedBed[][]}
const clone=(a:EditedBed[]):EditedBed[]=>a.map(x=>({...x,pose:{...x.pose},bed:{...x.bed}}));
export const initialEditor=(rooms:WardRoom[],beds:WardBed[]):EditorState=>{
 const items:EditedBed[]=[];
 for(const room of rooms){const list=beds.filter(b=>b.ward_id===room.ward_id).sort((a,b)=>a.code.localeCompare(b.code,'zh-CN',{numeric:true})||a.id-b.id);
 list.forEach((bed,slot)=>items.push({key:`bed:${bed.id}`,bed,pose:{wardId:room.ward_id,slot,rotation:0},synthetic:false}));}
 return {items,history:[],future:[]};
};
export function roomSlots(_room:WardRoom,bedCount=0):number {return Math.max(12,Math.ceil(Math.max(bedCount,1)/3)*3+3)}
export function validatePose(state:EditorState,rooms:WardRoom[],key:string,pose:EditPose):string|null {
 const room=rooms.find(r=>r.ward_id===pose.wardId);if(!room)return '病房不存在';
 if(!Number.isInteger(pose.slot)||pose.slot<0||pose.slot>=roomSlots(room,state.items.filter(i=>i.pose.wardId===room.ward_id).length))return '超出病房合法床位槽位';
 if(![0,90,180,270].includes(pose.rotation))return '旋转角度不合法';
 if(state.items.some(i=>i.key!==key&&i.pose.wardId===pose.wardId&&i.pose.slot===pose.slot))return '该槽位已有床位';
 return null;
}
function commit(state:EditorState,items:EditedBed[]):EditorState {return {items,history:[...state.history.slice(-49),clone(state.items)],future:[]}}
export function addDraft(state:EditorState,rooms:WardRoom[],roomId:number,slot:number,bedCode:string):EditorState{
 const code=bedCode.trim();if(!code||state.items.some(i=>i.bed.code===code))throw new Error('模拟床号为空或重复');
 const room=rooms.find(r=>r.ward_id===roomId);if(!room)throw new Error('找不到病房');
 const key=`draft:${code}`;const pose:EditPose={wardId:roomId,slot,rotation:0};const reason=validatePose(state,rooms,key,pose);if(reason)throw new Error(reason);
 const sample=state.items.find(i=>i.pose.wardId===roomId)?.bed??state.items[0]?.bed;
 if(!sample)throw new Error('当前场景没有床位模板');
 const bed:WardBed={...sample,id:-1-Math.max(0,...state.items.filter(i=>i.bed.id<0).map(i=>-i.bed.id)),code,status:'AVAILABLE',ward_id:roomId,ward_code:room.code,ward_name:room.name,department_id:room.department_id,department_name:room.department_name,building:room.building,floor:room.floor,patient:null,state_warning:null};
 return commit(state,[...state.items,{key,bed,pose,synthetic:true}]);
}
export function moveDraft(state:EditorState,rooms:WardRoom[],key:string,pose:EditPose):EditorState {
 const target=state.items.find(i=>i.key===key);if(!target)throw new Error('床位不存在');
 const reason=validatePose(state,rooms,key,pose);if(reason)throw new Error(reason);
 const room=rooms.find(r=>r.ward_id===pose.wardId)!;
 return commit(state,state.items.map(i=>i.key===key?{...i,pose,bed:{...i.bed,ward_id:room.ward_id,ward_code:room.code,ward_name:room.name,building:room.building,floor:room.floor,department_id:room.department_id,department_name:room.department_name}}:i));
}
export function removeDraft(state:EditorState,key:string):EditorState {if(!state.items.some(i=>i.key===key))throw new Error('床位不存在');return commit(state,state.items.filter(i=>i.key!==key))}
export function undo(state:EditorState):EditorState {if(!state.history.length)return state;return {items:clone(state.history[state.history.length-1]!),history:state.history.slice(0,-1),future:[clone(state.items),...state.future]}}
export function redo(state:EditorState):EditorState {if(!state.future.length)return state;return {items:clone(state.future[0]),history:[...state.history,clone(state.items)],future:state.future.slice(1)}}
export function editorBeds(state:EditorState):WardBed[]{return state.items.map(i=>i.bed)}
export function editorLayout(rooms:WardRoom[],state:EditorState):HospitalPlan {return createHospitalPlan(rooms,editorBeds(state))}

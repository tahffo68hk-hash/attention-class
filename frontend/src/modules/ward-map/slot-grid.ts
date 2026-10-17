/** Fixed floor tiles for the synthetic Ward Map editor. Presentation coordinates only. */
import type {WardRoom} from './types';
import type {SceneRoom} from './scene-layout';
import type {EditorState,EditPose,Rotation} from './editor';

export const SLOT_COLUMNS=3;
export const SLOT_X_STEP=3.08;
export const SLOT_Z_STEP=3.4;
export const SLOT_LEFT_OFFSET=2.35;
export const SLOT_END_OFFSET=1.9;
export type SlotOccupancy='empty'|'real'|'draft';
export interface FloorSlot {
  wardId:number;roomCode:string;slot:number;label:string;
  x:number;z:number;rotation:Rotation;occupancy:SlotOccupancy;bedId:number|null;
  available:boolean;
}
export function slotCenter(room:SceneRoom,slot:number):{x:number;z:number} {
  if(!Number.isInteger(slot)||slot<0)throw new Error('槽位编号必须是非负整数');
  const col=slot%SLOT_COLUMNS,row=Math.floor(slot/SLOT_COLUMNS);
  return {x:room.x+SLOT_LEFT_OFFSET+col*SLOT_X_STEP,
    z:room.side==='north'?room.z+SLOT_END_OFFSET+row*SLOT_Z_STEP
      :room.z+room.depth-SLOT_END_OFFSET-row*SLOT_Z_STEP};
}
/** A fixed 3-column footprint, derived from room depth, NEVER from how many draft beds exist. */
export function floorSlotCount(room:SceneRoom):number {
  const rows=Math.max(0,Math.floor((room.depth-3+1e-6)/SLOT_Z_STEP));
  return rows*SLOT_COLUMNS;
}
export function listFloorSlots(room:SceneRoom,state:EditorState):FloorSlot[] {
  const occupied=new Map<number,{bedId:number;synthetic:boolean}>();
  for(const item of state.items){
    if(item.pose.wardId!==room.room.ward_id)continue;
    if(occupied.has(item.pose.slot))throw new Error(`病房 ${room.room.code} 存在重叠槽位`);
    occupied.set(item.pose.slot,{bedId:item.bed.id,synthetic:item.synthetic});
  }
  return Array.from({length:floorSlotCount(room)},(_,slot)=>{
    const occupant=occupied.get(slot);
    const occupancy:SlotOccupancy=!occupant?'empty':occupant.synthetic?'draft':'real';
    return {wardId:room.room.ward_id,roomCode:room.room.code,slot,
      label:`${room.room.code} · S${String(slot+1).padStart(2,'0')}`,
      ...slotCenter(room,slot),rotation:0,occupancy,
      bedId:occupant?.bedId??null,available:!occupant};
  });
}
export function slotIntent(state:EditorState,rooms:WardRoom[],pose:EditPose,
  tool:'add'|'move'|'remove',selectedId:number|null):{ok:boolean;message:string;targetId:number|null} {
  const room=rooms.find(r=>r.ward_id===pose.wardId);
  if(!room)return {ok:false,message:'病房不存在',targetId:null};
  if(!Number.isInteger(pose.slot)||pose.slot<0)return {ok:false,message:'槽位编号无效',targetId:null};
  const occupant=state.items.find(i=>i.pose.wardId===pose.wardId&&i.pose.slot===pose.slot);
  if(tool==='remove'){
    if(!occupant)return {ok:false,message:'槽位已经为空',targetId:null};
    if(!occupant.synthetic)return {ok:false,message:'正式床位不能在模拟沙盘中直接删除；请使用 What-if 临时禁用',targetId:occupant.bed.id};
    return {ok:true,message:'移除模拟床位',targetId:occupant.bed.id};
  }
  if(tool==='add')return occupant
    ?{ok:false,message:occupant.synthetic?'已有模拟床位':'已有正式床位',targetId:occupant.bed.id}
    :{ok:true,message:'可添加模拟床位',targetId:null};
  const moving=state.items.find(i=>i.bed.id===selectedId);
  if(!moving)return {ok:false,message:'请先选中要移动的模拟床位',targetId:null};
  if(!moving.synthetic)return {ok:false,message:'正式床位不可在模拟模式移动',targetId:moving.bed.id};
  return occupant&&occupant.bed.id!==moving.bed.id
    ?{ok:false,message:'目标槽位已被占用',targetId:occupant.bed.id}
    :{ok:true,message:'可移动到此槽位',targetId:moving.bed.id};
}

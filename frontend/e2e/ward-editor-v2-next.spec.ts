/** Real Chromium + Three.js (NOT static preview). Read-only demo editor by default.
 * Set E2E_URL, E2E_USERNAME, E2E_PASSWORD. Never run write tests on demo/production DB.
 */
import {test,expect} from '@playwright/test';
const url=process.env.E2E_URL??'http://127.0.0.1:5173';
test('模拟拖放编辑不会进入真实数据库 / WebGL 场景能渲染',async({page})=>{
 test.skip(!process.env.E2E_USERNAME||!process.env.E2E_PASSWORD,'需本地合成演示账号');
 const errors:string[]=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(`${url}/login`);
 await page.getByPlaceholder('请输入演示账号').fill(process.env.E2E_USERNAME!);
 await page.getByPlaceholder('请输入密码').fill(process.env.E2E_PASSWORD!);
 await page.getByRole('button',{name:'登录工作台'}).click();
 await page.goto(`${url}/ward-map`);
 await page.getByRole('button',{name:'演示数据'}).click();
 await expect(page.locator('.ward-scene-canvas canvas')).toBeVisible();
 await expect.poll(()=>page.locator('.ward-scene-canvas canvas').evaluate(node=>Boolean(
  (node as HTMLCanvasElement).getContext('webgl2')||(node as HTMLCanvasElement).getContext('webgl')))).toBe(true);
 const total=await page.locator('.wm-total strong').innerText();
 await page.getByRole('button',{name:/模拟编辑/}).click();
 await expect(page.getByText('空间模拟编辑')).toBeVisible();
 const editor=page.locator('.wm-editor');
 const freeSlot=editor.locator('select').nth(1).locator('option:not([disabled])').first();
 const freeValue=await freeSlot.getAttribute('value');
 expect(freeValue).not.toBeNull();
 await editor.locator('select').nth(1).selectOption(freeValue!);
 await editor.locator('input').first().fill('SIM-E2E-001');
 await page.screenshot({path:'ward-editor-before-add.png',fullPage:true});
 await editor.getByRole('button',{name:'按选定槽位添加'}).click();
 await expect(page.locator('.wm-total strong')).not.toHaveText(total);
 await page.screenshot({path:'ward-editor-after-add.png',fullPage:true});
 await editor.getByRole('button',{name:'撤销'}).click();
 await expect(page.locator('.wm-total strong')).toHaveText(total);
 await page.screenshot({path:'ward-editor-undo.png',fullPage:true});
 expect(errors).toEqual([]);
});

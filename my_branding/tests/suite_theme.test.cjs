const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../public/js/suite-theme.js'), 'utf8');
function boot(theme, systemDark=false) {
    const storage = new Map([['theme','dark'],['vueuse-color-scheme','dark']]);
    const attrs = {}, calls = []; let observe, mediaChange;
    const media = {matches:systemDark,addEventListener:(_, fn)=>{mediaChange=fn;}};
    const context = {window:{__NEXUM_BRAND__:{theme,theme_csrf:'test-csrf'},matchMedia:()=>media},
        document:{documentElement:{setAttribute:(key,value)=>{attrs[key]=value;},classList:{toggle:()=>{}},style:{}}},
        location:{pathname:'/crm'}, localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
        MutationObserver:class {constructor(fn){observe=fn;}observe(){}},
        fetch:async (url,options)=>{calls.push({url,body:JSON.parse(options.body)});return {ok:true};},
    };
    vm.runInNewContext(source, context);
    return {context, storage, attrs, calls, nativeChange(value) {storage.set('theme',value);observe();}, systemChange() {media.matches=!media.matches;mediaChange();}};
}
test('signed-in Light replaces stale dark storage without writing a user preference',()=>{
    const state=boot('Light',true);
    assert.equal(state.attrs['data-theme'],'light');
    assert.equal(state.storage.get('theme'),'light');
    assert.equal(state.calls.length,0);
});
test('native app theme toggle saves the same User preference used by Desk',async()=>{
    const state=boot('Light');state.nativeChange('dark');
    await new Promise(resolve=>setImmediate(resolve));
    assert.equal(state.attrs['data-theme'],'dark');
    assert.deepEqual(state.calls,[{url:'/api/method/frappe.core.doctype.user.user.switch_theme',body:{theme:'Dark'}}]);
});
test('Automatic follows the OS without converting that choice into permanent Dark',()=>{
    const state=boot('Automatic',false);state.systemChange();
    assert.equal(state.attrs['data-theme'],'dark');
    assert.equal(state.storage.get('theme'),'system');
    assert.equal(state.calls.length,0);
});

test('failed rapid theme changes restore the last server-confirmed preference', async()=>{
    for (const firstSucceeded of [false, true]) {
        const state=boot('Light');
        state.context.document.createElement=()=>({setAttribute(){},remove(){}});
        state.context.document.body={appendChild(){}};
        state.context.setTimeout=()=>0;
        const replies=[];
        state.context.fetch=()=>new Promise(resolve=>replies.push(resolve));
        const theme=state.context.window.NexumTheme;
        const first=theme.setChoice('dark');
        const second=theme.setChoice('light');
        await new Promise(resolve=>setImmediate(resolve));
        replies[0]({ok:firstSucceeded});
        await first;
        await new Promise(resolve=>setImmediate(resolve));
        replies[1]({ok:false});
        await second;
        const expected=firstSucceeded?'dark':'light';
        assert.equal(theme.getChoice(),expected,'failed writes cannot become the rollback preference');
        assert.equal(state.attrs['data-theme'],expected);
        assert.equal(state.storage.get('theme'),expected);
    }
});

test('an older failed save cannot roll back a later repeated theme choice', async()=>{
    const state=boot('Light');
    state.context.document.createElement=()=>({setAttribute(){},remove(){}});
    state.context.document.body={appendChild(){}};
    state.context.setTimeout=()=>0;
    const replies=[];
    state.context.fetch=()=>new Promise(resolve=>replies.push(resolve));
    const theme=state.context.window.NexumTheme;
    const first=theme.setChoice('dark');
    const second=theme.setChoice('light');
    const third=theme.setChoice('dark');
    await new Promise(resolve=>setImmediate(resolve));
    replies[0]({ok:false});
    await first;
    assert.equal(theme.getChoice(),'dark','first Dark and latest Dark are distinct intentions');
    await new Promise(resolve=>setImmediate(resolve));
    replies[1]({ok:false});
    await second;
    await new Promise(resolve=>setImmediate(resolve));
    replies[2]({ok:true});
    await third;
    assert.equal(theme.getChoice(),'dark');
    assert.equal(state.attrs['data-theme'],'dark');
});

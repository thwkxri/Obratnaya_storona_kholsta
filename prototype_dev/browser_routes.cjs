const {chromium}=require('./test_runtime/node_modules/playwright-core');
const fs=require('fs'),path=require('path'),{pathToFileURL}=require('url');
const verified=JSON.parse(fs.readFileSync(path.join(__dirname,'verification.json'),'utf8'));
const manifest=require('./build_manifest.json');
const general=manifest.backgrounds_planned.filter(bg=>bg.type==='Общий вид').map(bg=>bg.id);
const optionalScripts=['/story360.js','/license-key.js','/user.js'];
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const results=[];
 try{
 for(const [name,example] of Object.entries(verified.examples)){
  if(process.env.CHECK_ROUTES&&!process.env.CHECK_ROUTES.split(',').includes(name))continue;
  const context=await browser.newContext({viewport:{width:390,height:844}});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('requestfailed',request=>{
    if(!optionalScripts.some(script=>request.url().endsWith(script)))errors.push(request.url());
  });
  // Skip animation timing for the scripted walkthrough.
  await page.addInitScript(()=>{
    let testNow=Date.now();Date.now=()=>testNow+=350;
    let story;
    Object.defineProperty(window,'STORY_TEXT',{get:()=>story,set(value){
      story=typeof value==='string'?value.replace(/^transitionMs = 250$/m,'transitionMs = 0'):value;
    }});
  });
  const sequence=example.choices_to_final_menu;
  await page.goto(pathToFileURL(path.resolve(__dirname,'../game/index.html')).href);
  await page.waitForFunction(()=>window.VN_ENGINE_READY===true);
  const outcome=await page.evaluate(async ({sequence,general,checkAllFiles})=>{
    const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
    const checkedBackgrounds=new Set();
    const speakers={'Илья':'ilya','Аркадий':'arkady','Вера':'vera','Никита':'nikita','Софья':'sofia','Тамара':'tamara'};
    const textBox=document.getElementById('textBox');
    let textVersion=0;
    new MutationObserver(()=>textVersion++).observe(textBox,{childList:true,subtree:true,characterData:true});
    if(checkAllFiles){
      for(const file of Object.values(window.STORY.assets.backgrounds)){
        const image=new Image();
        image.src=file;
        await image.decode();
        if(!image.naturalWidth)throw Error('Unreadable background: '+file);
      }
    }
    let choices=0,steps=0,itemViews=0,advanceFrom=-1;const start=performance.now();
    while(performance.now()-start<180000){
      const menu=document.getElementById('choices');
      if(!menu.classList.contains('hidden')){
        if(choices===sequence.length&&[...menu.querySelectorAll('.choiceLabel')].some(b=>b.textContent==='Не обвинять')){
          return {choices,steps,itemViews,backgrounds:[...checkedBackgrounds].sort(),reached_final_menu:true};
        }
        const btn=[...menu.querySelectorAll('.choiceBtn')].find(b=>b.querySelector('.choiceLabel').textContent===sequence[choices]);
        if(!btn)throw new Error('Unexpected menu '+choices+': '+menu.textContent+' expected '+sequence[choices]);
        advanceFrom=textVersion;
        btn.click();choices++;
      } else if(textBox.textContent&&textVersion!==advanceFrom){
        const caption=textBox.textContent;
        const speaker=document.getElementById('nameBox');
        const character=document.getElementById('charLayer');
        const bgLayer=document.getElementById('bgLayer');
        const item=caption==='Осмотр предмета.';
        const who=speaker.classList.contains('hidden')?null:speaker.textContent;
        const backgroundId=()=>bgLayer.src.match(/\/(BG\d+)\.png$/)?.[1];
        const matches=()=>{
          const background=backgroundId();
          const visibleCharacter=!character.classList.contains('hidden');
          return background&&bgLayer.complete&&bgLayer.naturalWidth&&
            (!item||(!visibleCharacter&&!general.includes(background)))&&
            (!who||(general.includes(background)&&visibleCharacter&&character.src.includes('/characters/'+speakers[who]+'/')&&character.complete&&character.naturalWidth));
        };
        const deadline=performance.now()+2500;
        while(!matches()&&performance.now()<deadline)await sleep(12);
        if(!matches()){
          throw Error(JSON.stringify({caption,who,bg:bgLayer.src,char:character.src}));
        }
        checkedBackgrounds.add(backgroundId());
        if(item)itemViews++;
        advanceFrom=textVersion;
        document.getElementById('dialog').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
      }
      steps++;await sleep(5);
    }
    throw new Error('Timed out at '+document.getElementById('textBox').textContent);
  },{sequence,general,checkAllFiles:results.length===0});
  if(outcome.choices!==sequence.length||errors.length)throw new Error(JSON.stringify({name,outcome,errors}));
  results.push({route:name,...outcome,page_errors:errors});console.log(name,'passed',outcome.steps,'UI steps');
  await context.close();
 }
 const reportName='browser_investigation_routes_report.json';
 fs.writeFileSync(path.join(__dirname,reportName),JSON.stringify({status:'passed',runtime:'Microsoft Edge, real engine and DOM controls; animations and click cooldown accelerated',decoded_backgrounds:manifest.active_backgrounds,results},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});

const {chromium}=require('./test_runtime/node_modules/playwright-core');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');

const checked=require('./verification.json');
const url=pathToFileURL(path.resolve(__dirname,'../game/index.html')).href+'?nosave=1';
const required=['Портрет в нише','Сверенный экземпляр альбома',
  'Объяснение ночного визита','Показание Никиты о свёртке'];
const cases=[
  {name:'complete',facts:checked.examples.AAA.facts,take:required,
    result:'Картина на месте. Нейтральная концовка'},
  {name:'extra',facts:checked.examples.AAA.facts,take:[...required,'Пыль на пиджаке'],
    result:'Недоказанное обвинение. Плохая концовка'},
  {name:'unseen',facts:{found:true,claim:true},take:required,
    result:'Недоказанное обвинение. Плохая концовка',
    absent:['Сверенный экземпляр альбома','Показание Никиты о свёртке','Заплата на покрывале']},
];

async function verifyCase(browser,test){
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  try{
    await page.addInitScript(facts=>{
      let now=Date.now();
      Date.now=()=>now+=350;
      let story;
      Object.defineProperty(window,'STORY_TEXT',{get:()=>story,set(value){
        story=value;
        if(typeof value!=='string')return;
        story=story.replace(/^startScene = s01$/m,'startScene = final_menu')
          .replace(/^transitionMs = 250$/m,'transitionMs = 0');
        for(const [key,seen] of Object.entries(facts)){
          if(seen)story=story.replace(new RegExp('^'+key+' = false$','m'),key+' = true');
        }
      }});
    },test.facts);
    await page.goto(url);
    await page.waitForFunction(()=>window.VN_ENGINE_READY===true);
    const report=await page.evaluate(async({take,result})=>{
      const opened=new Set(),marked=new Set(),seen=new Set();
      const groups=['Предметы и следы','Показания и документы','Ночь и маршруты'];
      for(let start=performance.now();performance.now()-start<90000;){
        const text=document.getElementById('textBox').textContent;
        if(text)seen.add(text);
        if(text===result)return {seen:[...seen],marked:[...marked],result};
        const menu=document.getElementById('choices');
        if(!menu.classList.contains('hidden')){
          const buttons=new Map([...menu.querySelectorAll('.choiceBtn')].map(btn=>[btn.querySelector('.choiceLabel').textContent,btn]));
          let label;
          if(buttons.has('Не обвинять')){
            if([...buttons.keys()].slice(0,5).join(',')!=='Аркадий,Вера,Никита,Софья,Тамара')throw Error('Unbalanced suspect menu');
            label='Аркадий';
          }
          else if(buttons.has('Проверить отмеченные записи')){
            label=groups.find(group=>!opened.has(group))||'Проверить отмеченные записи';
            opened.add(label);
          }else if(buttons.has('Выбрать, как предъявить записи'))label='Выбрать, как предъявить записи';
          else if(buttons.has('Предъявить при всех'))label='Предъявить при всех';
          else if(buttons.has('Следующая запись')){
            const heading=menu.querySelector('.choiceTitle')?.textContent;
            if(heading)seen.add(heading);
            const card=take.find(title=>heading===title);
            if(card&&buttons.has('Отметить для предъявления')&&!marked.has(card)){
              marked.add(card);label='Отметить для предъявления';
            }else label='Следующая запись';
          }else throw Error('Unexpected menu: '+menu.textContent);
          buttons.get(label).click();
        }else document.getElementById('dialog').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
        await new Promise(r=>setTimeout(r,12));
      }
      throw Error('Timed out: '+document.getElementById('textBox').textContent);
    },test);
    assert.deepEqual(errors,[]);
    for(const title of test.absent||[]){
      assert(!report.seen.some(line=>line.startsWith(title+'.')||line===title),title);
    }
    assert.equal(report.marked.length,test.take.filter(title=>!(test.absent||[]).includes(title)).length);
    console.log(test.name,report.result);
    return {test:test.name,ending:report.result,selected:report.marked,unseen:test.absent||[]};
  }finally{await page.close()}
}

(async()=>{
  const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
  try{
    const results=await Promise.all(cases.map(test=>verifyCase(browser,test)));
    fs.writeFileSync(path.join(__dirname,'browser_evidence_report.json'),
      JSON.stringify({status:'passed',scope:'Real Edge menu and card controls; starts at final menu with observed flags preloaded',results},null,2));
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});

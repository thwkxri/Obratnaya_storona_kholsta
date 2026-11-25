"""Compile the complete v9 staging script into the teacher's unmodified DSL."""
from pathlib import Path
import re, json, shutil, hashlib
from PIL import Image
from functools import lru_cache

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / 'prototype_dev'
SRC = DEV / 'scenario_v9'
GAME = ROOT / 'game'
PEOPLE = {
    'Илья': ('ilya', 'ilya_sokolov', '#B7CCDC'),
    'Аркадий': ('arkady', 'arkady_vorontsov', '#BED0B0'),
    'Вера': ('vera', 'vera_vorontsova', '#E1B9BF'),
    'Никита': ('nikita', 'nikita_vorontsov', '#CEC9BD'),
    'Софья': ('sofya', 'sofya_lebedeva', '#BDD1D4'),
    'Тамара': ('tamara', 'tamara', '#C4C3DD'),
}
EMOTIONS = dict(zip(('обычный','грустный','злой','удивлённый','весёлый'), ('normal','sad','angry','surprised','happy')))
LETTERS = {'А':'A', 'Б':'B', 'В':'C'}
FLAGS = set()
STAGING = []
COUNTS = {'dialogue': 0, 'narration': 0, 'background_cues': 0, 'item_view_steps': 0}
SCENE_ROOT=ROOT/'characters/scene_ready_v1'
SCENE_MANIFEST=json.loads((SCENE_ROOT/'manifest.json').read_text('utf8'))
ASSETS={a['resource_key']:dict(a,source_file=str((SCENE_ROOT/a['path']).relative_to(ROOT)),resolution='scene_ready') for a in SCENE_MANIFEST['assets']}
SOURCE_BANK={}
for name,(_,folder,_) in PEOPLE.items():
    for a in json.loads((ROOT/'characters'/folder/'staging_v1/manifest.json').read_text('utf8'))['assets']:
        SOURCE_BANK[(name,a['pose'],a['emotion'])]=(folder,a)

@lru_cache(maxsize=None)
def resolve_asset(name,pose,emotion,crop):
    if pose=='base':pose={'Илья':'I01','Аркадий':'A01','Вера':'V01','Никита':'N01','Софья':'S01','Тамара':'T01'}[name]
    key=f'{pose.lower()}_{emotion}_{crop}'
    if key in ASSETS:return ASSETS[key]
    cid,folder,_=PEOPLE[name]
    short={'sofya':'sofia'}.get(cid,cid)
    source=None
    bank=SOURCE_BANK.get((name,pose,emotion))
    if bank:
        _,a=bank
        if crop=='full':source=ROOT/'characters'/folder/'staging_v1'/a['full']
        else:
            export=next((e for e in a['exports'] if e['crop']==crop),None)
            if export:source=ROOT/'characters'/folder/'staging_v1'/export['path']
    if source is None:
        # Some exact base crops were not needed in the original 104 exports.
        base=base_png(folder,crop,emotion)
        if base.stem.startswith(pose.lower()+'_'):source=base
    if source is not None:
        asset={'character':name,'pose':pose,'emotion':emotion,'crop':crop,'resource_key':key,
               'path':f'assets/characters/{short}/{key}.png','source_file':str(source.relative_to(ROOT)),
               'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'pose_override':None,'resolution':'approved_source_export'}
    else:
        # Newly visible item-dialogue combinations were outside v9's 104-art
        # brief. Preserve the correct emotion/crop with an explicit pose alias.
        candidates=[a for a in ASSETS.values() if a['character']==name and a['emotion']==emotion and a['crop']==crop and a['resolution']=='scene_ready']
        candidates.sort(key=lambda a:(a['pose'].endswith('04')!=pose.endswith('04'),not a['pose'].endswith('01'),a['resource_key']))
        if not candidates:
            source=base_png(folder,crop,emotion)
            actual={'character':name,'pose':source.stem.split('_')[0].upper() if re.match(r'^[a-z]\d\d_',source.stem) else 'base','emotion':emotion,'crop':crop,
                    'path':f'assets/characters/{short}/base_{emotion}_{crop}.png','source_file':str(source.relative_to(ROOT)),
                    'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'pose_override':None}
        else:actual=candidates[0]
        asset=dict(actual,resource_key=key,requested_pose=pose,resolution='closest_approved_pose')
    ASSETS[key]=asset
    return asset

@lru_cache(maxsize=None)
def base_png(folder,crop,emotion):
    pattern='angry_arms_down.png' if folder=='sofya_lebedeva' and emotion=='angry' else '*'+emotion+'.png'
    candidates=list((ROOT/'characters/tone_matched_v2'/folder/crop).glob(pattern))
    assert len(candidates)==1,(folder,crop,emotion,candidates)
    return candidates[0]

@lru_cache(maxsize=None)
def placement(resource_key):
    asset=ASSETS[resource_key]
    with Image.open(ROOT/asset['source_file']) as image:
        _,h=image.size
    # Two shared camera framings. Gestures and silhouette width must never
    # change the actor's scale or horizontal anchor. Exact waist crops use
    # 1.85x the full-body pixel scale, irrespective of 890/930px crop height.
    # Native controller: baseHeight=.85H, workCenter=.575H;
    # top/H=.575-.425*scale+.85*(.5-focusy). Anchor both at .095H.
    scale=0.90 if asset['crop']=='full' else 0.90*1.85*h/1536
    focusy=(1.0-0.095)/0.85-scale/2
    return f'pos=center focusx=0.5 focusy={focusy:.6f} scale={scale:.6f}'

def expr(s):
    s = s.replace('`','').replace(' или ', ' or ').replace(' и ', ' and ')
    s = re.sub(r'(?<![<>=!])=(?!=)', '==', s)
    FLAGS.update(set(re.findall(r'\b[a-z][a-z_]*\b', s)) - {'true','false','and','or'})
    return s.replace(' and ', ' && ').replace(' or ', ' || ')

def sets(spec):
    lines = []
    for item in spec.split(';'):
        if not item.strip(): continue
        key, val = item.strip().split('=', 1)
        FLAGS.add(key.strip())
        lines.append('set ' + key.strip() + ' = ' + val.strip())
    return lines

EFFECTS = {
 '02A':'tact=tact + 1;portrait_story=true', '02B':'corner=true;sofia_help=true',
 '03A':'nikita_help=true;price_request=true', '03B':'nikita_help=false;price_request=false',
 '04A':'plan=true', '04B':'restoration_refusal=true;public_family=true',
 '06A':'time_anchor=true', '06B':'inside_route=true;vera_seen=true',
 '08A':'preserved=true', '08B':'written=true;claim=true;preserved=false;route_stories=true',
 '09A':'key_checked=true;nikita_help=true', '09B':'key_public=true;nikita_help=false',
 '10A':'chest_checked=true;chest_list=true;tamara_help=true',
 '10B':'chest_checked=true;tamara_help=false', '10C':'chest_deferred=true;tamara_help=false',
 '11A':'corner=true', '11B':'night_visit=true',
 '12A':'photo_checked=true;sofia_help=true', '12B':'photo_public=true;sofia_help=false',
 '13A':'note_checked=true', '13B':'vera_help=true;tact=tact + 1',
 '15A':'buyer_checked=true;nikita_help=true', '15B':'claim=true;nikita_night=true',
 '15C':'album_hearsay=true;nikita_night=true;night_replayed=true',
 '16A':'materials_checked=true;restoration_checked=true;sofia_help=true', '16B':'',
 '17A':'vera_route=true;note_location=true', '17B':'plan=true;niche_known=true',
 '17C':'vera_route=true;note_location=true;plan=true;niche_known=true;vera_private=true',
 '18A':'cleaning_seen=true;cloth_scrap=true', '18B':'trace=true;niche_known=true;cover_origin=true',
 '20A':'found=true;niche_known=true', '20B':'',
 '20C':'found=true;finding_preserved=true;finding_recorded=true;claim=true',
 '21A':'cover_origin=true', '21B':'nikita_help=true',
 '22A':'book_checked=true', '22B':'catalog_checked=true;claim=true',
 '23A':'bundle=true;album_hearsay=true;bundle_recorded=true;nikita_help=true',
 '23B':'handover=true;handover_recorded=true;tamara_help=true',
 '23C':'bundle=true;bundle_recorded=true;nikita_help=true',
 '24A':'found=true;finding_preserved=true;finding_recorded=true',
 '24B':'bundle=true;bundle_recorded=true;album_hearsay=true;nikita_help=true',
 '24C':'handover=true;handover_recorded=true;tamara_help=true',
 '24D':'finding_preserved=true;finding_recorded=true',
 '27A':'denial=true', '27B':'claim=true;book_checked=true',
 '28A':'tact=tact + 1;joint_place=true', '28B':'joint_place=false',
}

def conditional(condition, spec):
    return ['if ' + expr(condition), *sets(spec), 'end']

def effects(key):
    out = []
    special = {
      '11B': [('preserved', 'corner=true')],
      '15B': [('nikita_help or price_request', 'bundle=true')],
      '16B': [('sofia_help or corner', 'packing_map=true')],
      '18A': [('tamara_help', 'handover=true')],
      '20B': [('(trace or plan) and (corner or packing_map)', 'found=true;niche_known=true')],
      '21A': [('found','cover_match=true')],
      '21B': [('found','finding_public=true;finding_preserved=true'), ('found=false','search_public=true')],
    }
    for condition,spec in special.get(key,[]): out += conditional(condition,spec)
    if key=='20B': out+=conditional('found=false','search_incomplete=true')
    out += sets(EFFECTS[key])
    return out

BG = {}
for m in re.finditer(r'^\| (BG\d+) \| ([^|]+) \| ([^|]+) \|', (SRC/'00_production.md').read_text('utf8'), re.M):
    BG[m[1]] = {'id':m[1], 'type':m[2].strip(), 'description':m[3].strip(),
                'path':f'assets/backgrounds/{m[1]}.png'}
assert len(BG)==80

def quote(s):
    return json.dumps(s, ensure_ascii=False)

def room_of(bg):
    description=BG[bg]['description']
    return next((room for room in ('Холл','Галерея','Библиотека','Комната Ильи','Кабинет','Столовая') if description.startswith(room)),'')

def conversation_after_item(bg):
    room=room_of(bg)
    if not room:return []  # Portable book closeups retain the current room.
    candidates=[b for b in BG if BG[b]['type']=='Общий вид' and room_of(b)==room and (GAME/BG[b]['path']).is_file()]
    if not candidates:return []
    preceding=[b for b in candidates if int(b[2:])<int(bg[2:])]
    # These details belong to a different time of day or show a change in the
    # room (the cabinet is open). Registry order alone cannot pick that view.
    preferred={
        'BG06':'BG13', 'BG07':'BG13', 'BG08':'BG13', 'BG09':'BG13', 'BG10':'BG13',
        'BG39':'BG36', 'BG40':'BG36', 'BG44':'BG35', 'BG45':'BG36',
        'BG52':'BG47', 'BG53':'BG47', 'BG56':'BG47', 'BG72':'BG74',
    }.get(bg)
    fallback=preferred if preferred in candidates else (preceding[-1] if preceding else candidates[0])
    update=sets('conversation_room='+quote(room)+';conversation_slot='+quote(fallback))
    if bg in ('BG39','BG40','BG45'):
        return update
    return ['if conversation_room != '+quote(room),*update,'end']

def return_to_conversation():
    # Item images have their own reading step. A speaker always restores the
    # last general shot before their portrait and dialogue are displayed.
    result=['if detail_shot',*sets('detail_shot=false;background_slot=conversation_slot')]
    available=[bg['id'] for bg in BG.values() if bg['type']=='Общий вид' and (GAME/bg['path']).is_file()]
    for i,bg in enumerate(available):
        condition='if' if i==0 else 'elif'
        result+=[condition+' conversation_slot == '+quote(bg),'bg '+bg]
    if available:result.append('end')
    return result+['end']

def compile_body(text, context):
    """Conditions in v9 last until the next condition or an explicit common marker."""
    out=[]; active=False; may_show_detail=True
    def close():
        nonlocal active, may_show_detail
        if active: out.append('end'); active=False; may_show_detail=True
    for p in re.split(r'\n\s*\n', text):
        p=p.strip()
        if not p: continue
        c=re.fullmatch(r'\[Если (.*?):\]',p)
        if c:
            close(); out.append('if '+expr(c[1])); active=True; may_show_detail=True; continue
        if p.startswith('[Иначе:'):
            assert active, (context,p)
            out.append('else'); may_show_detail=True; continue
        if p.startswith(('Общ','[ОБЩАЯ','Первый вход','Возвращение после','Оба входа')):
            close(); continue
        if p.startswith('КАДР'):
            bg=re.match(r'КАДР (BG\d+)',p)[1]
            may_show_detail=BG[bg]['type']!='Общий вид'
            out += ['hide all', *sets('background_slot='+quote(bg)+';detail_shot='+str(may_show_detail).lower()), f'// bg {bg} — {BG[bg]["description"]}']
            if BG[bg]['type']=='Общий вид':out+=sets('conversation_slot='+quote(bg)+';conversation_room='+quote(room_of(bg)))
            else:out+=conversation_after_item(bg)
            if (GAME/BG[bg]['path']).is_file():
                out.append('bg '+bg)
                if BG[bg]['type']!='Общий вид':
                    # A real item image waits for an ordinary reading click.
                    # No empty placeholder or extra black-screen pause while
                    # the author has not supplied this image yet.
                    out.append(quote('Осмотр предмета.'))
                    COUNTS['item_view_steps']+=1
            COUNTS['background_cues']+=1
        elif p.startswith('Текст:'):
            out.append(quote(p[6:].strip())); COUNTS['narration']+=1
        elif p.startswith('**') and ':**' in p:
            head,speech=p[2:].split(':**',1)
            bits=head.split(' · ')
            name=bits[0].split(',')[0].split(' (')[0]
            cid, folder, _=PEOPLE[name]
            if len(bits)==4:
                emo=EMOTIONS[bits[1]]; crop='full' if bits[3]=='полный рост' else 'waist'
                pose=bits[2]
            else:
                # The user's revised staging rule also replaces old offscreen
                # lines with the approved neutral speaking portrait.
                emo='normal';crop='waist';pose='base'
            asset=resolve_asset(name,pose,emo,crop)
            if may_show_detail:
                out+=return_to_conversation()
                may_show_detail=False
            out.append(f'show {cid} {asset["resource_key"]} '+placement(asset['resource_key']))
            STAGING.append({'scene':context,'character':name,'requested_pose':pose,'resolved_pose':asset['pose'], 'emotion':emo,'crop':crop,'actual':asset['path'],'resolution':asset['resolution'],'pose_override':asset.get('pose_override') or ''})
            out.append(f'{cid}: '+quote(speech.strip())); COUNTS['dialogue']+=1
        elif p=='Здесь исполнить блок P.':
            close(); out+=proof_block(); may_show_detail=True
        elif p.startswith(('Титр:','Затемнение:')):
            close(); out+=['hide all',quote(re.search('«(.*?)»',p)[1])]
    close()
    return out

ENDINGS=(SRC/'04_endings.md').read_text('utf8')
def proof_block():
    common=ENDINGS.split('Общее начало:',1)[1].split('Далее выбрать',1)[0]
    book=ENDINGS.split('### P-книга:',1)[1].split('\n',1)[1].split('### P-покрывало:',1)[0]
    cover=ENDINGS.split('### P-покрывало:',1)[1].split('\n',1)[1].split('## E1.',1)[0]
    book=book.replace('bundle=true','take_bundle=true').replace('bundle=false','take_bundle=false').replace('handover=true','take_handover=true')
    book=book.replace('Но это независимая связь с переносимой домашней вещью, а не вывод из одной книги.', 'Форма заплаты и шов на фотографии совпадают с тканью вокруг портрета.')
    book=book.replace(' Пыль на пиджаке я в это основание не включаю.','')
    cover=cover.replace('Поэтому я проверил другой источник.', 'Заплата и шов связывают переданное покрывало с тканью вокруг найденного портрета. Теперь нужен ещё один источник.')
    return compile_body(common,'P')+['if take_book_checked',*compile_body(book,'P_book'),'else',*compile_body(cover,'P_cover'),'end']

def sections():
    joined='\n'.join((SRC/f).read_text('utf8') for f in ['01_evening_morning.md','02_investigation.md','03_search_final_choice.md'])
    hubs={}
    def hub(m):
        mapping={'H1':'10','H2':'14','H3':'21'}
        for p in re.split(r'(?=^(?:Первый вход[^\n]*:|Возвращение после \d\d:))',m[2],flags=re.M):
            if p.startswith('Первый вход'): hubs[mapping[m[1]]]=p
            elif p.startswith('Возвращение после'): hubs[re.match(r'Возвращение после (\d\d)',p)[1]]=p
        return ''
    joined=re.sub(r'^### Возврат (H[123])[^\n]*\n(.*?)(?=^## \d\d\.|\Z)',hub,joined,flags=re.M|re.S)
    scenes={m[1]:m[0] for m in re.finditer(r'^## (\d\d)\. (.*?)(?=^## \d\d\.|\Z)',joined,re.M|re.S)}
    return scenes,hubs

HIDDEN_CONDITIONS = {
    '15C': 'time_anchor and key_checked and nikita_help',
    '17C': 'vera_seen and vera_help',
    '20C': 'vera_private',
    '23C': 'night_replayed',
    '24D': 'photo_checked and packing_map and found',
}

def hidden_scenes():
    text=(SRC/'09_hidden_scenes.md').read_text('utf8')
    return {m[1]:(m[2],m[3]) for m in re.finditer(r'^## (\d\d[A-Z])\. «(.*?)»\n(.*?)(?=^## |\Z)',text,re.M|re.S)}

def branch_chunks(scenes):
    chunks={}
    for text in scenes.values():
        matches=list(re.finditer(r'^### (\d\d)([АБВ])\. «(.*?)»',text,re.M))
        for i,m in enumerate(matches):
            chunk=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]
            chunks[m[1]+LETTERS[m[2]]]=re.split(r'\[ОБЩАЯ СЦЕНА ПОСЛЕ ВЫБОРА\]|Общая условная вставка после любой ветви:',chunk,maxsplit=1)[0]
    chunks['23A']=chunks['23A'].replace(
        'Я начал с публичного подозрения и закрыл тебе возможность нормально объяснить. Сейчас прошу отдельное показание, не согласие с моей версией.',
        'Хочу записать твой рассказ отдельно. Скажи, что видел сам.')
    chunks['24B']=chunks['24B'].replace('а не заранее подтвердить моё обвинение','и отделить его от моих догадок')
    chunks['27B']=chunks['27B'].replace(
        'Но объяснение визита не совпадает с тем, что вы знали о книге вечером. Я отмечу это вместе с остальными фактами, не вместо них.',
        'Запишу оба ответа: про передачу вечером и про то, за чем вы пошли ночью.')
    chunks['21A']=chunks['21A'].split('КАДР BG58. Возврат в кабинет к ответу владельца.',1)[0]
    chunks['24A']=chunks['24A'].split('**Илья · обычный · I03 · по пояс:** Оставим.',1)[0]
    chunks['22A']=chunks['22A'].replace(
        'Это не сходится с записанной причиной ночного визита за этим альбомом. Ошибку памяти ещё следует дать объяснить самому Аркадию. Но несовпадение уже основано на конкретных источниках.',
        'Теперь в блокноте отдельно лежат слова о ночном визите и запись о самом экземпляре.')
    return chunks

def choices(options, title=None):
    header='menu plain' if title is None else 'menu plain title='+quote(title)
    return [header,*[f'choice {quote(label)} -> {target}' for label,target in options],'end']

def conditional_choices(always, optional):
    if not optional:
        return choices(always)
    condition,label,target=optional[0]
    rest=optional[1:]
    return ['if '+expr(condition),*conditional_choices(always+[(label,target)],rest),
            'else',*conditional_choices(always,rest),'end']

def journal_link(target, end):
    return [f'scene {target}',*sets(f'journal_return={quote(end)};journal_presenting=false;journal_back=false'),'goto journal_0']

SUSPECTS = {'arkady':'Аркадий','vera':'Вера','nikita':'Никита','sofya':'Софья','tamara':'Тамара'}

# The guards are set only after the observation or report is shown in a scene.
# One fact can have several sources, but only one card in an argument.
CARDS = (
    ('found','found','Портрет в нише','Я увидел и опознал портрет Елены в библиотечной нише. По находке нельзя установить, кто его туда положил.'),
    ('claim','claim','Объяснение ночного визита','В записанном объяснении Аркадий назвал «Сады старой усадьбы» целью ночного визита в библиотеку.'),
    ('album_hearsay','album_hearsay','Пересказ Никиты об альбоме','По словам Никиты, Аркадий сказал, что зашёл за альбомом. В этом рассказе названия нет.'),
    ('book_checked','book_checked','Сверенный экземпляр альбома','Я сверил посвящение и свою вечернюю запись. Это тот экземпляр, который Аркадий передал мне в 22:10.'),
    ('handover','handover','Показание Тамары о покрывале','Тамара сказала, что ночью у кабинета передала покрывало Аркадию лично. Куда он понёс его дальше, она не видела.'),
    ('denial','denial','Ответ Аркадия о передаче','Аркадий ответил, что Тамара ночью не передавала покрывало ему в руки.'),
    ('bundle','bundle','Показание Никиты о свёртке','Никита узнал Аркадия у библиотеки и видел плоский свёрток. Он не видел содержимого.'),
    ('cover_match','cover_match','Заплата на покрывале','Я сопоставил заплату и шов найденной ткани с фотографией покрывала из кабинета.'),
    ('key_seen','key_seen','Запасной ключ','Я видел у Никиты запасной ключ. Сам ключ не показывает, когда им пользовались.'),
    ('photo_seen','photo_seen','Рабочий снимок Софьи','Я видел рабочую фотографию оборота рамы. Снимок показывает размер и крепления.'),
    ('note_checked','note_checked','Восстановленное письмо Веры','Мы восстановили фрагменты. В записке было извинение. Время её появления из текста неизвестно.'),
    ('chest_checked','chest_checked','Осмотр сундука','При осмотре я не нашёл портрет в сундуке. Содержимое до осмотра мне неизвестно.'),
    ('dust_seen','dust_seen','Пыль на пиджаке','Я видел светлую пыль на пиджаке и на старых поверхностях. Её источник не установлен.'),
    ('time_anchor','time_anchor','Щелчок в 00:40','Я услышал щелчок двери и записал время. Кто был у двери, я не видел.'),
    ('vera_seen','vera_seen','Встреча с Верой ночью','Я встретил Веру в холле. Из какой комнаты она вышла, я не видел.'),
    ('buyer_checked','buyer_checked','Переписка с покупателем','По переписке и ответу покупателя речь шла о пейзаже «Берег».'),
    ('restoration_checked','restoration_checked','Ответ мастерской','Я сверил документы. В них был предварительный расчёт без согласованного вывоза.'),
    ('tamara_route','tamara_route','Порядок дел Тамары','Тамара сказала, что сначала отнесла чашки, а затем занялась бельём. Время между этими действиями неизвестно.'),
    ('vera_route','vera_route','Путь Веры к консоли','Я проверил, что к консоли можно подойти с разных сторон. Одно положение Веры в холле не показывает, откуда она пришла.'),
    ('door_view','door_view','Вид из дверей галереи','Я видел из дверей край стены. Место у самой рамы видно только частично.'),
    ('niche_access','niche_access','Устройство секции','Я осмотрел ручку. Открыть секцию можно со стороны стола или ближних полок.'),
    ('cloth_scrap','cloth_scrap','Лоскут из корзины','Тамара показала лоскут, который убрала у галереи. Я не установил его происхождение.'),
)
ARGUMENTS = (
    {'found','claim','book_checked','bundle'},
    {'found','claim','book_checked','handover','cover_match'},
    {'found','handover','denial','cover_match','bundle'},
)

def evidence_scenes():
    keys=[row[0] for row in CARDS]
    groups=[['found','book_checked','cover_match','key_seen','photo_seen','chest_checked','dust_seen','niche_access','cloth_scrap'],
            ['claim','album_hearsay','handover','denial','bundle','tamara_route','buyer_checked','restoration_checked'],
            ['time_anchor','vera_seen','vera_route','door_view','note_checked']]
    assert sorted(keys)==sorted(k for group in groups for k in group)
    labels=['Предметы и следы','Показания и документы','Ночь и маршруты']
    card_data={k:(guard,title,detail) for k,guard,title,detail in CARDS}
    out=['scene journal_0', 'hide all',
         'if journal_presenting -> evidence_home',
         quote('Блокнот Ильи. Здесь только записи этого прохождения.'),
         *choices([(label,f'journal_open_{i}') for i,label in enumerate(labels)]+[('Закрыть блокнот','journal_exit')]),
         'scene evidence_home','hide all',
         quote('Выберите одну доказательную цепочку. Отметки можно менять до подтверждения.'),
         *choices([(label,f'journal_open_{i}') for i,label in enumerate(labels)]+[
             ('Проверить отмеченные записи','review_argument'),('Сменить подозреваемого','final_menu')]),
         'scene journal_exit']
    for target in ('s14_menu','s21_menu','s26_after','s27_menu','final_menu'):
        out += [f'if journal_return == {quote(target)} -> {target}']
    out+=['goto final_menu']
    for group_index,group in enumerate(groups):
        first=f'card_{group[0]}'
        out += [f'scene journal_open_{group_index}',*sets('journal_back=false'),f'goto {first}']
        for i,key in enumerate(group):
            guard,title,detail=card_data[key]
            card=f'card_{key}'
            prev=f'card_{group[i-1]}' if i else 'journal_0'
            nxt=f'card_{group[i+1]}' if i+1<len(group) else 'journal_0'
            back=f'back_{key}'
            forward=f'next_{key}'
            out += [f'scene {card}',f'if {expr(guard)} == false',f'if journal_back -> {prev}',f'goto {nxt}','end',
                    quote(f'{title}. {detail}'),
                    'if journal_presenting',
                    f'if take_{key}',
                    *choices([('Снять отметку',f'unpick_{key}'),('Следующая запись',forward),('Предыдущая запись',back),('К разделам','journal_0')],title+' · отмечено'),
                    'else',
                    *choices([('Отметить для предъявления',f'pick_{key}'),('Следующая запись',forward),('Предыдущая запись',back),('К разделам','journal_0')],title),
                    'end','else',
                    *choices([('Следующая запись',forward),('Предыдущая запись',back),('К разделам','journal_0')],title),'end',
                    f'scene {forward}',*sets('journal_back=false'),f'goto {nxt}',
                    f'scene {back}',*sets('journal_back=true'),f'goto {prev}',
                    f'scene pick_{key}',f'if {expr(guard)} == false -> {card}',*sets(f'take_{key}=true'),f'goto {card}',
                    f'scene unpick_{key}',*sets(f'take_{key}=false'),f'goto {card}']
    out+=['scene review_argument',*sets('argument_summary=""')]
    for key,guard,title,_ in CARDS:
        out += ['if '+expr(f'take_{key} and {guard}'),
                'if argument_summary != ""',*sets('argument_summary=argument_summary + " · "'),'end',
                *sets('argument_summary=argument_summary + '+quote(title)),'end']
    out+=['if argument_summary == ""',*sets('argument_summary="Записи не отмечены"'),'end']
    out+=choices([('Выбрать, как предъявить записи','accusation_format'),('Вернуться к выбору записей','evidence_home'),('Сменить подозреваемого','final_menu')],'{argument_summary}')
    out+=['scene accusation_format',*choices([('Предъявить сперва наедине','submit_private'),
                                              ('Предъявить при всех','submit_public'),
                                              ('Вернуться к отмеченным записям','review_argument')],'{argument_summary}'),
          'scene submit_private',*sets('private_accusation=true'),'goto submit_argument',
          'scene submit_public',*sets('private_accusation=false'),'goto submit_argument']
    exact=[]; sufficient=[]
    for valid in ARGUMENTS:
        required=[f'take_{key} && ({guard})' for key,guard,_,_ in CARDS if key in valid]
        omitted=[f'take_{key} == false' for key in keys if key not in valid]
        sufficient.append('('+' && '.join(required)+')')
        exact.append('('+' && '.join(required+omitted)+')')
    out+=['scene submit_argument',*sets('proof='+' || '.join(exact)+';argument_extra='+' || '.join(sufficient)),
          'set journal_presenting = false']
    out+=['if suspect == "arkady"', 'if private_accusation -> accuse_private','goto accuse_public','end']
    for name in ('vera','nikita','sofya','tamara'):
        out+=[f'if suspect == {quote(name)} -> accuse_{name}']
    out+=['goto final_menu']
    return out

def route_scenes(chunks, hidden):
    source=(SRC/'10_investigation_routes.md').read_text('utf8')
    authored={}
    for m in re.finditer(r'^## (\w+)\n(.*?)(?=^## |\Z)',source,re.M|re.S):
        parts=re.split(r'^### ([AB])\. «(.*?)»\s*\n',m[2],flags=re.M)
        authored[m[1]]=(parts[0],dict(zip(parts[1::3],zip(parts[2::3],parts[3::3]))))
    out=[]

    def start(name):
        out.extend([f'scene {name}',*compile_body(authored[name][0],name)])

    def add(name, text, target, changes='', original=None):
        out.extend([f'scene {name}',*compile_body(text,name)])
        if original:
            out.extend(effects(original))
        out.extend([*sets(changes),f'goto {target}'])

    def local(name, letter, target, changes=''):
        label,text=authored[name][1][letter]
        add(name+letter,text,target,changes)
        return label,name+letter

    def authored_choices(name, target, changes):
        start(name)
        options=[(label,name+letter) for letter,(label,_) in authored[name][1].items()]
        out.extend(choices(options))
        for letter in authored[name][1]:
            local(name,letter,target,changes.get(letter,''))

    authored_choices('r09','s10',{'A':'key_seen=true;nikita_help=true;key_checked=true'})
    authored_choices('r10','s11',{'A':'tamara_help=true;tamara_route=true','B':'tamara_help=true'})
    authored_choices('r11','s12',{'A':'door_view=true','B':'night_visit=true'})
    authored_choices('r12','s13',{'A':'sofia_help=true','B':'sofia_help=true'})
    authored_choices('r13','s14',{'A':'vera_route=true','B':'vera_help=true;tact=tact + 1'})

    start('r16')
    out+=choices([('Восстановить, откуда Никита видел лицо','r16A'),
                  ('Сверить, о какой картине говорил покупатель','r16B')])
    out+=['scene r16A','if night_replayed',*compile_body(hidden['23C'][1],'r16C'),*effects('23C'),
          'else',*compile_body(chunks['23A'],'r16A'),*effects('23A'),'end','goto s17']
    add('r16B',chunks['15A'],'s17',original='15A')
    start('r17')
    out+=conditional_choices([('Пройти с Верой от лестницы до консоли','r17A'),
                              (authored['r17'][1]['B'][0],'r17B')],
                             [(HIDDEN_CONDITIONS['17C'],hidden['17C'][0],'s17C')])
    add('r17A',chunks['17A'],'s18',original='17A')
    local('r17','B','s18','vera_route=true')
    start('r18')
    out+=choices([('Уточнить рассказ Тамары о покрывале','r18A'),(authored['r18'][1]['B'][0],'r18B')])
    add('r18A',chunks['18A'],'s19',original='18A')
    local('r18','B','s19')
    start('r19')
    out+=['goto s20']

    out+=['scene s23_objects',*compile_body(authored['s23'][0],'s23_objects')]
    out+=choices([('Сверить покрывало с фотографией кабинета','s23_patch'),
                  (authored['s23'][1]['B'][0],'s23_access')])
    add('s23_patch',chunks['21A'],'s24',original='21A')
    add('s23_access',authored['s23'][1]['B'][1],'s24','niche_access=true')

    start('r22')
    out+=conditional_choices([(label,'r22'+letter) for letter,(label,_) in authored['r22'][1].items()],
                             [('bundle_recorded=false','Записать наблюдение Никиты','r22_n'),
                              ('handover_recorded=false','Записать рассказ Тамары о передаче','r22_t')])
    local('r22','A','s23')
    local('r22','B','s23')
    add('r22_n',chunks['23A'],'s23',original='23A')
    add('r22_t',chunks['23B'],'s23',original='23B')
    start('r23')
    out+=conditional_choices([('Уточнить, какой участок холла был виден','r23_view'),
                              ('Сверить порядок дел со слов Тамары','r23_order')],
                             [('bundle_recorded=false and night_replayed=false','Записать наблюдение Никиты','r23_n'),
                              ('bundle_recorded=false and night_replayed',hidden['23C'][0],'r23_secret'),
                              ('handover_recorded=false','Записать передачу покрывала','r23_t')])
    add('r23_view',authored['r11'][0]+authored['r11'][1]['A'][1],'s24','door_view=true')
    add('r23_order',authored['r22'][1]['B'][1],'s24')
    add('r23_n',chunks['23A'],'s24',original='23A')
    add('r23_t',chunks['23B'],'s24',original='23B')
    add('r23_secret',hidden['23C'][1],'s24',original='23C')

    out+=['scene s24','if route_witnesses -> r24',
          quote('Я успею ещё одну проверку. Можно закончить предметный осмотр или обратиться за недостающим показанием.')]
    out+=conditional_choices([('Осмотреть и зафиксировать положение рамы','s24A'),
                              ('Сверить устройство секции','s24_access')],
                             [('bundle_recorded=false and night_replayed=false','Записать наблюдение Никиты','s24B'),
                              ('bundle_recorded=false and night_replayed',hidden['23C'][0],'s24_secret'),
                              ('handover_recorded=false','Записать передачу покрывала','s24C'),
                              (HIDDEN_CONDITIONS['24D'],hidden['24D'][0],'s24D')])
    start('r24')
    out+=conditional_choices([('Осмотреть и зафиксировать положение рамы','s24A'),
                              ('Сверить устройство секции','s24_access')],
                             [('found and cover_match=false','Сверить заплату с фотографией','r24_patch'),
                              ('bundle_recorded=false and night_replayed=false','Записать наблюдение Никиты','s24B'),
                              ('bundle_recorded=false and night_replayed',hidden['23C'][0],'s24_secret'),
                              ('handover_recorded=false','Записать передачу покрывала','s24C')])
    for key in ('24A','24B','24C'):
        add('s'+key,chunks[key],'s25',original=key)
    add('s24D',hidden['24D'][1].split('Текст: Аркадий входит, когда мы заканчиваем.',1)[0],'s25',original='24D')
    add('s24_secret',hidden['23C'][1],'s25',original='23C')
    add('s24_access',authored['s23'][1]['B'][1],'s25','niche_access=true')
    add('r24_patch',chunks['21A'],'s25',original='21A')
    return out

def last_question(chunks):
    photo='''КАДР BG25.

Текст: На рабочем снимке виден оборот рамы с размерами и креплениями.

**Софья · обычный · S02 · по пояс:** Я сфотографировала раму с этого ракурса, чтобы сохранить расположение креплений. Время, когда портрет сняли со стены, по фотографии установить нельзя.'''
    scrap='''КАДР BG59.

Текст: Тамара показывает лоскут, который убрала утром у галереи. На нём нет признаков, по которым его можно было бы уверенно связать с покрывалом.

**Тамара · обычный · T04 · по пояс:** Я положила его в корзину до разговора о пропаже. Откуда он взялся, сказать не могу.'''
    topics={
        'arkady': [('Уточнить, о каком альбоме шла речь','s27B',chunks['27B'],'27B',''),
                   ('Спросить о личной передаче покрывала','s27A',chunks['27A'],'27A','')],
        'vera': [('Пройти от лестницы до консоли','s27_vera_path',chunks['17A'],'17A',''),
                 ('Уточнить, какое место было на плане','s27_vera_plan',chunks['17B'],'17B','')],
        'nikita': [('Сверить переписку о цене','s27_nikita_buyer',chunks['15A'],'15A',''),
                   ('Уточнить, что он видел у библиотеки','s27_nikita_night',chunks['24B'],'24B','')],
        'sofya': [('Посмотреть исходный рабочий снимок','s27_sofya_photo',photo,None,'photo_seen=true'),
                  ('Сверить, что ответила мастерская','s27_sofya_reply',chunks['16A'],'16A','')],
        'tamara': [('Посмотреть лоскут из корзины','s27_tamara_cloth',scrap,None,'cloth_scrap=true'),
                   ('Записать, кому она передала покрывало','s27_tamara_cover',chunks['23B'],'23B','')],
    }
    out=compile_body('КАДР BG78.\n\n**Илья · обычный · I04 · по пояс:** До общего разговора могу уточнить ещё одну деталь. Остальное останется в блокноте таким, каким я это услышал.', '27')
    out+=['goto s27_menu','scene s27_menu',
          *choices([(name,'s27_'+key) for key,name in SUSPECTS.items()]+[('Открыть блокнот','review_s27')], 'С кем поговорить?'),
          *journal_link('review_s27','s27_menu')]
    for key,entries in topics.items():
        out += ['scene s27_'+key,*choices([(label,target) for label,target,*_ in entries]
                       +[('Выбрать другого собеседника','s27_menu')], 'Какую деталь уточнить?')]
        for _,target,text,original,changes in entries:
            out += ['scene '+target,*compile_body(text,target),*(effects(original) if original else []),
                    *sets(changes),'goto s28']
    return out

def build():
    previous=json.loads((DEV/'build_manifest.json').read_text('utf8')) if (DEV/'build_manifest.json').is_file() else {}
    scenes,hubs=sections(); body=[]; menus={}; scene_labels={}
    hidden=hidden_scenes()
    assert hidden.keys()==HIDDEN_CONDITIONS.keys()
    chunks=branch_chunks(scenes)
    for num,text in scenes.items():
        if num=='24':
            continue
        scene_labels['s'+num]=text.splitlines()[0][3:]
        body += ['','scene s'+num, '// '+scene_labels['s'+num]]
        if num in ('09','10','11','12','13'):
            body+=['if route_stories -> r'+num]
        if num in ('16','17','18','19'):
            body+=['if route_night -> r'+num]
        if num in ('22','23'):
            body+=['if route_witnesses -> r'+num]
        if num=='23':
            body+=['goto s23_objects']
            continue
        if num=='15':
            body+=compile_body('КАДР BG78.\n\n**Илья · обычный · I04 · по пояс:** До открытия дороги успею проверить либо документы и вещи, либо ночные рассказы. С чего начну?',num)
            body+=conditional_choices([('Продолжить с Софьей и проверить вещи','s15_objects'),
                                      ('Восстановить ночной маршрут с Никитой и Тамарой','s15_night')],
                                     [(HIDDEN_CONDITIONS['15C'],hidden['15C'][0],'s15C')])
            body+=['scene s15_objects','goto s16','scene s15_night',*sets('route_night=true'),'goto s16',
                   'scene s15C',*compile_body(hidden['15C'][1],'15C'),*effects('15C'),*sets('route_night=true'),'goto s16']
            continue
        if num=='21':
            body+=compile_body('КАДР BG78.\n\n**Илья · обычный · I04 · по пояс:** До открытия дороги осталось время ещё на один круг. Можно сверить вещи на месте или отдельно уточнить, что люди видели ночью.',num)
            body+=['goto s21_menu','scene s21_menu',
                   *choices([('Сверить вещи и документы','s22'),('Сопоставить рассказы по отдельности','start_witnesses'),
                             ('Открыть блокнот','review_s21')]),
                   'scene start_witnesses',*sets('route_witnesses=true'),'goto s22',*journal_link('review_s21','s21_menu')]
            continue
        if num=='26':
            body+=compile_body('КАДР BG56.\n\nТекст: Я перечитываю свои записи. Рядом с каждым наблюдением оставляю источник, а догадки держу отдельно.\n\n**Илья · обычный · I04 · по пояс:** Можно свериться с блокнотом и задать ещё один вопрос. Всё, чего я не увидел и не услышал, так и останется за пределами записи.',num)
            body+=['goto s26_after','scene s26_after',*choices([('Задать последний вопрос','s27'),
                    ('Открыть блокнот','review_s26')]),*journal_link('review_s26','s26_after')]
            continue
        if num=='27':
            body+=last_question(chunks)
            continue
        if num=='29':
            prefix=text.split('Пункты меню и точные реплики Ильи:',1)[0]
            body+=compile_body(prefix,num)
            body += [quote('Выбор завершит расследование. Можно вернуться к записи фактов; новые проверки уже закрыты.'),'goto final_menu']
            continue
        nxt='s'+f'{int(num)+1:02}'
        if num in hubs:
            nxt='h'+num
        matches=list(re.finditer(r'^### (\d\d)([АБВ])\. «(.*?)»',text,re.M))
        if not matches:
            body+=compile_body(text,num)
            if num=='05': body+=sets('album_in_room=true')
            if num=='19': body+=sets('dust_seen=true')
            if num=='14':
                body+=['goto s14_menu','scene s14_menu',*choices([('Продолжить расследование','s15'),
                        ('Открыть блокнот','review_s14')]),*journal_link('review_s14','s14_menu')]
                continue
            body+=['goto '+nxt]
        else:
            body+=compile_body(text.split('ВЫБОР:',1)[0],num)
            if num=='09':body+=sets('key_seen=true')
            if num=='12':body+=sets('photo_seen=true')
            opts=[(LETTERS[m[2]],m[3]) for m in matches]
            renamed={
                '09':{'B':'Записать, где лежит ключ'},
                '10':{'B':'Сверить содержимое по общей описи'},
                '12':{'B':'Спросить Софью о подготовке при всех'},
            }
            opts=[(letter,renamed.get(num,{}).get(letter,label)) for letter,label in opts]
            bonus=next(((key,(key[-1],label),chunk) for key,(label,chunk) in hidden.items() if key.startswith(num)),None)
            menus[num]=opts+[bonus[1]] if bonus else opts
            def menu(options):
                links=[(label,'s'+num+key) for key,label in options]
                return choices(links)
            def gated_menu(options):
                if bonus is None:return menu(options)
                key,option,_=bonus
                available=([o for o in options if o[0]!='A'] if num=='23' else options)+[option]
                return ['if '+expr(HIDDEN_CONDITIONS[key]),*menu(available),'else',*menu(options),'end']
            body+=gated_menu(opts)
            common=text.split('[ОБЩАЯ СЦЕНА ПОСЛЕ ВЫБОРА]',1)[1] if '[ОБЩАЯ СЦЕНА ПОСЛЕ ВЫБОРА]' in text else ''
            shared17='Общая условная вставка после любой ветви:'
            for i,m in enumerate(matches):
                key=num+LETTERS[m[2]]
                chunk=chunks[key]
                if key=='09B':
                    chunk='**Илья · обычный · I03 · по пояс:** Отмечу, где лежит ключ. Если понадобится уточнить поручение, спрошу тебя отдельно.\n\n**Никита · обычный · N01 · по пояс:** Хорошо. Пока оставлю его на скамье.'
                if key=='12B':
                    chunk='**Софья · обычный · S02 · по пояс:** Я готовила рабочие материалы. Про сам снимок могу рассказать при всех, а полный ответ мастерской лучше прочитать отдельно.'
                if key=='12A':
                    chunk='КАДР BG25.\n\nТекст: Софья открывает исходный файл. На снимке оборот рамы и размерная карточка. Дата совпадает с её рассказом.\n\n**Софья · обычный · S02 · по пояс:** Это рабочий снимок. Если понадобятся условия мастерской, там есть отдельное письмо.'
                if key=='16B':
                    chunk=chunk.replace('после обвинения','без точных исходных размеров')
                if key=='10B':
                    chunk='КАДР BG09.\n\nТекст: Тамара открывает сундук и при всех вынимает дорожки и лампу. Мы видим стенки и дно. Портрета в сундуке нет.\n\n**Тамара · обычный · T04 · по пояс:** Если нужен список, покажу позже. Здесь мы пока только сверили содержимое.'
                body+=['','scene s'+key]+compile_body(chunk,key)+effects(key)+['goto s'+num+'_after']
            if bonus:
                key,(_,label),chunk=bonus
                scene_labels['s'+key]=label
                target={'15C':'s16','17C':'s18'}.get(key,'s'+num+'_after')
                body+=['','scene s'+key]+compile_body(chunk,key)+effects(key)+['goto '+target]
            body+=['','scene s'+num+'_after']
            if num=='17':
                shared=text.split(shared17,1)[1].split('[ОБЩАЯ',1)[0]
                body+=compile_body(shared,num+'_shared')+conditional('vera_help','claim=true')
            body+=compile_body(common,num+'_after')+['goto '+nxt]
        if num in hubs:
            body+=['','scene h'+num]+compile_body(hubs[num],'h'+num)+['goto s'+f'{int(num)+1:02}']
    body+=route_scenes(chunks,hidden)
    final= scenes['29'].split('Пункты меню и точные реплики Ильи:',1)[1].split('Служебное ветвление:',1)[0]
    actions=['private','public','vera','nikita','sofya','tamara','refuse']
    items=re.findall(r'^- «(.*?)» — (\*\*.*)$',final,re.M)
    assert len(items)==7
    body+=['scene final_menu',*choices([(name,'choose_'+key) for key,name in SUSPECTS.items()]
           +[('Не обвинять','accuse_refuse'),('Открыть блокнот','review_final')],'Кого вы считаете виновным?'),
           *journal_link('review_final','final_menu')]
    for a in SUSPECTS:
        body += [f'scene choose_{a}',*sets(f'suspect={quote(a)};journal_presenting=true;journal_back=false'),
                 *sets(';'.join(f'take_{key}=false' for key,_,_,_ in CARDS)),'goto evidence_home']
    body+=evidence_scenes()
    for (_,speech),action in zip(items,actions):
        body+=['','scene accuse_'+action]
        if action in SUSPECTS:
            body+=['if private_accusation',*compile_body('КАДР BG68.\n\nТекст: Сначала мы разговариваем в кабинете.', '29_private_other'),
                   'else',*compile_body('КАДР BG80.','29_public_other'),'end']
        body+=compile_body(speech,'29_'+action)
        if action=='private':
            body+=compile_body('КАДР BG68.','29_private')
        if action!='refuse':
            for key,guard,title,detail in CARDS:
                body+=['if '+expr(f'take_{key} and {guard}'),quote(f'Илья предъявляет запись «{title}». {detail}'),'end']
        if action in ['private','public']:
            body+=['if proof == false -> E7']
            if action=='private': body+=['if tact >= 2 -> E1','goto private_bridge']
            else: body+=['goto E2']
        else:
            if action in SUSPECTS:
                body+=['if private_accusation',quote('Собеседник просит вернуться в столовую, чтобы ответить при остальных. Мы возвращаемся вместе.'),'end']
            body+=['goto '+dict(vera='E3',nikita='E4',sofya='E5',tamara='E6',refuse='E8')[action]]
    bridge=scenes['29'].split('КАДР BG68.',1)[1]
    body+=['','scene private_bridge']+compile_body('КАДР BG68.\n\n'+bridge,'bridge')+['goto E2']
    for i in range(1,9):
        sid='E'+str(i)
        text=ENDINGS.split('## '+sid+'.',1)[1].split('## E',1)[0]
        # The player's selected cards have just been read. Do not fill in
        # evidence on their behalf in the opening of a mistaken accusation.
        if sid in ('E3','E4','E5','E6'):
            invented = {
                'E3':'У вас был конфликт из-за портрета. И вы сначала скрыли, что ночью были в галерее.',
                'E4':'Долг, фотографии коллекции, запасной ключ и скрытый ночной выход.',
                'E5':'Вы знали крепления, имели рабочий снимок и подготовили материалы до согласия владельца.',
                'E6':'У вас доступ к комнатам, вы знали нишу, выходили ночью и убрали ткань, о которой сначала промолчали.',
            }
            text=text.replace(invented[sid],'Я сделал такой вывод из записей, которые только что предъявил.')
            text=text.replace('Ты перечислил всё, чего я стыдился.', 'Ты назвал моё имя.')
            text=text.replace('Все три пункта относятся к одной профессиональной задаче. Они не превращаются в три независимых наблюдения кражи.',
                              'Это была рабочая подготовка. По ней нельзя установить, кто снял раму.')
        if sid=='E7':
            body+=['','scene E7','if private_accusation',*compile_body('КАДР BG68.','E7_private'),
                   'else',*compile_body('КАДР BG80.','E7_public'),'end']
            text=text.replace('`found=', '`take_found=').replace('`bundle=', '`take_bundle=')
            text=text.replace('`book_lie=true`','`take_claim=true and take_book_checked=true`')
            text=text.replace('`cover_lie=true`','`take_handover=true and take_denial=true`')
            text=text.replace('`book_lie=false` и `cover_lie=false` и `take_bundle=false`',
                              '`take_claim=false and take_handover=false and take_bundle=false`')
            text=text.replace('Местонахождение портрета я в выполненных проверках не установил.','Находку портрета я в предъявление не включил.')
            text=text.replace('Цепочка неполна. Я назвал вывод раньше, чем установил необходимые связи.',
                              'Предъявленные записи не сложились в одну цепочку. Я назвал вывод раньше, чем показал необходимые связи.')
            body+=['if argument_extra',quote('В предъявление попали лишние записи. Полная цепочка смешалась с дополнительными доводами.'),'end']
        else: body+=['','scene '+sid]
        body+=compile_body(text,sid)
    # Endings terminate normally; the engine's own restart button resets all flags.
    flags=set(FLAGS)|{'tact','private_accusation','background_slot'}
    header=['[meta]','title = "Обратная сторона холста"','projectId = propavshaya_kartina_v1','startScene = s01','lang = ru','mode = release','window = vertical','autosave = true','transition = fade','transitionMs = 250','aboutEnabled = true','aboutTitle = "Обратная сторона холста"','aboutText = "Мария Прохоренко и Дмитрий Сухобаевский.[br]Камерный детектив, 12+.[br]Прототип с тремя развилками и блокнотом Ильи."','','[bg]']
    for bg in BG.values():
        header.append(('' if (GAME/bg['path']).is_file() else '// ')+bg['id']+' file='+bg['path'])
    header+=['','[char]']
    copies=[];copied=set()
    for key,asset in sorted(ASSETS.items()):
        name=asset['character'];cid,_,color=PEOPLE[name];rel=asset['path'];src=ROOT/asset['source_file']
        assert hashlib.sha256(src.read_bytes()).hexdigest()==asset['sha256'],str(src)
        if rel not in copied:
            dst=GAME/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
            copies.append({'source':str(src.relative_to(ROOT)),'destination':rel,'sha256':asset['sha256']});copied.add(rel)
        header.append(f'{cid} emotion={key} file={rel} name="{name}" color={color}')
    (GAME/'assets/backgrounds').mkdir(parents=True,exist_ok=True)
    header+=['','[var]']+[v+' = '+('0' if v=='tact' else '""' if v in ('background_slot','conversation_slot','conversation_room','suspect','journal_return','argument_summary') else 'false') for v in sorted(flags)]+['','[scene]']
    dsl='\n'.join('# '+line[3:] if line.startswith('// ') else line for line in header+body)+'\n'
    escaped=dsl.replace('\\','\\\\').replace('`','\\`').replace('${','\\${')
    (GAME/'story.js').write_text('window.STORY_TEXT = `\n'+escaped+'`;\n',encoding='utf8')
    (DEV/'story.dsl.txt').write_text(dsl,encoding='utf8')
    # Retire only our own prior generated copies, after checksum and absolute
    # workspace-boundary checks. Approved source directories are never touched.
    boundary=(GAME/'assets/characters').resolve()
    for old in previous.get('characters',[]):
        if old['destination'] in copied:continue
        target=(GAME/old['destination']).resolve()
        assert target.is_relative_to(boundary) and target.suffix=='.png'
        if target.is_file():
            assert hashlib.sha256(target.read_bytes()).hexdigest()==old['sha256'],str(target)
            target.unlink()
    report={'engine_version':'v0.6.10.1','engine_commit':'91b49c9ca73183d36d8a9b3d596d30b1bdc945c2','scenario':'scenario_v9', 'author_moments':30,'consequential_choices':22,'endings':8,'scene_ready_exports':104,'registered_character_states':len(ASSETS),'backgrounds_planned':list(BG.values()),'active_backgrounds':sum((GAME/b['path']).is_file() for b in BG.values()),'characters':copies,'staging_fallbacks':STAGING,'text_counts':COUNTS,'menus':menus,'scene_labels':scene_labels}
    (DEV/'build_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({**COUNTS,'character_pngs':len(copies),'background_slots':len(BG),'dsl_bytes':len(dsl.encode())}))

if __name__=='__main__': build()

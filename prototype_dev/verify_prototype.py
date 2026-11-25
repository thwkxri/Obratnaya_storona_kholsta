"""Check compiled investigation routes and the evidence notebook."""
from pathlib import Path
import ast, re, json, random, hashlib
from itertools import product
from build_prototype import ARGUMENTS, BG, CARDS, SUSPECTS
from collections import Counter
from functools import lru_cache
ROOT=Path(__file__).resolve().parent
story=json.loads((ROOT/'parsed_story.json').read_text('utf8'))
initial_vars=story['vars']
scenes={s['id']:s['actions'] for s in story['scenes']}
backgrounds=story['assets']['backgrounds']
seen_backgrounds=set()
@lru_cache(maxsize=None)
def compile_expression(s):
    s=s.replace('&&',' and ').replace('||',' or ')
    s=re.sub(r'\btrue\b','True',s);s=re.sub(r'\bfalse\b','False',s)
    tree=ast.parse(s.strip(),mode='eval')
    allowed=(ast.Expression,ast.BoolOp,ast.And,ast.Or,ast.Compare,ast.Eq,ast.NotEq,ast.GtE,ast.Name,ast.Load,ast.Constant,ast.BinOp,ast.Add)
    assert all(isinstance(n,allowed) for n in ast.walk(tree)),s
    return compile(tree,'<dsl>','eval')

def evaluate(s,v):
    return eval(compile_expression(s),{'__builtins__':{}},v)

def execute(actions,v,seen=None,texts=None):
    for a in actions or []:
        t=a['type']
        if t=='set':
            key,expr=a['expression'].split('=',1);v[key.strip()]=evaluate(expr,v)
        elif t=='if_block':
            chosen=next((b['actions'] for b in a['branches'] if evaluate(b['condition'],v)),a.get('elseActions',[]))
            result=execute(chosen,v,seen,texts)
            if result:return result
        elif t=='if_expr' and evaluate(a['condition'],v):return ('goto',a['target'])
        elif t=='goto':return ('goto',a['target'])
        elif t=='choice':return ('menu',a['choices'])
        elif t=='bg':
            bg=a['bgId']
            assert bg in backgrounds and bg==v['background_slot'],(bg,v['background_slot'])
            v['_shown_background']=bg
            seen_backgrounds.add(bg)
        elif t in ('say','text'):
            if t=='say':
                assert v.get('_shown_character')==a['charVar'],('speaker portrait missing',a)
                bg=v.get('_shown_background')
                assert bg==v['conversation_slot'] and BG[bg]['type']=='Общий вид',('wrong conversation background',a,bg)
            if a['text']=='Осмотр предмета.':
                bg=v['_shown_background']
                assert BG[bg]['type']!='Общий вид' and v['detail_shot'] and not v.get('_shown_character'),bg
            if texts is not None:texts.append(a['text'])
        elif t=='char':
            v['_shown_character']=a.get('charId')
            if a.get('charId'):
                assert not v['detail_shot'], 'sprite overlaps a detail shot'
                assert a['emotion'] in story['assets']['characters'][a['charId']]['images']

def walk(start, route, variables=None, rng=None, stop=()):
    v=dict(initial_vars if variables is None else variables)
    visited=[]; clicks=[]; texts=[]; sid=start
    for _ in range(400):
        if sid in stop:return sid,v,visited,clicks,texts
        visited.append(sid)
        result=execute(scenes[sid],v,texts=texts)
        if not result:
            assert re.fullmatch(r'E[1-8]',sid),sid
            return sid,v,visited,clicks,texts
        kind,target=result
        if kind=='menu':
            opts={o['actions'][0]['target']:o['text'] for o in target}
            requested=route.get(sid)
            if isinstance(requested,list):
                requested=requested.pop(0)
            if requested is None:
                available=[k for k in opts if not k.startswith('review_')]
                requested=rng.choice(available) if rng else available[0]
            assert requested in opts,(sid,requested,opts)
            clicks.append(opts[requested])
            target=requested
        sid=target
    raise AssertionError(('nonterminating route',visited[-15:]))

def selected_verdict(state, selected, suspect):
    v=dict(state,suspect='arkady' if suspect in ('private','public') else suspect,
           private_accusation=suspect=='private',journal_presenting=True)
    for key,_,_,_ in CARDS:v['take_'+key]=key in selected
    return walk('submit_argument',{},v)

def route_for(early,middle,late):
    route={'s02':'s02A','s08':'s08B' if early else 's08A',
           's15':'s15_night' if middle else 's15_objects',
           's20':'s20A','s21_menu':'start_witnesses' if late else 's22',
           's27_menu':'s27_arkady','s27_arkady':'s27B','s28':'s28A'}
    if late and not middle:route['r22']='r22_n'
    if not late and not middle:route['s24']='s24B'
    return route

def card_title(key):
    return next(title for k,_,title,_ in CARDS if k==key)

def verify():
    menu=lambda sid: execute(scenes[sid],dict(initial_vars))[1]
    final=menu('final_menu')
    assert [option['text'] for option in final[:5]]==list(SUSPECTS.values())
    assert [option['actions'][0]['target'] for option in final[:5]]==['choose_'+key for key in SUSPECTS]
    assert [option['text'] for option in menu('s27_menu')[:5]]==list(SUSPECTS.values())
    assert all(len(menu('s27_'+key))==3 for key in SUSPECTS)
    for key in SUSPECTS:
        _,v,visited,_,_=walk('choose_'+key,{},stop={'evidence_home'})
        assert visited==['choose_'+key] and v['suspect']==key
    examples={}; endings=Counter()
    expected={'found','claim','book_checked','bundle'}
    for bits in product((False,True),repeat=3):
        name=''.join('B' if bit else 'A' for bit in bits)
        _,v,visited,clicks,_=walk('s01',route_for(*bits),stop={'final_menu'})
        assert {f's{i:02}' for i in range(1,30)}<=set(visited),(name,visited)
        assert set(k for k in expected if v[k])==expected,(name,v)
        alternates={'r09','r10','r11','r12','r13'} if bits[0] else set()
        if bits[1]:alternates|={'r16','r17','r18','r19'}
        if bits[2]:alternates|={'r22','r23','r24'}
        assert alternates <= set(visited),(name,alternates,visited)
        e,*_=selected_verdict(v,expected,'private')
        assert e=='E1',(name,e)
        examples[name]={'choices_to_final_menu':clicks,'facts':{key:v[guard] for key,guard,_,_ in CARDS}}

    for route, expected_scenes in (
        (dict(route_for(False,True,True),s06='s06A',s09='s09A',s15='s15C',r16='r16A'),{'s15C','r16A'}),
        (dict(route_for(False,True,True),s06='s06B',s13='s13B',r17='s17C',s20='s20C'),{'s17C','s20C'}),
        (dict(route_for(False,False,False),s12='s12A',s16='s16B',s24='s24D'),{'s24D'}),
    ):
        _,_,visited,_,_=walk('s01',route,stop={'final_menu'})
        assert expected_scenes<=set(visited)

    _,unconfirmed,_,_,_=walk('s01',dict(route_for(False,True,False),s13='s13A',s24='s24_access',s27_arkady='s27A'),
                              stop={'final_menu'})
    assert unconfirmed['album_hearsay'] and not unconfirmed['claim']
    for argument in ARGUMENTS[1:]:
        route=dict(route_for(False,True,False),s10='s10A',r18='r18A',s23_objects='s23_patch')
        if 'denial' in argument:route['s27_arkady']='s27A'
        _,v,_,_,_=walk('s01',route,stop={'final_menu'})
        assert argument <= {key for key,guard,_,_ in CARDS if v[guard]}
        assert selected_verdict(v,argument,'public')[0]=='E2'

    rng=random.Random(20261106)
    for _ in range(256):
        _,v,visited,_,_=walk('s01',{},rng=rng,stop={'final_menu'})
        assert {f's{i:02}' for i in range(1,30)}<=set(visited)
        avail={key for key,guard,_,_ in CARDS if v[guard]}
        for suspect,ending in (('vera','E3'),('nikita','E4'),('sofya','E5'),('tamara','E6')):
            result,*_=selected_verdict(v,avail,suspect)
            assert result==ending
            endings[result]+=1
        for argument in ARGUMENTS:
            selected=argument&avail
            e,*_=selected_verdict(v,selected,'public')
            assert e==('E2' if argument<=avail else 'E7'),(selected,e)
            endings[e]+=1
        result,*_=walk('accuse_refuse',{},v)
        assert result=='E8'
        endings[result]+=1

    final_room=dict(initial_vars,background_slot='BG79',conversation_slot='BG79',_shown_background='BG79')
    available=dict(final_room,**{guard:True for _,guard,_,_ in CARDS})
    for argument in ARGUMENTS:
        ending,*_=selected_verdict(available,argument,'public')
        assert ending=='E2'
        for key,guard,_,_ in CARDS:
            changed=argument^{key}
            assert selected_verdict(available,changed,'public')[0]=='E7'
            if key in argument:
                assert selected_verdict(dict(available,**{guard:False}),argument,'public')[0]=='E7'

    # Walk the actual reader menus. Unseen records are skipped in either direction
    # and cannot be selected, even if navigation enters their generated scene.
    state=dict(final_room,found=True,dust_seen=True,journal_presenting=True,suspect='arkady')
    _,v,visited,_,texts=walk('evidence_home',{
        'evidence_home':['journal_open_0','review_argument'],
        'card_found':['pick_found','next_found','journal_0'],
        'card_dust_seen':['pick_dust_seen','unpick_dust_seen','back_dust_seen'],
        'review_argument':'accusation_format','accusation_format':'submit_public',
    },state,stop={'E7'})
    assert v['take_found'] and not v['take_dust_seen']
    assert not any(card_title(k) in line for k in ('book_checked','cover_match','key_seen','photo_seen') for line in texts)
    assert v['argument_summary']==card_title('found')

    manifest=json.loads((ROOT/'build_manifest.json').read_text('utf8'))
    assert len(backgrounds)==manifest['active_backgrounds']
    for bg,path in backgrounds.items():
        assert path==BG[bg]['path'] and (ROOT.parent/'game'/path).is_file(),bg
    for item in manifest['characters']:
        dst=ROOT.parent/'game'/item['destination']
        assert hashlib.sha256(dst.read_bytes()).hexdigest()==item['sha256']
    registered={item['destination']:item['sha256'] for item in manifest['characters']}
    approved=json.loads((ROOT.parent/'characters/scene_ready_v1/manifest.json').read_text('utf8'))
    assert all(registered[a['path']]==a['sha256'] for a in approved['assets'])
    report={'status':'passed','block_combinations':len(examples),'story_moments_per_route':30,
            'planned_consequential_decisions':22,'random_investigations':256,
            'endings':dict(endings),'final_verdicts_checked':sum(endings.values()),
            'three_exact_evidence_sets':True,'seen_only_and_unmark_checked':True,'symmetric_suspect_menus':True,
            'registered_backgrounds':len(backgrounds),'backgrounds_seen_on_test_routes':len(seen_backgrounds),
            'examples':examples}
    (ROOT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='examples'},ensure_ascii=False))

if __name__=='__main__':
    verify()

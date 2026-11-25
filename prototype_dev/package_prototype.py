from pathlib import Path
import json, hashlib, zipfile

ROOT=Path(__file__).resolve().parent.parent
DEV=ROOT/'prototype_dev'
GAME=ROOT/'game'
manifest=json.loads((DEV/'build_manifest.json').read_text('utf8'))
active={bg['id'] for bg in manifest['backgrounds_planned'] if (GAME/bg['path']).is_file()}
assert len(active)==manifest['active_backgrounds'], 'Rebuild story.js after changing the background files'
lines=['# Реестр фоновых изображений','',
       f'Подключено {len(active)} фонов. Статус «Резерв» отмечает планы из постановочного реестра, которые сейчас не используются в игре.','',
       'Для правки существующего фона замените PNG в игровом каталоге. Сохраните ID и имя файла, чтобы сцены подхватили новую версию.','',
       '| ID | Тип | Содержание | Путь от папки игры | Статус |','|---|---|---|---|---|']
for bg in manifest['backgrounds_planned']:
    status='В игре' if bg['id'] in active else 'Резерв'
    lines.append(f'| {bg["id"]} | {bg["type"]} | {bg["description"]} | `{bg["path"]}` | {status} |')
(DEV/'BACKGROUNDS.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
# Keep the exact staging requests reviewable without creating more art.
with (DEV/'character_staging.json').open('w',encoding='utf8') as out:
    unique={tuple(row.items()) for row in manifest['staging_fallbacks']}
    json.dump([dict(row) for row in sorted(unique)],out,ensure_ascii=False,indent=2)
release=json.loads((DEV/'upstream/vn-vertical-engine-update/release-manifest.json').read_text('utf8'))
verified=[]
for path,metadata in release['files'].items():
    assert hashlib.sha256((GAME/path).read_bytes()).hexdigest()==metadata['sha256'],path
    verified.append(path)
archive=ROOT/'Obratnaya_storona_kholsta_prototype_v1.zip'
temporary=archive.with_suffix('.tmp')
with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
    for f in sorted(GAME.rglob('*')):
        if f.is_file():z.write(f,'Obratnaya_storona_kholsta/'+f.relative_to(GAME).as_posix())
with zipfile.ZipFile(temporary) as z:
    damaged=z.testzip()
    assert damaged is None,damaged
temporary.replace(archive)
with archive.open('rb') as file:
    digest=hashlib.file_digest(file,'sha256').hexdigest()
report={'archive':archive.name,'size_bytes':archive.stat().st_size,'sha256':digest,'unchanged_system_files':verified,'character_pngs':len(manifest['characters']),'scene_ready_pngs':104,'background_pngs':len(active)}
(DEV/'package_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='unchanged_system_files'}))

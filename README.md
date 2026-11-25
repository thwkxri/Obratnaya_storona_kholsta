<h1 align="center">Обратная сторона холста</h1>

<p align="center"><em>Камерная детективная визуальная новелла · 12+</em></p>

<p align="center">
  <img src="docs/screenshots/arrival.png" width="900" alt="Начало игры. Вход в усадьбу дождливым вечером">
</p>

<p align="center">
  <a href="https://github.com/thwkxri/Obratnaya_storona_kholsta/archive/refs/heads/main.zip"><strong>Скачать игру</strong></a>
  · <a href="#как-играть">Как играть</a>
  · <a href="#как-менять-игру">Исходники</a>
</p>

## До открытия дороги

Из домашней галереи исчезает портрет. Дорога закрыта из-за непогоды, и у Ильи есть время осмотреть усадьбу и расспросить её обитателей. В блокноте он собирает то, что увидел, услышал и смог проверить.

Три решения меняют ход расследования. В финале игрок сам выбирает, кого назвать и какие записи предъявить. История может закончиться восемью способами.

## Как играть

Распакуйте архив целиком и откройте `game/index.html` в Microsoft Edge или Google Chrome. Игра работает локально без установки и подключения к интернету. [Скачать ZIP](https://github.com/thwkxri/Obratnaya_storona_kholsta/archive/refs/heads/main.zip)

Нажмите на реплику или используйте Enter и пробел, чтобы продолжить. Прогресс сохраняется в браузере. Кнопка ↻ начинает прохождение заново.

<p align="center">
  <img src="docs/screenshots/hall.png" width="270" alt="Аркадий в холле усадьбы">
  <img src="docs/screenshots/notebook.png" width="270" alt="Илья с блокнотом в столовой">
</p>

## Как менять игру

- **Фоны.** Чтобы заменить изображение, сохраните его имя, например `BG01.png`. [Игровые PNG](game/assets/backgrounds), [реестр фонов](prototype_dev/BACKGROUNDS.md).
- **Сценарий.** После правок постановки пересоберите `game/story.js` командами ниже. [Исходники сценария](prototype_dev/scenario_v9).
- **Постановка персонажей.** Масштаб, кадрирование и привязка образов задаются при сборке. [Сборщик](prototype_dev/build_prototype.py), [таблица поз](prototype_dev/POSE_SUBSTITUTIONS.md).

Для сборки и проверки нужны Python 3.11+ с Pillow и Node.js. Для запуска готовой игры эти инструменты не нужны.

```sh
python -m pip install Pillow
python prototype_dev/build_prototype.py
node prototype_dev/parse_story.cjs
python prototype_dev/verify_prototype.py
```

Для проверки интерфейса в Edge на Windows выполните `npm ci --prefix prototype_dev/test_runtime`, затем запустите `node prototype_dev/browser_routes.cjs` и `node prototype_dev/browser_evidence.cjs`.

## Текущая версия

25 ноября 2026 года подключены 75 фоновых иллюстраций. Крупные планы улик показываются отдельным шагом без персонажей. Перед следующей репликой игра возвращает общий план и выводит говорящего.

Проверены все восемь сочетаний маршрутов и все восемь концовок. В Edge также проверены загрузка всех фоновых PNG, выбор аргументов и восстановление автосохранения. После обновления сюжета прохождение прежней версии может начаться заново.

## Авторы и движок

Мария Прохоренко и Дмитрий Сухобаевский.

Новелла работает на движке Ильи Барило. Его условия распространения и сторонние уведомления включены в папку игры. [vn-vertical-engine v0.6.10.1](https://github.com/IlyaBarilo/vn-vertical-engine/releases/tag/v0.6.10.1), [лицензия движка](game/LICENSE), [уведомления](game/NOTICE.md).

# 01. Что сделано: подсветка клавиатуры

## Итог

Цвет подсветки клавиатуры меняется **напрямую записью в Embedded Controller (EC)**
через `ec_sys`. Проверено на HP Victus 16-r0xxx — розовый `255,105,180` применяется.

## Как это работает

1. В Linux нет `/sys/class/leds/*kbd_backlight*` на этой машине → стандартный
   механизм LED-класса недоступен (Patch hp-wmi multicolor LED **не влит** в upstream).
2. Значения RGB лежат в памяти EC по смещению `0x08..0x0A`.
3. Доступ к EC: модуль `ec_sys` с параметром `write_support=1`,
   файл `/sys/kernel/debug/ec/ec0/io` (это файл-отображение всей EC-памяти,
   читается и пишется напрямую).

### Проверенный дамп (до/после)

```
0000: 00 00 00 00 00 01 40 aa ff ff ff 00 ff 00 00 01   ......@.........
0010: 00 16 3a 12 00 00 ff ff ff ff ff ff 00 ff ff 24   ..:............$
0020: 00 00 00 00 00 00 00 00 00 ff 20 00 00 36 50 55   .......... ..6PU
0030: 4a 41 30 42 55 31 48 53 33 4e 48 00 01 00 00 ff   JA0BU1HS3NH.....
```

- `0x08..0x0A = ff ff ff` → белый (текущий цвет).
- `0x32..0x3C` = серийный номер (`JA0BU1HS3NH`).
- `0x29 = 0x20` — кандидат на яркость подсветки (не подтверждено).

## Установленные скрипты

### `~/.local/bin/victus-kbd` (backend, root)

```python
EC_PATH  = "/sys/kernel/debug/ec/ec0/io"
OFFSETS  = (8, 9, 10)          # R, G, B

def ensure_ec():
    if not os.path.exists("/sys/kernel/debug"):
        subprocess.run(["mount","-t","debugfs","none","/sys/kernel/debug"], check=True)
    if not os.path.exists(EC_PATH):
        subprocess.run(["modprobe","ec_sys","write_support=1"], check=True)

def write_rgb(r, g, b):
    with open(EC_PATH, "r+b", buffering=0) as f:
        f.seek(OFFSETS[0])
        f.write(bytes((r, g, b)))
```

Команды: `get`, `dump [start] [len]`, `pink|red|blue|...`, `off`, `"R G B"`.

### `~/.local/bin/ColorMaker` (без root)

Создаёт/листает именованные цвета. Только английские имена (`a-z0-9_-`).
Хранилище: `~/.config/victus-kbd/colors.conf` вида `name = r,g,b`.
Встроенная палитра: 50+ цветов (red, pink, hotpink, magenta, violet, ...).

### `~/.local/bin/Changer` (обёртка, зовёт `sudo victus-kbd`)

```
Changer <имя> | R G B | #RRGGBB | list | random | off
```

## Проверка

```bash
sudo ~/.local/bin/victus-kbd dump 0 64      # чтение EC
sudo ~/.local/bin/victus-kbd pink           # rgb (255,255,255) -> (255,105,180)
Changer list
Changer orange
```

## Известные ограничения

1. **Нужен root** на каждую запись → пароль sudo каждый раз.
2. **Нет яркости** — только цвет. Яркость в OMEN/Win управляется WMI-событием
   `HPWMI_BACKLIT_KB_BRIGHTNESS = 0x0D`, на Linux оно не пробрасывается в LED-класс
   (скрипт `omarchy-brightness-keyboard` ищет `*kbd_backlight*` и здесь не работает).
3. **Нет зон** — пишем 3 байта, т.е. одна зона. 4-зонные OMEN потребуют другого layout.
4. **Риск**: прямая запись в EC. Некорректные значения могут заморозить контроллер
   и потребовать hard reboot. Поэтому: только offset 0x08..0x0A, только 0..255.
5. **Сохранность**: цвет держится до сброса EC (обычно до перезагрузки/сна).
   Нужен autostart для восстановления.
6. Значение «максимальной яркости» в EC на разных ревизиях бывает `0xE4` (228),
   а не `0xFF` — для своего устройства проверять `dump`.

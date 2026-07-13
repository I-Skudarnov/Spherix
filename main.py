#!/usr/bin/env python3
"""
Filler_hex — гексагональный клон игры Filler (по мотивам игры Скударнова И., 1991).
Python/pygame.

Этап 1: игровое поле из правильных шестиугольников («pointy-top»), 28 столбцов × 16
рядов = 448 гексов, случайная раскраска в 7 цветов; отрисовка поля, верхней строки
со счётом и подписью, нижней палитры-маркера.
"""

import pygame, random, math, sys, os, asyncio
from array import array

# ── Цвета 7 типов гексов (порядок как в задании и в нижней палитре) ───────
# синий, зелёный, жёлтый, красный, фиолетовый, коричневый, белый.
COLORS = [
    ( 72,  72, 240),   # 0 синий
    ( 72, 240,  72),   # 1 зелёный
    (240, 240,  72),   # 2 жёлтый
    (240,  72,  72),   # 3 красный
    (240,  72, 240),   # 4 фиолетовый
    (168,  72,   0),   # 5 коричневый
    (240, 240, 240),   # 6 белый
]
NCOLORS = len(COLORS)

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
HEX_BORDER = (40, 70, 70)     # тонкая граница между гексами (как на скриншоте)
UI_YELLOW = (255, 255, 90)    # активный пункт меню
UI_GREEN  = (110, 240, 110)   # выбранный ответ
UI_GRAY   = (150, 150, 150)   # ещё не активный пункт

# ── Геометрия поля ───────────────────────────────────────────────────────
COLS, ROWS = 28, 16           # 28 столбцов × 16 рядов = 448 гексов
HEX_R = 18                    # радиус (центр→вершина) шестиугольника
HW = math.sqrt(3) * HEX_R     # ширина гекса (между плоскими боковыми гранями)
VSTEP = 1.5 * HEX_R           # шаг между рядами по вертикали

TOP_H    = 40                 # верхняя строка (счёт и подпись)
MARGIN_X = 16                 # боковые поля
GAP      = 14                 # зазор между полем и палитрой
PAL_H    = 72                 # высота нижней палитры

BOARD_W = HW * (COLS + 0.5)                  # ширина поля в пикселях
BOARD_H = VSTEP * (ROWS - 1) + 2 * HEX_R     # высота поля в пикселях

SCREEN_W = int(BOARD_W + 2 * MARGIN_X)
SCREEN_H = int(TOP_H + BOARD_H + GAP + PAL_H + MARGIN_X)

BOARD_X0 = MARGIN_X           # левый край поля
BOARD_Y0 = TOP_H              # верхний край поля

# ── Нижние палитры (две: P1 слева, P2 справа) ────────────────────────────
PAL_MARGIN  = 30              # отступ крайнего гекса палитры от края экрана
PAL_STEP    = 61             # шаг между гексами в палитре
PAL_Y       = TOP_H + BOARD_H + GAP + PAL_H / 2   # центр палитр по вертикали
MARKER_SIZE = int(2 * HW)    # сторона квадрата-маркера (~2× размера гекса)


def palette_center(player, i):
    """Центр i-го гекса (0..6) в палитре игрока player (0 — левая, 1 — правая)."""
    if player == 0:
        cx = PAL_MARGIN + i * PAL_STEP
    else:
        cx = SCREEN_W - PAL_MARGIN - (NCOLORS - 1 - i) * PAL_STEP
    return cx, PAL_Y


def hex_center(col, row):
    """Пиксельный центр гекса (col, row). Нечётные ряды смещены вправо на пол-гекса."""
    cx = BOARD_X0 + HW / 2 + col * HW + (row & 1) * (HW / 2)
    cy = BOARD_Y0 + HEX_R + row * VSTEP
    return cx, cy


def hex_points(cx, cy, r=HEX_R):
    """6 вершин «pointy-top» шестиугольника (вершины сверху и снизу)."""
    hw = math.sqrt(3) * r / 2
    return [
        (cx,      cy - r),       # верх
        (cx + hw, cy - r / 2),   # верх-право
        (cx + hw, cy + r / 2),   # низ-право
        (cx,      cy + r),       # низ
        (cx - hw, cy + r / 2),   # низ-лево
        (cx - hw, cy - r / 2),   # верх-лево
    ]


# ── Соседство гексов (pointy-top, раскладка "odd-r": нечётные ряды сдвинуты вправо)
# Смещения [dcol, drow] до 6 соседей, отдельно для чётных и нечётных рядов.
_ODDR_EVEN = [(+1, 0), (0, -1), (-1, -1), (-1, 0), (-1, +1), (0, +1)]
_ODDR_ODD  = [(+1, 0), (+1, -1), (0, -1), (-1, 0), (0, +1), (+1, +1)]

def neighbors(col, row):
    """Список соседних клеток (по граням) в пределах поля."""
    table = _ODDR_ODD if (row & 1) else _ODDR_EVEN
    res = []
    for dc, dr in table:
        c, r = col + dc, row + dr
        if 0 <= c < COLS and 0 <= r < ROWS:
            res.append((c, r))
    return res


# ── Состояние партии ─────────────────────────────────────────────────────
class Game:
    def __init__(self):
        # color[col][row] — индекс цвета (0..6)
        self.color = [[random.randrange(NCOLORS) for _ in range(ROWS)]
                      for _ in range(COLS)]
        # owner[col][row] — кому принадлежит гекс: None / 0 / 1
        self.owner = [[None] * ROWS for _ in range(COLS)]
        self.cur_color = [0, 0]        # текущий цвет группы каждого игрока
        self.score = [0, 0]            # очки игроков = размеры групп
        self.turn = 0                  # чей ход: 0 — первый игрок, 1 — второй
        self.marker = [0, 0]           # позиция маркера в палитре каждого игрока
        # Стартовые группы: P1 — из левого-нижнего угла, P2 — из правого-верхнего.
        self._init_groups()
        self._update_score()
        # Маркеры обоих игроков — на крайний левый доступный цвет.
        self.reset_marker_left(0)
        self.reset_marker_left(1)

    # ── Стартовые группы ─────────────────────────────────────────────────
    def _init_groups(self):
        """Каждый игрок владеет связной одноцветной группой со своим углом."""
        self._flood_claim(0, ROWS - 1, 0)          # P1 — левый-нижний угол
        self._flood_claim(COLS - 1, 0, 1)          # P2 — правый-верхний угол

    def _flood_claim(self, sc, sr, player):
        """Захватить связную область цвета угла, начиная с (sc, sr), за player.

        Не трогает клетки, уже занятые другим игроком.
        """
        from collections import deque
        col0 = self.color[sc][sr]
        if self.owner[sc][sr] is not None:
            return
        self.owner[sc][sr] = player
        q = deque([(sc, sr)])
        while q:
            c, r = q.popleft()
            for nc, nr in neighbors(c, r):
                if self.owner[nc][nr] is None and self.color[nc][nr] == col0:
                    self.owner[nc][nr] = player
                    q.append((nc, nr))
        self.cur_color[player] = col0

    # ── Клетки игрока и счёт ──────────────────────────────────────────────
    def cells_of(self, player):
        return [(c, r) for c in range(COLS) for r in range(ROWS)
                if self.owner[c][r] == player]

    def _update_score(self):
        for p in (0, 1):
            self.score[p] = sum(1 for c in range(COLS) for r in range(ROWS)
                                if self.owner[c][r] == p)

    # ── Ход: выбор цвета → перекраска группы + захват прилегающих ─────────
    def apply_move(self, player, new_color):
        """Игрок player выбирает цвет new_color: вся его группа перекрашивается
        в этот цвет и захватывает все смежные (по граням) свободные гексы того
        же цвета (повторная заливка). Обновляет текущий цвет и счёт."""
        from collections import deque
        cells = self.cells_of(player)
        # Перекрашиваем свою группу в новый цвет.
        for c, r in cells:
            self.color[c][r] = new_color
        # Заливка: захватываем смежные свободные гексы нужного цвета.
        q = deque(cells)
        while q:
            c, r = q.popleft()
            for nc, nr in neighbors(c, r):
                if self.owner[nc][nr] is None and self.color[nc][nr] == new_color:
                    self.owner[nc][nr] = player
                    q.append((nc, nr))
        self.cur_color[player] = new_color
        self._update_score()

    # ── Маркер выбора цвета ───────────────────────────────────────────────
    def valid_colors(self, player):
        """Цвета, доступные игроку для хода: все, кроме своего текущего и
        текущего цвета противника."""
        excl = {self.cur_color[player], self.cur_color[1 - player]}
        return [i for i in range(NCOLORS) if i not in excl]

    def move_marker(self, player, direction):
        """Сдвинуть маркер игрока на 1 в сторону direction (+1 вправо/-1 влево),
        по кругу, ПРОПУСКАЯ недоступные цвета (оба текущих)."""
        valid = self.valid_colors(player)
        if not valid:
            return
        i = self.marker[player]
        for _ in range(NCOLORS):
            i = (i + direction) % NCOLORS
            if i in valid:
                self.marker[player] = i
                return

    def ensure_valid_marker(self, player):
        """Если маркер игрока оказался на недоступном цвете — перевести на
        ближайший доступный (вправо)."""
        if self.marker[player] not in self.valid_colors(player):
            self.move_marker(player, +1)

    def reset_marker_left(self, player):
        """Поставить маркер на КРАЙНИЙ ЛЕВЫЙ доступный цвет палитры (мин. индекс).
        Вызывается перед ходом игрока, чтобы маркер не «прыгал»."""
        valid = self.valid_colors(player)
        if valid:
            self.marker[player] = min(valid)

    def clone(self):
        """Лёгкая копия состояния (для просчёта ходов ИИ)."""
        g = Game.__new__(Game)
        g.color = [col[:] for col in self.color]
        g.owner = [col[:] for col in self.owner]
        g.cur_color = self.cur_color[:]
        g.score = self.score[:]
        g.turn = self.turn
        g.marker = self.marker[:]
        return g


# ── Искусственный интеллект (Beginner / Expert / Master = 1 / 2 / 3 хода) ──
def weighted_gain_apply(game, player, color):
    """Применить ход цветом color к game (МУТИРУЕТ game) и вернуть взвешенный
    прирост: захваченные на этом ходу гексы считаются за 2, если они выходят
    ЗА ПРАВЫЙ КРАЙ группы (для P1) / ЗА ЛЕВЫЙ КРАЙ (для P2), иначе за 1.

    Это поощряет стремление «только вперёд» — наступление в сторону соперника.
    """
    cells_before = game.cells_of(player)
    if not cells_before:
        game.apply_move(player, color)
        return 0
    # край группы по X до хода: правый для P1, левый для P2
    xs = [hex_center(c, r)[0] for c, r in cells_before]
    edge = max(xs) if player == 0 else min(xs)
    before = set(cells_before)
    game.apply_move(player, color)
    val = 0
    for c in range(COLS):
        for r in range(ROWS):
            if game.owner[c][r] == player and (c, r) not in before:
                cx = hex_center(c, r)[0]
                forward = (cx > edge) if player == 0 else (cx < edge)
                val += 2 if forward else 1
    return val


def _minimax(game, mover, ai, depth):
    """Минимакс по взвешенному прир. очков. Возвращает (взв.прирост ai − opp)
    при оптимальной игре обоих на оставшуюся глубину."""
    if depth == 0:
        return 0
    valids = game.valid_colors(mover)
    if not valids:
        return 0
    best = None
    for color in valids:
        g2 = game.clone()
        gain = weighted_gain_apply(g2, mover, color)
        sub = _minimax(g2, 1 - mover, ai, depth - 1)
        val = (gain if mover == ai else -gain) + sub
        if best is None:
            best = val
        elif mover == ai:
            best = max(best, val)
        else:
            best = min(best, val)
    return best if best is not None else 0


# ── Параметры «ошибок» ИИ (на стадии отладки легко варьировать) ──────────
# Безошибочный ИИ скучен, поэтому с вероятностью MISTAKE_PROB[уровень] ИИ делает
# «мягкую» ошибку: берёт не лучший ход, а СЛУЧАЙНЫЙ из MISTAKE_TOPN лучших.
MISTAKE_PROB = {
    1: 0.10,   # Beginner
    2: 0.05,   # Expert
    3: 0.01,   # Master
}
MISTAKE_TOPN = 3   # из скольких лучших ходов выбирать при «ошибке» (2–3)


def ai_choose(game, player, level):
    """Выбрать цвет хода для ИИ уровня level (1 Beginner / 2 Expert / 3 Master).

    Обычно — лучший ход по взвешенной оценке (тай-брейк: P1 самый ПРАВЫЙ цвет
    палитры, P2 — самый ЛЕВЫЙ). С вероятностью MISTAKE_PROB[level] делается
    «мягкая» ошибка: случайный из MISTAKE_TOPN лучших ходов.
    """
    valids = game.valid_colors(player)
    if not valids:
        return None
    scored = []
    for color in valids:
        g2 = game.clone()
        gain = weighted_gain_apply(g2, player, color)
        sub = _minimax(g2, 1 - player, player, level - 1)
        scored.append((gain + sub, color))
    scored.sort(key=lambda t: t[0], reverse=True)   # по убыванию оценки

    # «Мягкая» ошибка: случайный ход из нескольких лучших.
    if random.random() < MISTAKE_PROB.get(level, 0):
        return random.choice(scored[:MISTAKE_TOPN])[1]

    # Иначе — лучший ход; тай-брейк среди равных по оценке.
    best_val = scored[0][0]
    cands = [c for v, c in scored if v == best_val]
    return max(cands) if player == 0 else min(cands)


# ── Отрисовка ────────────────────────────────────────────────────────────
def draw_board(surf, game):
    """Нарисовать все гексы поля."""
    for col in range(COLS):
        for row in range(ROWS):
            cx, cy = hex_center(col, row)
            pts = hex_points(cx, cy)
            pygame.draw.polygon(surf, COLORS[game.color[col][row]], pts)
            pygame.draw.polygon(surf, HEX_BORDER, pts, 1)


def draw_top(surf, font, game):
    """Верхняя строка: счёт игроков по краям, подпись по центру."""
    left = font.render("= %d =" % game.score[0], True, WHITE)
    right = font.render("= %d =" % game.score[1], True, WHITE)
    title = font.render("Game by Skudarnov I., 1991", True, WHITE)
    surf.blit(left, (MARGIN_X, (TOP_H - left.get_height()) // 2))
    surf.blit(right, (SCREEN_W - MARGIN_X - right.get_width(),
                      (TOP_H - right.get_height()) // 2))
    surf.blit(title, ((SCREEN_W - title.get_width()) // 2,
                      (TOP_H - title.get_height()) // 2))


def draw_palette(surf, game):
    """Две нижние палитры (P1 слева, P2 справа) по 7 цветных гексов.

    Квадратный маркер (~2× размера гекса, гекс по центру) рисуется на палитре
    того игрока, чей сейчас ход.
    """
    for player in (0, 1):
        for i in range(NCOLORS):
            cx, cy = palette_center(player, i)
            pts = hex_points(cx, cy, HEX_R)
            pygame.draw.polygon(surf, COLORS[i], pts)
            pygame.draw.polygon(surf, HEX_BORDER, pts, 1)
    # Маркер на палитре текущего игрока.
    cx, cy = palette_center(game.turn, game.marker[game.turn])
    s = MARKER_SIZE
    pygame.draw.rect(surf, WHITE, (int(cx - s / 2), int(cy - s / 2), s, s), 2)


# ── Ввод игрока ───────────────────────────────────────────────────────────
# Клавиши: P1 — z (влево), x (выбор), c (вправо); P2 — 1/2/3 цифр. панели.
P1_LEFT, P1_SELECT, P1_RIGHT = (pygame.K_z,), (pygame.K_x,), (pygame.K_c,)
P2_LEFT   = (pygame.K_KP1, pygame.K_1)
P2_SELECT = (pygame.K_KP2, pygame.K_2)
P2_RIGHT  = (pygame.K_KP3, pygame.K_3)

def handle_key(game, key):
    """Обработать нажатие для ТЕКУЩЕГО игрока. Возвращает True, если сделан ход."""
    p = game.turn
    left, select, right = (P1_LEFT, P1_SELECT, P1_RIGHT) if p == 0 \
        else (P2_LEFT, P2_SELECT, P2_RIGHT)
    if key in left:
        game.move_marker(p, -1)
    elif key in right:
        game.move_marker(p, +1)
    elif key in select:
        game.apply_move(p, game.marker[p])       # ход выбранным цветом
        return True                                # передачу хода делает run_game (done)
    return False


def redraw(surf, font, game, remain=None):
    surf.fill(BLACK)
    draw_top(surf, font, game)
    draw_board(surf, game)
    draw_palette(surf, game)
    # Обратный отсчёт времени на ход (в зазоре между палитрами).
    if remain is not None:
        t = font.render(str(int(remain)), True, UI_YELLOW)
        surf.blit(t, (SCREEN_W // 2 - t.get_width() // 2,
                      int(PAL_Y) - t.get_height() // 2))


# ── Стартовый экран (выбор игроков, уровня, времени) ─────────────────────
async def wait_key():
    """Дождаться нажатия клавиши или закрытия окна; вернуть событие.

    Неблокирующий опрос (await каждый кадр) — обязателен для pygbag/браузера.
    """
    while True:
        for ev in pygame.event.get():
            if ev.type in (pygame.KEYDOWN, pygame.QUIT):
                return ev
        await asyncio.sleep(0)


def _draw_slider(surf, font, think):
    """Слайдер 0–30 секунд с метками и треугольным указателем на think."""
    x0, x1 = (SCREEN_W - 360) // 2, (SCREEN_W - 360) // 2 + 360
    y = 360
    pygame.draw.line(surf, WHITE, (x0, y), (x1, y), 2)
    for v in range(0, 31, 5):
        x = x0 + v / 30 * 360
        pygame.draw.line(surf, WHITE, (x, y - 7), (x, y + 7), 2)
        lbl = font.render(str(v), True, WHITE)
        surf.blit(lbl, (x - lbl.get_width() // 2, y - 30))
    # треугольный указатель под линией
    mx = x0 + think / 30 * 360
    pygame.draw.polygon(surf, UI_YELLOW,
                        [(mx, y + 10), (mx - 7, y + 22), (mx + 7, y + 22)])
    val = font.render("( 0 = no limit )", True, UI_YELLOW)
    surf.blit(val, ((SCREEN_W - val.get_width()) // 2, y + 30))


def _draw_start(surf, font, big, types, level, think, step):
    """Стартовый экран ПОШАГОВО: показываем только отвеченные вопросы и текущий."""
    surf.fill(BLACK)
    x = 70
    title = big.render("F I L L E R _ h e x", True, COLORS[1])
    surf.blit(title, ((SCREEN_W - title.get_width()) // 2, 14))

    def line(text, yy, color):
        surf.blit(font.render(text, True, color), (x, yy))

    def ptype(t, ctrl):
        return "" if t is None else ("   <- human (%s)" % ctrl if t == 'H'
                                     else "   <- computer (IBM PC)")

    # Вопрос 1 — первый игрок (показывается всегда).
    line("Choose I  Player :  Z,X,C - 1  ,  IBM PC - 2" + ptype(types[0], "z,x,c"),
         90, UI_YELLOW if step == 0 else UI_GREEN)
    # Вопрос 2 — второй игрок (после ответа на 1-й).
    if step >= 1:
        line("Choose II Player :  1,2,3 - 1  ,  IBM PC - 2" + ptype(types[1], "1,2,3"),
             130, UI_YELLOW if step == 1 else UI_GREEN)
    # Вопрос 3 — уровень (только если есть компьютер).
    if 'C' in types and step >= 2:
        names = {1: "Beginner", 2: "Expert", 3: "Master"}
        sel = ("   <- " + names[level]) if level else ""
        line("Choose level :  Beginner - 1 ,  Expert - 2 ,  Master - 3" + sel,
             185, UI_YELLOW if step == 2 else UI_GREEN)
    # Вопрос 4 — время на ход (шкала).
    if step >= 3:
        line("Enter amount of seconds for thinking :", 300, UI_YELLOW)
        _draw_slider(surf, font, think)


async def start_screen(surf, font, big):
    """Стартовый экран. Возвращает настройки {types,level,think} или None (выход)."""
    types = [None, None]      # 'H' человек / 'C' компьютер
    level = None              # 1/2/3 (None, если оба люди)
    think = 15                # секунд на ход (0 — без лимита)
    step = 0                  # 0 PlayerI, 1 PlayerII, 2 level, 3 слайдер
    NUM1 = (pygame.K_1, pygame.K_KP1)
    NUM2 = (pygame.K_2, pygame.K_KP2)
    NUM3 = (pygame.K_3, pygame.K_KP3)
    while True:
        _draw_start(surf, font, big, types, level, think, step)
        pygame.display.flip()
        ev = await wait_key()
        if ev.type == pygame.QUIT:
            return None
        k = ev.key
        if k == pygame.K_ESCAPE:
            return None
        if step == 0:
            if k in NUM1: types[0] = 'H'; step = 1
            elif k in NUM2: types[0] = 'C'; step = 1
        elif step == 1:
            if k in NUM1: types[1] = 'H'
            elif k in NUM2: types[1] = 'C'
            else: continue
            step = 2 if 'C' in types else 3   # уровень — только если есть компьютер
        elif step == 2:
            if k in NUM1: level = 1; step = 3
            elif k in NUM2: level = 2; step = 3
            elif k in NUM3: level = 3; step = 3
        elif step == 3:
            if k == pygame.K_LEFT:  think = max(0, think - 1)
            elif k == pygame.K_RIGHT: think = min(30, think + 1)
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return {"types": types, "level": level, "think": think}


# ── Звук ─────────────────────────────────────────────────────────────────
# Синтез тонов в буфер (без numpy — работает и в браузере pygbag).
SND_RATE   = 22050
SOUND_OK   = False
_move_cache = {}
_snd_win_h = None       # фанфары (победа человека)
_snd_win_c = None       # «смешок» (победа компьютера)

# Победные мелодии: список (частота_Гц, длительность_с); частота 0 — пауза.
FANFARE = [(392,0.16),(523,0.16),(659,0.16),(784,0.30),(0,0.05),
           (659,0.15),(784,0.42),(0,0.04),(1047,0.55)]            # ~2.2 c, ввысь
CHUCKLE = [(466,0.10),(0,0.06),(440,0.10),(0,0.06),(392,0.10),(0,0.06),
           (349,0.11),(0,0.07),(311,0.12),(0,0.08),(262,0.14),(0,0.10),
           (220,0.18),(0,0.06),(175,0.34)]                        # ~1.7 c, вниз

def _make_buffer(segments, vol):
    """Собрать 16-битный моно-буфер из сегментов (синус, с фейдами по краям)."""
    buf = array('h')
    amp = int(9000 * vol)               # все звуки негромкие
    for freq, dur in segments:
        n = int(dur * SND_RATE)
        fade = min(220, max(1, n // 6))
        two_pi_f = 2.0 * math.pi * freq / SND_RATE
        for i in range(n):
            v = 0 if freq <= 0 else int(amp * math.sin(two_pi_f * i))
            if i < fade:
                v = v * i // fade
            elif i > n - fade:
                v = v * (n - i) // fade
            buf.append(v)
    return buf

def make_sound(segments, vol):
    try:
        return pygame.mixer.Sound(buffer=_make_buffer(segments, vol).tobytes())
    except Exception:
        return None

def init_sound():
    """Инициализировать микшер и собрать победные мелодии. Без звука игра тоже идёт."""
    global SOUND_OK, _snd_win_h, _snd_win_c
    try:
        pygame.mixer.init()             # параметры заданы pre_init() в main()
        SOUND_OK = True
    except Exception:
        SOUND_OK = False
        return
    _snd_win_h = make_sound(FANFARE, 0.30)
    _snd_win_c = make_sound(CHUCKLE, 0.30)

def move_sound(gain):
    """Звук хода: чем больше присоединено гексов, тем НИЖЕ и ДЛИННЕЕ тон."""
    if not SOUND_OK or gain <= 0:
        return None
    g = min(gain, 40)
    if g not in _move_cache:
        freq = max(120, 520 - g * 12)
        dur  = min(0.50, 0.10 + g * 0.011)
        _move_cache[g] = make_sound([(freq, dur)], 0.22)
    return _move_cache[g]

def play(snd):
    if snd is not None:
        try:
            snd.play()
        except Exception:
            pass


# ── Игровой цикл, конец игры, Play again ─────────────────────────────────
WIN_SCORE     = COLS * ROWS // 2   # 224: победа при счёте СТРОГО больше
COMP_DELAY_MS = 600                # пауза перед ходом компьютера (чтобы было видно)

def _winner(game, no_progress):
    """Победитель (0/1) или None. Победа при счёте > WIN_SCORE; иначе при
    заполнении поля / отсутствии прогресса — у кого больше очков."""
    if game.score[0] > WIN_SCORE:
        return 0
    if game.score[1] > WIN_SCORE:
        return 1
    if sum(game.score) >= COLS * ROWS or no_progress >= 4:
        if game.score[0] == game.score[1]:
            return 'draw'                       # ничья (напр. 224 : 224)
        return 0 if game.score[0] > game.score[1] else 1
    return None


async def run_game(game, surf, font, clock):
    """Провести партию. Возвращает индекс победителя (0/1) или 'quit'."""
    types = game.settings["types"]
    level = game.settings["level"]
    think = game.settings["think"]
    turn_start = pygame.time.get_ticks()
    prev_total = sum(game.score)
    no_progress = 0

    def done(mover):
        """Завершить ход mover: передать очередь, обновить таймеры/прогресс.
        Вернуть победителя или None."""
        nonlocal turn_start, prev_total, no_progress
        game.turn = 1 - mover
        game.reset_marker_left(game.turn)        # маркер нового игрока — крайний левый доступный
        turn_start = pygame.time.get_ticks()
        total = sum(game.score)
        if total == prev_total:
            no_progress += 1
        else:
            no_progress = 0
            prev_total = total
        return _winner(game, no_progress)

    while True:
        clock.tick(30)
        now = pygame.time.get_ticks()
        cur = game.turn
        is_human = (types[cur] == 'H')

        # ── ввод (люди + выход) ──
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return 'quit'
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    return 'quit'
                if is_human:
                    before = game.score[cur]
                    if handle_key(game, ev.key):            # сделан ход
                        play(move_sound(game.score[cur] - before))
                        w = done(cur)
                        if w is not None:
                            return w
                        break   # ход сделан — остальные события кадра не трогаем

        # ── ход компьютера (после паузы) ──
        if not is_human and now - turn_start >= COMP_DELAY_MS:
            col = ai_choose(game, cur, level)
            before = game.score[cur]
            if col is not None:
                game.marker[cur] = col          # показать выбранный цвет
                game.apply_move(cur, col)
            play(move_sound(game.score[cur] - before))
            w = done(cur)
            if w is not None:
                return w
        # ── тайм-аут человека: авто-ход цветом под маркером ──
        elif is_human and think > 0 and now - turn_start >= think * 1000:
            before = game.score[cur]
            game.apply_move(cur, game.marker[cur])
            play(move_sound(game.score[cur] - before))
            w = done(cur)
            if w is not None:
                return w

        # ── отрисовка с обратным отсчётом ──
        remain = None
        if is_human and think > 0:
            remain = max(0, think - (now - turn_start) // 1000)
        redraw(surf, font, game, remain)
        pygame.display.flip()
        await asyncio.sleep(0)          # отдать управление браузеру (pygbag)


async def wave_fill(game, surf, font, winner, clock):
    """Победная заливка: всё поле окрашивается цветом победного хода волной по
    столбцам — слева направо (P1) или справа налево (P2), ~0.05 с/столбец."""
    color = game.cur_color[winner]
    # фанфары при победе человека, «издевательский смешок» при победе компьютера
    if game.settings["types"][winner] == 'H':
        play(_snd_win_h)
    else:
        play(_snd_win_c)
    cols = range(COLS) if winner == 0 else range(COLS - 1, -1, -1)
    for col in cols:
        for row in range(ROWS):
            game.color[col][row] = color
            game.owner[col][row] = winner
        # счёт НЕ пересчитываем: в углах остаются итоговые очки партии.
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
        redraw(surf, font, game)
        pygame.display.flip()
        await asyncio.sleep(0.05)       # ~0.05 c между столбцами (неблокирующе)


async def show_draw(game, surf, font, big, clock):
    """Окно с МИГАЮЩЕЙ надписью «Drawn!» по центру: ~2 с или до нажатия клавиши
    (по более раннему событию). Поле под окном остаётся (итоговое 224:224)."""
    start = pygame.time.get_ticks()
    while True:
        now = pygame.time.get_ticks()
        if now - start >= 2000:
            return
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or ev.type == pygame.KEYDOWN:
                return
        redraw(surf, font, game)                      # застывшее поле
        if ((now - start) // 400) % 2 == 0:           # мигание ~каждые 0.4 с
            msg = big.render("Drawn !", True, UI_YELLOW)
            pad = 28
            bw, bh = msg.get_width() + pad * 2, msg.get_height() + pad * 2
            bx, by = (SCREEN_W - bw) // 2, (SCREEN_H - bh) // 2
            pygame.draw.rect(surf, BLACK, (bx, by, bw, bh))
            pygame.draw.rect(surf, UI_YELLOW, (bx, by, bw, bh), 2)
            surf.blit(msg, (bx + pad, by + pad))
        pygame.display.flip()
        clock.tick(30)
        await asyncio.sleep(0)


async def ask_again(surf, font):
    """Спросить «Play again? (Y/N)». True — да (Y), False — нет (N/Esc/закрытие)."""
    msg = font.render("Play again ?    ( Y / N )", True, UI_YELLOW)
    pad = 24
    bw, bh = msg.get_width() + pad * 2, msg.get_height() + pad * 2
    bx, by = (SCREEN_W - bw) // 2, (SCREEN_H - bh) // 2
    pygame.draw.rect(surf, BLACK, (bx, by, bw, bh))
    pygame.draw.rect(surf, UI_YELLOW, (bx, by, bw, bh), 2)
    surf.blit(msg, (bx + pad, by + pad))
    pygame.display.flip()
    while True:
        ev = await wait_key()
        if ev.type == pygame.QUIT:
            return False
        if ev.key == pygame.K_y:
            return True
        if ev.key in (pygame.K_n, pygame.K_ESCAPE):
            return False


# ── Точка входа ──────────────────────────────────────────────────────────
def load_font(size):
    """Шрифт интерфейса. В браузере (pygbag, sys.platform=='emscripten') системных
    шрифтов нет — используем встроенный шрифт pygame. На десктопе — «Courier New»."""
    if sys.platform == "emscripten":
        return pygame.font.Font(None, size)
    try:
        f = pygame.font.SysFont("Courier New", size, bold=True)
        if f is not None:
            return f
    except Exception:
        pass
    return pygame.font.Font(None, size)


async def goodbye(surf, big):
    """Финальный экран после выхода (N на Play again / Esc на старт-экране):
    программа завершена. В браузере вкладку не закрыть — показываем сообщение."""
    surf.fill(BLACK)
    msg = big.render("Thanks for playing !", True, UI_YELLOW)
    surf.blit(msg, ((SCREEN_W - msg.get_width()) // 2, SCREEN_H // 2 - 30))
    hint = load_font(18).render("Refresh the page (F5) to play again", True, UI_GRAY)
    surf.blit(hint, ((SCREEN_W - hint.get_width()) // 2, SCREEN_H // 2 + 24))
    pygame.display.flip()
    while True:                  # удерживаем экран; новых партий не начинаем
        pygame.event.get()      # вычитываем события, чтобы вкладка не «висла»
        await asyncio.sleep(0.1)


async def web_stopped(surf, big):
    """На вебе N/Esc не завершают программу (страницу не перезагрузить без
    потери разрешения на звук) — но должна быть чёткая точка «остановки»,
    а не мгновенный проброс обратно в экран настройки игроков. Показываем
    финальное сообщение и ждём любую клавишу, чтобы вернуться в меню."""
    surf.fill(BLACK)
    msg = big.render("Thanks for playing !", True, UI_YELLOW)
    surf.blit(msg, ((SCREEN_W - msg.get_width()) // 2, SCREEN_H // 2 - 30))
    hint = load_font(18).render("Press any key to play again", True, UI_GRAY)
    surf.blit(hint, ((SCREEN_W - hint.get_width()) // 2, SCREEN_H // 2 + 24))
    pygame.display.flip()
    await wait_key()


async def main():
    # Микшер: формат задаём ДО pygame.init(); моно 16-бит, 22050 Гц.
    try:
        pygame.mixer.pre_init(SND_RATE, -16, 1)
    except Exception:
        pass
    pygame.init()
    # SCALED: SDL масштабирует кадр под окно/холст С СОХРАНЕНИЕМ ПРОПОРЦИЙ
    # (в браузере pygbag это убирает вертикальное растяжение гексов).
    try:
        surf = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED)
    except Exception:
        surf = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Filler_hex")
    init_sound()
    font = load_font(18)
    big  = load_font(30)
    clock = pygame.time.Clock()

    # Внешний цикл — стартовый экран (выбор игроков). В браузере (emscripten)
    # вкладку/страницу не перезагружаем ради повтора — это заново показывает
    # экран pygbag "click/touch page". Поэтому на вебе выход из партии/меню
    # возвращает в меню, а не завершает программу.
    is_web = sys.platform == "emscripten"

    quit_all = False
    while not quit_all:
        settings = await start_screen(surf, font, big)
        if settings is None:                  # Esc на стартовом экране — выход
            if is_web:
                await web_stopped(surf, big)
                continue
            break
        while True:                           # серия партий с этими настройками
            game = Game()
            game.settings = settings
            result = await run_game(game, surf, font, clock)
            if result == 'quit':
                break                         # Esc в партии — назад к старт-экрану
            if result == 'draw':
                await show_draw(game, surf, font, big, clock)     # ничья
            else:
                await wave_fill(game, surf, font, result, clock)  # победная заливка
            if not await ask_again(surf, font):
                if is_web:
                    await web_stopped(surf, big)
                    break                      # N — назад к старт-экрану (не выход)
                quit_all = True               # N — выход из программы
                break

    await goodbye(surf, big)                  # финальный экран, новую игру не начинаем
    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())

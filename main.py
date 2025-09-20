import os, sys, random, re
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import pygame

# ----------------- НАСТРОЙКИ -----------------
START_BANKROLL = 200
START_BET = 10
BET_STEP = 5

# Количество колод в "шве". Игнорируется, если NO_DUPLICATES=True
SHOE_DECKS = 6

# ВКЛЮЧИТЬ уникальные карты (одна колода 52 карты, без дублей)
NO_DUPLICATES = True

DEALER_STANDS_SOFT_17 = True
WIN_PAYOUT = 1.0
BLACKJACK_PAYOUT = 1.5
WINDOW_SIZE = (1280, 720)
FPS = 60

# степень затемнения фона (0.0 = нет, 1.0 = полностью чёрный)
BG_DIM_DEFAULT = 0.3
BG_DIM_STEP = 0.05

# Пути: ищем карты и в assets/cards/, и рядом с .py
ROOT = Path(__file__).parent.resolve()
CARD_SEARCH_DIRS = [ROOT / "assets" / "cards", ROOT]

# кастомный шрифт (необязательно)
CUSTOM_FONT = ROOT / "assets" / "font.ttf"

# авто-поиск фоновой текстуры
TABLE_BG = None  # путь определим автоматически
def find_table_bg() -> Optional[Path]:
    candidates = [
        ROOT / "assets" / "table_background.png",
        ROOT / "assets" / "table_background.jpg",
        ROOT / "assets" / "table_background.jpeg",
        ROOT / "assets" / "table_background.webp",
        ROOT / "table_background.png",
        ROOT / "table_background.jpg",
        ROOT / "table_background.jpeg",
        ROOT / "table_background.webp",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

WHITE=(240,240,240); GRAY=(170,170,170); GREEN=(22,90,60); GOLD=(252,186,3); BLACK=(0,0,0)

RANKS = ["A","2","3","4","5","6","7","8","9","10","J","Q","K"]
SUITS = ["S","H","D","C"]  # Spades, Hearts, Diamonds, Clubs

SUIT_FROM_WORD = {
    "spade":"S","spades":"S","spead":"S","speads":"S","s":"S",
    "heart":"H","hearts":"H","h":"H",
    "diamond":"D","diamonds":"D","d":"D",
    "club":"C","clubs":"C","c":"C",
}
RANK_FROM_WORD = {
    "a":"A","ace":"A","j":"J","jack":"J","q":"Q","queen":"Q","k":"K","king":"K",
    "t":"10","10":"10","2":"2","3":"3","4":"4","5":"5","6":"6","7":"7","8":"8","9":"9",
}
CARD_EXTS = (".png",".jpg",".jpeg",".webp")

# ----------------- ШРИФТ/ОЦЕНКА РУКИ -----------------
def load_font(size:int):
    try:
        if CUSTOM_FONT.exists():
            return pygame.font.Font(str(CUSTOM_FONT), size)
    except Exception:
        pass
    return pygame.font.SysFont("freesansbold", size)

def best_value(cards: List[str]) -> Tuple[int,bool]:
    vals=[]; aces=0
    for c in cards:
        r=c[:-1]
        if r in ("J","Q","K"): vals.append(10)
        elif r=="A": vals.append(11); aces+=1
        else: vals.append(int(r))
    total=sum(vals)
    while total>21 and aces>0:
        total-=10; aces-=1
    is_bj=(len(cards)==2 and total==21)
    return total, is_bj

# ----------------- ПАРСЕР ИМЁН ФАЙЛОВ -----------------
def parse_card_filename(name:str) -> Optional[str]:
    """
    Возвращает код 'RS' (например 'AS', 'KD') или None.
    Поддерживает:
      - rank_suit: 'K_Clubs', '10-Hearts', 'kc', 'as'
      - suit_rank: 'spades_3', 'hearts-10', 'diamonds_q', 'clubs_a'
      - опечатку: 'speads'
      - регистр/разделители не важны.
    """
    base = Path(name).stem.lower().strip()

    # 1) короткие слитные формы: 'kc', 'as', '10h'
    m = re.fullmatch(r'(10|[2-9tjqka])\s*([shdc])', base)
    if m:
        rank = RANK_FROM_WORD[m.group(1)]
        suit = SUIT_FROM_WORD[m.group(2)]
        return f"{rank}{suit}"
    # и наоборот: 's3', 'h10'
    m = re.fullmatch(r'([shdc])\s*(10|[2-9tjqka])', base)
    if m:
        suit = SUIT_FROM_WORD[m.group(1)]
        rank = RANK_FROM_WORD[m.group(2)]
        return f"{rank}{suit}"

    # 2) разбиваем по неалфанум-символам и ищем ранг/масть в любом порядке
    tokens = [t for t in re.split(r'[^a-z0-9]+', base) if t]
    rank = None
    suit = None
    for t in tokens:
        if rank is None and t in RANK_FROM_WORD:
            rank = RANK_FROM_WORD[t]
        if suit is None and t in SUIT_FROM_WORD:
            suit = SUIT_FROM_WORD[t]
    if rank and suit:
        return f"{rank}{suit}"

    # 3) попытка через «произвольный порядок слов»
    suit_pat = r'(spades?|speads?|hearts?|diamonds?|clubs?|[shdc])'
    rank_pat = r'(10|[2-9tjqka]|ace|jack|queen|king)'
    m = re.search(fr'{suit_pat}.*{rank_pat}', base)
    if not m:
        m = re.search(fr'{rank_pat}.*{suit_pat}', base)
        if not m:
            return None
        rank_raw, suit_raw = m.group(1), m.group(2)
    else:
        suit_raw, rank_raw = m.group(1), m.group(2)

    suit_raw = suit_raw[0] if suit_raw in 'shdc' else suit_raw
    rank = RANK_FROM_WORD.get(rank_raw, RANK_FROM_WORD.get(rank_raw[0], None))
    suit = SUIT_FROM_WORD.get(suit_raw, SUIT_FROM_WORD.get(suit_raw[0], None))
    if rank and suit:
        return f"{rank}{suit}"
    return None

# ----------------- КАРТИНКИ КАРТ -----------------
class CardImages:
    def __init__(self, size:Tuple[int,int]):
        self.w,self.h=size
        self.images: Dict[str, pygame.Surface] = {}
        self.back: Optional[pygame.Surface] = None
        self.missing = self._make_placeholder()

    def _make_placeholder(self):
        surf = pygame.Surface((self.w,self.h), pygame.SRCALPHA)
        surf.fill((0,0,0,0))
        pygame.draw.rect(surf, (230,230,230), (0,0,self.w,self.h), border_radius=16)
        pygame.draw.rect(surf, (100,100,100), (0,0,self.w,self.h), 3, border_radius=16)
        return surf

    def _load_scale(self, path:Path):
        img = pygame.image.load(str(path)).convert_alpha()
        return pygame.transform.smoothscale(img, (self.w,self.h))

    def load_all(self):
        # Рубашка
        self.back = None
        for base in CARD_SEARCH_DIRS:
            if not base.exists(): continue
            for f in base.iterdir():
                low = f.name.lower()
                if low.startswith("back") and low.endswith(CARD_EXTS):
                    try:
                        self.back = self._load_scale(f); break
                    except Exception: pass
            if self.back is not None: break
        if self.back is None:
            self.back = self._make_placeholder()

        # Карты
        seen=set()
        for base in CARD_SEARCH_DIRS:
            if not base.exists(): continue
            for f in base.iterdir():
                low = f.name.lower()
                if not low.endswith(CARD_EXTS): continue
                code = parse_card_filename(f.name)
                if code and code not in seen:
                    try:
                        self.images[code] = self._load_scale(f)
                        seen.add(code)
                    except Exception:
                        pass
        # Плейсхолдеры для недостающих
        for s in SUITS:
            for r in RANKS:
                self.images.setdefault(r+s, self.missing)

    def get(self, code:str) -> pygame.Surface:
        return self.images.get(code, self.missing)

# ----------------- КОЛОДА -----------------
def new_shoe() -> List[str]:
    """
    Если NO_DUPLICATES=True — создаёт одну уникальную колоду (52 карты).
    Иначе — стандартный "шов" из SHOE_DECKS колод.
    """
    if NO_DUPLICATES:
        deck = [r+s for s in SUITS for r in RANKS]  # 52 разных карт
    else:
        deck=[]
        for _ in range(SHOE_DECKS):
            for s in SUITS:
                for r in RANKS:
                    deck.append(r+s)
    random.shuffle(deck)
    return deck

# ----------------- UI -----------------
class Button:
    def __init__(self, rect, text, font, bg=(35,35,35), fg=WHITE):
        self.rect=pygame.Rect(rect); self.text=text; self.font=font
        self.bg=bg; self.fg=fg; self.enabled=True
    def draw(self, screen, hover=False):
        col = (self.bg[0]+15,self.bg[1]+15,self.bg[2]+15) if (hover and self.enabled) else self.bg
        if not self.enabled: col=(60,60,60)
        pygame.draw.rect(screen, col, self.rect, border_radius=12)
        pygame.draw.rect(screen, (255,255,255), self.rect, 2, border_radius=12)
        label=self.font.render(self.text, True, self.fg)
        screen.blit(label,(self.rect.centerx-label.get_width()//2, self.rect.centery-label.get_height()//2))
    def hit(self, pos): return self.enabled and self.rect.collidepoint(pos)

# ----------------- ИГРА -----------------
class Game:
    def __init__(self, screen):
        self.screen=screen
        self.W,self.H=self.screen.get_size()
        self.clock=pygame.time.Clock()
        self.font_big=load_font(40); self.font=load_font(26); self.font_small=load_font(20)

        # размеры карт
        self.card_h=int(self.H*0.24); self.card_w=int(self.card_h*0.7); self.card_dx=int(self.card_w*0.36)
        self.images=CardImages((self.card_w,self.card_h)); self.images.load_all()

        # фон
        self.table_bg = None
        self._raw_bg = None
        try:
            bg_path = find_table_bg()
            if bg_path:
                img = pygame.image.load(str(bg_path)).convert()
                self._raw_bg = img
                self.table_bg = pygame.transform.smoothscale(self._raw_bg, (self.W, self.H))
        except Exception:
            self.table_bg = None

        # степень затемнения
        self.bg_dim = BG_DIM_DEFAULT

        self.reset_all()

        # кнопки
        y=self.H-80; x=30; w,h=150,48
        self.btn_deal=Button((x,y,w,h),"DEAL [Space]",self.font)
        self.btn_hit=Button((x+160,y,w,h),"HIT [H]",self.font)
        self.btn_stand=Button((x+320,y,w,h),"STAND [S]",self.font)
        self.btn_double=Button((x+480,y,w,h),"DOUBLE [D]",self.font)
        self.btn_minus=Button((self.W-260,y,60,h),"−  [ [ ]",self.font)
        self.btn_plus=Button((self.W-190,y,60,h),"+  ] ]",self.font)
        self.btns=[self.btn_deal,self.btn_hit,self.btn_stand,self.btn_double,self.btn_minus,self.btn_plus]

    def _rescale_bg(self):
        if self._raw_bg is not None:
            self.table_bg = pygame.transform.smoothscale(self._raw_bg, (self.W, self.H))

    def reset_all(self):
        self.shoe=new_shoe()
        self.bankroll=START_BANKROLL
        self.bet=START_BET
        self.state="betting"
        self.player=[]; self.dealer=[]
        self.message="BET and DEAL (Space)."

    # ---- действия ----
    def _draw_from_shoe(self) -> str:
        if not self.shoe:
            # если закончились карты — перетасуем новую уникальную колоду
            self.shoe = new_shoe()
        return self.shoe.pop()

    def deal_round(self):
        if self.bet<=0 or self.bet>self.bankroll:
            self.message="Correct the bet."
            return
        self.player=[self._draw_from_shoe(), self._draw_from_shoe()]
        self.dealer=[self._draw_from_shoe(), self._draw_from_shoe()]
        self.bankroll -= self.bet
        self.state="player"; self.message="Your move."
        pv,pbj=best_value(self.player); dv,dbj=best_value(self.dealer)
        if pbj or dbj:
            self.state="resolve"; self.resolve(blackjack_check=True)

    def hit(self):
        if self.state!="player": return
        self.player.append(self._draw_from_shoe())
        pv,_=best_value(self.player)
        if pv>21:
            self.state="resolve"; self.message="Too much!"; self.resolve()

    def stand(self):
        if self.state!="player": return
        self.state="dealer"; self.dealer_play()

    def double(self):
        # Удваивает ставку, выдаёт ровно одну карту, затем автопереход к дилеру
        if self.state!="player" or len(self.player)!=2 or self.bankroll<self.bet: return
        self.bankroll -= self.bet; self.bet *= 2
        self.player.append(self._draw_from_shoe())
        pv,_=best_value(self.player)
        if pv>21:
            self.state="resolve"; self.message="Too much after Double!"; self.resolve()
        else:
            self.state="dealer"; self.dealer_play()

    def dealer_play(self):
        while True:
            dv,_=best_value(self.dealer)
            # soft 17
            total_raw=0; ace=0
            for c in self.dealer:
                r=c[:-1]
                total_raw += 11 if r=="A" else 10 if r in ("J","Q","K") else int(r)
                if r=="A": ace+=1
            while total_raw>21 and ace>0:
                total_raw-=10; ace-=1
            soft17=(total_raw==17 and any(c[:-1]=="A" for c in self.dealer))

            if dv<17 or (not DEALER_STANDS_SOFT_17 and soft17):
                self.dealer.append(self._draw_from_shoe())
            else:
                break
        self.state="resolve"; self.resolve()

    def resolve(self, blackjack_check=False):
        pv,pbj=best_value(self.player); dv,dbj=best_value(self.dealer)
        win_amt=0; msg=""
        if blackjack_check:
            if pbj and dbj: msg="push - both have Blackjack."; self.bankroll+=self.bet
            elif pbj: msg="Blackjack! Victory."; win_amt=int(self.bet*(1+BLACKJACK_PAYOUT)); self.bankroll+=win_amt
            elif dbj: msg="Blackjack at dealer. Defeat."
        else:
            if pv>21: msg="Too much. Defeat."
            elif dv>21: msg="The dealer overcharged. Victory!"; win_amt=int(self.bet*(1+WIN_PAYOUT)); self.bankroll+=win_amt
            elif pv>dv: msg="Victory!"; win_amt=int(self.bet*(1+WIN_PAYOUT)); self.bankroll+=win_amt
            elif pv<dv: msg="Defeat."
            else: msg="Push."; self.bankroll+=self.bet
        self.message = msg + "  [Space] — new deal"
        self.state="betting"; self.bet=min(self.bet, self.bankroll)

        # Перетасуем новую колоду, если карт почти не осталось
        if len(self.shoe) < 15:
            self.shoe = new_shoe()

    # ---- рендер ----
    def draw_card(self, code, x, y, face_up=True):
        img = self.images.get(code) if face_up else self.images.back
        self.screen.blit(img, (x,y))

    def draw_table(self):
        if self.table_bg: self.screen.blit(self.table_bg,(0,0))
        else: self.screen.fill(GREEN)

        # затемнение фона
        if self.bg_dim > 0:
            veil = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * self.bg_dim)))
            self.screen.blit(veil, (0, 0))

        self.screen.blit(self.font_big.render("BlackShrimp_by_PEPSI", True, WHITE),(20,16))
        self.screen.blit(self.font.render(f"Bank: {self.bankroll}", True, GOLD),(20,70))
        self.screen.blit(self.font.render(f"Bet: {self.bet}", True, WHITE),(20,102))
        self.screen.blit(self.font_small.render(self.message, True, WHITE),(20,140))

    def draw_hands(self):
        # позиции: дилер сверху, игрок снизу
        dealer_y = int(self.H * 0.10)
        player_y = int(self.H * 0.52)
        dx = self.card_dx
        px0 = self.W // 2 - max(self.card_w, dx) * 2

        # --- игрок ---
        for i, c in enumerate(self.player):
            self.draw_card(c, px0 + i * dx, player_y, True)
        pv, _ = best_value(self.player)
        self.screen.blit(self.font.render(f"Your hand: {pv}", True, GOLD), (px0, player_y - 28))

        # --- дилер ---
        for i, c in enumerate(self.dealer):
            # во время хода игрока: первая карта закрыта, остальные открыты
            if self.state == "player":
                face = (i > 0)
            else:
                face = True
            self.draw_card(c, px0 + i * dx, dealer_y, face)

        if self.state == "player" and len(self.dealer) >= 2:
            dealer_text = "??"
        else:
            dv, _ = best_value(self.dealer)
            dealer_text = str(dv)
        self.screen.blit(self.font.render(f"Dealer: {dealer_text}", True, GOLD), (px0, dealer_y - 28))

    def draw_buttons(self):
        betting=(self.state=="betting"); playing=(self.state=="player")
        self.btn_deal.enabled=betting and self.bet>0 and self.bankroll>=self.bet
        self.btn_hit.enabled=playing
        self.btn_stand.enabled=playing
        self.btn_double.enabled=playing and len(self.player)==2 and self.bankroll>=self.bet
        self.btn_minus.enabled=betting and self.bet>0
        self.btn_plus.enabled=betting and self.bankroll>0
        mouse=pygame.mouse.get_pos()
        for b in self.btns: b.draw(self.screen, b.hit(mouse))

    def run(self):
        running=True; fullscreen=False
        while running:
            _dt=self.clock.tick(FPS)/1000.0
            for e in pygame.event.get():
                if e.type==pygame.QUIT: running=False
                elif e.type==pygame.KEYDOWN:
                    if e.key==pygame.K_ESCAPE: running=False
                    if e.key==pygame.K_F11:
                        fullscreen=not fullscreen
                        pygame.display.set_mode((0,0), pygame.FULLSCREEN) if fullscreen else pygame.display.set_mode(WINDOW_SIZE)
                        self.screen=pygame.display.get_surface()
                        self.W, self.H = self.screen.get_size()
                        self._rescale_bg()
                        continue
                    if e.key==pygame.K_SPACE and self.state=="betting": self.deal_round()
                    if e.key==pygame.K_h and self.state=="player": self.hit()
                    if e.key==pygame.K_s and self.state=="player": self.stand()
                    if e.key==pygame.K_d and self.state=="player": self.double()
                    if e.key==pygame.K_LEFTBRACKET and self.state=="betting": self.bet=max(0,self.bet-BET_STEP)
                    if e.key==pygame.K_RIGHTBRACKET and self.state=="betting": self.bet=min(self.bankroll,self.bet+BET_STEP)
                    # регулятор затемнения
                    if e.key == pygame.K_MINUS:
                        self.bg_dim = max(0.0, round(self.bg_dim - BG_DIM_STEP, 2))
                    if e.key in (pygame.K_EQUALS, pygame.K_PLUS):
                        self.bg_dim = min(1.0, round(self.bg_dim + BG_DIM_STEP, 2))

                elif e.type==pygame.MOUSEBUTTONDOWN and e.button==1:
                    pos=e.pos
                    if self.btn_deal.hit(pos): self.deal_round()
                    elif self.btn_hit.hit(pos): self.hit()
                    elif self.btn_stand.hit(pos): self.stand()
                    elif self.btn_double.hit(pos): self.double()
                    elif self.btn_minus.hit(pos) and self.state=="betting": self.bet=max(0,self.bet-BET_STEP)
                    elif self.btn_plus.hit(pos) and self.state=="betting": self.bet=min(self.bankroll,self.bet+BET_STEP)

            self.draw_table(); self.draw_hands(); self.draw_buttons()
            pygame.display.flip()
        pygame.quit(); sys.exit()

# ----------------- ENTRY -----------------
def main():
    pygame.init()
    pygame.display.set_caption("Blackjack — custom art (auto-load)")
    pygame.display.set_mode(WINDOW_SIZE)
    Game(pygame.display.get_surface()).run()

if __name__ == "__main__":
    main()

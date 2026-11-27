import json
import re
import time
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

CABECALHOS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MAX_PAGINAS = 30
RE_ANO = re.compile(r"\b(?:19|20)\d{2}\b")
RE_ANO_PAR = re.compile(r"\b(?:19|20)\d{2}\s*/\s*((?:19|20)\d{2})\b")

MARCAS = ["Chevrolet", "GM", "Volkswagen", "VW", "Fiat", "Ford", "Honda",
          "Hyundai", "Toyota", "Renault", "Jeep", "Nissan", "Peugeot",
          "Citroen", "Citroën", "BMW", "Audi", "Mercedes-Benz", "Mercedes",
          "Mitsubishi", "Kia", "Volvo", "Land Rover", "Suzuki", "Kawasaki",
          "Yamaha", "Chrysler", "Dodge", "Ssangyong", "Mini", "JAC", "Chery",
          "BYD", "Ram", "Porsche", "Lexus", "Subaru", "Troller"]
RE_MARCA = re.compile(
    r"(?<!\w)(" + "|".join(sorted(MARCAS, key=len, reverse=True)) + r")(?!\w)",
    re.I)

CORES = ["Branco", "Branca", "Preto", "Preta", "Prata", "Prateado", "Prateada",
         "Cinza", "Vermelho", "Vermelha", "Azul", "Verde", "Amarelo", "Amarela",
         "Laranja", "Marrom", "Bege", "Dourado", "Dourada", "Vinho", "Grafite",
         "Bordô", "Roxo", "Rosa", "Champagne", "Chumbo"]
RE_COR = re.compile(
    r"(?<![A-Za-zÀ-ÿ])(" + "|".join(sorted(CORES, key=len, reverse=True)) + r")(?![A-Za-zÀ-ÿ])",
    re.I)

RE_CLASSE_MODELO = re.compile(r"model", re.I)
RE_CLASSE_ANO = re.compile(r"year|(?<![a-z])ano(?![a-z])", re.I)
RE_CLASSE_COR = re.compile(r"(?<![a-z])(cor|color|colour)(?![a-z])", re.I)
RE_PRECO = re.compile(r"R\$\s*([\d.]+(?:,\d{2})?)")


def formatar_preco(v):
    s = str(v).strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        n = float(s)
    except ValueError:
        return ""
    if n <= 0:
        return ""
    return "R$ " + f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def achar_cor(card, texto):
    """Procura a cor: primeiro nos blocos marcados como 'cor', depois no texto todo."""
    for el in card.find_all(class_=RE_CLASSE_COR):
        m = RE_COR.search(el.get_text(" ", strip=True))
        if m:
            return m.group(1).capitalize()
    m = RE_COR.search(texto)
    return m.group(1).capitalize() if m else ""


# ---------------------------------------------------------------
# Leitura pelos links/cards do HTML
# ---------------------------------------------------------------
def url_limpa(href, base):
    if not href or href.startswith(("#", "javascript:", "tel:", "mailto:")):
        return None
    u = urlparse(urljoin(base, href))
    if u.netloc != urlparse(base).netloc:
        return None
    return f"{u.scheme}://{u.netloc}{u.path}"


def chave(url):
    partes = [p for p in urlparse(url).path.strip("/").split("/") if p]
    return (partes[0] if len(partes) >= 2 else "", len(partes))


def achar_card(link, k, base):
    alvo = url_limpa(link["href"], base)
    card = link
    while card.parent is not None and card.parent.name not in ("body", "html"):
        vizinhos = set()
        for a in card.parent.find_all("a", href=True):
            u = url_limpa(a["href"], base)
            if u and chave(u) == k:
                vizinhos.add(u)
        if vizinhos != {alvo}:
            break
        card = card.parent
    return card


def extrair_veiculos(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    por_chave = {}
    for a in soup.find_all("a", href=True):
        u = url_limpa(a["href"], base_url)
        if u:
            por_chave.setdefault(chave(u), {}).setdefault(u, a)

    melhores = []
    for k, urls in por_chave.items():
        if len(urls) < 2:
            continue
        achados = []
        for u, a in urls.items():
            card = achar_card(a, k, base_url)
            texto = card.get_text(" ", strip=True)
            if RE_ANO.search(texto) and ("R$" in texto or "km" in texto.lower()):
                achados.append((u, a, card))
        if len(achados) > len(melhores):
            melhores = achados

    veiculos = {}
    for u, a, card in melhores:
        texto = card.get_text(" ", strip=True)
        cab = card.find(["h1", "h2", "h3", "h4"])
        img = card.find("img", alt=True)
        titulo = ((cab.get_text(" ", strip=True) if cab else "")
                  or a.get("title", "") or a.get_text(" ", strip=True)
                  or (img["alt"] if img else "")).strip()

        # alguns sites separam a marca (título) do modelo (outro bloco)
        el_modelo = card.find(class_=RE_CLASSE_MODELO)
        if el_modelo:
            texto_modelo = el_modelo.get_text(" ", strip=True)
            if texto_modelo and texto_modelo.lower() not in titulo.lower():
                titulo = f"{titulo} {texto_modelo}".strip()

        # ano: prefere o bloco marcado como "ano"
        ano = ""
        el_ano = card.find(class_=RE_CLASSE_ANO)
        if el_ano:
            m = RE_ANO.search(el_ano.get_text(" ", strip=True))
            ano = m.group(0) if m else ""
        if not ano:
            m = RE_ANO_PAR.search(texto)
            ano = m.group(1) if m else (RE_ANO.search(texto) or [""])[0]

        mm = RE_MARCA.search(titulo) or RE_MARCA.search(texto)
        km = re.search(r"([\d.]+)\s*km", texto, re.I)
        mp = RE_PRECO.search(texto)
        preco = f"R$ {mp.group(1)}" if mp else ""
        veiculos[u] = {
            "marca": mm.group(1) if mm else "",
            "titulo": titulo,
            "ano": ano,
            "km": km.group(1) if km else "",
            "cor": achar_cor(card, texto),
            "preco": preco,
            "link": u,
            "card_html": str(card)[:4000],
        }
    return veiculos


# ---------------------------------------------------------------
# Leitura por dados JSON (sites que carregam por JavaScript)
# ---------------------------------------------------------------
CHAVES_MODELO = {"modelo", "veiculo", "model", "nome", "titulo", "title"}
CHAVES_ANO = {"ano", "year", "ano_modelo", "anomodelo"}


def parece_veiculo(d):
    chaves = {str(k).lower() for k in d}
    return bool(chaves & CHAVES_MODELO) and bool(chaves & CHAVES_ANO)


def achar_lista_json(obj, nivel=0):
    """Procura a maior lista de itens com cara de veículo dentro de um JSON."""
    melhor = []
    if nivel > 6:
        return melhor
    if isinstance(obj, list):
        amostra = obj[:5]
        if (len(obj) >= 2 and all(isinstance(x, dict) for x in amostra)
                and all(parece_veiculo(x) for x in amostra)):
            melhor = obj
        for x in obj[:20]:
            if isinstance(x, (list, dict)):
                sub = achar_lista_json(x, nivel + 1)
                if len(sub) > len(melhor):
                    melhor = sub
    elif isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, (list, dict)):
                sub = achar_lista_json(v, nivel + 1)
                if len(sub) > len(melhor):
                    melhor = sub
    return melhor


def pegar(item, nomes):
    baixo = {str(k).lower(): v for k, v in item.items()}
    for n in nomes:
        v = baixo.get(n)
        if v not in (None, "") and not isinstance(v, (list, dict)):
            return str(v).strip()
    return ""


def veiculos_do_json(lista):
    saida = {}
    for i, it in enumerate(lista):
        if not isinstance(it, dict):
            continue
        cod = pegar(it, ["cod_veiculo", "id", "codigo"]) or str(i)
        saida[cod] = {
            "marca": pegar(it, ["marca", "brand", "make"]),
            "titulo": pegar(it, ["veiculo", "modelo", "model", "nome", "titulo", "title"]),
            "ano": pegar(it, ["ano", "year", "ano_modelo", "anomodelo"]),
            "km": pegar(it, ["km", "quilometragem", "kilometragem", "mileage"]),
            "cor": pegar(it, ["cor", "color", "colour", "cor_veiculo", "corveiculo"]),
            "preco": (formatar_preco(pegar(it, ["valor_oferta"]))
                      or formatar_preco(pegar(it, ["valor", "preco", "price"]))),
            "link": cod,
            "card_html": "",
        }
    return saida


# ---------------------------------------------------------------
# Paginação e download
# ---------------------------------------------------------------
def descobrir_paginacao(html):
    for href in re.findall(r'href=["\']([^"\']+)["\']', html):
        m = re.search(r"[?&;](page|pagina|pg|paged|p)=\d+", href)
        if m:
            return ("query", m.group(1))
        m = re.search(r"/(page|pagina|pg)/\d+", href)
        if m:
            return ("path", m.group(1))
    return ("query", "page")


def url_da_pagina(url, pagina, estilo):
    tipo, nome = estilo
    if tipo == "path":
        return url.rstrip("/") + f"/{nome}/{pagina}"
    partes = urlparse(url)
    q = dict(parse_qsl(partes.query))
    q[nome] = pagina
    return urlunparse(partes._replace(query=urlencode(q)))


def baixar_html(alvo):
    resp = requests.get(alvo, headers=CABECALHOS, timeout=30)
    resp.raise_for_status()
    return resp.text


class Navegador:
    """Abre a página num navegador invisível (para sites que carregam por JavaScript)."""

    def __init__(self):
        self.p = None
        self.nav = None
        self.jsons = []

    def _guardar(self, resp):
        try:
            if "json" in resp.headers.get("content-type", ""):
                self.jsons.append(json.loads(resp.text()))
        except Exception:
            pass

    def html(self, alvo):
        if self.nav is None:
            from playwright.sync_api import sync_playwright
            self.p = sync_playwright().start()
            self.nav = self.p.chromium.launch(headless=True)
        self.jsons = []
        pagina = self.nav.new_page(viewport={"width": 1280, "height": 900})
        pagina.on("response", self._guardar)
        try:
            pagina.goto(alvo, wait_until="domcontentloaded", timeout=60000)
            try:
                pagina.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            for _ in range(8):  # rola a página para carregar itens "preguiçosos"
                pagina.mouse.wheel(0, 5000)
                pagina.wait_for_timeout(400)
            return pagina.content()
        finally:
            pagina.close()

    def fechar(self):
        try:
            if self.nav:
                self.nav.close()
            if self.p:
                self.p.stop()
        except Exception:
            pass


# ---------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------
def coletar_estoque_loja(url):
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    todos = {}
    estilo = None
    usar_navegador = False
    navegador = Navegador()
    try:
        for pagina in range(1, MAX_PAGINAS + 1):
            alvo = url if pagina == 1 else url_da_pagina(url, pagina, estilo)
            html = navegador.html(alvo) if usar_navegador else baixar_html(alvo)
            da_pagina = extrair_veiculos(html, alvo)

            if pagina == 1 and not da_pagina and not usar_navegador:
                print("Nenhum veículo no HTML simples. Tentando com navegador "
                      "(o site deve carregar por JavaScript)...")
                try:
                    usar_navegador = True
                    html = navegador.html(alvo)
                    da_pagina = extrair_veiculos(html, alvo)
                except Exception as e:
                    print("Não foi possível usar o navegador:", e)
                    print("Instale com: pip install playwright  e  "
                          "python -m playwright install chromium")
                    break

            if pagina == 1:
                nome_arq = "debug_" + urlparse(url).netloc.replace(".", "_") + ".html"
                with open(nome_arq, "w", encoding="utf-8") as f:
                    f.write(html)
                estilo = descobrir_paginacao(html)

            if usar_navegador:
                melhor = []
                for obj in navegador.jsons:
                    sub = achar_lista_json(obj)
                    if len(sub) > len(melhor):
                        melhor = sub
                if len(melhor) >= 2:
                    todos = veiculos_do_json(melhor)
                    print(f"Estoque lido direto dos dados do site: {len(todos)} veículos")
                    break

            novos = {k: v for k, v in da_pagina.items() if k not in todos}
            print(f"Página {pagina}: {len(da_pagina)} veículos ({len(novos)} novos)")
            if not novos:
                break
            todos.update(novos)
            time.sleep(0.5)
    finally:
        navegador.fechar()

    if not todos:
        print("\nNão consegui reconhecer os veículos neste site.")
        print("Veja o arquivo debug_*.html criado nesta pasta.")
    return list(todos.values())


if __name__ == "__main__":
    link = input("Link do estoque da loja: ").strip()
    if not link:
        link = "https://jjveiculossc.com.br/estoque"
    lista = coletar_estoque_loja(link)
    print(f"\nTOTAL: {len(lista)} veículos\n")
    for v in lista:
        print(f"- {v['marca']} | {v['titulo']} | {v['ano']} | {v['km']} km | "
              f"{v['cor'] or 'cor ?'} | {v['preco']}")
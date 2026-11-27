import re
import unicodedata
from difflib import SequenceMatcher

# ---------------------------------------------------------------
# AJUSTES (pode mexer aqui)
# ---------------------------------------------------------------
TOL_KM = 3000           # diferença de km aceita entre loja e Autocarro
FILTRO_ESTRITO = False  # False: KM/cor só ajudam a escolher o par certo e geram aviso
                        # True : KM/cor diferentes => NÃO é o mesmo veículo

MARCAS = ["fiat", "ford", "honda", "hyundai", "toyota", "renault", "jeep",
          "nissan", "peugeot", "citroen", "bmw", "audi", "mitsubishi", "kia",
          "volvo", "suzuki", "kawasaki", "yamaha", "chrysler", "dodge",
          "ssangyong", "mini", "jac", "chery", "byd", "ram", "porsche",
          "lexus", "subaru", "troller", "landrover", "volkswagen",
          "chevrolet", "mercedes"]
ALIAS_MARCAS = {m: m for m in MARCAS}
ALIAS_MARCAS.update({"vw": "volkswagen", "gm": "chevrolet", "chevy": "chevrolet",
                     "mercedesbenz": "mercedes", "benz": "mercedes"})

# marcas que aparecem com nomes diferentes de um lado e do outro
GRUPOS_MARCAS = [{"dodge", "ram"}]


def marcas_compativeis(x, y):
    if not x or not y or x == y:
        return True
    return any(x in g and y in g for g in GRUPOS_MARCAS)


ALIAS_COR = {"branca": "branco", "preta": "preto", "vermelha": "vermelho",
             "amarela": "amarelo", "dourada": "dourado", "prateado": "prata",
             "prateada": "prata", "cinzenta": "cinza", "bordo": "vinho"}

# cores que às vezes vêm coladas no nome (ex.: "WEEKENDPRATA")
CORES_TITULO = {"prata", "branco", "branca", "preto", "preta", "cinza", "vermelho",
                "vermelha", "azul", "verde", "amarelo", "amarela", "vinho",
                "dourado", "dourada", "bege", "marrom", "laranja", "grafite"}

RUIDO = {"flex", "gasolina", "diesel", "alcool", "etanol", "aut", "auto",
         "automatico", "automatica", "manual", "mec", "mecanico", "mecanica",
         "cvt", "dsg", "tiptronic", "awd", "turbo", "biturbo", "bi", "tsi",
         "tfsi", "tdi", "tb", "mt", "at", "portas", "porta", "v6", "v8",
         "cv", "hp", "mpi", "mpfi", "vvt", "gdi", "tce", "tdci"} | CORES_TITULO

PREFIXO_QUASE = "PROVÁVEL MESMO CARRO (confira)"
RE_RUIDO = re.compile(r"\d+v|\d+cv|\d+p|\d+x\d+")
RE_ANO = re.compile(r"(?:19|20)\d{2}")


def normalizar_texto(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("land rover", "landrover")
    s = s.replace("mercedes-benz", "mercedes").replace("mercedes benz", "mercedes")
    s = re.sub(r"\s+-\s+", " ", s)           # " - " vira separador
    s = re.sub(r"(?<=\w)-(?=\w)", "", s)     # t-cross -> tcross
    s = re.sub(r"[^a-z0-9.\s]", " ", s)      # tira símbolos
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)  # ponto só fica entre números (2.0)
    s = re.sub(r"(?<=[a-z])(?=\d\.\d)", " ", s)  # palio1.8 -> palio 1.8
    return s


def normalizar_cor(c):
    t = normalizar_texto(str(c or "")).strip()
    return ALIAS_COR.get(t, t)


def km_numero(v):
    """'111.000' ou '111000 km' -> 111000 (ou None se não houver km)."""
    t = re.sub(r"\D", "", str(v.get("km", "")))
    return int(t) if t else None


def extrair_ano(v):
    achados = RE_ANO.findall(str(v.get("ano", ""))) or RE_ANO.findall(v.get("titulo", ""))
    return achados[-1] if achados else ""   # "2021/2022" -> 2022


def tem_digito(t):
    return any(c.isdigit() for c in t)


def preparar(v):
    tokens = normalizar_texto(f"{v.get('marca', '')} {v.get('titulo', '')}").split()
    marca = ""
    palavras = []
    for t in tokens:
        if t in ALIAS_MARCAS:
            marca = marca or ALIAS_MARCAS[t]
            continue
        if RE_ANO.fullmatch(t) or re.fullmatch(r"\d+\.\d+", t):
            continue
        for c in CORES_TITULO:                       # "weekendprata" -> "weekend"
            if t.endswith(c) and len(t) - len(c) >= 4:
                t = t[: -len(c)]
                break
        if t in RUIDO or RE_RUIDO.fullmatch(t):
            continue
        t = t.strip(".")
        if not t:
            continue
        if t in palavras or (len(t) >= 4 and t in "".join(palavras)):   # repetido ("500F 500F")
            continue
        palavras.append(t)

    # núcleo = modelo (ex.: "cb 500 f", "cg 160", "onix", "t-cross")
    nucleo, i = [], 0
    if palavras:
        nucleo.append(palavras[0])
        i = 1
        while i < len(palavras) and len(nucleo) < 4:
            t = palavras[i]
            if tem_digito(t) and len(t) <= 5:
                nucleo.append(t)
            elif tem_digito(nucleo[-1]) and t.isalpha() and len(t) <= 2:
                nucleo.append(t)
            else:
                break
            i += 1
    versao = {t for t in palavras[i:] if not t.isdigit() and len(t) >= 2}
    return {"marca": marca, "ano": extrair_ano(v), "nucleo": nucleo, "versao": versao,
            "km": km_numero(v), "cor": normalizar_cor(v.get("cor", "")),
            "preco": preco_numero(v)}


def nucleo_compativel(a, b):
    if not a or not b:
        return False
    ja, jb = "".join(a), "".join(b)
    if ja == jb:
        return True
    n = min(len(a), len(b))
    if a[:n] == b[:n]:                 # um núcleo é o começo do outro
        return True
    if len(a) == 1 and len(b) == 1 and min(len(ja), len(jb)) >= 5:
        return SequenceMatcher(None, ja, jb).ratio() >= 0.88   # erro de digitação
    return False


def parecidos(x, y):
    if x == y:
        return True
    if min(len(x), len(y)) >= 3 and (x.startswith(y) or y.startswith(x)):
        return True
    return min(len(x), len(y)) >= 4 and (x in y or y in x)


def contar_parecidos(A, B):
    return sum(1 for a in A if any(parecidos(a, b) for b in B))


def pontuar(a, b):
    """0 = não é o mesmo veículo. Quanto maior, mais parecido."""
    if not a["ano"] or a["ano"] != b["ano"]:
        return 0
    if not marcas_compativeis(a["marca"], b["marca"]):
        return 0

    if FILTRO_ESTRITO:
        if a["cor"] and b["cor"] and a["cor"] != b["cor"]:
            return 0
        if (a["km"] is not None and b["km"] is not None
                and abs(a["km"] - b["km"]) > TOL_KM):
            return 0

    va, vb = a["versao"], b["versao"]
    if nucleo_compativel(a["nucleo"], b["nucleo"]):
        if va and vb:
            comuns = contar_parecidos(va, vb)
            if comuns == 0:            # mesmo modelo, versões totalmente diferentes
                return 0
            return 2 + comuns / min(len(va), len(vb))
        return 2
    # plano B: nome escrito em outra ordem ou muito abreviado
    if a["nucleo"] and b["nucleo"] and a["nucleo"][0] == b["nucleo"][0]:
        return 0                       # mesmo modelo-base mas núcleo diferente (ex.: CB 500F x CB 500X)
    ta, tb = set(a["nucleo"]) | va, set(b["nucleo"]) | vb
    menor = min(len(ta), len(tb))
    comuns = contar_parecidos(ta, tb)
    if menor and comuns >= 2 and comuns / menor >= 0.6:
        return 1 + comuns / menor
    return 0


def pontuar_aproximado(a, b):
    """2ª passada (só nas sobras): aceita ano com 1 de diferença e nome mais solto.
    KM parecido + mesma cor funcionam como PROVA EXTRA de que é o mesmo carro.
    0 = não parece o mesmo veículo. Marca incompatível continua eliminando."""
    if not a["ano"] or not b["ano"]:
        return 0
    dano = abs(int(a["ano"]) - int(b["ano"]))
    if dano > 1:
        return 0
    if not marcas_compativeis(a["marca"], b["marca"]):
        return 0
    if not a["nucleo"] or not b["nucleo"]:
        return 0

    cor_ok = bool(a["cor"] and b["cor"] and a["cor"] == b["cor"])
    km_ok = (a["km"] is not None and b["km"] is not None
             and abs(a["km"] - b["km"]) <= TOL_KM)
    preco_ok = (a["preco"] is not None and b["preco"] is not None
                and a["preco"] == b["preco"])
    # prova forte: cor + KM, ou preço igual junto com cor ou KM
    forte = (cor_ok and km_ok) or (preco_ok and (cor_ok or km_ok))
    bonus = (0.5 if cor_ok else 0) + (0.5 if km_ok else 0) + (0.5 if preco_ok else 0)

    va, vb = a["versao"], b["versao"]
    ta, tb = set(a["nucleo"]) | va, set(b["nucleo"]) | vb
    if nucleo_compativel(a["nucleo"], b["nucleo"]):
        if va and vb:
            comuns = contar_parecidos(va, vb)
            if comuns == 0:
                if not forte:          # versões diferentes: só aceita com prova forte
                    return 0
                pontos = 1.5
            else:
                pontos = 2 + comuns / min(len(va), len(vb))
        else:
            pontos = 2
    else:
        if a["nucleo"][0] == b["nucleo"][0]:
            return 0                   # ex.: CB 500F x CB 500X
        menor = min(len(ta), len(tb))
        comuns = contar_parecidos(ta, tb)
        if menor and comuns >= 2 and comuns / menor >= 0.5:
            pontos = 1 + comuns / menor
        elif forte and comuns >= 1:    # nome fraco, mas cor + KM + ano batem
            pontos = 1
        else:
            return 0
    return pontos + bonus - 0.5 * dano  # mesmo ano ganha de ano diferente


def motivo_quase(l, a):
    al, aa = extrair_ano(l), extrair_ano(a)
    if al != aa:
        motivo = f"ano diferente (loja {al} x Autocarro {aa})"
    else:
        motivo = "nome escrito de forma diferente"
    batem = []
    cl, ca = normalizar_cor(l.get("cor", "")), normalizar_cor(a.get("cor", ""))
    if cl and cl == ca:
        batem.append("mesma cor")
    kl, ka = km_numero(l), km_numero(a)
    if kl is not None and ka is not None and abs(kl - ka) <= TOL_KM:
        batem.append("KM parecido")
    pl, pa = preco_numero(l), preco_numero(a)
    if pl is not None and pa is not None and pl == pa:
        batem.append("mesmo preço")
    titulo_a = " ".join(a.get("titulo", "").split())
    texto = f"{PREFIXO_QUASE}: {motivo}. Autocarro: {titulo_a}"
    if batem:
        texto += f"  [batem: {', '.join(batem)}]"
    return texto


def mesmos_dados(a, b):
    """ANO + KM + COR + PREÇO iguais (e marca compatível) = é o mesmo veículo,
    mesmo que o nome esteja escrito de outro jeito."""
    if not a["ano"] or a["ano"] != b["ano"]:
        return False
    if not marcas_compativeis(a["marca"], b["marca"]):
        return False
    if not (a["cor"] and a["cor"] == b["cor"]):
        return False
    if a["km"] is None or b["km"] is None or abs(a["km"] - b["km"]) > TOL_KM:
        return False
    return a["preco"] is not None and a["preco"] == b["preco"]


def preco_numero(v):
    """'R$ 52.900,00' -> 52900.0 (ou None se não houver preço)."""
    t = re.sub(r"[^\d,]", "", str(v.get("preco", "")))
    try:
        return float(t.replace(",", ".")) if t else None
    except ValueError:
        return None


def diferenca_preco(x, y):
    px, py = preco_numero(x), preco_numero(y)
    return abs(px - py) if px is not None and py is not None else 0


def desempate(a, b, va, vb):
    """Quando há carros repetidos (mesmo modelo/ano): prefere mesma cor,
    depois km mais próximo, depois preço mais próximo."""
    cor_igual = 1 if a["cor"] and a["cor"] == b["cor"] else 0
    if a["km"] is not None and b["km"] is not None:
        dkm = abs(a["km"] - b["km"])
    else:
        dkm = 10 ** 9
    return (cor_igual, -dkm, -diferenca_preco(va, vb))


def _milhar(n):
    return f"{n:,}".replace(",", ".")


def divergencias(l, a):
    """Avisos sobre um par já casado (km ou cor diferentes)."""
    msgs = []
    kl, ka = km_numero(l), km_numero(a)
    if kl is not None and ka is not None and abs(kl - ka) > TOL_KM:
        msgs.append(f"KM diferente: loja {_milhar(kl)} x Autocarro {_milhar(ka)}")
    cl, ca = normalizar_cor(l.get("cor", "")), normalizar_cor(a.get("cor", ""))
    if cl and ca and cl != ca:
        msgs.append(f"Cor diferente: loja {l.get('cor')} x Autocarro {a.get('cor')}")
    return msgs


def filtrar(lista, cor="", km_min=None, km_max=None):
    """Mantém só os veículos da cor / faixa de km pedida.
    Se há filtro de km e o veículo não tem km informado, ele fica de fora."""
    cor = normalizar_cor(cor)
    saida = []
    for v in lista:
        if cor and normalizar_cor(v.get("cor", "")) != cor:
            continue
        km = km_numero(v)
        if km_min is not None or km_max is not None:
            if km is None:
                continue
            if km_min is not None and km < km_min:
                continue
            if km_max is not None and km > km_max:
                continue
        saida.append(v)
    return saida


def comparar(loja, autocarro):
    L = [preparar(v) for v in loja]
    A = [preparar(v) for v in autocarro]
    pares = []
    for i, l in enumerate(L):
        for j, a in enumerate(A):
            s = pontuar(l, a)
            if s > 0:
                pares.append((s,) + desempate(l, a, loja[i], autocarro[j]) + (i, j))
    pares.sort(reverse=True)

    usados_l, usados_a, em_ambos, divergentes = set(), set(), [], []
    for p in pares:                       # cada veículo só casa uma vez
        i, j = p[-2], p[-1]
        if i in usados_l or j in usados_a:
            continue
        usados_l.add(i)
        usados_a.add(j)
        em_ambos.append((loja[i], autocarro[j]))
        msgs = divergencias(loja[i], autocarro[j])
        if msgs:
            divergentes.append((loja[i], autocarro[j], msgs))

    # passada por DADOS: ano + KM + cor + preço iguais = mesmo carro (nome diferente)
    cand = []
    for i, l in enumerate(L):
        if i in usados_l:
            continue
        for j, a in enumerate(A):
            if j not in usados_a and mesmos_dados(l, a):
                cand.append((abs(l["km"] - a["km"]), i, j))
    cand.sort()
    por_dados = []
    for _, i, j in cand:
        if i in usados_l or j in usados_a:
            continue
        usados_l.add(i)
        usados_a.add(j)
        em_ambos.append((loja[i], autocarro[j]))
        por_dados.append((loja[i], autocarro[j]))

    # última passada: sobras que provavelmente são o mesmo carro (ano +-1, nome parecido)
    pares2 = []
    for i, l in enumerate(L):
        if i in usados_l:
            continue
        for j, a in enumerate(A):
            if j in usados_a:
                continue
            s = pontuar_aproximado(l, a)
            if s > 0:
                pares2.append((s,) + desempate(l, a, loja[i], autocarro[j]) + (i, j))
    pares2.sort(reverse=True)

    quase_iguais = []
    for p in pares2:
        i, j = p[-2], p[-1]
        if i in usados_l or j in usados_a:
            continue
        usados_l.add(i)
        usados_a.add(j)
        msgs = [motivo_quase(loja[i], autocarro[j])] + divergencias(loja[i], autocarro[j])
        quase_iguais.append((loja[i], autocarro[j], msgs))
        divergentes.append((loja[i], autocarro[j], msgs))   # a tela atual já mostra esta lista

    return {
        "qtd_loja": len(loja),
        "qtd_autocarro": len(autocarro),
        "so_loja": [v for i, v in enumerate(loja) if i not in usados_l],
        "so_autocarro": [v for j, v in enumerate(autocarro) if j not in usados_a],
        "em_ambos": em_ambos,
        "divergentes": divergentes,
        "quase_iguais": quase_iguais,
        "por_dados": por_dados,
    }


def nome(v):
    marca = v.get("marca", "")
    titulo = " ".join(v.get("titulo", "").split())
    if marca and marca.lower() in titulo.lower():
        marca = ""
    base = " ".join(x for x in [marca, titulo, str(v.get("ano", ""))] if x)
    extras = []
    km = km_numero(v)
    if km is not None:
        extras.append(f"{_milhar(km)} km")
    if v.get("cor"):
        extras.append(str(v["cor"]).title())
    if extras:
        base += "  |  " + "  |  ".join(extras)
    preco = v.get("preco", "")
    return f"{base}  -  {preco}" if preco else base


def mostrar_resultado(r):
    print("=== RESULTADO ===")
    print(f"Autocarro: {r['qtd_autocarro']} veículos")
    print(f"Loja: {r['qtd_loja']} veículos")
    dif = abs(r["qtd_autocarro"] - r["qtd_loja"])
    if not r["so_loja"] and not r["so_autocarro"]:
        if r.get("quase_iguais"):
            print(f"[OK] Os estoques batem, com {len(r['quase_iguais'])} carro(s) para você conferir.")
        else:
            print("[OK] Os estoques são iguais.")
    else:
        print(f"[DIFERENTE] Diferença de quantidade: {dif} veículo(s)")
    print("\nEstão no AUTOCARRO, mas não estão na LOJA:")
    for v in r["so_autocarro"]:
        print("  *", nome(v))
    if not r["so_autocarro"]:
        print("  (nenhum)")
    print("\nEstão na LOJA, mas não estão no AUTOCARRO:")
    for v in r["so_loja"]:
        print("  *", nome(v))
    if not r["so_loja"]:
        print("  (nenhum)")
    if r.get("quase_iguais"):
        print("\nProvavelmente o MESMO carro (nome ou ano diferente) - confira:")
        for l, a, msgs in r["quase_iguais"]:
            print("  * Loja:     ", nome(l))
            print("    Autocarro:", nome(a))
    print("\nEncontrados nos dois estoques:")
    for l, a in r["em_ambos"]:
        print("  *", nome(l))
    if r.get("por_dados"):
        print("\nDestes, reconhecidos pelos dados (ANO, KM, COR e PREÇO iguais; nome diferente):")
        for l, a in r["por_dados"]:
            print("  * Loja:     ", nome(l))
            print("    Autocarro:", nome(a))
    reais = [d for d in r["divergentes"] if not d[2][0].startswith(PREFIXO_QUASE)]
    if reais:
        print("\nNos dois, mas com KM/cor diferentes:")
        for l, a, msgs in reais:
            print("  *", nome(l).split("  -  ")[0])
            for m in msgs:
                print("      ", m)


if __name__ == "__main__":
    loja = [
        {"marca": "Volkswagen", "titulo": "T-Cross 1.0 200 TSI", "ano": "2022", "km": "30.000", "cor": "Branca"},
        {"marca": "Fiat", "titulo": "Toro Freedom 1.3 Turbo Flex", "ano": "2020", "km": "60.000", "cor": "Preta"},
        {"marca": "Hyundai", "titulo": "HB20 1.0 Comfort", "ano": "2022", "km": "25.000", "cor": "Prata"},
        {"marca": "GM - Chevrolet", "titulo": "Onix 1.0 LT", "ano": "2015", "km": "111.000", "cor": "Preta"},
        {"marca": "GM - Chevrolet", "titulo": "Onix 1.0 LT", "ano": "2015", "km": "80.000", "cor": "Branca"},
        {"marca": "Fiat", "titulo": "Palio Weekend Adventure LOCKER 1.8 Flex", "ano": "2012/2013", "km": "90.000", "cor": "Prata"},
        {"marca": "Fiat", "titulo": "Uno Way 1.0 Flex", "ano": "2018", "km": "50.000", "cor": "Branca"},
        {"marca": "Honda", "titulo": "City EXL 1.5 Flex", "ano": "2019", "km": "40.000", "cor": "Prata"},
        {"marca": "Fortcar", "titulo": "REBOQUE TOP REB TRP751", "ano": "2026", "km": "", "cor": "Preto", "preco": "R$ 9.900,00"},
        {"marca": "GTX 325", "titulo": "SEADOO GTX 325 2025", "ano": "2025", "km": "6", "cor": "Marrom", "preco": "R$ 189.900,00"},
        {"marca": "Ford", "titulo": "Ka 1.5 12V SEDAN SE FLEX AUT.", "ano": "2019", "km": "72.800", "cor": "Vermelho"},
        {"marca": "Ford", "titulo": "Fiesta 1.0 8V FLEXCLASS FLEX", "ano": "2012", "km": "128.500", "cor": "Vermelho"},
        {"marca": "", "titulo": "Volvo XC 60 2.0", "ano": "2012", "km": "167.000", "cor": "Prata", "preco": "R$ 39.990,00"},
        {"marca": "", "titulo": "Ram 2500 TROPIVAN", "ano": "2008", "km": "160.000", "cor": "Preta", "preco": "R$ 119.990,00"},
        {"marca": "", "titulo": "SRX", "ano": "2011", "km": "149.000", "cor": "Cinza", "preco": "R$ 50.000,00"},
        {"marca": "", "titulo": "bike eletrica", "ano": "2025", "km": "1.000", "cor": "Preta", "preco": "R$ 7.000,00"},
        {"marca": "Hyundai", "titulo": "HB20 Comfort 1.0", "ano": "2024", "km": "62.000", "cor": "Branca", "preco": "R$ 69.990,00"},
    ]
    autocarro = [
        {"marca": "", "titulo": "VW T-CROSS", "ano": "2022", "km": "30000", "cor": "Branco"},
        {"marca": "", "titulo": "Fiat Toro", "ano": "2020", "km": "75000", "cor": "Preto"},
        {"marca": "", "titulo": "Hyundai HB20", "ano": "2022", "km": "25000", "cor": "Vermelho"},
        {"marca": "", "titulo": "Chevrolet Onix", "ano": "2015", "km": "80000", "cor": "Branco"},
        {"marca": "", "titulo": "Honda Civic", "ano": "2018", "km": "90000", "cor": "Cinza"},
        {"marca": "", "titulo": "PALIO1.8 MPI ADVENTURE LOCKER WEEKENDPRATA", "ano": "2012", "km": "90000", "cor": "Prata"},
        {"marca": "", "titulo": "UNO1.0 WAY BRANCO", "ano": "2018", "km": "50000", "cor": "Branco"},
        {"marca": "", "titulo": "HONDA CITY SEDAN AUT", "ano": "2019", "km": "41500", "cor": "Prata"},
        {"marca": "", "titulo": "REBOQUE REBOQUE CARRO 1 EIXO", "ano": "2026", "km": "0", "cor": "Preta", "preco": "R$ 9.900,00"},
        {"marca": "", "titulo": "JET SKI SEA DOO RXT-X 325", "ano": "2025", "km": "0", "cor": "", "preco": "R$ 189.900,00"},
        {"marca": "", "titulo": "FORD KA 1.5 SE 12V", "ano": "2019", "km": "72800", "cor": "Vermelho"},
        {"marca": "", "titulo": "FORD FIESTA 1.0 MPI CLASS 8V", "ano": "2012", "km": "128500", "cor": "Vermelho"},
        {"marca": "", "titulo": "VOLVO XC60 2.0 T5 COMFORT FWD TURBO", "ano": "2012", "km": "167000", "cor": "Prata", "preco": "R$ 39.990,00"},
        {"marca": "", "titulo": "DODGE RAM 5.9 TROPIVAN 2500 SLT 4X4 TURBO", "ano": "2008", "km": "160000", "cor": "Preta", "preco": "R$ 119.990,00"},
        {"marca": "", "titulo": "CADILLAC SRX 3.0 CROSSOVER AWD V6", "ano": "2011", "km": "149000", "cor": "Cinza", "preco": "R$ 50.000,00"},
        {"marca": "", "titulo": "DUOS MOTO ELETRICA EKO-7", "ano": "2025", "km": "1000", "cor": "Preta", "preco": "R$ 7.000,00"},
        {"marca": "", "titulo": "VOLKSWAGEN SAVEIRO 1.6 MI 8V", "ano": "2014", "km": "160000", "cor": "Branca", "preco": "R$ 49.990,00"},
    ]
    mostrar_resultado(comparar(loja, autocarro))
    print("\n--- Só pretos até 120.000 km ---")
    mostrar_resultado(comparar(filtrar(loja, "preto", None, 120000),
                               filtrar(autocarro, "preto", None, 120000)))
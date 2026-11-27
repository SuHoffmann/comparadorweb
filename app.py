import re
import subprocess
import sys

import streamlit as st

from coletor_loja import coletar_estoque_loja
from comparador import comparar, filtrar, nome

st.set_page_config(page_title="Comparador de Estoque", page_icon="🚗", layout="wide")


@st.cache_resource
def instalar_navegador():
    """Baixa o Chromium do Playwright na primeira execução do servidor."""
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       check=False, timeout=600)
    except Exception:
        pass
    return True


def ler_km(texto):
    digitos = re.sub(r"\D", "", texto or "")
    return int(digitos) if digitos else None


@st.cache_data(ttl=600, show_spinner=False)
def coletar(link):
    return coletar_estoque_loja(link)


st.title("🚗 Comparador de Estoque")
st.caption("Compara o estoque da loja com o do Autocarro.")

link_loja = st.text_input("Estoque da loja", placeholder="https://jjveiculossc.com.br/estoque")
link_auto = st.text_input("Estoque do Autocarro", placeholder="Link público do estoque no Autocarro")

st.markdown("**Filtros (opcional)**")
c1, c2, c3 = st.columns(3)
cor = c1.text_input("Cor")
km_min = ler_km(c2.text_input("KM mínimo"))
km_max = ler_km(c3.text_input("KM máximo"))

if st.button("COMPARAR ESTOQUES", type="primary"):
    if not link_loja.strip() or not link_auto.strip():
        st.error("Preencha os dois links.")
        st.stop()

    instalar_navegador()
    try:
        with st.spinner("Coletando o estoque da loja..."):
            loja = coletar(link_loja)
        if not loja:
            st.error("Não consegui ler o estoque da loja.")
            st.stop()
        with st.spinner("Coletando o estoque do Autocarro..."):
            auto = coletar(link_auto)
        if not auto:
            st.error("Não consegui ler o estoque do Autocarro (pode exigir login).")
            st.stop()
    except Exception as e:
        st.error(f"Erro: {e}")
        st.stop()

    partes = []
    if cor.strip():
        partes.append(f"cor {cor.strip()}")
    if km_min is not None:
        partes.append(f"KM a partir de {km_min:,}".replace(",", "."))
    if km_max is not None:
        partes.append(f"KM até {km_max:,}".replace(",", "."))
    if partes:
        loja = filtrar(loja, cor, km_min, km_max)
        auto = filtrar(auto, cor, km_min, km_max)
        if not loja and not auto:
            st.warning("Nenhum veículo passou pelo filtro (o site pode não informar KM/cor).")
            st.stop()
        st.info("Filtro: " + ", ".join(partes))

    r = comparar(loja, auto)

    st.header("Resultado")
    m1, m2, m3 = st.columns(3)
    m1.metric("Autocarro", f"{r['qtd_autocarro']} veículos")
    m2.metric("Loja", f"{r['qtd_loja']} veículos")
    m3.metric("Diferença", abs(r["qtd_autocarro"] - r["qtd_loja"]))

    if not r["so_loja"] and not r["so_autocarro"]:
        st.success("OS ESTOQUES SÃO IGUAIS")
    else:
        st.error(f"Diferença de quantidade: {abs(r['qtd_autocarro'] - r['qtd_loja'])} veículo(s)")

    st.subheader("Estão no AUTOCARRO, mas não estão na LOJA")
    for v in r["so_autocarro"]:
        st.write("• " + nome(v))
    if not r["so_autocarro"]:
        st.caption("(nenhum)")

    st.subheader("Estão na LOJA, mas não estão no AUTOCARRO")
    for v in r["so_loja"]:
        st.write("• " + nome(v))
    if not r["so_loja"]:
        st.caption("(nenhum)")

    if r.get("quase_iguais"):
        st.subheader(f"Provavelmente o MESMO carro — confira ({len(r['quase_iguais'])})")
        for l, a, _ in r["quase_iguais"]:
            st.write("• **Loja:** " + nome(l))
            st.write("   **Autocarro:** " + nome(a))

    with st.expander(f"Encontrados nos dois estoques ({len(r['em_ambos'])})"):
        for l, a in r["em_ambos"]:
            st.write("• " + nome(l).split("  -  ")[0])
            st.caption(f"Loja: {l.get('preco') or '-'}  |  Autocarro: {a.get('preco') or '-'}")

    reais = [d for d in r["divergentes"] if not d[2][0].startswith("PROVÁVEL MESMO CARRO")]
    if reais:
        st.subheader(f"Nos dois, mas com KM/cor diferentes ({len(reais)})")
        for l, a, msgs in reais:
            st.write("• " + nome(l).split("  -  ")[0])
            for msg in msgs:
                st.warning(msg)

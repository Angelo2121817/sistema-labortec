import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import re
import os
import html
from pypdf import PdfReader
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components

# ==============================================================================
# 0. FUNÇÃO UNIVERSAL DE CONVERSÃO DE DATAS → SEMPRE DD/MM/YYYY
# ==============================================================================

def to_br_date(value):
    """Converte qualquer formato (date, datetime, YYYY-MM-DD ou já BR) em DD/MM/YYYY"""
    if value is None:
        return ""

    # Se for um objeto date
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    value = str(value).strip()

    # Caso já esteja em formato BR
    if re.match(r"^\d{2}/\d{2}/\d{4}$", value):
        return value

    # Caso venha como YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            pass

    # Caso venha com T (ex: 2025-10-08T00:00:00)
    if re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            pass

    return value  # retorna no estado original caso não consiga identificar

# ==============================================================================
# 1. FUNÇÕES DE EXTRAÇÃO PDF (CETESB & PADRÃO)
# ==============================================================================

def extrair_dados_cetesb(f):
    try:
        reader = PdfReader(f)
        text = reader.pages[0].extract_text() or ""
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        d = {"Nome": "", "CNPJ": "", "End": "", "Bairro": "", "Cidade": "", "CEP": "", "UF": "SP", "Cod_Cli": "", "Tel": "", "Email": ""}

        for i, line in enumerate(lines):
            cnpj_m = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", line)
            if cnpj_m:
                d["CNPJ"] = cnpj_m.group(1)
                d["Nome"] = line.replace(d["CNPJ"], "").strip()

                if i + 1 < len(lines):
                    prox = lines[i + 1]
                    cad_m = re.search(r"(\d+-\d+-\d+)", prox)
                    d["End"] = prox.replace(cad_m.group(1), "").strip() if cad_m else prox

                if i + 2 < len(lines):
                    addr_line = lines[i + 2]
                    cep_m = re.search(r"(\d{5}-\d{3})", addr_line)
                    if cep_m:
                        d["CEP"] = cep_m.group(1)
                        partes_antes = addr_line.split(d["CEP"])[0].strip()
                        m_num_bai = re.match(r"(\d+)\s+(.*)", partes_antes)
                        if m_num_bai:
                            d["End"] = f"{d['End']}, {m_num_bai.group(1)}"
                            d["Bairro"] = m_num_bai.group(2).strip()

                        d["Cidade"] = addr_line.split(d["CEP"])[-1].strip()

                break

        return d

    except Exception:
        return None


def ler_pdf_antigo(f):
    try:
        reader = PdfReader(f)
        primeira = reader.pages[0].extract_text() or ""

        if "CETESB" in primeira.upper():
            return extrair_dados_cetesb(f)

        text = ""
        for p in reader.pages:
            t = p.extract_text()
            if t:
                text += t + "\n"

        clean = re.sub(r"\s+", " ", text).strip()
        idx = clean.lower().find("cliente")
        core = clean[idx:] if idx != -1 else clean

        d = {"Nome": "", "Cod_Cli": "", "End": "", "CEP": "", "Bairro": "", "Cidade": "", "UF": "", "CNPJ": "", "Tel": "", "Email": ""}

        def extract(key, stops):
            m = re.search(re.escape(key) + r"[:\s]*", core, re.IGNORECASE)
            if not m:
                return ""
            fragment = core[m.end():]
            min_i = len(fragment)
            for stop in stops:
                sm = re.search(re.escape(stop), fragment, re.IGNORECASE)
                if sm and sm.start() < min_i:
                    min_i = sm.start()
            return fragment[:min_i].strip().strip(":-/| ")

        d["Nome"] = extract("Cliente", ["CNPJ", "CPF", "Endereço"])

        cnpj_match = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", core)
        d["CNPJ"] = cnpj_match.group(1) if cnpj_match else ""

        d["End"] = extract("Endereço", ["Bairro", "Cidade", "CEP"])
        d["Bairro"] = extract("Bairro", ["Cidade", "CEP"])
        d["Cidade"] = extract("Cidade", ["CEP"])
        cep_m = re.search(r"(\d{5}-\d{3})", core)
        d["CEP"] = cep_m.group(1) if cep_m else ""

        return d

    except Exception:
        return None


# ==============================================================================
# 2. CONFIGURAÇÃO & CONEXÃO
# ==============================================================================

st.set_page_config(page_title="Sistema Integrado v61", layout="wide", page_icon="🧪")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except:
    st.error("Erro crítico ao conectar no Google Sheets.")
    st.stop()

# ==============================================================================
# 3. LOGIN
# ==============================================================================

CREDENCIAIS = {
    "General": "labormetal22",
    "Fabricio": "fabricio2225",
    "Anderson": "anderson2225",
    "Angelo": "angelo2225",
}

def obter_horario_br():
    return datetime.utcnow() - timedelta(hours=3)

def obter_saudacao():
    h = obter_horario_br().hour
    if 5 <= h < 12: return "Bom dia"
    if 12 <= h < 18: return "Boa tarde"
    return "Boa noite"

def verificar_senha():
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False
        st.session_state["usuario_nome"] = ""

    if not st.session_state["autenticado"]:
        st.markdown("<h1 style='text-align:center;'>🔐 ACESSO RESTRITO</h1>", unsafe_allow_html=True)

        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            senha = st.text_input("Código:", type="password")
            if st.button("ACESSAR"):
                for nome, pw in CREDENCIAIS.items():
                    if senha == pw:
                        st.session_state["autenticado"] = True
                        st.session_state["usuario_nome"] = nome
                        st.rerun()
                st.error("Senha incorreta.")
        return False
    return True

if not verificar_senha():
    st.stop()

# ==============================================================================
# 4. CARREGAR DADOS (COM CONVERSÃO DE DATAS PARA DD/MM/YYYY)
# ==============================================================================

def carregar_dados():
    try:
        # ----------------- ESTOQUE -----------------
        df_est = conn.read("Estoque", ttl=0)
        if isinstance(df_est, pd.DataFrame) and not df_est.empty:
            df_est.columns = [c.strip() for c in df_est.columns]
            st.session_state["estoque"] = df_est
        else:
            st.session_state["estoque"] = pd.DataFrame()

        # ----------------- CLIENTES -----------------
        df_cli = conn.read("Clientes", ttl=0)
        if isinstance(df_cli, pd.DataFrame) and not df_cli.empty:
            df_cli.columns = [c.strip() for c in df_cli.columns]
            if "Email" not in df_cli.columns:
                df_cli["Email"] = ""
            if "Nome" in df_cli.columns:
                st.session_state["clientes_db"] = df_cli.set_index("Nome").to_dict("index")
            else:
                st.session_state["clientes_db"] = {}

        # ----------------- LOGS -----------------
        for aba in ["Log_Vendas", "Log_Entradas", "Log_Laudos"]:
            df = conn.read(aba, ttl=0)

            if isinstance(df, pd.DataFrame) and not df.empty:
                df.columns = [c.strip() for c in df.columns]
                # Normaliza datas no carregamento:
                if "Data" in df.columns:
                    df["Data"] = df["Data"].apply(to_br_date)

                if aba == "Log_Laudos":
                    for col in ["Data_Coleta", "Data_Resultado"]:
                        if col not in df.columns:
                            df[col] = ""
                        df[col] = df[col].apply(to_br_date)

                    if "Status" not in df.columns:
                        df["Status"] = "Pendente"

                st.session_state[aba.lower()] = df.to_dict("records")
            else:
                st.session_state[aba.lower()] = []

        return True

    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return False


# ==============================================================================
# 5. SALVAR DADOS (CONVERSÃO SEGURA DE TODOS OS FORMATOS)
# ==============================================================================

def salvar_dados():
    try:
        # ESTOQUE
        conn.update("Estoque", st.session_state["estoque"])

        # CLIENTES
        if st.session_state.get("clientes_db"):
            df_cli = pd.DataFrame.from_dict(st.session_state["clientes_db"], orient="index").reset_index().rename(columns={"index": "Nome"})
            conn.update("Clientes", df_cli)

        # LOGS PADRÃO
        conn.update("Log_Vendas", pd.DataFrame(st.session_state["log_vendas"]))
        conn.update("Log_Entradas", pd.DataFrame(st.session_state["log_entradas"]))

        # LOG LAUDOS — CONVERTE TUDO PARA DD/MM/YYYY
        df_l = pd.DataFrame(st.session_state["log_laudos"])

        if not df_l.empty:
            for col in ["Data_Coleta", "Data_Resultado"]:
                if col in df_l.columns:
                    df_l[col] = df_l[col].apply(to_br_date)

            if "Status" not in df_l.columns:
                df_l["Status"] = "Pendente"

        conn.update("Log_Laudos", df_l)

        st.toast("💾 Dados sincronizados!")

    except Exception as e:
        st.error(f"Erro ao salvar: {e}")


# Inicializa se necessário
if "dados_carregados" not in st.session_state:
    carregar_dados()
    st.session_state["dados_carregados"] = True

# Inicializar estruturas vazias
for key in ["log_vendas", "log_entradas", "log_laudos"]:
    st.session_state.setdefault(key, [])

st.session_state.setdefault("estoque", pd.DataFrame())
st.session_state.setdefault("clientes_db", {})

# ==============================================================================
# 6. TEMA VISUAL
# ==============================================================================

def aplicar_tema(theme):
    css = """
    <style>
        .centered-title { text-align:center; color:#1e3d59; font-weight:700; padding:20px 0; font-size:2.5em; }
    </style>
    """

    if theme == "⚪ Padrão":
        css += "<style>.stApp{background:#FFFFFF;color:#000;}</style>"
    elif theme == "🔵 Azul":
        css += "<style>.stApp{background:#F0F8FF;color:#003366;}</style>"
    elif theme == "🌿 Verde":
        css += "<style>.stApp{background:#F1F8E9;color:#1B5E20;}</style>"
    elif theme == "⚫ Dark":
        css += "<style>.stApp{background:#0E1117;color:#FAFAFA;}</style>"

    st.markdown(css, unsafe_allow_html=True)
    # ==============================================================================
# 7. MENU LATERAL
# ==============================================================================

st.sidebar.title("🛠️ MENU")
st.sidebar.success(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")

tema_sel = st.sidebar.selectbox(
    "Tema:",
    ["⚪ Padrão", "🔵 Azul", "🌿 Verde", "⚫ Dark"]
)
aplicar_tema(tema_sel)

menu = st.sidebar.radio(
    "Navegar:",
    [
        "📊 Dashboard",
        "🧪 Laudos",
        "💰 Vendas & Orçamentos",
        "📥 Entrada",
        "📦 Estoque",
        "📋 Conferência Geral",
        "👥 Clientes"
    ]
)

# ==============================================================================
# 8. DASHBOARD — COM DATA CORRIGIDA DD/MM/YYYY + CARROSSEL
# ==============================================================================

if menu == "📊 Dashboard":

    st.markdown("<div class='centered-title'>📊 Dashboard Operacional</div>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("<h3 style='text-align:center;color:#1e3d59;'>📡 Radar de Coletas e Resultados</h3>", unsafe_allow_html=True)

    laudos = st.session_state.get("log_laudos", [])
    pendentes = [l for l in laudos if l.get("Status", "Pendente") == "Pendente"]

    if not pendentes:
        st.success("✅ Tudo em dia!")
    else:
        itens_html = ""

        for l in pendentes:

            cliente = html.escape(str(l.get("Cliente", "")))
            data_coleta = to_br_date(l.get("Data_Coleta", ""))
            data_resultado = to_br_date(l.get("Data_Resultado", ""))

            itens_html += f"""
            <div class="carousel-item">
                <div class="coleta-cliente">🏢 {cliente}</div>
                <div class="prevista-label">Coleta:</div>
                <div class="neon-date">📅 {data_coleta}</div>

                <div class="prevista-label" style="margin-top:8px;">Resultado:</div>
                <div class="neon-result">🧪 {data_resultado}</div>
            </div>
            """

        # CSS do carrossel com velocidade adaptativa
        velocidade = max(20, len(pendentes) * 5)

        carrossel = f"""
        <style>
            .carousel-wrapper {{
                overflow:hidden;
                width:100%;
                padding:10px 0;
            }}
            .carousel-track {{
                display:flex;
                width:calc(300px * {len(pendentes) * 2});
                animation:scroll {velocidade}s linear infinite;
            }}
            .carousel-track:hover {{
                animation-play-state:paused;
            }}
            @keyframes scroll {{
                0% {{ transform:translateX(0); }}
                100% {{ transform:translateX(calc(-300px * {len(pendentes)})); }}
            }}
            .carousel-item {{
                width:280px;
                background:white;
                margin-right:20px;
                padding:15px;
                border-radius:12px;
                border-left:6px solid #ff4b4b;
                height:170px;
                display:flex;
                flex-direction:column;
                justify-content:center;
                box-shadow:0 4px 10px rgba(0,0,0,0.1);
            }}
            .coleta-cliente {{
                font-weight:bold;
                color:#1e3d59;
                margin-bottom:6px;
                font-size:15px;
                white-space:nowrap;
                overflow:hidden;
                text-overflow:ellipsis;
            }}
            .prevista-label {{
                font-size:12px;
                color:#666;
                font-weight:600;
                text-transform:uppercase;
            }}
            .neon-date {{
                font-weight:bold;
                color:#d32f2f;
                font-size:15px;
            }}
            .neon-result {{
                font-weight:bold;
                color:#1e7e34;
                font-size:16px;
            }}
        </style>

        <div class="carousel-wrapper">
            <div class="carousel-track">
                {itens_html}
                {itens_html}
            </div>
        </div>
        """

        components.html(carrossel, height=200)

    st.markdown("---")
    st.info("Espaço livre para gráficos, KPIs, cards extras etc.")
    # ==============================================================================
# 9. LAUDOS — TUDO COM DATA NO PADRÃO BR (DD/MM/YYYY)
# ==============================================================================

elif menu == "🧪 Laudos":
    st.title("🧪 Gestão de Laudos")

    # ----------------------------------
    # AGENDAR NOVA COLETA
    # ----------------------------------
    with st.expander("📅 Agendar Nova Coleta", expanded=True):
        with st.form("form_novo_laudo"):

            cliente = st.selectbox("Cliente", list(st.session_state["clientes_db"].keys()))

            c1, c2 = st.columns(2)

            data_coleta = c1.date_input("Data da Coleta")
            data_resultado = c2.date_input("Previsão do Resultado", value=data_coleta + timedelta(days=7))

            if st.form_submit_button("Agendar"):
                novo = {
                    "Cliente": cliente,
                    "Data_Coleta": to_br_date(data_coleta),
                    "Data_Resultado": to_br_date(data_resultado),
                    "Status": "Pendente",
                }
                st.session_state["log_laudos"].append(novo)
                salvar_dados()
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Editar / Atualizar Laudos")

    laudos = st.session_state.get("log_laudos", [])

    if not laudos:
        st.info("Nenhum laudo registrado ainda.")
    else:
        df = pd.DataFrame(laudos)

        # Força datas em formato visível BR
        df["Data_Coleta"] = df["Data_Coleta"].apply(to_br_date)
        df["Data_Resultado"] = df["Data_Resultado"].apply(to_br_date)
        df["ID"] = df.index

        edit = st.data_editor(
            df[["ID", "Cliente", "Data_Coleta", "Data_Resultado", "Status"]],
            hide_index=True,
            use_container_width=True,
            disabled=["ID", "Cliente", "Data_Coleta"]
        )

        if st.button("💾 Salvar Alterações"):
            for _, row in edit.iterrows():
                idx = int(row["ID"])
                st.session_state["log_laudos"][idx]["Data_Resultado"] = to_br_date(row["Data_Resultado"])
                st.session_state["log_laudos"][idx]["Status"] = row["Status"]

            salvar_dados()
            st.success("Laudos atualizados!")
            st.rerun()


# ==============================================================================
# 10. VENDAS & ORÇAMENTOS — TUDO NORMALIZADO
# ==============================================================================

elif menu == "💰 Vendas & Orçamentos":

    st.title("💰 Vendas e Orçamentos")

    if not st.session_state["clientes_db"]:
        st.warning("Nenhum cliente cadastrado.")
        st.stop()

    clientes = list(st.session_state["clientes_db"].keys())

    c1, c2 = st.columns([2, 1])
    cliente = c1.selectbox("Cliente", clientes)
    vendedor = c2.text_input("Vendedor", st.session_state["usuario_nome"])

    dados_cliente = st.session_state["clientes_db"][cliente]

    col1, col2, col3 = st.columns(3)
    plano = col1.text_input("Plano", "28/42 DIAS")
    forma_pag = col2.text_input("Forma", "BOLETO ITAU")
    venc = col3.text_input("Vencimento", "A COMBINAR")

    df = st.session_state["estoque"].copy()

    if "Qtd" not in df.columns:
        df.insert(0, "Qtd", 0.0)

    df["Qtd"] = pd.to_numeric(df["Qtd"], errors="coerce").fillna(0)

    edit = st.data_editor(
        df[["Qtd", "Produto", "Cod", "Marca", "NCM", "Unidade", "Preco_Base", "Saldo"]],
        use_container_width=True,
        hide_index=True
    )

    selecionados = edit[edit["Qtd"] > 0].copy()
    selecionados["Total"] = selecionados["Qtd"] * selecionados["Preco_Base"]

    total_geral = selecionados["Total"].sum()

    if not selecionados.empty:
        st.metric("Total", f"R$ {total_geral:,.2f}")

        colA, colB = st.columns(2)

        # -------------------------
        # ORÇAMENTO
        # -------------------------
        with colA:
            if st.button("📄 Gerar Orçamento", use_container_width=True):
                pdf = criar_doc_pdf(
                    vendedor,
                    cliente,
                    dados_cliente,
                    selecionados.to_dict("records"),
                    total_geral,
                    {"plano":plano, "forma":forma_pag, "venc":venc},
                    "ORÇAMENTO"
                )
                st.download_button("📥 Baixar Orçamento", pdf, f"Orcamento_{cliente}.pdf", "application/pdf")

        # -------------------------
        # PEDIDO
        # -------------------------
        with colB:
            origem = st.radio("Origem:", ["METAL QUÍMICA", "INDEPENDENTE"], horizontal=True)
            if st.button("✅ Confirmar Pedido", use_container_width=True):

                pdf = criar_doc_pdf(
                    vendedor,
                    cliente,
                    dados_cliente,
                    selecionados.to_dict("records"),
                    total_geral,
                    {"plano":plano, "forma":forma_pag, "venc":venc},
                    "PEDIDO"
                )

                # DESCONTAR DO ESTOQUE
                if origem == "METAL QUÍMICA":
                    for _, r in selecionados.iterrows():
                        idx = st.session_state["estoque"][st.session_state["estoque"]["Cod"] == r["Cod"]].index
                        if not idx.empty:
                            i = idx[0]
                            st.session_state["estoque"].at[i, "Saldo"] -= r["Qtd"]

                        st.session_state["log_vendas"].append({
                            "Data": to_br_date(datetime.now()),
                            "Cliente": cliente,
                            "Produto": r["Produto"],
                            "Qtd": r["Qtd"],
                            "Vendedor": vendedor
                        })

                    salvar_dados()
                    st.success("Pedido registrado!")

                else:
                    st.success("Pedido registrado!")

                st.download_button("📥 Baixar Pedido", pdf, f"Pedido_{cliente}.pdf", "application/pdf")


# ==============================================================================
# 11. CLIENTES — NORMALIZADO
# ==============================================================================

elif menu == "👥 Clientes":
    st.title("👥 Gestão de Clientes")

    # --------------------- CADASTRAR ---------------------
    with st.expander("📂 Cadastrar / Importar PDF"):

        up = st.file_uploader("Importar PDF", type="pdf")
        if up and st.button("Processar PDF"):
            dados = ler_pdf_antigo(up)
            if dados:
                for k, v in dados.items():
                    st.session_state[f"f_{k}"] = v
                st.success("Dados carregados!")

        with st.form("form_novo_cliente"):
            nome = st.text_input("Nome / Razão Social", st.session_state.get("f_Nome", ""))
            c1, c2 = st.columns(2)
            cnpj = c1.text_input("CNPJ", st.session_state.get("f_CNPJ", ""))
            tel = c2.text_input("Telefone", st.session_state.get("f_Tel", ""))
            email = st.text_input("Email", st.session_state.get("f_Email", ""))
            end = st.text_input("Endereço", st.session_state.get("f_End", ""))
            c3, c4, c5 = st.columns([2, 1, 1])
            cid = c3.text_input("Cidade", st.session_state.get("f_Cidade", ""))
            uf = c4.text_input("UF", st.session_state.get("f_UF", "SP"))
            cep = c5.text_input("CEP", st.session_state.get("f_CEP", ""))

            if st.form_submit_button("Salvar Cliente"):
                st.session_state["clientes_db"][nome] = {
                    "CNPJ": cnpj,
                    "Tel": tel,
                    "Email": email,
                    "End": end,
                    "Cidade": cid,
                    "UF": uf,
                    "CEP": cep,
                }
                salvar_dados()
                st.success("Cliente salvo!")
                st.rerun()

    # --------------------- LISTAGEM ---------------------
    st.markdown("---")
    st.subheader("📋 Lista de Clientes")

    if not st.session_state["clientes_db"]:
        st.info("Nenhum cliente cadastrado.")
    else:
        df_cli = pd.DataFrame.from_dict(st.session_state["clientes_db"], orient="index").reset_index().rename(columns={"index": "Nome"})
        edit = st.data_editor(
            df_cli,
            use_container_width=True,
            num_rows="dynamic",
            hide_index=True,
        )

        if st.button("💾 Atualizar Clientes"):
            st.session_state["clientes_db"] = edit.set_index("Nome").to_dict("index")
            salvar_dados()
            st.success("Clientes atualizados!")
            st.rerun()


# ==============================================================================
# 12. ESTOQUE
# ==============================================================================

elif menu == "📦 Estoque":
    st.title("📦 Estoque")

    df = st.data_editor(
        st.session_state["estoque"],
        use_container_width=True,
        num_rows="dynamic"
    )

    if not df.equals(st.session_state["estoque"]):
        st.session_state["estoque"] = df
        salvar_dados()


# ==============================================================================
# 13. CONFERÊNCIA GERAL
# ==============================================================================

elif menu == "📋 Conferência Geral":
    st.title("📋 Conferência Geral")

    tab1, tab2, tab3 = st.tabs(["📊 Vendas", "📥 Entradas", "🧪 Laudos"])

    # VENDAS
    with tab1:
        df = pd.DataFrame(st.session_state["log_vendas"])
        if not df.empty:
            df["Data"] = df["Data"].apply(to_br_date)
            st.dataframe(df.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhuma venda registrada.")

    # ENTRADAS
    with tab2:
        df = pd.DataFrame(st.session_state["log_entradas"])
        if not df.empty:
            df["Data"] = df["Data"].apply(to_br_date)
            st.dataframe(df.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhuma entrada no estoque registrada.")

    # LAUDOS
    with tab3:
        df = pd.DataFrame(st.session_state["log_laudos"])
        if not df.empty:
            df["Data_Coleta"] = df["Data_Coleta"].apply(to_br_date)
            df["Data_Resultado"] = df["Data_Resultado"].apply(to_br_date)
            st.dataframe(df.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhum laudo registrado.")


# ==============================================================================
# 14. ENTRADA DE ESTOQUE
# ==============================================================================

elif menu == "📥 Entrada":
    st.title("📥 Entrada de Estoque")

    if st.session_state["estoque"].empty:
        st.warning("Cadastre produtos antes de registrar entradas.")
        st.stop()

    with st.form("form_entrada"):
        produto = st.selectbox(
            "Produto",
            st.session_state["estoque"]["Produto"].astype(str).tolist()
        )
        qtd = st.number_input("Quantidade", min_value=0.0)

        if st.form_submit_button("Registrar Entrada"):
            idx = st.session_state["estoque"][st.session_state["estoque"]["Produto"] == produto].index[0]
            st.session_state["estoque"].at[idx, "Saldo"] += qtd

            st.session_state["log_entradas"].append({
                "Data": to_br_date(datetime.now()),
                "Produto": produto,
                "Qtd": qtd
            })

            salvar_dados()
            st.success("Entrada registrada!")
            st.rerun()
        


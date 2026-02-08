import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import os
import html
from pypdf import PdfReader
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components

# ==============================================================================
# 0. PADRONIZAÇÃO DE DATA → SEMPRE DD/MM/YYYY
# ==============================================================================

def to_br_date(v):
    """Converte para DD/MM/YYYY"""
    if v is None:
        return ""

    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y")

    v = str(v).strip()

    # dd/mm/yyyy
    if re.match(r"^\d{2}/\d{2}/\d{4}$", v):
        return v

    # yyyy-mm-dd
    if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        try:
            return datetime.strptime(v, "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            return v

    # yyyy-mm-ddTHH:MM:SS
    if "T" in v:
        try:
            return datetime.strptime(v[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except:
            return v

    return v

# ==============================================================================
# 1. FUNÇÕES PARA EXTRAIR DADOS DO PDF
# ==============================================================================

def extrair_dados_cetesb(f):
    try:
        reader = PdfReader(f)
        text = reader.pages[0].extract_text() or ""
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        d = {"Nome": "", "CNPJ": "", "End": "", "Bairro": "", "Cidade": "", "CEP": "",
             "UF": "SP", "Cod_Cli": "", "Tel": "", "Email": ""}

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
    except:
        return None


def ler_pdf_antigo(f):
    try:
        reader = PdfReader(f)
        primeira = reader.pages[0].extract_text() or ""

        if "CETESB" in primeira.upper():
            return extrair_dados_cetesb(f)

        text = ""
        for p in reader.pages:
            txt = p.extract_text()
            if txt:
                text += txt + "\n"

        out = {"Nome": "", "Cod_Cli": "", "End": "", "CEP": "", "Bairro": "",
               "Cidade": "", "UF": "", "CNPJ": "", "Tel": "", "Email": ""}

        clean = re.sub(r"\s+", " ", text).strip()
        idx = clean.lower().find("cliente")
        core = clean[idx:] if idx != -1 else clean

        def extract(key, stops):
            m = re.search(key + r"[:\s]*", core, re.IGNORECASE)
            if not m:
                return ""
            frag = core[m.end():]
            end_idx = len(frag)
            for stop in stops:
                sm = re.search(stop, frag, re.IGNORECASE)
                if sm and sm.start() < end_idx:
                    end_idx = sm.start()
            return frag[:end_idx].strip(" :/-|")

        out["Nome"] = extract("Cliente", ["CNPJ", "CPF", "Endereço"])
        cnpj_m = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", core)
        out["CNPJ"] = cnpj_m.group(1) if cnpj_m else ""
        out["End"] = extract("Endereço", ["Bairro", "Cidade", "CEP"])
        out["Bairro"] = extract("Bairro", ["Cidade", "CEP"])
        out["Cidade"] = extract("Cidade", ["CEP"])
        cep_m = re.search(r"(\d{5}-\d{3})", core)
        out["CEP"] = cep_m.group(1) if cep_m else ""

        return out

    except:
        return None

# ==============================================================================
# 2. CONFIGURAÇÃO STREAMLIT + CONEXÃO
# ==============================================================================

st.set_page_config(page_title="Sistema Integrado v61", layout="wide", page_icon="🧪")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except:
    st.error("Erro ao conectar ao Google Sheets (verifique secrets.toml).")
    st.stop()

# ==============================================================================
# 3. LOGIN
# ==============================================================================

CREDENCIAIS = {
    "General": "labormetal22",
    "Fabricio": "fabricio2225",
    "Anderson": "anderson2225",
    "Angelo": "angelo2225"
}

def obter_horario_br():
    return datetime.utcnow() - timedelta(hours=3)

def obter_saudacao():
    h = obter_horario_br().hour
    if 5 <= h < 12:
        return "Bom dia"
    if 12 <= h < 18:
        return "Boa tarde"
    return "Boa noite"

def verificar_senha():
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False
        st.session_state["usuario_nome"] = ""

    if not st.session_state["autenticado"]:
        st.markdown("<h1 style='text-align:center;'>🔐 ACESSO RESTRITO</h1>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 2, 1])

        with c2:
            codigo = st.text_input("Código:", type="password")
            if st.button("ACESSAR"):
                for nome, senha in CREDENCIAIS.items():
                    if codigo == senha:
                        st.session_state["autenticado"] = True
                        st.session_state["usuario_nome"] = nome
                        st.rerun()
                st.error("Código incorreto.")

        return False

    return True

if not verificar_senha():
    st.stop()

# ==============================================================================
# 4. CARREGAMENTO E SALVAMENTO DE DADOS (Sheets)
# ==============================================================================

def salvar_dados():
    try:
        # ESTOQUE
        conn.update(
            worksheet="Estoque",
            data=st.session_state["estoque"],
            reload=True
        )

        # CLIENTES
        df_cli = pd.DataFrame.from_dict(
            st.session_state["clientes_db"],
            orient="index"
        )
        df_cli.reset_index(inplace=True)
        df_cli.rename(columns={"index": "Nome"}, inplace=True)

        conn.update(
            worksheet="Clientes",
            data=df_cli,
            reload=True
        )

        # LOG VENDAS
        df_v = pd.DataFrame(st.session_state["log_vendas"])
        conn.update(
            worksheet="Log_Vendas",
            data=df_v,
            reload=True
        )

        # LOG ENTRADAS
        df_e = pd.DataFrame(st.session_state["log_entradas"])
        conn.update(
            worksheet="Log_Entradas",
            data=df_e,
            reload=True
        )

        # LOG LAUDOS
        df_l = pd.DataFrame(st.session_state["log_laudos"])
        if not df_l.empty:
            df_l["Data_Coleta"] = df_l["Data_Coleta"].apply(to_br_date)
            df_l["Data_Resultado"] = df_l["Data_Resultado"].apply(to_br_date)

        conn.update(
            worksheet="Log_Laudos",
            data=df_l,
            reload=True
        )

        st.toast("💾 Dados sincronizados!")

    except Exception as e:
        st.error(f"Erro salvar: {e}")
        # =========================
        # LOG LAUDOS
        # =========================
        df_l = pd.DataFrame(st.session_state["log_laudos"])

        if not df_l.empty:
            df_l["Data_Coleta"] = df_l["Data_Coleta"].apply(to_br_date)
            df_l["Data_Resultado"] = df_l["Data_Resultado"].apply(to_br_date)

        conn.update(
            worksheet="Log_Laudos",
            data=df_l
        )

        # Sucesso
        st.toast("💾 Dados sincronizados!")

    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

        # ---------------- LOGS ----------------
        for aba in ["Log_Vendas", "Log_Entradas", "Log_Laudos"]:
            df_l = conn.read(aba, ttl=0)
            if isinstance(df_l, pd.DataFrame):
                df_l.columns = [str(c).strip() for c in df_l.columns]
                if aba == "Log_Laudos":
                    for col in ["Data_Coleta", "Data_Resultado"]:
                        if col not in df_l:
                            df_l[col] = ""
                        df_l[col] = df_l[col].apply(to_br_date)
                st.session_state[aba.lower()] = df_l.to_dict("records")
            else:
                st.session_state[aba.lower()] = []
        return True
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return False


def salvar_dados():
    try:
        conn.update("Estoque", st.session_state["estoque"])

        df_cli = pd.DataFrame.from_dict(st.session_state["clientes_db"], orient="index")
        df_cli.reset_index(inplace=True)
        df_cli = df_cli.rename(columns={"index": "Nome"})
        conn.update("Clientes", df_cli)

        conn.update("Log_Vendas", pd.DataFrame(st.session_state["log_vendas"]))
        conn.update("Log_Entradas", pd.DataFrame(st.session_state["log_entradas"]))

        df_l = pd.DataFrame(st.session_state["log_laudos"])
        for col in ["Data_Coleta", "Data_Resultado"]:
            if col in df_l:
                df_l[col] = df_l[col].apply(to_br_date)
        conn.update("Log_Laudos", df_l)

        st.toast("Dados sincronizados!")
    except Exception as e:
        st.error(f"Erro salvar: {e}")

# Inicialização
if "dados_carregados" not in st.session_state:
    carregar_dados()
    st.session_state["dados_carregados"] = True

# ==============================================================================
# 5. PDF + criar_doc_pdf
# ==============================================================================

class PDF(FPDF):
    def header(self):
        if os.path.exists("labortec.jpg"):
            self.image("labortec.jpg", x=10, y=8, w=48)

        off = 10

        self.set_font("Arial", "B", 19)
        self.set_xy(65, 10 + off)
        self.cell(100, 10, "LABORTEC", 0, 0, "L")

        self.set_xy(110, 10 + off)
        titulo = getattr(self, "titulo_doc", "")
        self.cell(90, 10, titulo, 0, 1, "R")

        self.set_font("Arial", "", 10)
        self.set_xy(65, 22 + off)
        self.cell(100, 5, "Rua Alfredo Bruno, 22 - Campinas/SP - CEP 13040-235", 0, 0)

        self.set_xy(110, 22 + off)
        self.cell(90, 5, f"Data: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, "R")

        self.set_xy(65, 27 + off)
        self.cell(100, 5, "labortecconsultoria@gmail.com | (19) 3238-9320", 0)

        self.set_xy(110, 27 + off)
        vendedor = getattr(self, "vendedor_nome", "")
        self.cell(90, 5, f"Vendedor: {vendedor}", 0, 1, "R")

        self.set_xy(65, 32 + off)
        self.cell(100, 5, "CNPJ: 03.763.197/0001-09", 0, 1)

        self.line(10, 42 + off, 200, 42 + off)
        self.set_y(48 + off)

    def footer(self):
        self.set_y(-25)
        self.set_font("Arial", "I", 7)
        self.cell(0, 4, "Obs.: Frete não incluso. Proposta válida por 5 dias.", 0, 1, "C")
        self.cell(0, 4, "Prazo de retirada: 3 a 5 dias úteis após confirmação.", 0, 1, "C")

def criar_doc_pdf(vendedor, cliente, dados_cli, itens, total, cond, titulo):

    pdf = PDF()
    pdf.vendedor_nome = vendedor
    pdf.titulo_doc = titulo

    pdf.add_page()
    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 8, f" Cliente: {cliente}", 1, 1, "L", True)

    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 6, f" Endereço: {dados_cli.get('End','')}", "LR", 1)
    pdf.cell(0, 6, f" Cidade: {dados_cli.get('Cidade','')}/{dados_cli.get('UF','')} - CEP: {dados_cli.get('CEP','')}", "LR", 1)
    pdf.cell(0, 6, f" CNPJ: {dados_cli.get('CNPJ','')} - Tel: {dados_cli.get('Tel','')}", "LRB", 1)
    pdf.ln(4)

    pdf.cell(0, 8, f" Pagto: {cond.get('plano','')} | Forma: {cond.get('forma','')} | Vencto: {cond.get('venc','')}", 1, 1)
    pdf.ln(5)

    pdf.set_font("Arial", "B", 8)
    w = [15, 15, 80, 25, 25, 30]
    cols = ["Un", "Qtd", "Produto", "Marca", "NCM", "Total"]
    for i, c in enumerate(cols):
        pdf.cell(w[i], 7, c, 1, 0, "C")
    pdf.ln()
    pdf.set_font("Arial", "", 8)

    for itm in itens:
        pdf.cell(w[0], 6, str(itm.get("Unidade","KG")), 1)
        pdf.cell(w[1], 6, str(itm.get("Qtd","0")), 1, 0, "C")
        pdf.cell(w[2], 6, str(itm.get("Produto",""))[:40], 1)
        pdf.cell(w[3], 6, str(itm.get("Marca","LABORTEC")), 1)
        pdf.cell(w[4], 6, str(itm.get("NCM","")), 1)
        try:
            pdf.cell(w[5], 6, f"{float(itm.get('Total',0)):.2f}", 1, 1, "R")
        except:
            pdf.cell(w[5], 6, "0.00", 1, 1, "R")

    pdf.set_font("Arial", "B", 10)
    pdf.cell(sum(w[:-1]), 10, "TOTAL GERAL: ", 0, 0, "R")
    pdf.cell(w[-1], 10, f"R$ {total:,.2f}", 1, 1, "R")

    pdf.ln(20)
    y = pdf.get_y()

    pdf.line(25, y, 90, y)
    pdf.line(120, y, 185, y)

    pdf.set_font("Arial", "", 9)
    pdf.set_xy(25, y + 2)
    pdf.cell(65, 5, "Assinatura Cliente", 0, 0, "C")
    pdf.set_xy(120, y + 2)
    pdf.cell(65, 5, "Assinatura Labortec", 0, 1, "C")

    return pdf.output(dest="S").encode("latin-1")
    # ==============================================================================
# 6. TEMA / MENU LATERAL
# ==============================================================================

def aplicar_tema(escolha):
    css = """
    <style>
        .centered-title { text-align: center; color: #1e3d59; font-weight: bold; padding: 20px 0; font-size: 2.5em; }
    </style>
    """
    if escolha == "⚪ Padrão (Clean)":
        css += "<style>.stApp { background-color: #FFFFFF !important; color: #000000 !important; }</style>"
    elif escolha == "🔵 Azul Labortec":
        css += "<style>.stApp { background-color: #F0F8FF !important; color: #002B4E !important; } h1,h2,h3 { color: #004aad !important; }</style>"
    elif escolha == "🌿 Verde Natureza":
        css += "<style>.stApp { background-color: #F1F8E9 !important; color: #1B5E20 !important; }</style>"
    elif escolha == "⚫ Dark Mode (Noturno)":
        css += "<style>.stApp { background-color: #0E1117 !important; color: #FAFAFA !important; } .prevista-label { color: #aaa; }</style>"

    st.markdown(css, unsafe_allow_html=True)


# MENU
st.sidebar.title("🛠️ MENU")
st.sidebar.success(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")

tema_sel = st.sidebar.selectbox(
    "Tema:",
    ["⚪ Padrão (Clean)", "🔵 Azul Labortec", "🌿 Verde Natureza", "⚫ Dark Mode (Noturno)"]
)

aplicar_tema(tema_sel)

menu = st.sidebar.radio(
    "Navegar:",
    [
        "📊 Dashboard",
        "🧪 Laudos",
        "💰 Vendas & Orçamentos",
        "📥 Entrada",
        "📦 Produtos",
        "📋 Conferência Geral",
        "👥 Clientes"
    ]
)

# ==============================================================================
# 7. DASHBOARD — CORRIGIDO, FUNCIONAL, COM CARROSSEL
# ==============================================================================

if menu == "📊 Dashboard":

    st.markdown('<div class="centered-title">📊 Dashboard Operacional</div>', unsafe_allow_html=True)
    st.markdown("---")

    # TÍTULO DO PAINEL DE RESULTADOS
    st.markdown("<h3 style='text-align: center; color: #1e3d59;'>📡 Radar de Coletas e Resultados</h3>", unsafe_allow_html=True)

    laudos = st.session_state.get("log_laudos", [])
    pendentes = [l for l in laudos if l.get("Status", "Pendente") == "Pendente"]

    if not pendentes:
        st.success("✅ Tudo em dia!")

    else:
        # Montagem dos cards
        items_html = ""
        loop_factor = 2 if len(pendentes) > 4 else 8

        for l in pendentes:
            cliente = html.escape(l.get("Cliente", ""))
            coleta = html.escape(to_br_date(l.get("Data_Coleta", "")))
            resultado = html.escape(to_br_date(l.get("Data_Resultado", "")))

            items_html += f"""
            <div class="carousel-item">
                <div class="coleta-cliente">🏢 {cliente}</div>

                <div class="prevista-label">Coleta:</div>
                <div class="neon-date">📅 {coleta}</div>

                <div class="prevista-label" style="margin-top:8px;">Resultado:</div>
                <div class="neon-result">🧪 {resultado}</div>
            </div>
            """

        # CSS + Componente de Carrossel
        carrossel = f"""
        <style>
            .carousel-wrapper {{
                overflow: hidden;
                width: 100%;
                padding: 10px 0;
            }}
            .carousel-track {{
                display: flex;
                width: calc(300px * {len(pendentes) * 2});
                animation: scroll {max(20, len(pendentes)*5)}s linear infinite;
            }}
            @keyframes scroll {{
                0%   {{ transform: translateX(0); }}
                100% {{ transform: translateX(calc(-300px * {len(pendentes)})); }}
            }}
            .carousel-item {{
                width: 280px;
                margin-right: 20px;
                background: white;
                padding: 15px;
                border-radius: 12px;
                border-left: 6px solid #ff4b4b;
                box-shadow: 0 4px 10px rgba(0,0,0,0.08);
                height: 170px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }}
            .coleta-cliente {{
                font-weight: bold;
                color: #1e3d59;
                margin-bottom: 8px;
                font-size: 16px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}
            .prevista-label {{
                font-size: 13px;
                color: #666;
                font-weight: 600;
            }}
            .neon-date {{
                font-weight: bold;
                color: #d32f2f;
                font-size: 15px;
            }}
            .neon-result {{
                font-weight: bold;
                color: #1e7e34;
                font-size: 16px;
            }}
        </style>

        <div class="carousel-wrapper">
            <div class="carousel-track">
                {items_html}
                {items_html}
            </div>
        </div>
        """

        components.html(carrossel, height=200)

    st.markdown("---")

    # BASE PARA GRÁFICOS
    st.info("Gráficos e indicadores podem ser adicionados aqui.")
    # ==============================================================================
# 8. LAUDOS — AGENDAMENTO, EDIÇÃO E VISUALIZAÇÃO
# ==============================================================================

elif menu == "🧪 Laudos":
    st.title("🧪 Gestão de Laudos")

    # ------------------- AGENDAR COLETA -------------------
    with st.expander("📅 Agendar Nova Coleta", expanded=True):
        with st.form("f_laudo"):
            cli_l = st.selectbox("Cliente", list(st.session_state["clientes_db"].keys()))
            c1, c2 = st.columns(2)
            data_l = c1.date_input("Data da Coleta")
            data_r = c2.date_input("Previsão do Resultado", value=data_l + timedelta(days=7))

            if st.form_submit_button("Agendar"):
                novo = {
                    "Cliente": cli_l,
                    "Data_Coleta": to_br_date(data_l),
                    "Data_Resultado": to_br_date(data_r),
                    "Status": "Pendente",
                }
                st.session_state["log_laudos"].append(novo)
                salvar_dados()
                st.rerun()

    # ------------------- EDIÇÃO -------------------
    st.markdown("---")
    st.subheader("📋 Editar Previsões / Status")

    laudos = st.session_state.get("log_laudos", [])

    if not laudos:
        st.info("Sem laudos cadastrados.")
    else:
        df_p = pd.DataFrame(laudos)
        df_p["ID"] = df_p.index
        df_p["Data_Coleta"] = df_p["Data_Coleta"].apply(to_br_date)
        df_p["Data_Resultado"] = df_p["Data_Resultado"].apply(to_br_date)

        ed = st.data_editor(
            df_p[["ID", "Cliente", "Data_Coleta", "Data_Resultado", "Status"]],
            use_container_width=True,
            hide_index=True,
            disabled=["ID", "Cliente", "Data_Coleta"],
        )

        if st.button("💾 Salvar Alterações"):
            for _, row in ed.iterrows():
                i = int(row["ID"])
                st.session_state["log_laudos"][i]["Data_Resultado"] = to_br_date(row["Data_Resultado"])
                st.session_state["log_laudos"][i]["Status"] = row["Status"]

            salvar_dados()
            st.success("Atualizado!")
            st.rerun()

# ==============================================================================
# 9. VENDAS & ORÇAMENTOS — GERAR PDF + ATUALIZAR ESTOQUE
# ==============================================================================

elif menu == "💰 Vendas & Orçamentos":

    st.title("💰 Vendas e Orçamentos")

    if not st.session_state["clientes_db"]:
        st.warning("Nenhum cliente cadastrado ainda.")
        st.stop()

    # CLIENTE + VENDEDOR
    c1, c2 = st.columns([2, 1])
    cliente = c1.selectbox("Cliente", list(st.session_state["clientes_db"].keys()))
    vendedor = c2.text_input("Vendedor", st.session_state["usuario_nome"])
    dados_cli = st.session_state["clientes_db"][cliente]

    # CONDIÇÕES
    col1, col2, col3 = st.columns(3)
    plano = col1.text_input("Plano", "28/42 DIAS")
    forma = col2.text_input("Forma", "BOLETO ITAU")
    venc = col3.text_input("Vencimento", "A COMBINAR")

    # PRODUTOS
    df_prod = st.session_state["estoque"].copy()
    if "Qtd" not in df_prod.columns:
        df_prod.insert(0, "Qtd", 0.0)

    ed_prod = st.data_editor(
        df_prod[["Qtd", "Produto", "Cod", "Marca", "NCM", "Unidade", "Preco_Base", "Saldo"]],
        use_container_width=True,
        hide_index=True
    )

    itens = ed_prod[ed_prod["Qtd"] > 0].copy()
    itens["Total"] = itens["Qtd"] * itens["Preco_Base"]
    total_geral = itens["Total"].sum()

    if not itens.empty:
        st.metric("Total", f"R$ {total_geral:,.2f}")

        c_orc, c_ped = st.columns(2)

        # ------------ ORÇAMENTO --------------
        with c_orc:
            if st.button("📄 Gerar Orçamento", use_container_width=True):
                pdf = criar_doc_pdf(
                    vendedor,
                    cliente,
                    dados_cli,
                    itens.to_dict("records"),
                    total_geral,
                    {"plano": plano, "forma": forma, "venc": venc},
                    "ORÇAMENTO"
                )
                st.download_button("📥 Baixar Orçamento", pdf, f"Orcamento_{cliente}.pdf", "application/pdf")

        # ------------ PEDIDO --------------
        with c_ped:
            origem = st.radio("Origem:", ["METAL QUÍMICA", "INDEPENDENTE"], horizontal=True)

            if st.button("✅ Confirmar Pedido", use_container_width=True):

                # Gerar PDF
                pdf = criar_doc_pdf(
                    vendedor,
                    cliente,
                    dados_cli,
                    itens.to_dict("records"),
                    total_geral,
                    {"plano": plano, "forma": forma, "venc": venc},
                    "PEDIDO"
                )

                # Atualizar estoque
                if origem == "METAL QUÍMICA":
                    for _, linha in itens.iterrows():
                        idx = st.session_state["estoque"][st.session_state["estoque"]["Cod"] == linha["Cod"]].index
                        if len(idx):
                            st.session_state["estoque"].at[idx[0], "Saldo"] -= linha["Qtd"]

                        st.session_state["log_vendas"].append(
                            {
                                "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                "Cliente": cliente,
                                "Produto": linha["Produto"],
                                "Qtd": linha["Qtd"],
                                "Vendedor": vendedor,
                            }
                        )

                    salvar_dados()
                    st.success("Pedido registrado!")

                else:
                    st.success("Pedido registrado (sem movimentação de estoque).")

                st.download_button("📥 Baixar Pedido", pdf, f"Pedido_{cliente}.pdf", "application/pdf")

# ==============================================================================
# 10. CLIENTES — CADASTRO / IMPORTAÇÃO / EDIÇÃO
# ==============================================================================

elif menu == "👥 Clientes":
    st.title("👥 Gestão de Clientes")

    # IMPORTAÇÃO
    with st.expander("📂 Importar PDF CETESB"):
        pdf_cli = st.file_uploader("Enviar PDF", type="pdf")
        if pdf_cli and st.button("Processar PDF"):
            dados = ler_pdf_antigo(pdf_cli)
            if dados:
                for k, v in dados.items():
                    st.session_state[f"f_{k}"] = v
                st.success("Dados carregados!")

    # CADASTRO
    with st.form("f_cli"):
        nome = st.text_input("Nome", st.session_state.get("f_Nome", ""))
        c1, c2 = st.columns(2)
        cnpj = c1.text_input("CNPJ", st.session_state.get("f_CNPJ", ""))
        tel = c2.text_input("Tel", st.session_state.get("f_Tel", ""))
        email = st.text_input("Email", st.session_state.get("f_Email", ""))
        end = st.text_input("Endereço", st.session_state.get("f_End", ""))
        c3, c4, c5 = st.columns([2, 1, 1])
        cidade = c3.text_input("Cidade", st.session_state.get("f_Cidade", ""))
        uf = c4.text_input("UF", st.session_state.get("f_UF", "SP"))
        cep = c5.text_input("CEP", st.session_state.get("f_CEP", ""))

        if st.form_submit_button("Salvar Cliente"):
            st.session_state["clientes_db"][nome] = {
                "CNPJ": cnpj,
                "Tel": tel,
                "Email": email,
                "End": end,
                "Cidade": cidade,
                "UF": uf,
                "CEP": cep,
            }
            salvar_dados()
            st.success("Cliente salvo!")
            st.rerun()

    # LISTAGEM
    st.markdown("---")
    st.subheader("📋 Lista de Clientes")

    df_cli = pd.DataFrame.from_dict(st.session_state["clientes_db"], orient="index")
    df_cli.reset_index(inplace=True)
    df_cli.rename(columns={"index": "Nome"}, inplace=True)

    tab = st.data_editor(df_cli, use_container_width=True, hide_index=True, num_rows="dynamic")

    if st.button("💾 Atualizar Lista"):
        st.session_state["clientes_db"] = tab.set_index("Nome").to_dict("index")
        salvar_dados()
        st.success("Atualizado!")
        st.rerun()

# ==============================================================================
# 11. PRODUTOS
# ==============================================================================

elif menu == "📦 Produtos":
    st.title("📦 Produtos")

    tabela = st.data_editor(
        st.session_state["estoque"],
        use_container_width=True,
        num_rows="dynamic",
        hide_index=False
    )

    if not tabela.equals(st.session_state["estoque"]):
        st.session_state["estoque"] = tabela
        salvar_dados()

# ==============================================================================
# 12. CONFERÊNCIA GERAL
# ==============================================================================

elif menu == "📋 Conferência Geral":
    st.title("📋 Conferência Geral")

    t1, t2, t3 = st.tabs(["📊 Vendas", "📥 Entradas", "🧪 Laudos"])

    # VENDAS
    with t1:
        df = pd.DataFrame(st.session_state["log_vendas"])
        if not df.empty:
            df["Data"] = df["Data"].apply(to_br_date)
            st.dataframe(df.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhuma venda registrada.")

    # ENTRADAS
    with t2:
        df = pd.DataFrame(st.session_state["log_entradas"])
        if not df.empty:
            df["Data"] = df["Data"].apply(to_br_date)
            st.dataframe(df.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhuma entrada registrada.")

    # LAUDOS
    with t3:
        df = pd.DataFrame(st.session_state["log_laudos"])
        if not df.empty:
            df["Data_Coleta"] = df["Data_Coleta"].apply(to_br_date)
            df["Data_Resultado"] = df["Data_Resultado"].apply(to_br_date)
            st.dataframe(df.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhum laudo registrado.")

# ==============================================================================
# 13. ENTRADA DE ESTOQUE
# ==============================================================================

elif menu == "📥 Entrada":
    st.title("📥 Entrada de Estoque")

    produtos = st.session_state["estoque"]["Produto"].astype(str).tolist()

    with st.form("f_ent"):
        prod = st.selectbox("Produto", produtos)
        qtd = st.number_input("Quantidade", min_value=0.0)

        if st.form_submit_button("Registrar"):

            idx = st.session_state["estoque"][st.session_state["estoque"]["Produto"] == prod].index

            if len(idx) == 0:
                st.error("Produto não encontrado.")
            else:
                i = idx[0]
                st.session_state["estoque"].at[i, "Saldo"] += qtd

                st.session_state["log_entradas"].append(
                    {"Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                     "Produto": prod,
                     "Qtd": qtd}
                )

                salvar_dados()
                st.success("Entrada registrada!")
                st.rerun()



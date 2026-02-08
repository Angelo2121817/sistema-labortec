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
        primeira_pagina = reader.pages[0].extract_text() or ""

        if "CETESB" in primeira_pagina.upper():
            return extrair_dados_cetesb(f)

        text = ""
        for p in reader.pages:
            t = p.extract_text()
            if t:
                text += t + "\n"

        clean = re.sub(r"\s+", " ", text).strip()
        idx = clean.lower().find("cliente")
        core = clean[idx:] if idx != -1 else clean

        def extract(key, stops):
            match = re.search(re.escape(key) + r"[:\s]*", core, re.IGNORECASE)
            if not match:
                return ""
            fragment = core[match.end():]
            min_i = len(fragment)
            for stop in stops:
                sm = re.search(re.escape(stop), fragment, re.IGNORECASE)
                if sm and sm.start() < min_i:
                    min_i = sm.start()
            return fragment[:min_i].strip(":-/| ")

        out = {"Nome": "", "Cod_Cli": "", "End": "", "CEP": "", "Bairro": "",
               "Cidade": "", "UF": "", "CNPJ": "", "Tel": "", "Email": ""}

        out["Nome"] = extract("Cliente", ["CNPJ", "CPF", "Endereço"])
        cnpj_match = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", core)
        out["CNPJ"] = cnpj_match.group(1) if cnpj_match else ""

        out["End"] = extract("Endereço", ["Bairro", "Cidade", "Cep", "CEP"])
        out["Bairro"] = extract("Bairro", ["Cidade", "Cep", "CEP"])
        out["Cidade"] = extract("Cidade", ["Cep", "CEP"])

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
    elif 12 <= h < 18:
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
            senha = st.text_input("Código:", type="password")
            if st.button("ACESSAR"):
                for n, s in CREDENCIAIS.items():
                    if senha == s:
                        st.session_state["autenticado"] = True
                        st.session_state["usuario_nome"] = n
                        st.rerun()
                st.error("Incorreto")
        return False
    return True

if not verificar_senha():
    st.stop()

# ==============================================================================
# 4. CARREGAMENTO E SALVAMENTO DE DADOS (Sheets)
# ==============================================================================
def carregar_dados():
    try:
        df_est = conn.read("Estoque", ttl=0)
        if isinstance(df_est, pd.DataFrame) and not df_est.empty:
            df_est.columns = [c.strip() for c in df_est.columns]
            st.session_state["estoque"] = df_est

        df_cli = conn.read("Clientes", ttl=0)
        if isinstance(df_cli, pd.DataFrame) and not df_cli.empty:
            df_cli.columns = [c.strip() for c in df_cli.columns]
            if "Email" not in df_cli.columns:
                df_cli["Email"] = ""
            if "Nome" in df_cli.columns:
                st.session_state["clientes_db"] = df_cli.set_index("Nome").to_dict("index")
            else:
                st.session_state["clientes_db"] = {}

        for aba in ["Log_Vendas", "Log_Entradas", "Log_Laudos"]:
            df = conn.read(aba, ttl=0)
            if isinstance(df, pd.DataFrame) and not df.empty:
                df.columns = [c.strip() for c in df.columns]
                if aba == "Log_Laudos":
                    if "Cliente" not in df.columns:
                        df["Cliente"] = ""
                    if "Data_Coleta" not in df.columns:
                        df["Data_Coleta"] = ""
                    if "Data_Resultado" not in df.columns:
                        df["Data_Resultado"] = "Não definida"
                    if "Status" not in df.columns:
                        df["Status"] = "Pendente"
                    
                    for c in ["Cliente", "Data_Coleta", "Data_Resultado", "Status"]:
                        df[c] = df[c].fillna("").astype(str)
                st.session_state[aba.lower()] = df.to_dict("records")
            else:
                st.session_state[aba.lower()] = []
        return True
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return False


def salvar_dados():
    try:
        # ESTOQUE
        conn.update("Estoque", st.session_state["estoque"])

        # CLIENTES
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

st.session_state.setdefault("estoque", pd.DataFrame(columns=["Cod", "Produto", "Marca", "NCM", "Unidade", "Preco_Base", "Saldo", "Estoque_Inicial", "Estoque_Minimo"]))
st.session_state.setdefault("clientes_db", {})

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
        self.set_font("Arial", "B", 19)
        self.set_xy(110, 10 + off)
        titulo_doc = getattr(self, "titulo_doc", "ORÇAMENTO")
        self.cell(90, 10, titulo_doc, 0, 1, "R")
        self.set_font("Arial", "", 10)
        self.set_xy(65, 20 + off)
        self.cell(100, 5, "Rua Alfredo Bruno, 22 - Campinas/SP - CEP 13040-235", 0, 0, "L")
        self.set_xy(110, 20 + off)
        self.cell(90, 5, f"Data: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, "R")
        self.set_xy(65, 25 + off)
        self.cell(100, 5, "labortecconsultoria@gmail.com | Tel.: (19) 3238-9320", 0)
        self.set_xy(110, 25 + off)
        vendedor_nome = getattr(self, "vendedor_nome", "Sistema")
        self.cell(90, 5, f"Vendedor: {vendedor_nome}", 0, 1, "R")
        self.set_xy(65, 30 + off)
        self.cell(100, 5, "C.N.P.J.: 03.763.197/0001-09", 0, 1, "L")
        self.line(10, 40 + off, 200, 40 + off)
        self.set_y(48 + off)

    def footer(self):
        self.set_y(-25)
        self.set_font("Arial", "I", 7)
        self.cell(0, 4, "Obs.: FRETE NÃO INCLUÍDO. PROPOSTA VÁLIDA POR 5 DIAS.", 0, 1, "C")
        self.cell(0, 4, "PRAZO DE RETIRADA: 3 A 5 DIAS ÚTEIS APÓS CONFIRMAÇÃO.", 0, 0, "C")

def criar_doc_pdf(vendedor, cliente, dados_cli, itens, total, condicoes, titulo):
    pdf = PDF()
    pdf.vendedor_nome = vendedor
    pdf.titulo_doc = titulo
    pdf.add_page()
    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 8, f" Cliente: {cliente}", 1, 1, "L", fill=True)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 6, f" Endereço: {dados_cli.get('End', '')}", "LR", 1)
    pdf.cell(0, 6, f" Cidade: {dados_cli.get('Cidade', '')}/{dados_cli.get('UF', '')} - CEP: {dados_cli.get('CEP', '')}", "LR", 1)
    pdf.cell(0, 6, f" CNPJ: {dados_cli.get('CNPJ', '')} - Tel: {dados_cli.get('Tel', '')}", "LRB", 1)
    pdf.ln(5)
    pdf.cell(0, 8, f" Pagto: {condicoes.get('plano', '')} | Forma: {condicoes.get('forma', '')} | Vencto: {condicoes.get('venc', '')}", 1, 1)
    pdf.ln(6)
    pdf.set_font("Arial", "B", 8)
    w = [15, 15, 85, 25, 20, 30]
    cols = ["Un", "Qtd", "Produto", "Marca", "NCM", "Total"]
    for i, c in enumerate(cols):
        pdf.cell(w[i], 7, c, 1, 0, "C", fill=True)
    pdf.ln()
    pdf.set_font("Arial", "", 8)
    for r in itens:
        pdf.cell(w[0], 7, str(r.get("Unidade", "KG")), 1, 0, "C")
        pdf.cell(w[1], 7, str(r.get("Qtd", 0)), 1, 0, "C")
        pdf.cell(w[2], 7, str(r.get("Produto", ""))[:52], 1, 0, "L")
        pdf.cell(w[3], 7, str(r.get("Marca", "LABORTEC")), 1, 0, "C")
        pdf.cell(w[4], 7, str(r.get("NCM", "")), 1, 0, "C")
        try:
            pdf.cell(w[5], 7, f"{float(r.get('Total', 0)):.2f}", 1, 1, "R")
        except:
            pdf.cell(w[5], 7, "0.00", 1, 1, "R")
    pdf.set_font("Arial", "B", 10)
    pdf.cell(sum(w) - w[5], 10, "TOTAL GERAL: ", 0, 0, "R")
    pdf.cell(w[5], 10, f"R$ {total:,.2f}", 1, 1, "R")
    pdf.ln(30)
    y = pdf.get_y()
    pdf.line(25, y, 90, y)
    pdf.line(120, y, 185, y)
    pdf.set_font("Arial", "", 8)
    pdf.set_xy(25, y + 2)
    pdf.cell(65, 4, "Assinatura Cliente", 0, 0, "C")
    pdf.set_xy(120, y + 2)
    pdf.cell(65, 4, "Assinatura Labortec", 0, 1, "C")
    return pdf.output(dest="S").encode("latin-1")

# ==============================================================================
# 6. MENU LATERAL
# ==============================================================================

st.sidebar.title("🛠️ MENU")
st.sidebar.success(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")
tema_sel = st.sidebar.selectbox("Tema:", ["⚪ Padrão (Clean)", "🔵 Azul Labortec", "🌿 Verde Natureza", "⚫ Dark Mode (Noturno)"])
aplicar_tema(tema_sel)
menu = st.sidebar.radio("Navegar:", ["📊 Dashboard", "🧪 Laudos", "💰 Vendas & Orçamentos", "📥 Entrada", "📦 Estoque", "📋 Conferência Geral", "👥 Clientes"])

# ==============================================================================
# 7. DASHBOARD — COM DATA CORRIGIDA DD/MM/YYYY + CARROSSEL
# ==============================================================================

if menu == "📊 Dashboard":
    st.markdown('<div class="centered-title">📊 Dashboard Operacional</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("<h3 style='text-align: center; color: #1e3d59;'>📡 Radar de Coletas e Resultados</h3>", unsafe_allow_html=True)
    laudos = st.session_state.get("log_laudos", [])
    pendentes = [l for l in laudos if str(l.get("Status", "Pendente")) == "Pendente"]
    if not pendentes:
        st.success("✅ Tudo em dia!")
    else:
        itens_html = ""
        loop_factor = 2 if len(pendentes) > 4 else 8
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
        carousel_component = f"""
        <style>
            .carousel-wrapper {{ overflow:hidden; width:100%; padding:10px 0; }}
            .carousel-track {{ display:flex; width:calc(300px * {len(pendentes) * 2}); animation:scroll {max(20, len(pendentes)*5)}s linear infinite; }}
            .carousel-track:hover {{ animation-play-state:paused; }}
            @keyframes scroll {{ 0% {{ transform:translateX(0); }} 100% {{ transform:translateX(calc(-300px * {len(pendentes)})); }} }}
            .carousel-item {{ width:280px; background:white; margin-right:20px; padding:15px; border-radius:12px; border-left:6px solid #ff4b4b; height:170px; display:flex; flex-direction:column; justify-content:center; }}
            .coleta-cliente {{ font-weight:bold; color:#1e3d59; margin-bottom:6px; font-size:15px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
            .prevista-label {{ font-size:12px; color:#666; font-weight:600; text-transform:uppercase; }}
            .neon-date {{ font-weight:bold; color:#d32f2f; font-size:15px; }}
            .neon-result {{ font-weight:bold; color:#1e7e34; font-size:16px; }}
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
# 8. LAUDOS — TUDO COM DATA NO PADRÃO BR (DD/MM/YYYY)
# ==============================================================================

elif menu == "🧪 Laudos":
    st.title("🧪 Gestão de Laudos")
    with st.expander("📅 Agendar Nova Coleta", expanded=True):
        with st.form("form_laudo"):
            cliente = st.selectbox("Cliente", list(st.session_state["clientes_db"].keys()))
            c1, c2 = st.columns(2)
            data_coleta = c1.date_input("Data da Coleta")
            data_resultado = c2.date_input("Previsão do Resultado", value=data_coleta + timedelta(days=7))
            if st.form_submit_button("Agendar"):
                novo = {
                    "Cliente": cliente,
                    "Data_Coleta": to_br_date(data_coleta),
                    "Data_Resultado": to_br_date(data_resultado),
                    "Status": "Pendente"
                }
                st.session_state["log_laudos"].append(novo)
                salvar_dados()
                st.rerun()
    st.markdown("---")
    st.subheader("📋 Editar Previsões")
    laudos = st.session_state.get("log_laudos", [])
    if not laudos:
        st.info("Nenhum laudo registrado.")
    else:
        df = pd.DataFrame(laudos)
        df["ID"] = df.index
        df["Data_Coleta"] = df["Data_Coleta"].apply(to_br_date)
        df["Data_Resultado"] = df["Data_Resultado"].apply(to_br_date)
        ed = st.data_editor(df[["ID", "Cliente", "Data_Coleta", "Data_Resultado", "Status"]], use_container_width=True, hide_index=True, disabled=["ID", "Cliente", "Data_Coleta"])
        if st.button("💾 Salvar Alterações"):
            for _, row in ed.iterrows():
                idx = int(row["ID"])
                st.session_state["log_laudos"][idx]["Data_Resultado"] = to_br_date(row["Data_Resultado"])
                st.session_state["log_laudos"][idx]["Status"] = row["Status"]
            salvar_dados()
            st.success("Laudos atualizados!")
            st.rerun()

# ==============================================================================
# 9. VENDAS & ORÇAMENTOS — TUDO NORMALIZADO
# ==============================================================================

elif menu == "💰 Vendas & Orçamentos":
    st.title("💰 Vendas e Orçamentos")
    if not st.session_state["clientes_db"]:
        st.warning("Nenhum cliente cadastrado.")
        st.stop()
    c1, c2 = st.columns([2, 1])
    cliente = c1.selectbox("Cliente", list(st.session_state["clientes_db"].keys()))
    vendedor = c2.text_input("Vendedor", st.session_state["usuario_nome"])
    dados_cliente = st.session_state["clientes_db"][cliente]
    col1, col2, col3 = st.columns(3)
    plano = col1.text_input("Plano", "28/42 DIAS")
    forma = col2.text_input("Forma", "BOLETO ITAU")
    venc = col3.text_input("Vencimento", "A COMBINAR")
    df = st.session_state["estoque"].copy()
    if "Qtd" not in df.columns:
        df.insert(0, "Qtd", 0.0)
    ed = st.data_editor(df[["Qtd", "Produto", "Cod", "Marca", "NCM", "Unidade", "Preco_Base", "Saldo"]], use_container_width=True, hide_index=True)
    itens_sel = ed[ed["Qtd"] > 0].copy()
    itens_sel["Total"] = itens_sel["Qtd"] * itens_sel["Preco_Base"]
    total = itens_sel["Total"].sum()
    if not itens_sel.empty:
        st.metric("Total", f"R$ {total:,.2f}")
        c_orc, c_ped = st.columns(2)
        with c_orc:
            if st.button("📄 Gerar Orçamento", use_container_width=True):
                pdf = criar_doc_pdf(vendedor, cliente, dados_cliente, itens_sel.to_dict("records"), total, {"plano": plano, "forma": forma, "venc": venc}, "ORÇAMENTO")
                st.download_button("📥 Baixar Orçamento", pdf, f"Orcamento_{cliente}.pdf", "application/pdf")
        with c_ped:
            origem = st.radio("Origem:", ["METAL QUÍMICA", "INDEPENDENTE"], horizontal=True)
            if st.button("✅ Confirmar Pedido", use_container_width=True):
                pdf = criar_doc_pdf(vendedor, cliente, dados_cliente, itens_sel.to_dict("records"), total, {"plano": plano, "forma": forma, "venc": venc}, "PEDIDO")
                if origem == "METAL QUÍMICA":
                    for _, row in itens_sel.iterrows():
                        idx = st.session_state["estoque"][st.session_state["estoque"]["Cod"] == row["Cod"]].index
                        if idx.empty:
                            st.error("Produto não encontrado no estoque.")
                        else:
                            st.session_state["estoque"].at[idx[0], "Saldo"] -= row["Qtd"]
                            st.session_state["log_vendas"].append({
                                "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                "Cliente": cliente,
                                "Produto": row["Produto"],
                                "Qtd": row["Qtd"],
                                "Vendedor": vendedor
                            })
                    salvar_dados()
                    st.success("Pedido registrado!")
                else:
                    st.success("Pedido registrado (sem movimentação de estoque).")
                st.download_button("📥 Baixar Pedido", pdf, f"Pedido_{cliente}.pdf", "application/pdf")

# ==============================================================================
# 10. CLIENTES — NORMALIZADO
# ==============================================================================

elif menu == "👥 Clientes":
    st.title("👥 Gestão de Clientes")
    with st.expander("📂 Cadastrar / Importar"):
        up = st.file_uploader("Importar PDF", type="pdf")
        if up and st.button("Processar PDF"):
            dados = ler_pdf_antigo(up)
            if dados:
                for k, v in dados.items():
                    st.session_state[f"f_{k}"] = v
                st.success("Dados carregados!")
    with st.form("form_cliente"):
        nome = st.text_input("Nome / Razão Social", st.session_state.get("f_Nome", ""))
        c1, c2 = st.columns(2)
        cnpj = c1.text_input("CNPJ", st.session_state.get("f_CNPJ", ""))
        tel = c2.text_input("Telefone", st.session_state.get("f_Tel", ""))
        email = st.text_input("Email", st.session_state.get("f_Email", ""))
        end = st.text_input("Endereço", st.session_state.get("f_End", ""))
        c3, c4, c5 = st.columns([2, 1, 1])
        cidade = c3.text_input("Cidade", st.session_state.get("f_Cidade", ""))
        uf = c4.text_input("UF", st.session_state.get("f_UF", "SP"))
        cep = c5.text_input("CEP", st.session_state.get("f_CEP", ""))
        if st.form_submit_button("💾 Salvar Cliente"):
            st.session_state["clientes_db"][nome] = {"CNPJ": cnpj, "Tel": tel, "Email": email, "End": end, "Cidade": cidade, "UF": uf, "CEP": cep}
            salvar_dados()
            st.success("Cliente salvo!")
            st.rerun()
    st.markdown("---")
    st.subheader("📋 Lista de Clientes")
    if not st.session_state["clientes_db"]:
        st.info("Nenhum cliente cadastrado.")
    else:
        df_cli = pd.DataFrame.from_dict(st.session_state["clientes_db"], orient="index").reset_index().rename(columns={"index": "Nome"})
        ed = st.data_editor(df_cli, use_container_width=True, num_rows="dynamic", hide_index=True)
        if st.button("💾 Atualizar Clientes"):
            st.session_state["clientes_db"] = ed.set_index("Nome").to_dict("index")
            salvar_dados()
            st.success("Clientes atualizados!")
            st.rerun()

# ==============================================================================
# 11. ESTOQUE
# ==============================================================================

elif menu == "📦 Estoque":
    st.title("📦 Estoque")
    ed = st.data_editor(st.session_state["estoque"], use_container_width=True, num_rows="dynamic")
    if not ed.equals(st.session_state["estoque"]):
        st.session_state["estoque"] = ed
        salvar_dados()

# ==============================================================================
# 12. CONFERÊNCIA GERAL
# ==============================================================================

elif menu == "📋 Conferência Geral":
    st.title("📋 Conferência Geral")
    t1, t2, t3 = st.tabs(["📊 Vendas", "📥 Entradas", "🧪 Laudos"])
    with t1:
        df = pd.DataFrame(st.session_state["log_vendas"])
        if not df.empty:
            df["Data"] = df["Data"].apply(to_br_date)
            st.dataframe(df.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhuma venda registrada.")
    with t2:
        df = pd.DataFrame(st.session_state["log_entradas"])
        if not df.empty:
            df["Data"] = df["Data"].apply(to_br_date)
            st.dataframe(df.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhuma entrada registrada.")
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
    if st.session_state["estoque"].empty:
        st.warning("Cadastre produtos antes de registrar entradas.")
        st.stop()
    with st.form("form_entrada"):
        produto = st.selectbox("Produto", st.session_state["estoque"]["Produto"].astype(str).tolist())
        qtd = st.number_input("Quantidade", min_value=0.0)
        if st.form_submit_button("Registrar Entrada"):
            idx = st.session_state["estoque"][st.session_state["estoque"]["Produto"] == produto].index
            if idx.empty:
                st.error("Produto não encontrado.")
            else:
                i = idx[0]
                st.session_state["estoque"].at[i, "Saldo"] += qtd
                st.session_state["log_entradas"].append({
                    "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "Produto": produto,
                    "Qtd": qtd
                })
                salvar_dados()
                st.success("Entrada registrada!")
                st.rerun()

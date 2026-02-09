import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import os
import html
import json
from pypdf import PdfReader
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components

# ==============================================================================
# 0. FUNÇÕES DE EXTRAÇÃO PDF (CETESB & PADRÃO)
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
        primeira_pagina = reader.pages[0].extract_text() or ""
        if "CETESB" in primeira_pagina.upper():
            return extrair_dados_cetesb(f)

        text = ""
        for p in reader.pages:
            t = p.extract_text()
            if t:
                text += t + "\n"

        clean = re.sub(r"\s+", " ", text).strip()
        idx_inicio = clean.lower().find("cliente")
        core = clean[idx_inicio:] if idx_inicio != -1 else clean

        d = {"Nome": "", "Cod_Cli": "", "End": "", "CEP": "", "Bairro": "", "Cidade": "", "UF": "", "CNPJ": "", "Tel": "", "Email": ""}

        def extract(key, stops):
            match = re.search(re.escape(key) + r"[:\s]*", core, re.IGNORECASE)
            if not match:
                return ""
            fragment = core[match.end():]
            min_idx = len(fragment)
            for stop in stops:
                stop_match = re.search(re.escape(stop), fragment, re.IGNORECASE)
                if stop_match and stop_match.start() < min_idx:
                    min_idx = stop_match.start()
            return fragment[:min_idx].strip(" :/-|").strip()

        d["Nome"] = extract("Cliente", ["CNPJ", "CPF", "Endereço", "Data:", "Código:"])

        cnpj_match = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", core)
        d["CNPJ"] = cnpj_match.group(1) if cnpj_match else ""

        d["End"] = extract("Endereço", ["Bairro", "Cidade", "Cep", "CEP"])
        d["Bairro"] = extract("Bairro", ["Cidade", "Cep", "CEP"])
        d["Cidade"] = extract("Cidade", ["Cep", "CEP"])

        cep_match = re.search(r"(\d{5}-\d{3})", core)
        d["CEP"] = cep_match.group(1) if cep_match else ""

        return d
    except Exception:
        return None


# ==============================================================================
# 1. CONFIGURAÇÃO E CONEXÃO
# ==============================================================================
st.set_page_config(page_title="Sistema Integrado v70", layout="wide", page_icon="🧪")
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception:
    st.error("Erro Crítico: Verifique o 'Secrets' no Streamlit Cloud.")
    st.stop()


# ==============================================================================
# 2. SEGURANÇA E LOGIN
# ==============================================================================
CREDENCIAIS = {"General": "labormetal22", "Fabricio": "fabricio2225", "Anderson": "anderson2225", "Angelo": "angelo2225"}


def obter_horario_br():
    return datetime.utcnow() - timedelta(hours=3)


def obter_saudacao():
    hora = obter_horario_br().hour
    if 5 <= hora < 12:
        return "Bom dia"
    elif 12 <= hora < 18:
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
# 3. MOTOR DE DADOS
# ==============================================================================
def _normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _fix_date_br(val):
    if not val or pd.isna(val) or str(val).strip() == "":
        return ""
    try:
        return pd.to_datetime(val, dayfirst=True).strftime("%d/%m/%Y")
    except:
        return val

def _fix_datetime_br(val):
    if not val or pd.isna(val) or str(val).strip() == "":
        return ""
    try:
        return pd.to_datetime(val, dayfirst=True).strftime("%d/%m/%Y %H:%M")
    except:
        return val

def carregar_dados():
    try:
        df_est = conn.read(worksheet="Estoque", ttl=0)
        if isinstance(df_est, pd.DataFrame) and not df_est.empty:
            df_est = _normalizar_colunas(df_est)
            st.session_state["estoque"] = df_est

        df_cli = conn.read(worksheet="Clientes", ttl=0)
        if isinstance(df_cli, pd.DataFrame) and not df_cli.empty:
            df_cli = _normalizar_colunas(df_cli)
            if "Email" not in df_cli.columns:
                df_cli["Email"] = ""
            if "Nome" in df_cli.columns:
                st.session_state["clientes_db"] = df_cli.set_index("Nome").to_dict("index")
            else:
                st.session_state["clientes_db"] = {}

        for aba in ["Log_Vendas", "Log_Entradas", "Log_Laudos"]:
            df = conn.read(worksheet=aba, ttl=0)
            if isinstance(df, pd.DataFrame) and not df.empty:
                df = _normalizar_colunas(df)
                
                if aba == "Log_Laudos":
                    if "Cliente" not in df.columns: df["Cliente"] = ""
                    if "Status" not in df.columns: df["Status"] = "Pendente"
                    if "Data_Coleta" not in df.columns: df["Data_Coleta"] = ""
                    if "Data_Resultado" not in df.columns: df["Data_Resultado"] = "Não definida"

                    if "Data_Coleta" in df.columns:
                        df["Data_Coleta"] = df["Data_Coleta"].apply(_fix_date_br)
                    if "Data_Resultado" in df.columns:
                        df["Data_Resultado"] = df["Data_Resultado"].apply(_fix_date_br)
                    
                    for c in ["Cliente", "Status"]:
                        df[c] = df[c].fillna("").astype(str)

                elif aba in ["Log_Vendas", "Log_Entradas"]:
                    if "Data" in df.columns:
                        df["Data"] = df["Data"].apply(_fix_datetime_br)
                    
                st.session_state[aba.lower()] = df.to_dict("records")
            else:
                st.session_state[aba.lower()] = []
        return True
    except Exception:
        return False


def salvar_dados():
    try:
        conn.update(worksheet="Estoque", data=st.session_state["estoque"])
        
        if st.session_state.get("clientes_db"):
            df_clis = pd.DataFrame.from_dict(st.session_state["clientes_db"], orient="index").reset_index().rename(columns={"index": "Nome"})
            conn.update(worksheet="Clientes", data=df_clis)
            
        conn.update(worksheet="Log_Vendas", data=pd.DataFrame(st.session_state.get("log_vendas", [])))
        conn.update(worksheet="Log_Entradas", data=pd.DataFrame(st.session_state.get("log_entradas", [])))
        conn.update(worksheet="Log_Laudos", data=pd.DataFrame(st.session_state.get("log_laudos", [])))
        
        st.toast("✅ Sincronizado!", icon="☁️")
    except Exception as e:
        print(f"Alerta silencioso ao salvar: {e}")
        pass

if "dados_carregados" not in st.session_state:
    carregar_dados()
    st.session_state["dados_carregados"] = True

for key in ["log_vendas", "log_entradas", "log_laudos"]:
    if key not in st.session_state:
        st.session_state[key] = []
if "estoque" not in st.session_state:
    st.session_state["estoque"] = pd.DataFrame(columns=["Cod", "Produto", "Marca", "NCM", "Unidade", "Preco_Base", "Saldo", "Estoque_Inicial", "Estoque_Minimo"])
if "clientes_db" not in st.session_state:
    st.session_state["clientes_db"] = {}


# ==============================================================================
# 4. TEMAS E CSS
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


# ==============================================================================
# 5. GERADOR DE PDF
# ==============================================================================
class PDF(FPDF):
    def header(self):
        if os.path.exists("labortec.jpg"):
            self.image("labortec.jpg", x=10, y=8, w=48)
        offset_y = 10
        self.set_font("Arial", "B", 19)
        self.set_xy(65, 10 + offset_y)
        self.cell(100, 10, "LABORTEC", 0, 0, "L")

        self.set_font("Arial", "B", 19)
        self.set_xy(110, 10 + offset_y)
        titulo_doc = getattr(self, "titulo_doc", "ORÇAMENTO")
        self.cell(90, 10, titulo_doc, 0, 1, "R")

        self.set_font("Arial", "", 10)
        self.set_xy(65, 20 + offset_y)
        self.cell(100, 5, "Rua Alfredo Bruno, 22 - Campinas/SP - CEP 13040-235", 0, 0, "L")
        self.set_xy(110, 20 + offset_y)
        self.cell(90, 5, f"Data: {obter_horario_br().strftime('%d/%m/%Y')}", 0, 1, "R")

        self.set_xy(65, 25 + offset_y)
        self.cell(100, 5, "labortecconsultoria@gmail.com | Tel.: (19) 3238-9320", 0, 0, "L")
        self.set_xy(110, 25 + offset_y)
        vendedor_nome = getattr(self, "vendedor_nome", "Sistema")
        self.cell(90, 5, f"Vendedor: {vendedor_nome}", 0, 1, "R")

        self.set_xy(65, 30 + offset_y)
        self.cell(100, 5, "C.N.P.J.: 03.763.197/0001-09", 0, 1, "L")

        self.line(10, 40 + offset_y, 200, 40 + offset_y)
        self.set_y(48 + offset_y)

    def footer(self):
        self.set_y(-25)
        self.set_font("Arial", "I", 7)
        self.cell(0, 4, "Obs.: FRETE NÃO INCLUSO. PROPOSTA VÁLIDA POR 5 DIAS.", 0, 1, "C")
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
    pdf.cell(0, 6, f" Endereço: {dados_cli.get('End', '')}", "LR", 1, "L")
    pdf.cell(0, 6, f" Cidade: {dados_cli.get('Cidade', '')}/{dados_cli.get('UF', '')} - CEP: {dados_cli.get('CEP', '')}", "LR", 1, "L")
    pdf.cell(0, 6, f" CNPJ: {dados_cli.get('CNPJ', '')} - Tel: {dados_cli.get('Tel', '')}", "LRB", 1, "L")
    pdf.ln(5)

    pdf.cell(0, 8, f" Pagto: {condicoes.get('plano', '')} | Forma: {condicoes.get('forma', '')} | Vencto: {condicoes.get('venc', '')}", 1, 1, "L")
    pdf.ln(6)

    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(225, 225, 225)
    w = [15, 15, 85, 25, 20, 30]
    cols = ["Un", "Qtd", "Produto", "Marca", "NCM", "Total"]
    for i, c in enumerate(cols):
        pdf.cell(w[i], 8, c, 1, 0, "C", fill=True)

    pdf.ln()
    pdf.set_font("Arial", "", 8)

    for r in itens:
        pdf.cell(w[0], 7, str(r.get("Unidade", "KG")), 1, 0, "C")
        pdf.cell(w[1], 7, str(r.get("Qtd", 0)), 1, 0, "C")
        pdf.cell(w[2], 7, str(r.get("Produto", ""))[:52], 1, 0, "L")
        pdf.cell(w[3], 7, str(r.get("Marca", "LABORTEC")), 1, 0, "C")
        pdf.cell(w[4], 7, str(r.get("NCM", "")), 1, 0, "C")
        try:
            total_item = r.get('Total', 0)
            if 'Preco_Final' in r: # Se tiver preco final, usa ele
                 total_item = r['Preco_Final'] * r['Qtd']
            
            pdf.cell(w[5], 7, f"{float(total_item):.2f}", 1, 1, "R")
        except Exception:
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
# 6. MENU LATERAL E TEMAS
# ==============================================================================
st.sidebar.title("🛠️ MENU GERAL")
st.sidebar.success(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")

if 'aviso_geral' not in st.session_state: st.session_state['aviso_geral'] = ""
st.sidebar.markdown("---")
with st.sidebar.expander("📢 DEFINIR AVISO"):
    aviso_txt = st.text_area("Mensagem do Mural:", value=st.session_state['aviso_geral'], height=100)
    c_salv, c_limp = st.columns(2)
    if c_salv.button("💾 Gravar"):
        st.session_state['aviso_geral'] = aviso_txt
        st.rerun()
    if c_limp.button("🗑️ Apagar"):
        st.session_state['aviso_geral'] = ""
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🎨 Personalizar Tela")
opcoes_temas = ["⚪ Padrão (Clean)", "🔵 Azul Labortec", "🌿 Verde Natureza", "⚫ Dark Mode (Noturno)", "🟠 Metal Industrial", "🌃 Cyber Dark"]
tema_sel = st.sidebar.selectbox("Escolha o visual:", opcoes_temas)
aplicar_tema(tema_sel)

menu = st.sidebar.radio("Navegar:", [
    "📊 Dashboard", 
    "🧪 Laudos", 
    "💰 Vendas & Orçamentos", 
    "📥 Entrada de Estoque", 
    "📦 Estoque", 
    "📋 Conferência Geral", 
    "👥 Clientes",
    "🛠️ Admin / Backup"
])

# ==============================================================================
# 7. PÁGINAS DO SISTEMA
# ==============================================================================

if menu == "📊 Dashboard":
    st.markdown('<div class="centered-title">📊 Dashboard Gerencial</div>', unsafe_allow_html=True)
    
    # --- ALERTA GERAL (VISUAL PREMIUM) ---
    if st.session_state['aviso_geral']:
        st.markdown(f"""
        <style>
            @keyframes pulse-soft {{
                0% {{ box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.4); }}
                70% {{ box-shadow: 0 0 0 15px rgba(220, 53, 69, 0); }}
                100% {{ box-shadow: 0 0 0 0 rgba(220, 53, 69, 0); }}
            }}
            .alert-box {{
                background: #fff0f1; color: #c53030; border-left: 6px solid #c53030;
                padding: 15px 20px; border-radius: 8px; margin-bottom: 25px;
                display: flex; align-items: center; gap: 15px; font-weight: 600;
                box-shadow: 0 4px 12px rgba(0,0,0,0.05); animation: pulse-soft 2s infinite;
            }}
            .alert-icon {{ font-size: 24px; }}
        </style>
        <div class="alert-box">
            <span class="alert-icon">📢</span>
            <span>{st.session_state['aviso_geral']}</span>
        </div>
        """, unsafe_allow_html=True)

    # --- RADAR DE LAUDOS (VISUAL PREMIUM) ---
    st.markdown("<h4 style='color: #1e3d59; margin-bottom: 20px; display: flex; align-items: center; gap: 10px;'><span style='font-size: 1.2em'>📡</span> Monitoramento de Coletas (Pendentes)</h4>", unsafe_allow_html=True)

    laudos_atuais = st.session_state.get("log_laudos", [])
    # Filtro Estrito: Apenas Pendentes
    ativos = [l for l in laudos_atuais if str(l.get("Status", "Pendente")) == "Pendente"]

    if not ativos:
        st.markdown("""
            <div style='background: #e8f5e9; color: #2e7d32; padding: 20px; border-radius: 12px; text-align: center; font-weight: 600; box-shadow: 0 4px 12px rgba(0,0,0,0.05);'>
                ✅ Radar Limpo! Nenhuma coleta pendente no momento.
            </div>
        """, unsafe_allow_html=True)
    else:
        items_html = ""
        for l in ativos:
            cliente = html.escape(str(l.get("Cliente", "") or "Cliente Desconhecido"))
            coleta = html.escape(str(l.get("Data_Coleta", "") or "--/--"))
            resultado = html.escape(str(l.get("Data_Resultado", "") or "--/--"))

            items_html += f"""
            <div class="card-premium">
                <div class="card-accent"></div>
                <div class="card-content">
                    <div class="client-header" title="{cliente}">
                        <span class="icon-building">🏢</span> {cliente}
                    </div>
                    <div class="dates-container">
                        <div class="date-box">
                            <div class="icon-label">📅 COLETA</div>
                            <div class="date-value">{coleta}</div>
                        </div>
                        <div class="vertical-divider"></div>
                        <div class="date-box">
                            <div class="icon-label">🧪 PREVISÃO</div>
                            <div class="date-value highlight">{resultado}</div>
                        </div>
                    </div>
                    <div class="status-footer">
                        <span class="status-badge">⏳ AGUARDANDO COLETA</span>
                    </div>
                </div>
            </div>
            """

        alinhamento = "center" if len(ativos) <= 3 else "flex-start"

        carousel_component = f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            .carousel-container {{ display: flex; overflow-x: auto; gap: 25px; padding: 15px 5px 30px 5px; width: 100%; justify-content: {alinhamento}; scroll-behavior: smooth; }}
            .carousel-container::-webkit-scrollbar {{ height: 10px; }}
            .carousel-container::-webkit-scrollbar-track {{ background: #f0f2f5; border-radius: 10px; }}
            .carousel-container::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 10px; border: 2px solid #f0f2f5; }}
            .card-premium {{ min-width: 280px; width: 280px; background: #ffffff; border-radius: 16px; box-shadow: 0 10px 30px -5px rgba(0,0,0,0.08); font-family: 'Inter', sans-serif; overflow: hidden; position: relative; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); border: 1px solid #f0f0f0; }}
            .card-premium:hover {{ transform: translateY(-8px); box-shadow: 0 20px 40px -10px rgba(30, 61, 89, 0.15); border-color: #e0e0e0; }}
            .card-accent {{ height: 6px; background: #1e3d59; width: 100%; }}
            .card-content {{ padding: 20px; display: flex; flex-direction: column; height: 100%; }}
            .client-header {{ font-size: 16px; font-weight: 700; color: #1e3d59; margin-bottom: 20px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: flex; align-items: center; gap: 8px; }}
            .icon-building {{ font-size: 18px; opacity: 0.8; }}
            .dates-container {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
            .date-box {{ flex: 1; text-align: center; }}
            .icon-label {{ font-size: 11px; color: #94a3b8; font-weight: 700; letter-spacing: 0.5px; margin-bottom: 6px; }}
            .date-value {{ font-size: 15px; font-weight: 700; color: #334155; }}
            .date-value.highlight {{ color: #004aad; }}
            .vertical-divider {{ width: 1px; height: 35px; background: #e2e8f0; margin: 0 15px; }}
            .status-footer {{ text-align: center; margin-top: auto; }}
            .status-badge {{ background: #e3f2fd; color: #1565c0; font-size: 12px; font-weight: 700; padding: 6px 16px; border-radius: 50px; display: inline-block; box-shadow: 0 2px 5px rgba(0,0,0,0.05); letter-spacing: 0.5px; }}
        </style>
        <div class="carousel-container">{items_html}</div>
        """
        components.html(carousel_component, height=250)

    st.markdown("---")

    # --- MÉTRICAS E GRÁFICOS ---
    st.markdown("<h4 style='color: #d32f2f; margin-top: 20px; display: flex; align-items: center; gap: 10px;'>🚨 Estoque Crítico (Abaixo do Mínimo)</h4>", unsafe_allow_html=True)
    
    df_est = st.session_state.get('estoque')
    if df_est is not None and not df_est.empty:
        try:
            saldo_num = pd.to_numeric(df_est['Saldo'], errors='coerce').fillna(0)
            min_num = pd.to_numeric(df_est['Estoque_Minimo'], errors='coerce').fillna(0)
            criticos = df_est[ (saldo_num < min_num) & (min_num > 0) ].copy()
            if not criticos.empty:
                st.dataframe(criticos[['Cod', 'Produto', 'Saldo', 'Estoque_Minimo']], use_container_width=True, hide_index=True, column_config={"Saldo": st.column_config.NumberColumn("Saldo Atual", format="%.2f"), "Estoque_Minimo": st.column_config.NumberColumn("Mínimo Desejado", format="%.0f")})
            else:
                st.markdown("<div style='background: #e8f5e9; color: #2e7d32; padding: 10px 15px; border-radius: 8px; font-weight: 600;'>👍 Situação Regular! Nenhum produto crítico.</div>", unsafe_allow_html=True)
        except: st.info("Dados insuficientes.")
    
    st.markdown("---")

    c_graf1, c_graf2 = st.columns(2)
    with c_graf1:
        st.markdown("### 📈 Volume de Vendas Diárias")
        log_v = st.session_state.get('log_vendas', [])
        if log_v:
            df_v = pd.DataFrame(log_v)
            df_v['Dia'] = pd.to_datetime(df_v['Data'], dayfirst=True, errors='coerce').dt.date
            st.area_chart(df_v.groupby('Dia')['Qtd'].sum(), color="#004aad")
        else: st.caption("Aguardando dados...")

    with c_graf2:
        st.markdown("### 🏆 Produtos Mais Vendidos")
        if log_v:
            df_v = pd.DataFrame(log_v)
            top_prods = df_v.groupby('Produto')['Qtd'].sum().sort_values(ascending=False).head(5)
            st.bar_chart(top_prods, color="#ffb400", horizontal=True)
        else: st.caption("Aguardando dados...")

elif menu == "🧪 Laudos":
    st.title("🧪 Gestão de Laudos")
    
    with st.expander("📅 Agendar Nova Coleta", expanded=True):
        with st.form("f_laudo"):
            cli_l = st.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
            c1, c2 = st.columns(2)
            data_l = c1.date_input("Data da Coleta", format="DD/MM/YYYY")
            data_r = c2.date_input("Previsão do Resultado", value=data_l + timedelta(days=7), format="DD/MM/YYYY")
            
            if st.form_submit_button("Agendar"):
                novo = {
                    'Cliente': cli_l, 
                    'Data_Coleta': data_l.strftime("%d/%m/%Y"), 
                    'Data_Resultado': data_r.strftime("%d/%m/%Y"), 
                    'Status': 'Pendente'
                }
                st.session_state['log_laudos'].append(novo)
                salvar_dados()
                st.success(f"Agendado para {data_l.strftime('%d/%m/%Y')}!")
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Editar Previsões e Status")
    
    laudos = st.session_state.get('log_laudos', [])
    laudos_ativos = [l for l in laudos if l.get('Status') != 'Arquivado']
    
    if not laudos_ativos: 
        st.info("Sem laudos ativos para editar.")
    else:
        df_p = pd.DataFrame(laudos)
        df_p['ID_Real'] = range(len(laudos))
        df_view = df_p[df_p['Status'] != 'Arquivado'].copy()

        df_view['Data_Coleta'] = pd.to_datetime(df_view['Data_Coleta'], dayfirst=True, errors='coerce')
        df_view['Data_Resultado'] = pd.to_datetime(df_view['Data_Resultado'], dayfirst=True, errors='coerce')

        ed_p = st.data_editor(
            df_view[['ID_Real', 'Cliente', 'Data_Coleta', 'Data_Resultado', 'Status']],
            use_container_width=True, hide_index=True, disabled=['ID_Real', 'Cliente'],
            column_config={
                "Data_Coleta": st.column_config.DateColumn("📅 Coleta", format="DD/MM/YYYY", step=1),
                "Data_Resultado": st.column_config.DateColumn("🧪 Previsão", format="DD/MM/YYYY", step=1),
                "Status": st.column_config.SelectboxColumn("Situação", options=["Pendente", "Em Análise", "Concluído", "Cancelado"])
            }
        )

        if st.button("💾 SALVAR ALTERAÇÕES"):
            for _, row in ed_p.iterrows():
                idx = int(row['ID_Real'])
                nova_coleta = row['Data_Coleta']
                if hasattr(nova_coleta, 'strftime'): nova_coleta = nova_coleta.strftime("%d/%m/%Y")
                nova_previsao = row['Data_Resultado']
                if hasattr(nova_previsao, 'strftime'): nova_previsao = nova_previsao.strftime("%d/%m/%Y")

                st.session_state['log_laudos'][idx]['Data_Coleta'] = str(nova_coleta)
                st.session_state['log_laudos'][idx]['Data_Resultado'] = str(nova_previsao)
                st.session_state['log_laudos'][idx]['Status'] = row['Status']
            
            salvar_dados()
            st.success("Dados atualizados!")
            st.rerun()

elif menu == "💰 Vendas & Orçamentos":
    st.title("💰 Vendas Inteligentes")
    if not st.session_state['clientes_db']: st.warning("Cadastre clientes!"); st.stop()
    
    c1, c2 = st.columns([2,1])
    cli = c1.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
    vend = c2.text_input("Vendedor", st.session_state['usuario_nome'])
    d_cli = st.session_state['clientes_db'][cli]
    
    # Blindagem Fator
    try:
        fator_cliente = float(d_cli.get('Fator', 1.0))
        if pd.isna(fator_cliente): fator_cliente = 1.0
    except: fator_cliente = 1.0
    
    if fator_cliente == 1.0:
        st.info(f"📋 Cliente **{cli}**: Tabela Padrão (Fator 1.0)")
    elif fator_cliente < 1.0:
        perc_desc = round((1.0 - fator_cliente) * 100)
        st.success(f"📉 Cliente **{cli}**: Tabela com DESCONTO de {perc_desc}% (Fator {fator_cliente})")
    else:
        perc_acres = round((fator_cliente - 1.0) * 100)
        st.warning(f"📈 Cliente **{cli}**: Tabela com ACRÉSCIMO de {perc_acres}% (Fator {fator_cliente})")
    
    col1, col2, col3 = st.columns(3)
    p_pag = col1.text_input("Plano", "28/42 DIAS"); f_pag = col2.text_input("Forma", "BOLETO ITAU"); venc = col3.text_input("Vencimento", "A COMBINAR")
    
    df_v = st.session_state['estoque'].copy()
    if 'Qtd' not in df_v.columns: df_v.insert(0, 'Qtd', 0.0)
    
    df_v['Preco_Final'] = df_v['Preco_Base'].astype(float) * fator_cliente
    
    ed_v = st.data_editor(
        df_v[['Qtd', 'Produto', 'Cod', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Preco_Final', 'Saldo']], 
        use_container_width=True, hide_index=True,
        column_config={
            "Preco_Base": st.column_config.NumberColumn("Preço Base", format="%.2f", disabled=True),
            "Preco_Final": st.column_config.NumberColumn("💵 Preço P/ Cliente", format="%.2f"),
            "Qtd": st.column_config.NumberColumn("Quantidade", step=1.0)
        }
    )
    
    itens_sel = ed_v[ed_v['Qtd'] > 0].copy()
    itens_sel['Total'] = itens_sel['Qtd'] * itens_sel['Preco_Final']
    total = itens_sel['Total'].sum()
    
    if not itens_sel.empty:
        st.divider()
        st.metric("Valor Total do Pedido", f"R$ {total:,.2f}")
        
        c_orc, c_ped = st.columns(2)
        with c_orc:
            if st.button("📄 ORÇAMENTO", use_container_width=True):
                dados_pdf = itens_sel.rename(columns={'Preco_Final': 'Unitario'}).to_dict('records')
                pdf = criar_doc_pdf(vend, cli, d_cli, dados_pdf, total, {'plano':p_pag, 'forma':f_pag, 'venc':venc}, "ORÇAMENTO")
                st.download_button("📥 Baixar Orçamento", pdf, f"Orcamento_{cli}.pdf", "application/pdf")
        
        with c_ped:
            origem = st.radio("Origem?", ["METAL QUÍMICA (Baixa Estoque)", "INDEPENDENTE (Sem Baixa)"], horizontal=True)
            if st.button("✅ FECHAR VENDA", type="primary", use_container_width=True):
                dados_pdf = itens_sel.rename(columns={'Preco_Final': 'Unitario'}).to_dict('records')
                pdf = criar_doc_pdf(vend, cli, d_cli, dados_pdf, total, {'plano':p_pag, 'forma':f_pag, 'venc':venc}, "PEDIDO")
                
                if "METAL" in origem:
                    for _, row in itens_sel.iterrows():
                        mask = st.session_state['estoque']['Cod'].astype(str) == str(row['Cod'])
                        if not st.session_state['estoque'][mask].empty:
                            idx = st.session_state['estoque'][mask].index[0]
                            atual = float(st.session_state['estoque'].at[idx, 'Saldo'] or 0)
                            st.session_state['estoque'].at[idx, 'Saldo'] = atual - float(row['Qtd'])
                    st.session_state['log_vendas'].append({'Data': obter_horario_br().strftime("%d/%m/%Y %H:%M"), 'Cliente': cli, 'Produto': 'Vários', 'Qtd': itens_sel['Qtd'].sum(), 'Vendedor': vend})
                    salvar_dados(); st.success("Venda Confirmada (Estoque Baixado)!")
                else: 
                    st.session_state['log_vendas'].append({'Data': obter_horario_br().strftime("%d/%m/%Y %H:%M"), 'Cliente': cli, 'Produto': 'Vários (Indep)', 'Qtd': itens_sel['Qtd'].sum(), 'Vendedor': vend})
                    salvar_dados(); st.success("Venda Confirmada (Sem Baixa)!")
                st.download_button("📥 Baixar Pedido", pdf, f"Pedido_{cli}.pdf", "application/pdf")

elif menu == "📥 Entrada de Estoque":
    st.title("📥 Entrada de Mercadoria")
    if st.session_state['estoque'].empty: st.warning("Cadastre produtos no estoque primeiro!"); st.stop()

    with st.form("f_ent"):
        opcoes = st.session_state['estoque'].apply(lambda x: f"{x['Cod']} - {x['Produto']}", axis=1)
        prod_sel = st.selectbox("Selecione o Produto", opcoes)
        qtd = st.number_input("Quantidade (KG)", min_value=0.0, step=1.0)
        
        if st.form_submit_button("✅ Confirmar Entrada"):
            cod = prod_sel.split(" - ")[0]
            mask = st.session_state['estoque']['Cod'].astype(str) == str(cod)
            if not st.session_state['estoque'][mask].empty:
                idx = st.session_state['estoque'][mask].index[0]
                try: saldo_atual = float(st.session_state['estoque'].at[idx, 'Saldo'])
                except: saldo_atual = 0.0
                
                novo_saldo = saldo_atual + float(qtd)
                st.session_state['estoque'].at[idx, 'Saldo'] = novo_saldo
                
                nome_prod = st.session_state['estoque'].at[idx, 'Produto']
                st.session_state['log_entradas'].append({
                    'Data': obter_horario_br().strftime("%d/%m/%Y %H:%M"),
                    'Produto': nome_prod, 'Qtd': qtd, 'Usuario': st.session_state['usuario_nome']
                })
                salvar_dados(); st.success(f"Entrada de +{qtd}Kg em {nome_prod} realizada!"); st.rerun()
            else: st.error("Erro: Produto não encontrado.")

elif menu == "📦 Estoque":
    st.title("📦 Estoque Geral & Cadastro")

    with st.expander("➕ CADASTRAR NOVO PRODUTO", expanded=False):
        with st.form("form_novo_prod"):
            st.write("📝 **Ficha do Produto**")
            c1, c2 = st.columns([1, 4])
            cod_novo = c1.text_input("Código (SKU)", placeholder="Ex: 1001")
            nome_novo = c2.text_input("Descrição do Produto", placeholder="Ex: REVELADOR RAIO-X")
            
            c3, c4, c5 = st.columns(3)
            marca_novo = c3.text_input("Marca", value="LABORTEC")
            ncm_novo = c4.text_input("NCM")
            unid_novo = c5.selectbox("Unidade", ["KG", "L", "UN", "M", "CX", "GALÃO"])
            
            c6, c7, c8 = st.columns(3)
            preco_novo = c6.number_input("💲 Preço Base (R$)", min_value=0.0, step=1.0)
            saldo_novo = c7.number_input("📦 Estoque Inicial", min_value=0.0, step=1.0)
            min_novo = c8.number_input("🚨 Estoque Mínimo", min_value=0.0, step=1.0)
            
            if st.form_submit_button("💾 SALVAR NOVO PRODUTO"):
                if cod_novo and nome_novo:
                    codigos_existentes = st.session_state['estoque']['Cod'].astype(str).values
                    if str(cod_novo) in codigos_existentes:
                        st.error("⛔ Erro: Já existe um produto com esse Código!")
                    else:
                        novo_item = {
                            "Cod": cod_novo, "Produto": nome_novo, "Marca": marca_novo,
                            "NCM": ncm_novo, "Unidade": unid_novo, "Preco_Base": preco_novo,
                            "Saldo": saldo_novo, "Estoque_Inicial": saldo_novo,
                            "Estoque_Minimo": min_novo
                        }
                        st.session_state['estoque'] = pd.concat([st.session_state['estoque'], pd.DataFrame([novo_item])], ignore_index=True)
                        salvar_dados(); st.success(f"✅ Produto '{nome_novo}' cadastrado!"); st.rerun()
                else: st.warning("⚠️ Atenção: Código e Nome são obrigatórios.")

    st.markdown("---")
    st.subheader("📦 Lista de Produtos")
    
    if not st.session_state["estoque"].empty:
        for col in ["Saldo", "Estoque_Minimo", "Preco_Base"]:
            if col in st.session_state["estoque"].columns:
                st.session_state["estoque"][col] = pd.to_numeric(st.session_state["estoque"][col], errors='coerce').fillna(0.0)
            else: st.session_state["estoque"][col] = 0.0

    def estilo_saldo(val): return 'background-color: #d4edda; color: #155724; font-weight: 900; border: 1px solid #c3e6cb'
    try: df_styled = st.session_state["estoque"].style.map(estilo_saldo, subset=["Saldo"])
    except: df_styled = st.session_state["estoque"]

    ed = st.data_editor(
        df_styled, use_container_width=True, num_rows="dynamic", key="editor_estoque_v6",
        column_config={
            "Saldo": st.column_config.NumberColumn("✅ SALDO", format="%.2f"),
            "Estoque_Minimo": st.column_config.NumberColumn("🚨 Mínimo", format="%.0f"),
            "Preco_Base": st.column_config.NumberColumn("💲 Preço", format="%.2f"),
            "Cod": st.column_config.TextColumn("Cód."),
            "Produto": st.column_config.TextColumn("Descrição", width="large"),
        }
    )
    
    if not ed.equals(st.session_state["estoque"]): 
        st.session_state["estoque"] = ed
        salvar_dados()

elif menu == "📋 Conferência Geral":
    st.title("📋 Conferência Tática")
    tab1, tab2, tab3 = st.tabs(["📊 Histórico de Vendas", "📥 Histórico de Entradas", "🧪 Gestão de Laudos"])

    with tab1:
        st.caption("Para apagar: Selecione a linha e pressione DELETE ou clique na lixeira.")
        if st.session_state.get('log_vendas'):
            df_v = pd.DataFrame(st.session_state['log_vendas'])
            vendas_editadas = st.data_editor(df_v, use_container_width=True, num_rows="dynamic", key="editor_log_vendas", hide_index=True)
            if st.button("💾 SALVAR ALTERAÇÕES (VENDAS)", type="primary"):
                st.session_state['log_vendas'] = vendas_editadas.to_dict('records')
                salvar_dados(); st.success("Atualizado!"); st.rerun()
        else: st.info("Nenhuma venda registrada.")

    with tab2:
        st.caption("Edite ou apague lançamentos errados.")
        if st.session_state.get('log_entradas'):
            df_e = pd.DataFrame(st.session_state['log_entradas'])
            entradas_editadas = st.data_editor(df_e, use_container_width=True, num_rows="dynamic", key="editor_log_entradas", hide_index=True)
            if st.button("💾 SALVAR ALTERAÇÕES (ENTRADAS)", type="primary"):
                st.session_state['log_entradas'] = entradas_editadas.to_dict('records')
                salvar_dados(); st.success("Atualizado!"); st.rerun()
        else: st.info("Nenhuma entrada registrada.")

    with tab3:
        laudos = st.session_state.get('log_laudos', [])
        pendentes = [l for l in laudos if l.get('Status') != 'Arquivado']
        arquivados = [l for l in laudos if l.get('Status') == 'Arquivado']

        st.markdown("#### ⚠️ Pendentes (Em Análise)")
        if not pendentes:

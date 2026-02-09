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
st.set_page_config(page_title="Sistema Integrado v61", layout="wide", page_icon="🧪")
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
        
        st.toast("✅ Dados Sincronizados!", icon="☁️")
    except Exception as e:
        # Se der erro, ele imprime no console do sistema mas NÃO trava a tela do usuário
        print(f"Erro silencioso ao salvar: {e}")
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
            pdf.cell(w[5], 7, f"{float(r.get('Total', 0)):.2f}", 1, 1, "R")
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
# ==============================================================================
# 6. MENU LATERAL E TEMAS
# ==============================================================================
st.sidebar.title("🛠️ MENU GERAL")
st.sidebar.success(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")

# --- SISTEMA DE AVISOS (TEXTO CORRIGIDO) ---
if 'aviso_geral' not in st.session_state: st.session_state['aviso_geral'] = ""
st.sidebar.markdown("---")
with st.sidebar.expander("📢 DEFINIR AVISO"):
    # Mudado de "Mensagem para a Tropa" para "Mensagem do Mural"
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

# Adicione "🛠️ Admin / Backup" no final da lista
menu = st.sidebar.radio("Navegar:", [
    "📊 Dashboard", 
    "🧪 Laudos", 
    "💰 Vendas & Orçamentos", 
    "📥 Entrada de Estoque", 
    "📦 Estoque", 
    "📋 Conferência Geral", 
    "👥 Clientes",
    "🛠️ Admin / Backup"  # <--- ADICIONE ISSO AQUI
])
# ==============================================================================
# 7. PÁGINAS DO SISTEMA
# ==============================================================================

# ==============================================================================
# 7. PÁGINAS DO SISTEMA
# ==============================================================================

if menu == "📊 Dashboard":
    st.markdown('<div class="centered-title">📊 Dashboard Gerencial</div>', unsafe_allow_html=True)
    
    # --- ALERTA GERAL ---
    if st.session_state['aviso_geral']:
        st.markdown(f"""
        <style>
            @keyframes pulse-red {{
                0% {{ box-shadow: 0 0 0 0 rgba(255, 23, 68, 0.7); transform: scale(1); }}
                50% {{ box-shadow: 0 0 0 10px rgba(255, 23, 68, 0); transform: scale(1.01); }}
                100% {{ box-shadow: 0 0 0 0 rgba(255, 23, 68, 0); transform: scale(1); }}
            }}
            .alert-blink {{
                background-color: #ffebee; border: 2px solid #ff1744; color: #b71c1c;
                padding: 8px 20px; border-radius: 50px; text-align: center;
                font-weight: bold; font-size: 1.1rem; margin: 0 auto 30px auto;
                width: fit-content; animation: pulse-red 2s infinite;
                display: flex; align-items: center; justify-content: center; gap: 10px;
            }}
        </style>
        <div class="alert-blink"><span>📢</span><span>{st.session_state['aviso_geral']}</span></div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    # --- RADAR DE LAUDOS (SEM REPETIÇÃO) ---
    st.markdown("<h4 style='text-align: left; color: #555; margin-bottom: 15px; padding-left: 10px; border-left: 5px solid #1e3d59;'>📡 PRÓXIMAS COLETAS (Apenas Pendentes)</h4>", unsafe_allow_html=True)

    laudos_atuais = st.session_state.get("log_laudos", [])
    
    # Filtro Estrito: Apenas Pendentes
    ativos = [l for l in laudos_atuais if str(l.get("Status", "Pendente")) == "Pendente"]

    if not ativos:
        st.success("✅ Tudo limpo! Nenhuma coleta pendente.")
    else:
        items_html = ""
        # MUDANÇA TÁTICA: Removemos o loop multiplicador. 
        # Agora a lista é exatamente o que existe.
        for l in ativos:
            cliente = html.escape(str(l.get("Cliente", "") or "Sem Nome"))
            coleta = html.escape(str(l.get("Data_Coleta", "") or "--/--"))
            resultado = html.escape(str(l.get("Data_Resultado", "") or "--/--"))

            items_html += f"""
            <div class="card">
                <div class="card-header" title="{cliente}">🏢 {cliente}</div>
                <div class="card-body">
                    <div class="data-group"><span class="label">📅 COLETA</span><span class="value-coleta">{coleta}</span></div>
                    <div class="divider"></div>
                    <div class="data-group"><span class="label">🧪 PREVISÃO</span><span class="value-result">{resultado}</span></div>
                </div>
                <div class="card-footer"><span class="status-pill">⏳ AGUARDANDO COLETA</span></div>
            </div>
            """

        # Lógica de Alinhamento:
        # Se tiver poucos itens (<= 3), centraliza na tela. Se tiver muitos, alinha a esquerda com rolagem.
        alinhamento = "center" if len(ativos) <= 3 else "flex-start"

        carousel_component = f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
            
            /* Container Flexível (Sem Animação Infinita) */
            .carousel-container {{
                display: flex;
                overflow-x: auto; /* Permite rolar se tiver muitos */
                gap: 20px;
                padding: 10px 5px 20px 5px;
                width: 100%;
                justify-content: {alinhamento}; /* Centraliza ou Alinha */
            }}
            
            /* Estiliza a barra de rolagem para ficar bonita */
            .carousel-container::-webkit-scrollbar {{ height: 8px; }}
            .carousel-container::-webkit-scrollbar-track {{ background: #f1f1f1; border-radius: 4px; }}
            .carousel-container::-webkit-scrollbar-thumb {{ background: #c1c1c1; border-radius: 4px; }}
            .carousel-container::-webkit-scrollbar-thumb:hover {{ background: #a8a8a8; }}

            .card {{ 
                min-width: 260px; /* Garante que o card não encolha */
                width: 260px; 
                background: #ffffff; 
                border-radius: 12px; 
                box-shadow: 0 4px 6px rgba(0,0,0,0.05); 
                font-family: 'Inter', sans-serif; 
                overflow: hidden; 
                border: 1px solid #e2e8f0; 
                transition: transform 0.2s; 
            }}
            
            .card:hover {{ 
                transform: translateY(-5px); 
                box-shadow: 0 15px 30px rgba(0,0,0,0.1); 
                border-color: #cbd5e1; 
            }}
            
            .card-header {{ background: linear-gradient(135deg, #1e3d59 0%, #162e44 100%); color: white; padding: 12px 15px; font-weight: 600; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-bottom: 3px solid #ffb400; }}
            .card-body {{ padding: 15px; display: flex; justify-content: space-between; align-items: center; background: #f8fafc; }}
            .data-group {{ display: flex; flex-direction: column; align-items: center; flex: 1; }}
            .divider {{ width: 1px; height: 30px; background: #cbd5e1; margin: 0 10px; }}
            .label {{ font-size: 10px; color: #64748b; font-weight: 800; letter-spacing: 0.5px; margin-bottom: 4px; }}
            .value-coleta {{ font-size: 14px; font-weight: 700; color: #334155; }}
            .value-result {{ font-size: 14px; font-weight: 700; color: #059669; }}
            .card-footer {{ background: #ffffff; padding: 10px; text-align: center; border-top: 1px solid #f1f5f9; }}
            .status-pill {{ background: #e0f2fe; color: #0369a1; font-size: 11px; font-weight: 700; padding: 4px 12px; border-radius: 20px; display: inline-block; }}
        </style>
        
        <div class="carousel-container">
            {items_html}
        </div>
        """
        components.html(carousel_component, height=230)

    # --- MÉTRICAS DE ESTOQUE ---
    st.markdown("<h4 style='text-align: left; color: #555; margin-top: 20px; border-left: 5px solid #d32f2f; padding-left: 10px;'>🚨 ESTOQUE CRÍTICO (Abaixo do Mínimo)</h4>", unsafe_allow_html=True)
    
    df_est = st.session_state.get('estoque')
    if df_est is not None and not df_est.empty:
        try:
            saldo_num = pd.to_numeric(df_est['Saldo'], errors='coerce').fillna(0)
            min_num = pd.to_numeric(df_est['Estoque_Minimo'], errors='coerce').fillna(0)
            criticos = df_est[ (saldo_num < min_num) & (min_num > 0) ].copy()
            if not criticos.empty:
                st.dataframe(criticos[['Cod', 'Produto', 'Saldo', 'Estoque_Minimo']], use_container_width=True, hide_index=True, column_config={"Saldo": st.column_config.NumberColumn("Saldo Atual", format="%.2f"), "Estoque_Minimo": st.column_config.NumberColumn("Mínimo Desejado", format="%.0f")})
            else:
                st.info("👍 Situação Regular! Nenhum produto com estoque baixo.")
        except: st.info("Dados insuficientes.")
    
    st.markdown("---")

    # --- GRÁFICOS ---
    c_graf1, c_graf2 = st.columns(2)
    with c_graf1:
        st.markdown("**📈 Volume de Vendas Diárias**")
        log_v = st.session_state.get('log_vendas', [])
        if log_v:
            df_v = pd.DataFrame(log_v)
            df_v['Dia'] = pd.to_datetime(df_v['Data'], dayfirst=True, errors='coerce').dt.date
            st.area_chart(df_v.groupby('Dia')['Qtd'].sum(), color="#004aad")
        else: st.caption("Aguardando dados...")

    with c_graf2:
        st.markdown("**🏆 Produtos Mais Vendidos**")
        if log_v:
            df_v = pd.DataFrame(log_v)
            top_prods = df_v.groupby('Produto')['Qtd'].sum().sort_values(ascending=False).head(5)
            st.bar_chart(top_prods, color="#ffb400", horizontal=True)
        else: st.caption("Aguardando dados...")
elif menu == "💰 Vendas & Orçamentos":
    st.title("💰 Vendas Inteligentes")
    if not st.session_state['clientes_db']: st.warning("Cadastre clientes!"); st.stop()
    
    # 1. Seleção do Cliente
    c1, c2 = st.columns([2,1])
    cli = c1.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
    vend = c2.text_input("Vendedor", st.session_state['usuario_nome'])
    d_cli = st.session_state['clientes_db'][cli]
    
    # 2. Resgate do Fator de Preço
    fator_cliente = float(d_cli.get('Fator', 1.0))
    
    # Mostra aviso visual com ARREDONDAMENTO CORRETO (CORREÇÃO APLICADA AQUI)
    if fator_cliente == 1.0:
        st.info(f"📋 Cliente **{cli}**: Tabela Padrão (Fator 1.0)")
    elif fator_cliente < 1.0:
        # Usamos round() para o computador arredondar 9.99 para 10
        perc_desc = round((1.0 - fator_cliente) * 100)
        st.success(f"📉 Cliente **{cli}**: Tabela com DESCONTO de {perc_desc}% (Fator {fator_cliente})")
    else:
        perc_acres = round((fator_cliente - 1.0) * 100)
        st.warning(f"📈 Cliente **{cli}**: Tabela com ACRÉSCIMO de {perc_acres}% (Fator {fator_cliente})")
    
    col1, col2, col3 = st.columns(3)
    p_pag = col1.text_input("Plano", "28/42 DIAS"); f_pag = col2.text_input("Forma", "BOLETO ITAU"); venc = col3.text_input("Vencimento", "A COMBINAR")
    
    # 3. Preparação da Tabela de Vendas
    df_v = st.session_state['estoque'].copy()
    if 'Qtd' not in df_v.columns: df_v.insert(0, 'Qtd', 0.0)
    
    # APLICAR O FATOR NO PREÇO!
    # Criamos uma coluna nova "Preco_Final" que é a Base x Fator
    df_v['Preco_Final'] = df_v['Preco_Base'].astype(float) * fator_cliente
    
    # Editor de Vendas (Mostramos o Preço Final já calculado)
    ed_v = st.data_editor(
        df_v[['Qtd', 'Produto', 'Cod', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Preco_Final', 'Saldo']], 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "Preco_Base": st.column_config.NumberColumn("Preço Base (R$)", format="%.2f", disabled=True),
            "Preco_Final": st.column_config.NumberColumn("💵 Preço P/ Cliente (R$)", format="%.2f"), # Editável se quiser ajuste manual pontual
            "Qtd": st.column_config.NumberColumn("Quantidade", step=1.0)
        }
    )
    
    # 4. Cálculo do Total (Usando o Preço Final)
    itens_sel = ed_v[ed_v['Qtd'] > 0].copy()
    itens_sel['Total'] = itens_sel['Qtd'] * itens_sel['Preco_Final']
    total = itens_sel['Total'].sum()
    
    if not itens_sel.empty:
        st.divider()
        c_tot, c_act = st.columns([1, 2])
        c_tot.metric("Valor Total do Pedido", f"R$ {total:,.2f}")
        
        c_orc, c_ped = c_act.columns(2)
        with c_orc:
            if st.button("📄 ORÇAMENTO", use_container_width=True):
                # No PDF, usamos o Preço Final como se fosse o unitário
                dados_pdf = itens_sel.rename(columns={'Preco_Final': 'Unitario'}).to_dict('records')
                pdf = criar_doc_pdf(vend, cli, d_cli, dados_pdf, total, {'plano':p_pag, 'forma':f_pag, 'venc':venc}, "ORÇAMENTO")
                st.download_button("📥 Baixar Orçamento", pdf, f"Orcamento_{cli}.pdf", "application/pdf")
        
        with c_ped:
            # Opção de Baixa
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
elif menu == "👥 Clientes":
    st.title("👥 Gestão de Clientes & Precificação")
    
    # Adicionamos o 'form_fator' na lista de campos
    campos = ['form_nome', 'form_tel', 'form_end', 'form_cnpj', 'form_cid', 'form_uf', 'form_cep', 'form_cod', 'form_fator']
    for c in campos: 
        if c not in st.session_state: 
            # O fator padrão é 1.0 (Preço normal)
            st.session_state[c] = 1.0 if c == 'form_fator' else ""

    def limpar_campos():
        for c in campos: 
            st.session_state[c] = 1.0 if c == 'form_fator' else ""

    def salvar_no_callback():
        nome = st.session_state['form_nome']
        if nome:
            st.session_state['clientes_db'][nome] = {
                'Tel': st.session_state['form_tel'], 'End': st.session_state['form_end'],
                'CNPJ': st.session_state['form_cnpj'], 'Cidade': st.session_state['form_cid'],
                'UF': st.session_state['form_uf'], 'CEP': st.session_state['form_cep'], 
                'Cod_Cli': st.session_state['form_cod'],
                # AQUI ESTÁ A MÁGICA: Salvamos o Fator
                'Fator': float(st.session_state['form_fator'])
            }
            salvar_dados(); st.toast(f"Cliente {nome} salvo com Tabela Personalizada!", icon="✅"); limpar_campos()
        else: st.toast("Erro: Nome obrigatório!", icon="❌")

    def excluir_cliente(nome):
        if nome in st.session_state['clientes_db']: del st.session_state['clientes_db'][nome]; salvar_dados(); st.toast("Removido.", icon="🗑️")

    def preparar_edicao(k, d):
        st.session_state['form_nome'] = str(k)
        st.session_state['form_tel'] = str(d.get('Tel', ''))
        st.session_state['form_end'] = str(d.get('End', ''))
        st.session_state['form_cnpj'] = str(d.get('CNPJ', ''))
        st.session_state['form_cid'] = str(d.get('Cidade', ''))
        st.session_state['form_uf'] = str(d.get('UF', ''))
        st.session_state['form_cep'] = str(d.get('CEP', ''))
        st.session_state['form_cod'] = str(d.get('Cod_Cli', ''))
        # Carrega o fator existente ou 1.0
        st.session_state['form_fator'] = float(d.get('Fator', 1.0))

    # --- FORMULÁRIO BLINDADO ---
    with st.form("form_cliente"):
        st.subheader("📝 Dados & Tabela de Preço")
        
        c1, c2 = st.columns([3, 1])
        c1.text_input("Nome / Razão Social", key="form_nome")
        c2.text_input("Cód. Cliente (Interno)", key="form_cod")
        
        c_fator, c_cnpj = st.columns([1, 2])
        # O CAMPO NOVO:
        c_fator.number_input("💲 Fator de Preço (1.0 = Normal)", min_value=0.1, max_value=5.0, step=0.05, key="form_fator", help="Ex: 0.90 dá 10% de desconto. 1.10 aumenta 10%.")
        c_cnpj.text_input("CNPJ", key="form_cnpj")
        
        c4, c5 = st.columns([1, 2])
        c4.text_input("Telefone", key="form_tel")
        c5.text_input("Endereço", key="form_end")
        
        c6, c7, c8 = st.columns([2, 1, 1])
        c6.text_input("Cidade", key="form_cid"); c7.text_input("UF", key="form_uf"); c8.text_input("CEP", key="form_cep")
        
        st.form_submit_button("💾 SALVAR DADOS", on_click=salvar_no_callback)

    st.button("🧹 Limpar / Cancelar", on_click=limpar_campos)
    
    st.markdown("---"); st.subheader("📇 Carteira de Clientes")
    if st.session_state['clientes_db']:
        busca = st.text_input("🔍 Buscar...", placeholder="Nome da empresa...")
        lista = sorted(list(st.session_state['clientes_db'].keys()))
        if busca: lista = [k for k in lista if busca.lower() in k.lower()]
        for k in lista:
            d = st.session_state['clientes_db'][k]
            fator = d.get('Fator', 1.0)
            
            # Mostra visualmente qual é a tabela do cliente
            cor_tabela = "blue" if fator == 1.0 else ("green" if fator < 1.0 else "red")
            tipo_tabela = "NORMAL" if fator == 1.0 else (f"DESC. {int((1-fator)*100)}%" if fator < 1.0 else f"ACRÉSC. {int((fator-1)*100)}%")
            
            with st.expander(f"🏢 {k} [{tipo_tabela}]"):
                col_a, col_b = st.columns(2)
                col_a.write(f"📍 {d.get('End', '')}"); col_b.write(f"📞 {d.get('Tel', '')} | CNPJ: {d.get('CNPJ', '')}")
                st.markdown(f"**Fator de Precificação:** :{cor_tabela}[{fator:.2f}]")
                
                c_edit, c_del = st.columns([1, 1])
                c_edit.button("✏️ EDITAR", key=f"ed_{k}", on_click=preparar_edicao, args=(k, d))
                c_del.button("🗑️ EXCLUIR", key=f"dl_{k}", on_click=excluir_cliente, args=(k,))
    else: st.info("Nenhum cliente cadastrado.")

elif menu == "📦 Estoque":
    st.title("📦 Estoque Geral")
    if not st.session_state["estoque"].empty:
        # Blindagem Numérica
        for col in ["Saldo", "Estoque_Minimo"]:
            if col in st.session_state["estoque"].columns:
                st.session_state["estoque"][col] = pd.to_numeric(st.session_state["estoque"][col], errors='coerce').fillna(0)
            else:
                st.session_state["estoque"][col] = 0.0

    def estilo_saldo(val): return 'background-color: #d4edda; color: #155724; font-weight: 900; border: 1px solid #c3e6cb'
    try: df_styled = st.session_state["estoque"].style.map(estilo_saldo, subset=["Saldo"])
    except: df_styled = st.session_state["estoque"]

    ed = st.data_editor(
        df_styled, use_container_width=True, num_rows="dynamic", key="editor_estoque_v5",
        column_config={
            "Saldo": st.column_config.NumberColumn("✅ SALDO (KG)", format="%.2f", step=1),
            "Estoque_Minimo": st.column_config.NumberColumn("🚨 Mínimo", format="%.0f", step=1),
            "Preco_Base": None, "Estoque_Inicial": None
        }
    )
    if not ed.equals(st.session_state["estoque"]): st.session_state["estoque"] = ed; salvar_dados()

# ==============================================================================
# 8. CONFERÊNCIA (AGORA COM ARQUIVAMENTO DE LAUDOS)
# ==============================================================================
# ==============================================================================
# 8. CONFERÊNCIA (COM PROTOCOLO DE LIMPEZA / EXCLUSÃO)
# ==============================================================================
elif menu == "📋 Conferência Geral":
    st.title("📋 Conferência Tática")
    
    # Abas para organizar
    tab1, tab2, tab3 = st.tabs(["📊 Histórico de Vendas", "📥 Histórico de Entradas", "🧪 Gestão de Laudos"])

    # --- ABA 1: VENDAS (COM EXCLUSÃO EM MASSA) ---
    with tab1:
        st.caption("Para apagar: Selecione a linha e pressione DELETE ou clique na lixeira ao lado da linha.")
        
        if st.session_state.get('log_vendas'):
            df_v = pd.DataFrame(st.session_state['log_vendas'])
            
            # Editor que permite deletar linhas (num_rows="dynamic")
            vendas_editadas = st.data_editor(
                df_v, 
                use_container_width=True, 
                num_rows="dynamic", # Isso libera a exclusão
                key="editor_log_vendas",
                hide_index=True
            )
            
            # Botão para confirmar a limpeza
            if st.button("💾 SALVAR ALTERAÇÕES (VENDAS)", type="primary"):
                st.session_state['log_vendas'] = vendas_editadas.to_dict('records')
                salvar_dados()
                st.success("Histórico de vendas atualizado!")
                st.rerun()
        else:
            st.info("Nenhuma venda registrada.")

    # --- ABA 2: ENTRADAS (COM EXCLUSÃO EM MASSA) ---
    with tab2:
        st.caption("Para corrigir lançamentos errados, edite ou apague a linha abaixo.")
        
        if st.session_state.get('log_entradas'):
            df_e = pd.DataFrame(st.session_state['log_entradas'])
            
            entradas_editadas = st.data_editor(
                df_e, 
                use_container_width=True, 
                num_rows="dynamic",
                key="editor_log_entradas",
                hide_index=True
            )
            
            if st.button("💾 SALVAR ALTERAÇÕES (ENTRADAS)", type="primary"):
                st.session_state['log_entradas'] = entradas_editadas.to_dict('records')
                salvar_dados()
                st.success("Histórico de entradas atualizado!")
                st.rerun()
        else:
            st.info("Nenhuma entrada registrada.")

    # --- ABA 3: LAUDOS (COM EXCLUSÃO DE ARQUIVO MORTO) ---
    with tab3:
        laudos = st.session_state.get('log_laudos', [])
        
        # Separa o joio do trigo
        pendentes = [l for l in laudos if l.get('Status') != 'Arquivado']
        arquivados = [l for l in laudos if l.get('Status') == 'Arquivado']

        # PARTE 1: PENDENTES (Foco em Resolver/Arquivar)
        st.markdown("#### ⚠️ Pendentes (Em Análise)")
        if not pendentes:
            st.success("Tudo limpo por aqui.")
        else:
            # Mostra pendentes apenas com opção de Arquivar
            for i, item in enumerate(laudos):
                if item.get('Status') != 'Arquivado':
                    with st.expander(f"📄 {item['Cliente']} | Coleta: {item['Data_Coleta']}"):
                        c1, c2 = st.columns([2, 1])
                        c1.write(f"**Previsão:** {item.get('Data_Resultado', '-')}")
                        link = c1.text_input("🔗 Link do PDF:", key=f"link_{i}", value=item.get('Link_Arquivo', ''))
                        
                        c2.write(""); c2.write("")
                        if c2.button("📂 ARQUIVAR", key=f"btn_arq_{i}"):
                            st.session_state['log_laudos'][i]['Status'] = 'Arquivado'
                            st.session_state['log_laudos'][i]['Link_Arquivo'] = link
                            st.session_state['log_laudos'][i]['Data_Arquivamento'] = datetime.now().strftime("%d/%m/%Y")
                            salvar_dados()
                            st.rerun()

        st.markdown("---")
        
        # PARTE 2: ARQUIVO MORTO (Foco em Excluir/Limpar)
        st.markdown(f"#### 🗄️ Arquivo Morto ({len(arquivados)})")
        st.caption("Aqui ficam os laudos antigos. Use o botão **EXCLUIR** para remover definitivamente do sistema.")

        if not arquivados:
            st.info("Arquivo morto vazio.")
        else:
            # Lista Inversa (Mais recentes primeiro) para facilitar
            for i, item in enumerate(laudos):
                if item.get('Status') == 'Arquivado':
                    # Card Vermelho Claro para indicar item velho
                    with st.expander(f"🗄️ {item['Cliente']} | Arquivado em: {item.get('Data_Arquivamento', '?')}"):
                        col_a, col_b = st.columns([3, 1])
                        
                        col_a.markdown(f"**Coleta:** {item['Data_Coleta']} | **Resultado:** {item['Data_Resultado']}")
                        if item.get('Link_Arquivo'):
                            col_a.markdown(f"🔗 [Acessar Arquivo na Nuvem]({item['Link_Arquivo']})")
                        else:
                            col_a.caption("Sem link de arquivo salvo.")

                        # BOTÃO DE EXCLUSÃO DEFINITIVA
                        col_b.write("")
                        if col_b.button("🗑️ APAGAR", key=f"del_laudo_{i}", type="primary"):
                            # Remove o item da lista principal usando o índice
                            st.session_state['log_laudos'].pop(i)
                            salvar_dados()
                            st.toast("Registro apagado do mapa!", icon="💥")
                            st.rerun()

elif menu == "📥 Entrada de Estoque":
    st.title("📥 Entrada de Mercadoria")
    
    if st.session_state['estoque'].empty: 
        st.warning("Cadastre produtos no estoque primeiro!")
        st.stop()

    with st.form("f_ent"):
        # Cria lista de opções
        opcoes = st.session_state['estoque'].apply(lambda x: f"{x['Cod']} - {x['Produto']}", axis=1)
        prod_sel = st.selectbox("Selecione o Produto", opcoes)
        qtd = st.number_input("Quantidade (KG)", min_value=0.0, step=1.0)
        
        if st.form_submit_button("✅ Confirmar Entrada"):
            # 1. Identifica o Produto
            cod = prod_sel.split(" - ")[0]
            mask = st.session_state['estoque']['Cod'].astype(str) == str(cod)
            
            if not st.session_state['estoque'][mask].empty:
                idx = st.session_state['estoque'][mask].index[0]
                
                # 2. BLINDAGEM MATEMÁTICA (Aqui estava o erro)
                # Converte o saldo atual para número na marra antes de somar
                try:
                    saldo_atual = float(st.session_state['estoque'].at[idx, 'Saldo'])
                except:
                    saldo_atual = 0.0
                
                novo_saldo = saldo_atual + float(qtd)
                
                # 3. Atualiza
                st.session_state['estoque'].at[idx, 'Saldo'] = novo_saldo
                
                # 4. Registra no Log
                nome_prod = st.session_state['estoque'].at[idx, 'Produto']
                st.session_state['log_entradas'].append({
                    'Data': obter_horario_br().strftime("%d/%m/%Y %H:%M"),
                    'Produto': nome_prod, 
                    'Qtd': qtd, 
                    'Usuario': st.session_state['usuario_nome']
                })
                
                # 5. Salva
                salvar_dados()
                st.success(f"Entrada de +{qtd}Kg em {nome_prod} realizada!")
                st.rerun()
            else:
                st.error("Erro: Produto não encontrado no índice.")
            # ==============================================================================
# 9. ÁREA RESTRITA (BACKUP E RESET)
# ==============================================================================
elif menu == "🛠️ Admin / Backup":
    st.title("🛠️ Bunker de Comando")
    st.markdown("---")

    # --- SENHA DE SEGURANÇA PARA ACESSAR O BUNKER ---
    # Só libera as funções perigosas se digitar a senha de admin
    senha_admin = st.text_input("🔑 Digite a Senha do General para liberar operações:", type="password")
    
    if senha_admin == "labormetal22": # A mesma senha do login do General
        
        st.success("🔓 Acesso Autorizado. Cuidado, General.")
        
        tab_bkp, tab_res, tab_nuc = st.tabs(["💾 SALVAR BACKUP", "♻️ RESTAURAR DADOS", "☢️ ZERAR SISTEMA"])

        # ------------------------------------------------------------------
        # 1. FAZER BACKUP (EXPORTAR)
        # ------------------------------------------------------------------
        with tab_bkp:
            st.subheader("💾 Gerar Cópia de Segurança")
            st.caption("Baixa um arquivo completo com Clientes, Estoque e Históricos.")
            
            if st.button("📦 CRIAR ARQUIVO DE BACKUP"):
                # Empacota tudo num dicionário Python
                pacote_dados = {
                    "estoque": st.session_state['estoque'].to_dict('records'),
                    "clientes": st.session_state['clientes_db'],
                    "vendas": st.session_state['log_vendas'],
                    "entradas": st.session_state['log_entradas'],
                    "laudos": st.session_state['log_laudos'],
                    "data_backup": datetime.now().strftime("%d/%m/%Y %H:%M")
                }
                
                # Converte para texto JSON
                arquivo_json = json.dumps(pacote_dados, indent=4)
                
                # Botão de Download
                data_hoje = datetime.now().strftime("%d-%m-%Y")
                st.download_button(
                    label="⬇️ BAIXAR ARQUIVO (.json)",
                    data=arquivo_json,
                    file_name=f"Backup_Sistema_V65_{data_hoje}.json",
                    mime="application/json",
                    type="primary"
                )

        # ------------------------------------------------------------------
        # 2. RESTAURAR (IMPORTAR)
        # ------------------------------------------------------------------
        with tab_res:
            st.subheader("♻️ Restaurar Dados Antigos")
            st.warning("⚠️ ATENÇÃO: Isso vai APAGAR o que está no sistema agora e substituir pelo arquivo que você enviar.")
            
            arquivo_up = st.file_uploader("Arraste o arquivo de backup (.json) aqui:", type="json")
            
            if arquivo_up is not None:
                if st.button("🔄 CONFIRMAR RESTAURAÇÃO"):
                    try:
                        dados = json.load(arquivo_up)
                        
                        # Reconstrói a memória
                        st.session_state['estoque'] = pd.DataFrame(dados['estoque'])
                        st.session_state['clientes_db'] = dados['clientes']
                        st.session_state['log_vendas'] = dados['vendas']
                        st.session_state['log_entradas'] = dados['entradas']
                        st.session_state['log_laudos'] = dados['laudos']
                        
                        # Salva na nuvem
                        salvar_dados()
                        st.balloons()
                        st.success("✅ Sistema Restaurado com Sucesso! (Pressione R para recarregar)")
                    except Exception as e:
                        st.error(f"Erro ao ler arquivo: {e}")

        # ------------------------------------------------------------------
        # 3. ZERAR TUDO (BOTÃO NUCLEAR)
        # ------------------------------------------------------------------
        with tab_nuc:
            st.subheader("☢️ ZERAR TUDO (Protocolo de Destruição)")
            st.error("⛔ PERIGO: ISSO APAGA CLIENTES, ESTOQUE, TUDO! NÃO TEM VOLTA.")
            
            confirmacao = st.text_input("Digite 'CONFIRMO' para liberar o botão:", placeholder="...")
            
            if confirmacao == "CONFIRMO":
                if st.button("💣 DETONAR / LIMPAR SISTEMA", type="primary"):
                    # Limpa as variáveis
                    st.session_state['estoque'] = pd.DataFrame(columns=['Cod', 'Produto', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Saldo', 'Estoque_Inicial', 'Estoque_Minimo'])
                    st.session_state['clientes_db'] = {}
                    st.session_state['log_vendas'] = []
                    st.session_state['log_entradas'] = []
                    st.session_state['log_laudos'] = []
                    
                    # Salva o vazio na nuvem
                    salvar_dados()
                    st.success("O terreno está limpo, General. Começando do zero.")
                    st.rerun()
            else:
                st.info("Botão travado por segurança.")

    else:
        st.info("🔒 Digite a senha administrativa acima para acessar o painel.")















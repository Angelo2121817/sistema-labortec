import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import os
from pypdf import PdfReader
from fpdf import FPDF
import json
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema Integrado v55", layout="wide", page_icon="🧪")

# --- CONEXÃO COM O GOOGLE SHEETS ---
# Essa linha é vital para o sistema funcionar
conn = st.connection("gsheets", type=GSheetsConnection)

# --- SISTEMA DE SEGURANÇA (COM ARTE VISUAL) ---
CREDENCIAIS = {
    "General": "labormetal22",
    "Fabricio": "fabricio2225",
    "Anderson": "anderson2225",
    "Angelo": "angelo2225"
}

def obter_saudacao():
    hora = (datetime.utcnow() - timedelta(hours=3)).hour
    if 5 <= hora < 12: return "Bom dia"
    elif 12 <= hora < 18: return "Boa tarde"
    else: return "Boa noite"

def verificar_senha():
    """Tela de Login com Design Labortec & Metal Química"""
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False
        st.session_state["usuario_nome"] = ""

    if not st.session_state["autenticado"]:
        # --- ARTE DA TELA DE LOGIN ---
        st.markdown("""
            <style>
                .login-container {
                    background-color: #f0f2f6;
                    padding: 30px;
                    border-radius: 15px;
                    border: 2px solid #d6d6d6;
                    text-align: center;
                    margin-bottom: 20px;
                }
                .titulo-principal {
                    color: #1f1f1f;
                    font-size: 28px;
                    font-weight: bold;
                    margin-bottom: 10px;
                }
                .sub-logos {
                    display: flex;
                    justify-content: center;
                    gap: 20px;
                    font-size: 18px;
                    font-weight: bold;
                }
                .labortec { color: #004aad; }
                .metal { color: #d35400; }
            </style>
            
            <div class="login-container">
                <div class="titulo-principal">🔐 SISTEMA INTEGRADO</div>
                <div class="sub-logos">
                    <span class="labortec">🧪 LABORTEC CONSULTORIA</span>
                    <span>|</span>
                    <span class="metal">⚙️ METAL QUÍMICA</span>
                </div>
                <p style="margin-top: 15px; color: #555;">Área Restrita aos Operadores</p>
            </div>
        """, unsafe_allow_html=True)
        
        # --- CAMPO DE SENHA ---
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
            senha = st.text_input("🔑 Digite seu Código de Acesso:", type="password")
            
            if st.button("🚀 ENTRAR NO SISTEMA", type="primary", use_container_width=True):
                usuario_encontrado = None
                for nome, senha_real in CREDENCIAIS.items():
                    if senha == senha_real:
                        usuario_encontrado = nome
                        break
                
                if usuario_encontrado:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_nome"] = usuario_encontrado
                    st.toast(f"Acesso Liberado: {usuario_encontrado}", icon="🔓")
                    st.rerun()
                else:
                    st.error("⛔ Acesso Negado: Código inválido.")
        return False
    
    return True

# --- EXECUÇÃO DO LOGIN ---
if not verificar_senha():
    st.stop()

# --- BARRA LATERAL (APÓS LOGIN) ---
if st.session_state["autenticado"]:
    try:
        st.sidebar.success(f"👋 **{obter_saudacao()}, {st.session_state['usuario_nome']}!**")
    except: pass

# --- FUNÇÕES DE BANCO DE DADOS (CARREGAR E SALVAR) ---
def carregar_dados():
    try:
        # 1. Estoque
        df_est = conn.read(worksheet="Estoque", ttl="0")
        if not df_est.empty: 
            st.session_state['estoque'] = df_est
            
        # 2. Clientes
        df_cli = conn.read(worksheet="Clientes", ttl="0")
        if not df_cli.empty: 
            st.session_state['clientes_db'] = df_cli.set_index('Nome').to_dict('index')
            
        # 3. Logs (Vendas, Entradas, Laudos)
        try:
            df_v = conn.read(worksheet="Log_Vendas", ttl="0")
            if not df_v.empty: st.session_state['log_vendas'] = df_v.to_dict('records')
        except: pass 

        try:
            df_e = conn.read(worksheet="Log_Entradas", ttl="0")
            if not df_e.empty: st.session_state['log_entradas'] = df_e.to_dict('records')
        except: pass

        try:
            df_l = conn.read(worksheet="Log_Laudos", ttl="0")
            if not df_l.empty: st.session_state['log_laudos'] = df_l.to_dict('records')
        except: pass

        return True
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        return False

def salvar_dados():
    try:
        # Salva Estoque
        conn.update(worksheet="Estoque", data=st.session_state['estoque'])
        
        # Salva Clientes
        if st.session_state.get('clientes_db'):
            df_clis = pd.DataFrame.from_dict(st.session_state['clientes_db'], orient='index').reset_index()
            df_clis.rename(columns={'index': 'Nome'}, inplace=True)
            conn.update(worksheet="Clientes", data=df_clis)
        
        # Salva Logs
        if st.session_state.get('log_vendas'):
            conn.update(worksheet="Log_Vendas", data=pd.DataFrame(st.session_state['log_vendas']))
        
        if st.session_state.get('log_entradas'):
            conn.update(worksheet="Log_Entradas", data=pd.DataFrame(st.session_state['log_entradas']))

        if st.session_state.get('log_laudos'):
            conn.update(worksheet="Log_Laudos", data=pd.DataFrame(st.session_state['log_laudos']))
            
        st.toast("💾 Salvo no Google Sheets!", icon="🚀")
    except Exception as e:
        st.warning(f"Erro ao salvar na nuvem: {e}")

# --- INICIALIZAÇÃO BLINDADA ---
if 'dados_carregados' not in st.session_state:
    st.session_state['dados_carregados'] = carregar_dados() # Tenta carregar do Google

# --- KIT DE SOBREVIVÊNCIA (Evita o KeyError) ---
if 'tabelas_precos' not in st.session_state:
    st.session_state['tabelas_precos'] = {
        'PADRAO': {},
        'REVENDA': {}
    }

if 'estoque' not in st.session_state:
    st.session_state['estoque'] = pd.DataFrame(columns=['Cod', 'Produto', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Saldo', 'Estoque_Inicial', 'Estoque_Minimo'])

if 'clientes_db' not in st.session_state:
    st.session_state['clientes_db'] = {}

if 'log_vendas' not in st.session_state: st.session_state['log_vendas'] = []
if 'log_entradas' not in st.session_state: st.session_state['log_entradas'] = []
if 'log_laudos' not in st.session_state: st.session_state['log_laudos'] = []

if not st.session_state['estoque'].empty:
    if 'Estoque_Inicial' not in st.session_state['estoque'].columns:
        st.session_state['estoque']['Estoque_Inicial'] = st.session_state['estoque']['Saldo']
    if 'Estoque_Minimo' not in st.session_state['estoque'].columns:
        st.session_state['estoque']['Estoque_Minimo'] = 0.0

if 'pdf_gerado' not in st.session_state: st.session_state['pdf_gerado'] = None
if 'nome_arquivo_pdf' not in st.session_state: st.session_state['nome_arquivo_pdf'] = "documento.pdf"

# --- GERENCIADOR DE TEMAS (AGRESSIVO) ---
def aplicar_tema(escolha):
    css = """
    <style>
        @media print {
            header, footer, aside, .stApp > header, .stApp > footer { display: none !important; }
            [data-testid="stSidebar"], [data-testid="stHeader"], .block-container button, .stDataEditor, .stFileUploader, .stExpander, .stAlert, .stMetric, .stForm, .stSelectbox, .stTextInput, .stNumberInput, .stCheckbox, .stRadio, .stImage { display: none !important; }
            .proposta-final { display: none !important; }
            body { background-color: white !important; }
        }
        [data-testid="stSidebar"] .block-container { text-align: center; align-items: center; }
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p, [data-testid="stSidebar"] label { text-align: center !important; width: 100%; }
        [data-testid="stSidebar"] div[data-baseweb="select"] { margin: 0 auto; }
        [data-testid="stSidebar"] .stRadio > div { display: flex; flex-direction: column; align-items: center; justify-content: center; }
        @keyframes blinker { 50% { opacity: 0; } }
        .blink-text { animation: blinker 1.5s linear infinite; color: #FF4B4B; font-weight: bold; }
        .scroll-container { height: 200px; overflow: hidden; position: relative; border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 10px; padding: 10px; background-color: rgba(255, 255, 255, 0.05); }
        .scroll-content { animation: scroll-up 15s linear infinite; position: absolute; width: 100%; }
        .scroll-content:hover { animation-play-state: paused; }
        @keyframes scroll-up { 0% { top: 100%; } 100% { top: -150%; } }
        .laudo-card { padding: 8px; margin-bottom: 8px; border-bottom: 1px solid rgba(128, 128, 128, 0.2); font-size: 14px; }
    """
    if escolha == "⚪ Padrão (Clean)":
        css += """
            .stApp { background-color: #FFFFFF !important; color: #000000 !important; }
            [data-testid="stSidebar"] { background-color: #F0F2F6 !important; border-right: 1px solid #D6D6D6; }
            h1, h2, h3, p, label, .stMarkdown, div { color: #000000 !important; }
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { background-color: #FFFFFF !important; color: #000000 !important; border-color: #CCCCCC !important; }
            [data-testid="stDataFrame"], [data-testid="stDataEditor"] { background-color: #FFFFFF !important; color: #000000 !important; }
        """
    elif escolha == "🔵 Azul Labortec":
        css += """
            .stApp { background-color: #F0F8FF !important; color: #002B4E !important; }
            [data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #B0C4DE; }
            h1, h2, h3, label, p { color: #002B4E !important; }
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { background-color: #FFFFFF !important; color: #002B4E !important; border: 1px solid #B0C4DE !important; }
            button[kind="primary"] { background-color: #0056b3 !important; border: none; color: white !important; }
        """
    elif escolha == "🌿 Verde Natureza":
        css += """
            .stApp { background-color: #F1F8E9 !important; color: #1B5E20 !important; }
            [data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #8BC34A; }
            h1, h2, h3, label, p { color: #1B5E20 !important; }
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { background-color: #FFFFFF !important; color: #1B5E20 !important; border: 1px solid #8BC34A !important; }
            button[kind="primary"] { background-color: #4CAF50 !important; border: none; color: white !important; }
        """
    elif escolha == "🍇 Roxo Executivo":
        css += """
            .stApp { background-color: #FAF5FB !important; color: #4A148C !important; }
            [data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #BA68C8; }
            h1, h2, h3, label, p { color: #4A148C !important; }
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { background-color: #FFFFFF !important; color: #4A148C !important; border: 1px solid #CE93D8 !important; }
            button[kind="primary"] { background-color: #8E24AA !important; border: none; color: white !important; }
        """
    elif escolha == "☕ Coffee (Sépia)":
        css += """
            .stApp { background-color: #FFF8E1 !important; color: #3E2723 !important; }
            [data-testid="stSidebar"] { background-color: #FAEBD7 !important; border-right: 1px solid #D7CCC8; }
            h1, h2, h3, label, p { color: #3E2723 !important; }
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { background-color: #FFFFFF !important; color: #3E2723 !important; border: 1px solid #8D6E63 !important; }
            button[kind="primary"] { background-color: #6D4C41 !important; border: none; color: white !important; }
        """
    elif escolha == "⚫ Dark Mode (Noturno)":
        css += """
            .stApp { background-color: #0E1117 !important; color: #FAFAFA !important; }
            [data-testid="stSidebar"] { background-color: #262730 !important; }
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div, .stDataEditor { background-color: #1c1e24 !important; color: white !important; border: 1px solid #444 !important; }
            h1, h2, h3, p, label, .stMarkdown { color: #FAFAFA !important; }
        """
    elif escolha == "🟠 Metal Industrial":
        css += """
            .stApp { background-color: #2C2C2C !important; color: #E0E0E0 !important; }
            [data-testid="stSidebar"] { background-color: #1F1F1F !important; border-right: 3px solid #FF8C00; }
            h1, h2, h3 { color: #FF8C00 !important; font-family: 'Courier New', monospace; }
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { background-color: #333 !important; color: #FF8C00 !important; border: 1px solid #FF8C00 !important; }
            button { border-radius: 0px !important; border: 1px solid #FF8C00 !important; }
        """
    elif escolha == "🌃 Cyber Dark":
        css += """
            .stApp { background-color: #000000 !important; color: #00FFFF !important; }
            [data-testid="stSidebar"] { background-color: #050505 !important; border-right: 1px solid #00FFFF; }
            h1, h2, h3 { color: #00FFFF !important; text-shadow: 0 0 5px #00FFFF; }
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { background-color: #111 !important; color: #00FFFF !important; border: 1px solid #00FFFF !important; }
            p, label, .stMarkdown { color: #E0FFFF !important; }
            button { border: 1px solid #00FFFF !important; color: #00FFFF !important; background-color: #000 !important; }
            button:hover { background-color: #00FFFF !important; color: #000 !important; }
        """
    css += "</style>"
    st.markdown(css, unsafe_allow_html=True)

# --- FUNÇÕES VISUAIS ---
def exibir_cabecalho_tela(titulo_secao, arquivo_logo, nome_empresa):
    col_img, col_txt = st.columns([1, 6])
    with col_img:
        if os.path.exists(arquivo_logo): st.image(arquivo_logo, width=130)
    with col_txt:
        st.title(titulo_secao)
        st.markdown(f"**{nome_empresa}**")
    st.markdown("---")

class PDF(FPDF):
    def header(self):
        logo_path = "labortec.jpg"
        if os.path.exists(logo_path):
            self.image(logo_path, x=10, y=2, w=55)

import streamlit as st
import pandas as pd
from datetime import datetime
import re
import os
from pypdf import PdfReader
from fpdf import FPDF
import os
import json
from streamlit_gsheets import GSheetsConnection
# --- SISTEMA DE SEGURANÇA (IDENTIFICAÇÃO POR SENHA) ---
from datetime import datetime, timedelta

# Tabela de Usuários e Senhas
# O sistema vai procurar a senha aqui e descobrir o nome sozinho
CREDENCIAIS = {
    "General": "labormetal22",
    "Fabricio": "fabricio2225",
    "Anderson": "anderson2225",
    "Angelo": "angelo2225"
}

def obter_saudacao():
    """Define se é Bom dia, Tarde ou Noite (Horário Brasil)"""
    hora = (datetime.utcnow() - timedelta(hours=3)).hour
    if 5 <= hora < 12: return "Bom dia"
    elif 12 <= hora < 18: return "Boa tarde"
    else: return "Boa noite"

def verificar_senha():
    """Tela de Login: Identifica o usuário apenas pela senha"""
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False
        st.session_state["usuario_nome"] = ""

    if not st.session_state["autenticado"]:
        st.markdown("<h2 style='text-align: center;'>🔐 Labortec - Acesso Restrito</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>Digite seu código pessoal para liberar o sistema.</p>", unsafe_allow_html=True)
        st.markdown("---")
        
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            # Apenas pede a senha
            senha_digitada = st.text_input("Senha de Acesso:", type="password")
            
            if st.button("🚀 ACESSAR", type="primary", use_container_width=True):
                usuario_encontrado = None
                
                # O DETETIVE: Procura a senha no banco de dados
                for nome, senha_real in CREDENCIAIS.items():
                    if senha_digitada == senha_real:
                        usuario_encontrado = nome
                        break # Achou! Para de procurar.
                
                if usuario_encontrado:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_nome"] = usuario_encontrado
                    st.toast(f"Identidade Confirmada: {usuario_encontrado}", icon="✅")
                    st.rerun()
                else:
                    st.error("⛔ Senha não identificada. Tente novamente.")
        return False
    
    # Se já estiver logado, mostra a saudação no menu lateral
    else:
        try:
            st.sidebar.success(f"👋 **{obter_saudacao()}, {st.session_state['usuario_nome']}!**")
        except: pass
        return True

# --- EXECUÇÃO DO LOGIN ---
if not verificar_senha():
    st.stop() # Trava o sistema aqui se não estiver logado

# --- CONFIGURAÇÃO INICIAL (ÍCONE DE QUÍMICA 🧪) ---
st.set_page_config(page_title="Sistema Integrado v55", layout="wide", page_icon="🧪")

# --- ARQUIVO DE BANCO DE DADOS ---
# --- CONEXÃO COM O GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        # Carrega Estoque
        df_est = conn.read(worksheet="Estoque", ttl="0")
        if not df_est.empty: st.session_state['estoque'] = df_est
            
        # Carrega Clientes
        df_cli = conn.read(worksheet="Clientes", ttl="0")
        if not df_cli.empty: 
            st.session_state['clientes_db'] = df_cli.set_index('Nome').to_dict('index')
            
        # Tenta carregar os Logs (Se existirem as abas)
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

        st.toast("✅ Nuvem Conectada!", icon="☁️")
        return True
    except Exception as e:
        st.error(f"Erro na conexão com Planilha: {e}")
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
    carregar_dados() # Tenta carregar do Google
    st.session_state['dados_carregados'] = True

# --- KIT DE SOBREVIVÊNCIA (Garante que nada falta) ---
# Se a tabela de preços não veio do Google, cria uma padrão agora
if 'tabelas_precos' not in st.session_state:
    st.session_state['tabelas_precos'] = {
        'PADRAO': {},
        'REVENDA': {}
    }

# Garante que as outras listas existam (caso a planilha esteja virgem)
if 'estoque' not in st.session_state:
    st.session_state['estoque'] = pd.DataFrame(columns=['Cod', 'Produto', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Saldo', 'Estoque_Inicial', 'Estoque_Minimo'])

if 'clientes_db' not in st.session_state:
    st.session_state['clientes_db'] = {}

if 'log_vendas' not in st.session_state: st.session_state['log_vendas'] = []
if 'log_entradas' not in st.session_state: st.session_state['log_entradas'] = []
if 'log_laudos' not in st.session_state: st.session_state['log_laudos'] = []

# Garante colunas vitais no estoque
if not st.session_state['estoque'].empty:
    if 'Estoque_Inicial' not in st.session_state['estoque'].columns:
        st.session_state['estoque']['Estoque_Inicial'] = st.session_state['estoque']['Saldo']
    if 'Estoque_Minimo' not in st.session_state['estoque'].columns:
        st.session_state['estoque']['Estoque_Minimo'] = 0.0

if 'pdf_gerado' not in st.session_state: st.session_state['pdf_gerado'] = None
if 'nome_arquivo_pdf' not in st.session_state: st.session_state['nome_arquivo_pdf'] = "documento.pdf"

# --- GERENCIADOR DE TEMAS (AGRESSIVO) ---
def aplicar_tema(escolha):
    # CSS BASE GLOBAL
    css = """
    <style>
        /* Ajuste de Impressão */
        @media print {
            header, footer, aside, .stApp > header, .stApp > footer { display: none !important; }
            [data-testid="stSidebar"], [data-testid="stHeader"], .block-container button, .stDataEditor, .stFileUploader, .stExpander, .stAlert, .stMetric, .stForm, .stSelectbox, .stTextInput, .stNumberInput, .stCheckbox, .stRadio, .stImage { display: none !important; }
            .proposta-final { display: none !important; }
            body { background-color: white !important; }
        }
        
        /* CENTRALIZAÇÃO TOTAL DO MENU LATERAL (SIDEBAR) */
        [data-testid="stSidebar"] .block-container {
            text-align: center;
            align-items: center;
        }
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p, [data-testid="stSidebar"] label {
            text-align: center !important;
            width: 100%;
        }
        [data-testid="stSidebar"] div[data-baseweb="select"] {
            margin: 0 auto;
        }
        [data-testid="stSidebar"] .stRadio > div {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }

        /* ANIMAÇÃO DE PISCAR */
        @keyframes blinker { 50% { opacity: 0; } }
        .blink-text { animation: blinker 1.5s linear infinite; color: #FF4B4B; font-weight: bold; }
        
        /* SCROLL CONTAINER */
        .scroll-container {
            height: 200px;
            overflow: hidden;
            position: relative;
            border: 1px solid rgba(128, 128, 128, 0.2);
            border-radius: 10px;
            padding: 10px;
            background-color: rgba(255, 255, 255, 0.05);
        }
        .scroll-content {
            animation: scroll-up 15s linear infinite;
            position: absolute;
            width: 100%;
        }
        .scroll-content:hover { animation-play-state: paused; }
        @keyframes scroll-up {
            0% { top: 100%; }
            100% { top: -150%; }
        }
        .laudo-card {
            padding: 8px;
            margin-bottom: 8px;
            border-bottom: 1px solid rgba(128, 128, 128, 0.2);
            font-size: 14px;
        }
    """
    
    # --- TEMAS CLAROS (FORÇA BRUTA BRANCA) ---
    # Aqui usamos !important em tudo para vencer o Modo Escuro do Windows
    
    if escolha == "⚪ Padrão (Clean)":
        css += """
            /* Fundo e Texto */
            .stApp { background-color: #FFFFFF !important; color: #000000 !important; }
            [data-testid="stSidebar"] { background-color: #F0F2F6 !important; border-right: 1px solid #D6D6D6; }
            h1, h2, h3, p, label, .stMarkdown, div { color: #000000 !important; }
            
            /* Inputs e Selects */
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { 
                background-color: #FFFFFF !important; 
                color: #000000 !important; 
                border-color: #CCCCCC !important;
            }
            /* Data Editor (Tabelas) */
            [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
                background-color: #FFFFFF !important;
                color: #000000 !important;
            }
        """
        
    elif escolha == "🔵 Azul Labortec":
        css += """
            .stApp { background-color: #F0F8FF !important; color: #002B4E !important; }
            [data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #B0C4DE; }
            h1, h2, h3, label, p { color: #002B4E !important; }
            
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { 
                background-color: #FFFFFF !important; 
                color: #002B4E !important; 
                border: 1px solid #B0C4DE !important;
            }
            button[kind="primary"] { background-color: #0056b3 !important; border: none; color: white !important; }
        """
        
    elif escolha == "🌿 Verde Natureza":
        css += """
            .stApp { background-color: #F1F8E9 !important; color: #1B5E20 !important; }
            [data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #8BC34A; }
            h1, h2, h3, label, p { color: #1B5E20 !important; }
            
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { 
                background-color: #FFFFFF !important; 
                color: #1B5E20 !important; 
                border: 1px solid #8BC34A !important;
            }
            button[kind="primary"] { background-color: #4CAF50 !important; border: none; color: white !important; }
        """
        
    elif escolha == "🍇 Roxo Executivo":
        css += """
            .stApp { background-color: #FAF5FB !important; color: #4A148C !important; }
            [data-testid="stSidebar"] { background-color: #FFFFFF !important; border-right: 1px solid #BA68C8; }
            h1, h2, h3, label, p { color: #4A148C !important; }
            
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { 
                background-color: #FFFFFF !important; 
                color: #4A148C !important; 
                border: 1px solid #CE93D8 !important;
            }
            button[kind="primary"] { background-color: #8E24AA !important; border: none; color: white !important; }
        """
        
    elif escolha == "☕ Coffee (Sépia)":
        css += """
            .stApp { background-color: #FFF8E1 !important; color: #3E2723 !important; }
            [data-testid="stSidebar"] { background-color: #FAEBD7 !important; border-right: 1px solid #D7CCC8; }
            h1, h2, h3, label, p { color: #3E2723 !important; }
            
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { 
                background-color: #FFFFFF !important; 
                color: #3E2723 !important; 
                border: 1px solid #8D6E63 !important;
            }
            button[kind="primary"] { background-color: #6D4C41 !important; border: none; color: white !important; }
        """

    # --- TEMAS ESCUROS (MANTÉM O DARK) ---

    elif escolha == "⚫ Dark Mode (Noturno)":
        css += """
            .stApp { background-color: #0E1117 !important; color: #FAFAFA !important; }
            [data-testid="stSidebar"] { background-color: #262730 !important; }
            
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div, .stDataEditor { 
                background-color: #1c1e24 !important; 
                color: white !important; 
                border: 1px solid #444 !important; 
            }
            h1, h2, h3, p, label, .stMarkdown { color: #FAFAFA !important; }
        """
        
    elif escolha == "🟠 Metal Industrial":
        css += """
            .stApp { background-color: #2C2C2C !important; color: #E0E0E0 !important; }
            [data-testid="stSidebar"] { background-color: #1F1F1F !important; border-right: 3px solid #FF8C00; }
            h1, h2, h3 { color: #FF8C00 !important; font-family: 'Courier New', monospace; }
            
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { 
                background-color: #333 !important; 
                color: #FF8C00 !important; 
                border: 1px solid #FF8C00 !important;
            }
            button { border-radius: 0px !important; border: 1px solid #FF8C00 !important; }
        """
        
    elif escolha == "🌃 Cyber Dark":
        css += """
            .stApp { background-color: #000000 !important; color: #00FFFF !important; }
            [data-testid="stSidebar"] { background-color: #050505 !important; border-right: 1px solid #00FFFF; }
            h1, h2, h3 { color: #00FFFF !important; text-shadow: 0 0 5px #00FFFF; }
            
            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div { 
                background-color: #111 !important; 
                color: #00FFFF !important; 
                border: 1px solid #00FFFF !important;
            }
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
            self.set_xy(70, 18)
            self.set_font('Arial', 'B', 12)
            self.cell(0, 5, 'LABORTEC CONSULTORIA', 0, 1, 'L')
            self.set_font('Arial', '', 9)
            self.set_xy(70, 24)
            self.cell(0, 5, 'Rua Alfredo Bruno, 22 - Parque da Figueira', 0, 1, 'L')
            self.set_xy(70, 29)
            self.cell(0, 5, 'Campinas/SP - CEP 13040-235', 0, 1, 'L')
            self.set_xy(70, 34)
            self.cell(0, 5, 'labortecconsultoria@gmail.com', 0, 1, 'L')
            self.set_xy(70, 39)
            self.cell(0, 5, 'Tel.: (19)3238-9320 | C.N.P.J.: 03.763.197/0001-09', 0, 1, 'L')
        else:
            self.set_font('Arial', 'B', 20)
            self.cell(0, 10, 'LABORTEC', 0, 1, 'L')
        self.line(10, 50, 200, 50)
        self.ln(45) 
    def footer(self):
        self.set_y(-25)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 4, 'Obs.: FRETE NÃO INCLUSO. PROPOSTA VÁLIDA POR 5 DIAS.', 0, 1, 'C')
        self.cell(0, 4, 'PRAZO DE RETIRADA: 3 A 5 DIAS ÚTEIS APÓS CONFIRMAÇÃO.', 0, 1, 'C')

def criar_pdf_nativo(vendedor, cliente, dados_cli, itens, total, condicoes, titulo_doc="ORÇAMENTO"):
    pdf = PDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.set_y(10)
    pdf.set_x(130)
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(70, 8, titulo_doc, 0, 1, 'R')
    pdf.set_x(130)
    pdf.set_font('Arial', '', 10)
    pdf.cell(70, 5, f'Data: {datetime.now().strftime("%d/%m/%Y")}', 0, 1, 'R')
    pdf.set_x(130)
    pdf.cell(70, 5, f'Vendedor: {vendedor}', 0, 1, 'R')
    pdf.set_y(55) 
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(0, 5, f"Cliente: {cliente} (Cód: {dados_cli.get('Cod_Cli','')})", 0, 1, 'L')
    pdf.set_font('Arial', '', 9)
    pdf.cell(0, 5, f"CNPJ: {dados_cli['CNPJ']}", 0, 1, 'L')
    pdf.cell(0, 5, f"Endereço: {dados_cli['End']}, {dados_cli['Bairro']}", 0, 1, 'L')
    pdf.cell(0, 5, f"Cidade: {dados_cli['Cidade']}/{dados_cli['UF']} - CEP: {dados_cli['CEP']}", 0, 1, 'L')
    pdf.cell(0, 5, f"Tel: {dados_cli['Tel']}", 0, 1, 'L')
    pdf.ln(5)
    pdf.set_fill_color(245, 245, 245)
    pdf.set_font('Arial', '', 9)
    pdf.cell(0, 7, f"Pagto: {condicoes['plano']} | Forma: {condicoes['forma']} | Venc: {condicoes['venc']}", 1, 1, 'L', True)
    pdf.ln(5)
    pdf.set_font('Arial', 'B', 8)
    pdf.set_fill_color(230, 230, 230)
    w = [12, 12, 85, 15, 20, 18, 18, 15] 
    h_col = ['Un', 'Qtd', 'Produto', 'Cód', 'Marca', 'NCM', 'Unit', 'Total']
    for i in range(len(h_col)): pdf.cell(w[i], 6, h_col[i], 1, 0, 'C', True)
    pdf.ln()
    pdf.set_font('Arial', '', 8)
    for r in itens:
        try: p_nome = r['Produto'].encode('latin-1', 'replace').decode('latin-1')[:55]
        except: p_nome = r['Produto'][:55]
        pdf.cell(w[0], 6, str(r['Unidade']), 1, 0, 'C')
        pdf.cell(w[1], 6, str(int(r['Qtd'])), 1, 0, 'C')
        pdf.cell(w[2], 6, p_nome, 1, 0, 'L')
        pdf.cell(w[3], 6, str(r['Cod']), 1, 0, 'C')
        pdf.cell(w[4], 6, str(r['Marca']), 1, 0, 'C')
        pdf.cell(w[5], 6, str(r['NCM']), 1, 0, 'C')
        pdf.cell(w[6], 6, f"{r['Preco']:.2f}", 1, 0, 'R')
        pdf.cell(w[7], 6, f"{r['Total']:.2f}", 1, 0, 'R')
        pdf.ln()
    pdf.ln(2)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(sum(w)-15, 8, 'TOTAL GERAL:', 0, 0, 'R')
    pdf.cell(15, 8, f"{total:,.2f}", 1, 1, 'R')
    pdf.ln(20)
    y = pdf.get_y()
    pdf.line(20, y, 90, y); pdf.line(110, y, 180, y)
    pdf.set_font('Arial', '', 8)
    pdf.set_xy(20, y+2)
    pdf.cell(70, 4, 'Assinatura Cliente', 0, 0, 'C')
    pdf.set_xy(110, y+2)
    pdf.cell(70, 4, 'Assinatura Labortec', 0, 1, 'C')
    return pdf.output(dest='S').encode('latin-1')
def extrair_dados_cetesb(f):
    """Extrai dados especificamente do layout de licenças da CETESB."""
    try:
        reader = PdfReader(f)
        text = reader.pages[0].extract_text()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        d = {
            'Nome': '', 'CNPJ': '', 'End': '', 'Bairro': '', 
            'Cidade': '', 'CEP': '', 'UF': 'SP', 'Cod_Cli': '', 'Tel': ''
        }
        
        for i, line in enumerate(lines):
            # O bloco de dados começa onde tem o CNPJ
            cnpj_m = re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', line)
            if cnpj_m:
                d['CNPJ'] = cnpj_m.group(1)
                d['Nome'] = line.replace(d['CNPJ'], '').strip()
                
                # Próxima linha: Logradouro
                if i + 1 < len(lines):
                    prox = lines[i+1]
                    cad_m = re.search(r'(\d+-\d+-\d+)', prox)
                    if cad_m:
                        d['End'] = prox.replace(cad_m.group(1), '').strip()
                    else:
                        d['End'] = prox
                
                # Linha seguinte: Número + Bairro + CEP + Cidade
                if i + 2 < len(lines):
                    addr_line = lines[i+2]
                    cep_m = re.search(r'(\d{5}-\d{3})', addr_line)
                    if cep_m:
                        d['CEP'] = cep_m.group(1)
                        partes_antes = addr_line.split(d['CEP'])[0].strip()
                        m_num_bai = re.match(r'(\d+)\s+(.*)', partes_antes)
                        if m_num_bai:
                            d['End'] = f"{d['End']}, {m_num_bai.group(1)}"
                            d['Bairro'] = m_num_bai.group(2).strip()
                        d['Cidade'] = addr_line.split(d['CEP'])[-1].strip()
                break
        return d
    except Exception as e:
        return None
def ler_pdf_antigo(f):
    try:
        reader = PdfReader(f)
        # Lê a primeira página para checar se é CETESB
        texto_inicial = reader.pages[0].extract_text() or ""
        
        if "CETESB" in texto_inicial.upper():
            return extrair_dados_cetesb(f)
            
        # Se não for CETESB, segue com a sua lógica original abaixo:
        text = ""
        for p in reader.pages:
            t = p.extract_text()
            if t: text += t + "\n"
        clean = re.sub(r'\s+', ' ', text).strip()
        idx_inicio = clean.lower().find("cliente")
        core = clean[idx_inicio:] if idx_inicio != -1 else clean
        d = {'Nome':'', 'Cod_Cli':'', 'End':'', 'CEP':'', 'Bairro':'', 'Cidade':'', 'UF':'', 'CNPJ':'', 'Tel':''}
        def extract(key, stops):
            try:
                match = re.search(re.escape(key) + r'[:\s]*', core, re.IGNORECASE)
                if not match: return ""
                start_idx = match.end()
                fragment = core[start_idx:]
                min_idx = len(fragment)
                for stop in stops:
                    stop_match = re.search(re.escape(stop), fragment, re.IGNORECASE)
                    if stop_match and stop_match.start() < min_idx: min_idx = stop_match.start()
                return fragment[:min_idx].strip(" :/-|").strip()
            except: return ""
        d['Nome'] = extract("Cliente", ["CNPJ", "CPF", "Endereço", "Data:", "Código:"])
        d['Nome'] = re.sub(r'\d{2}/\d{2}/\d{4}', '', d['Nome']).strip().split("Vendedor")[0].strip()
        cm = re.search(r'Cód(?:igo)?[:\s]*(\d+)', core, re.IGNORECASE)
        if cm: d['Cod_Cli'] = cm.group(1)
        raw_end = extract("Endereço", ["Bairro", "Cidade", "Cep", "CNPJ", "Pagto"])
        raw_bairro = extract("Bairro", ["Cidade", "Cep", "CNPJ", "Tel", "CPF"])
        if not raw_bairro and " - " in raw_end:
            partes = raw_end.split(" - ")
            d['End'] = partes[0].strip(); d['Bairro'] = partes[1].strip()
        else: d['End'] = raw_end; d['Bairro'] = raw_bairro
        d['Cidade'] = extract("Cidade", ["/", "-", "Cep", "UF", "CNPJ", "Tel"])
        um = re.search(r'Cidade.*?[:\s].*?[-/]\s*([A-Z]{2})', core, re.IGNORECASE)
        if um: d['UF'] = um.group(1)
        cpm = re.search(r'(\d{5}-\d{3})', core) or re.search(r'(\d{2}\.\d{3}-\d{3})', core)
        if cpm: d['CEP'] = cpm.group(1)
        cnm = re.search(r'(\d{2}\.\d{3}\.\d.3/\d{4}-\d{2})', core)
        if cnm: d['CNPJ'] = cnm.group(1)
        d['Tel'] = extract("Tel", ["Pagto", "Forma", "Venc", "Email", "Un", "Qtd"])
        return d
    except Exception as e: 
        st.error(f"Erro: {e}")
        return None

    try:
        reader = PdfReader(f)
        text = ""
        for p in reader.pages:
            t = p.extract_text()
            if t: text += t + "\n"
        clean = re.sub(r'\s+', ' ', text).strip()
        idx_inicio = clean.lower().find("cliente")
        core = clean[idx_inicio:] if idx_inicio != -1 else clean
        d = {'Nome':'', 'Cod_Cli':'', 'End':'', 'CEP':'', 'Bairro':'', 'Cidade':'', 'UF':'', 'CNPJ':'', 'Tel':''}
        def extract(key, stops):
            try:
                match = re.search(re.escape(key) + r'[:\s]*', core, re.IGNORECASE)
                if not match: return ""
                start_idx = match.end()
                fragment = core[start_idx:]
                min_idx = len(fragment)
                for stop in stops:
                    stop_match = re.search(re.escape(stop), fragment, re.IGNORECASE)
                    if stop_match and stop_match.start() < min_idx: min_idx = stop_match.start()
                return fragment[:min_idx].strip(" :/-|").strip()
            except: return ""
        d['Nome'] = extract("Cliente", ["CNPJ", "CPF", "Endereço", "Data:", "Código:"])
        d['Nome'] = re.sub(r'\d{2}/\d{2}/\d{4}', '', d['Nome']).strip().split("Vendedor")[0].strip()
        cm = re.search(r'Cód(?:igo)?[:\s]*(\d+)', core, re.IGNORECASE)
        if cm: d['Cod_Cli'] = cm.group(1)
        raw_end = extract("Endereço", ["Bairro", "Cidade", "Cep", "CNPJ", "Pagto"])
        raw_bairro = extract("Bairro", ["Cidade", "Cep", "CNPJ", "Tel", "CPF"])
        if not raw_bairro and " - " in raw_end:
            partes = raw_end.split(" - ")
            d['End'] = partes[0].strip(); d['Bairro'] = partes[1].strip()
        else: d['End'] = raw_end; d['Bairro'] = raw_bairro
        d['Cidade'] = extract("Cidade", ["/", "-", "Cep", "UF", "CNPJ", "Tel"])
        um = re.search(r'Cidade.*?[:\s].*?[-/]\s*([A-Z]{2})', core, re.IGNORECASE)
        if um: d['UF'] = um.group(1)
        cpm = re.search(r'(\d{5}-\d{3})', core) or re.search(r'(\d{2}\.\d{3}-\d{3})', core)
        if cpm: d['CEP'] = cpm.group(1)
        cnm = re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', core)
        if cnm: d['CNPJ'] = cnm.group(1)
        d['Tel'] = extract("Tel", ["Pagto", "Forma", "Venc", "Email", "Un", "Qtd"])
        return d
    except Exception as e: st.error(f"Erro: {e}"); return None

# --- SIDEBAR & MENU ---
st.sidebar.title("MENU GERAL")
st.sidebar.markdown("---")
st.sidebar.subheader("🎨 Personalizar Tela")
tema_padrao = st.session_state.get('tema_atual', "⚪ Padrão (Clean)")
opcoes_temas = ["⚪ Padrão (Clean)", "🔵 Azul Labortec", "🌿 Verde Natureza", "🍇 Roxo Executivo", "☕ Coffee (Sépia)", "⚫ Dark Mode (Noturno)", "🟠 Metal Industrial", "🌃 Cyber Dark"]
idx_tema = opcoes_temas.index(tema_padrao) if tema_padrao in opcoes_temas else 0
tema = st.sidebar.selectbox("Escolha o visual:", opcoes_temas, index=idx_tema, key='tema_selecionado_box')
if tema != st.session_state.get('tema_atual'):
    st.session_state['tema_atual'] = tema
    salvar_dados()
    st.rerun()
aplicar_tema(tema)

page = st.sidebar.radio("Navegar:", ["📊 DASHBOARD", "LAUDOS", "VENDAS (Labortec)", "ENTRADA DE ESTOQUE", "ESTOQUE (Metal Química)", "🚨 DEFINIR MÍNIMOS", "CONFERÊNCIA", "TABELAS DE PREÇO", "CLIENTES"])

# ==============================================================================
# DASHBOARD
# ==============================================================================
if page == "📊 DASHBOARD":
    st.markdown("<h1 style='text-align: center;'>⚗️ Central de Inteligência: Labortec & Metal Química</h1>", unsafe_allow_html=True)
    st.markdown("---")
    
    # 1. Painel de Laudos (Com Pisca ou Scroll)
    st.markdown("<h3 style='text-align: center;'>📅 Próximas Coletas de Efluente para Análise</h3>", unsafe_allow_html=True)
    laudos = st.session_state.get('log_laudos', [])
    
    if not laudos:
        st.info("Nenhuma coleta agendada.")
    else:
        try:
            laudos.sort(key=lambda x: datetime.strptime(x['Data_Coleta'], "%d/%m/%Y"))
        except: pass

        if len(laudos) <= 4:
            cols = st.columns(len(laudos))
            for i, l in enumerate(laudos):
                with cols[i]:
                    st.markdown(f"""
                    <div style='border:1px solid #ddd; padding:10px; border-radius:10px; text-align:center;'>
                        <div style='font-size:12px;'>CLIENTE</div>
                        <div style='font-weight:bold;'>{l['Cliente']}</div>
                        <hr style='margin:5px 0;'>
                        <div style='font-size:12px;'>DATA PREVISTA</div>
                        <div class='blink-text'>{l['Data_Coleta']}</div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            items_html = ""
            for l in laudos:
                cli = l['Cliente']
                data = l['Data_Coleta']
                items_html += f"<div class='laudo-card'><div class='laudo-cli'>{cli}</div><div class='laudo-data'>Coleta prevista: <span class='blink-text'>{data}</span></div></div>"
            
            st.markdown(f"""
            <div class='scroll-container'>
                <div class='scroll-content'>
                    {items_html}
                    {items_html}
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    
    log_vendas = st.session_state['log_vendas']
    log_entradas = st.session_state['log_entradas']
    total_saida_qtd = sum(item['Qtd'] for item in log_vendas)
    total_entrada_qtd = sum(item['Qtd'] for item in log_entradas)
    
    c1, c2 = st.columns(2)
    c1.metric("📦 Total Vendido (Geral)", f"{total_saida_qtd:,.1f} KG")
    c2.metric("📥 Total Reposição (Geral)", f"{total_entrada_qtd:,.1f} KG")
    
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.subheader("📈 Vendas por Dia")
        if log_vendas:
            df_vendas = pd.DataFrame(log_vendas)
            df_vendas['Data_Dt'] = pd.to_datetime(df_vendas['Data'], format="%d/%m/%Y %H:%M")
            df_vendas['Dia'] = df_vendas['Data_Dt'].dt.date
            vendas_dia = df_vendas.groupby('Dia')['Qtd'].sum()
            st.bar_chart(vendas_dia)
        else: st.info("Sem dados.")
    with col_g2:
        st.subheader("🏆 Produtos Mais Vendidos")
        if log_vendas:
            df_vendas = pd.DataFrame(log_vendas)
            top_produtos = df_vendas.groupby('Produto')['Qtd'].sum().sort_values(ascending=False).head(5)
            st.bar_chart(top_produtos, horizontal=True)
        else: st.info("Sem dados.")

# ==============================================================================
# LAUDOS (AGORA COM EXCLUSÃO)
# ==============================================================================
elif page == "LAUDOS":
    exibir_cabecalho_tela("Agendamento de Laudos", "labortec.jpg", "LABORTEC CONSULTORIA")
    st.info("📅 Agende aqui a estimativa de coleta para os laudos dos clientes.")
    
    clis = list(st.session_state['clientes_db'].keys())
    if not clis:
        st.warning("Cadastre clientes primeiro na aba 'CLIENTES'.")
    else:
        with st.form("form_laudo"):
            c1, c2 = st.columns(2)
            cli_sel = c1.selectbox("Selecione o Cliente:", clis)
            data_coleta = c2.date_input("Estimativa de Coleta:", format="DD/MM/YYYY")
            
            if st.form_submit_button("💾 Agendar Coleta"):
                novo_laudo = {
                    "Cliente": cli_sel,
                    "Data_Coleta": data_coleta.strftime("%d/%m/%Y"),
                    "Data_Registro": datetime.now().strftime("%d/%m/%Y %H:%M")
                }
                st.session_state['log_laudos'].append(novo_laudo)
                salvar_dados()
                st.success(f"Coleta agendada para {cli_sel} em {data_coleta.strftime('%d/%m/%Y')}")
    
    st.write("---")
    st.subheader("📋 Gerenciar Coletas (Selecione e Apague)")
    
    if st.session_state['log_laudos']:
        df_laudos = pd.DataFrame(st.session_state['log_laudos'])
        edited_laudos = st.data_editor(
            df_laudos,
            use_container_width=True,
            num_rows="dynamic", 
            key="editor_laudos"
        )
        if not edited_laudos.equals(df_laudos):
            st.session_state['log_laudos'] = edited_laudos.to_dict('records')
            salvar_dados()
            st.rerun()
    else:
        st.caption("Nenhum agendamento ativo.")

# ==============================================================================
# ENTRADA DE ESTOQUE
# ==============================================================================
elif page == "ENTRADA DE ESTOQUE":
    exibir_cabecalho_tela("Entrada de Mercadoria", "metal.jpg", "METAL QUÍMICA")
    st.info("📦 Registre aqui a chegada de produtos. Isso somará ao saldo atual.")
    c1,c2,c3 = st.columns([3,1,1])
    opcoes = st.session_state['estoque'].apply(lambda x: f"{x['Cod']} - {x['Produto']}", axis=1)
    prod = c1.selectbox("Produto:", opcoes)
    qtd = c2.number_input("Qtd (KG):", min_value=0.0)
    if c3.button("📥 Confirmar", type="primary") and qtd > 0:
        cod = prod.split(" - ")[0]
        idx = st.session_state['estoque'][st.session_state['estoque']['Cod']==cod].index[0]
        st.session_state['estoque'].at[idx, 'Saldo'] += qtd
        nome = st.session_state['estoque'].at[idx, 'Produto']
        st.session_state['log_entradas'].append({'Data': datetime.now().strftime("%d/%m/%Y %H:%M"), 'Produto': nome, 'Cod': cod, 'Qtd': qtd})
        salvar_dados()
        st.success(f"Entrada de {qtd} KG em {nome}!")
        st.rerun()

# ==============================================================================
# DEFINIR MÍNIMOS
# ==============================================================================
elif page == "🚨 DEFINIR MÍNIMOS":
    exibir_cabecalho_tela("Configurar Alertas de Estoque", "metal.jpg", "METAL QUÍMICA")
    st.info("💡 Defina abaixo qual a quantidade mínima para cada produto.")
    edited_min = st.data_editor(
        st.session_state['estoque'][['Cod', 'Produto', 'Unidade', 'Saldo', 'Estoque_Minimo']],
        key="editor_minimos",
        column_config={
            "Cod": st.column_config.TextColumn(disabled=True),
            "Produto": st.column_config.TextColumn(disabled=True),
            "Unidade": st.column_config.TextColumn(disabled=True),
            "Saldo": st.column_config.NumberColumn("Saldo Atual", disabled=True),
            "Estoque_Minimo": st.column_config.NumberColumn("⚠️ Mínimo (Editar)", required=True, min_value=0.0)
        },
        use_container_width=True, hide_index=True
    )
    if st.button("💾 Salvar Configuração de Alertas"):
        for i, row in edited_min.iterrows():
            idx = st.session_state['estoque'][st.session_state['estoque']['Cod'] == row['Cod']].index[0]
            st.session_state['estoque'].at[idx, 'Estoque_Minimo'] = row['Estoque_Minimo']
        salvar_dados()
        st.success("Limites de estoque atualizados com sucesso!")

# ==============================================================================
# ESTOQUE
# ==============================================================================
elif page == "ESTOQUE (Metal Química)":
    exibir_cabecalho_tela("Estoque & Produtos", "metal.jpg", "METAL QUÍMICA")
    criticos = st.session_state['estoque'][st.session_state['estoque']['Saldo'] <= st.session_state['estoque']['Estoque_Minimo']]
    if not criticos.empty:
        st.error(f"🚨 ALERTA: {len(criticos)} PRODUTOS COM ESTOQUE BAIXO OU ZERADO!")
        with st.expander("Ver Itens Críticos", expanded=True):
            st.dataframe(criticos[['Cod', 'Produto', 'Saldo', 'Estoque_Minimo']], use_container_width=True)
        st.markdown("---")

    with st.expander("➕ CADASTRAR NOVO PRODUTO", expanded=False):
        with st.form("add_prod"):
            c1, c2, c3 = st.columns([1, 3, 1])
            n_cod = c1.text_input("Código")
            n_nome = c2.text_input("Nome do Produto")
            n_un = c3.text_input("Unidade", "KG")
            c4, c5, c6 = st.columns(3)
            n_marca = c4.text_input("Marca", "LABORTEC")
            n_ncm = c5.text_input("NCM")
            n_preco = c6.number_input("Preço Base (R$)", min_value=0.0, format="%.2f")
            n_saldo = st.number_input("Estoque Inicial (KG)", min_value=0.0)
            if st.form_submit_button("💾 Salvar Produto"):
                if n_cod and n_nome:
                    novo = pd.DataFrame([{'Cod': n_cod, 'Produto': n_nome, 'Marca': n_marca, 'NCM': n_ncm, 'Unidade': n_un, 'Preco_Base': n_preco, 'Saldo': n_saldo, 'Estoque_Inicial': n_saldo, 'Estoque_Minimo': 0.0}])
                    st.session_state['estoque'] = pd.concat([st.session_state['estoque'], novo], ignore_index=True)
                    salvar_dados()
                    st.success(f"Produto '{n_nome}' cadastrado!")
                    st.rerun()
                else: st.error("Código e Nome obrigatórios.")
    st.write("---")
    st.info("📝 Edite diretamente na tabela abaixo:")
    edited_df = st.data_editor(
        st.session_state['estoque'],
        num_rows="dynamic",
        column_config={
            "Cod": st.column_config.TextColumn("Código"),
            "Produto": st.column_config.TextColumn("Nome", width="large"),
            "Preco_Base": st.column_config.NumberColumn("Preço Base", format="R$ %.2f"),
            "Saldo": st.column_config.NumberColumn("Saldo Atual (KG)", format="%.1f"),
            "Estoque_Inicial": st.column_config.NumberColumn("Estoque Inicial", format="%.1f"),
            "Estoque_Minimo": st.column_config.NumberColumn("Mínimo", format="%.1f"),
            "Unidade": st.column_config.TextColumn("Un", width="small")
        },
        use_container_width=True
    )
    if not edited_df.equals(st.session_state['estoque']):
        st.session_state['estoque'] = edited_df
        salvar_dados()
        st.toast("Estoque salvo!", icon="💾")

# ==============================================================================
# CONFERÊNCIA
# ==============================================================================
elif page == "CONFERÊNCIA":
    exibir_cabecalho_tela("Auditoria de Estoque", "metal.jpg", "METAL QUÍMICA")
    st.markdown("### 📊 Conferência: Vendas vs Estoque")
    
    df_conf = st.session_state['estoque'].copy()
    
    vendas_por_produto = {}
    for venda in st.session_state['log_vendas']:
        cod = venda['Cod']
        vendas_por_produto[cod] = vendas_por_produto.get(cod, 0) + venda['Qtd']
        
    entradas_por_produto = {}
    for entrada in st.session_state['log_entradas']:
        cod = entrada['Cod']
        entradas_por_produto[cod] = entradas_por_produto.get(cod, 0) + entrada['Qtd']
        
    df_conf['Vendas_MQ'] = df_conf['Cod'].map(vendas_por_produto).fillna(0)
    df_conf['Entradas_MQ'] = df_conf['Cod'].map(entradas_por_produto).fillna(0)
    df_conf['Saldo_Esperado'] = df_conf['Estoque_Inicial'] + df_conf['Entradas_MQ'] - df_conf['Vendas_MQ']
    df_conf['Diferenca'] = df_conf['Saldo'] - df_conf['Saldo_Esperado']
    
    def status_auditoria(diff):
        if abs(diff) < 0.01: return "✅ OK"
        elif diff > 0: return f"⚠️ SOBRA (+{diff:.1f})"
        else: return f"🚨 FALTA ({diff:.1f})"
    df_conf['Status'] = df_conf['Diferenca'].apply(status_auditoria)
    
    st.dataframe(
        df_conf[['Cod', 'Produto', 'Estoque_Inicial', 'Entradas_MQ', 'Vendas_MQ', 'Saldo_Esperado', 'Saldo', 'Status']],
        column_config={
            "Estoque_Inicial": st.column_config.NumberColumn("Inicial"),
            "Entradas_MQ": st.column_config.NumberColumn("➕ Entradas"),
            "Vendas_MQ": st.column_config.NumberColumn("➖ Vendas"),
            "Saldo_Esperado": st.column_config.NumberColumn("🟰 Deveria"),
            "Saldo": st.column_config.NumberColumn("Tem (Real)"),
        },
        use_container_width=True, hide_index=True
    )
    
    st.markdown("---")
    st.subheader("🔐 Painel de Correção de Estoque")
    c_pass, c_info = st.columns([1,2])
    senha = c_pass.text_input("Senha de Administrador:", type="password")
    
    if senha == "BOLSONARO":
        st.success("ACESSO PERMITIDO: Edição Habilitada")
        st.info("⚠️ Cuidado: Alterar aqui muda o estoque oficial.")
        edited_audit = st.data_editor(
            st.session_state['estoque'],
            key="editor_auditoria",
            column_config={
                "Cod": st.column_config.TextColumn(disabled=True),
                "Produto": st.column_config.TextColumn(disabled=True),
                "Saldo": st.column_config.NumberColumn("Saldo Real (Editar)", required=True),
                "Estoque_Inicial": st.column_config.NumberColumn("Inicial (Editar)", required=True)
            },
            use_container_width=True
        )
        if not edited_audit.equals(st.session_state['estoque']):
            st.session_state['estoque'] = edited_audit
            salvar_dados()
            st.rerun()
    elif senha:
        st.error("Senha Incorreta.")
    
    st.write("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 📤 Histórico de Saídas")
        if st.session_state['log_vendas']:
            st.dataframe(pd.DataFrame(st.session_state['log_vendas']).iloc[::-1], use_container_width=True, hide_index=True)
        else: st.caption("Vazio")
    with c2:
        st.markdown("#### 📥 Histórico de Entradas")
        if st.session_state['log_entradas']:
            st.dataframe(pd.DataFrame(st.session_state['log_entradas']).iloc[::-1], use_container_width=True, hide_index=True)
        else: st.caption("Vazio")

# ==============================================================================
# TABELAS DE PREÇO
# ==============================================================================
elif page == "TABELAS DE PREÇO":
    exibir_cabecalho_tela("Tabelas de Preço", "labortec.jpg", "LABORTEC CONSULTORIA")
    with st.expander("➕ Nova Tabela"):
        nova = st.text_input("Nome")
        if st.button("Criar") and nova and nova not in st.session_state['tabelas_precos']:
            st.session_state['tabelas_precos'][nova] = st.session_state['tabelas_precos']['PADRAO'].copy()
            salvar_dados()
            st.rerun()
    tabelas = list(st.session_state['tabelas_precos'].keys())
    sel = st.selectbox("Editar:", tabelas)
    if sel != "PADRAO" and st.button("Excluir"): 
        del st.session_state['tabelas_precos'][sel]
        salvar_dados()
        st.rerun()
    df_p = st.session_state['estoque'][['Cod','Produto']].copy()
    def get_p(c): return st.session_state['tabelas_precos'][sel].get(c, 0.0)
    df_p['Preco'] = df_p['Cod'].apply(get_p)
    ed = st.data_editor(df_p, use_container_width=True)
    if st.button("Salvar"):
        for _,r in ed.iterrows(): st.session_state['tabelas_precos'][sel][r['Cod']] = r['Preco']
        salvar_dados()
        st.success("Salvo!")

# ==============================================================================
# CLIENTES
# ==============================================================================
elif page == "CLIENTES":
    exibir_cabecalho_tela("Clientes", "labortec.jpg", "LABORTEC CONSULTORIA")
    with st.expander("Importar PDF"):
        up = st.file_uploader("PDF", type="pdf")
        if up and st.button("Ler"):
            d = ler_pdf_antigo(up)
            if d: st.session_state['temp'] = d; st.success("Dados lidos!")
            else: st.error("Erro leitura")
    if 'temp' not in st.session_state: st.session_state['temp'] = {k:'' for k in ['Cod_Cli','Nome','CNPJ','End','Bairro','Cidade','UF','CEP','Tel']}
    with st.form("cli"):
        st.write("Dados:")
        c1,c2 = st.columns([1,3])
        cod = c1.text_input("Cód", st.session_state['temp'].get('Cod_Cli',''))
        nom = c2.text_input("Nome", st.session_state['temp'].get('Nome',''))
        tabs = list(st.session_state['tabelas_precos'].keys())
        idx = 0
        if st.session_state['temp'].get('Tabela') in tabs: idx = tabs.index(st.session_state['temp'].get('Tabela'))
        tb = st.selectbox("Tabela", tabs, index=idx)
        cnpj = st.text_input("CNPJ", st.session_state['temp'].get('CNPJ',''))
        end = st.text_input("Endereço", st.session_state['temp'].get('End',''))
        bai = st.text_input("Bairro", st.session_state['temp'].get('Bairro',''))
        c3,c4,c5 = st.columns(3)
        cid = c3.text_input("Cidade", st.session_state['temp'].get('Cidade',''))
        uf = c4.text_input("UF", st.session_state['temp'].get('UF',''))
        tel = c5.text_input("Tel", st.session_state['temp'].get('Tel',''))
        cep = st.text_input("CEP", st.session_state['temp'].get('CEP',''))
        if st.form_submit_button("Salvar"):
            st.session_state['clientes_db'][nom] = {'Cod_Cli':cod,'CNPJ':cnpj,'End':end,'Bairro':bai,'Cidade':cid,'UF':uf,'CEP':cep,'Tel':tel,'Tabela':tb}
            salvar_dados()
            st.success("Salvo")
    for n in st.session_state['clientes_db']:
        c1,c2 = st.columns([4,1])
        c1.text(n)
        if c2.button("🗑️", key=n): 
            del st.session_state['clientes_db'][n]
            salvar_dados()
            st.rerun()

# ==============================================================================
# VENDAS
# ==============================================================================
else:
    exibir_cabecalho_tela("Vendas", "labortec.jpg", "LABORTEC CONSULTORIA")
    clis = list(st.session_state['clientes_db'].keys())
    if not clis: st.warning("Sem clientes"); st.stop()
    c1,c2,c3 = st.columns([2,1,1])
    cli_sel = c1.selectbox("Cliente", clis)
    vend = c2.text_input("Vendedor", "15- ANTONIO NETO")
    d_cli = st.session_state['clientes_db'][cli_sel]
    tab = d_cli.get('Tabela','PADRAO')
    if tab not in st.session_state['tabelas_precos']: tab = 'PADRAO'
    st.info(f"Tabela: {tab}")
    cc1,cc2,cc3 = st.columns(3)
    p_pag = cc1.text_input("Plano", "28/42 DIAS")
    f_pag = cc2.text_input("Forma", "BOLETO ITAU")
    venc = cc3.text_input("Venc.", "A COMBINAR")
    df_v = st.session_state['estoque'].copy()
    def get_p(c): return st.session_state['tabelas_precos'][tab].get(c, 0.0) or st.session_state['estoque'].loc[st.session_state['estoque']['Cod']==c,'Preco_Base'].values[0]
    df_v['Preco'] = df_v['Cod'].apply(get_p)
    if 'Qtd' not in df_v: df_v.insert(0,'Qtd',0)
    ed = st.data_editor(df_v, use_container_width=True)
    ed['Qtd'] = pd.to_numeric(ed['Qtd'], errors='coerce').fillna(0)
    itens = ed[ed['Qtd']>0].copy()
    itens['Total'] = itens['Qtd']*itens['Preco']
    total = itens['Total'].sum()
    if not itens.empty:
        st.metric("Total", f"R$ {total:,.2f}")
        c_blue, c_green = st.columns(2)
        with c_blue:
            if st.button("📄 ORÇAMENTO", type="primary"):
                pdf = criar_pdf_nativo(vend, cli_sel, d_cli, itens.to_dict('records'), total, {'plano':p_pag,'forma':f_pag,'venc':venc}, "ORÇAMENTO")
                st.session_state['pdf_gerado'] = pdf; st.session_state['name'] = "Orcamento.pdf"
        with c_green:
            origem = st.radio("Entrega?", ["METAL QUÍMICA", "INDEPENDENTE"])
            if st.button("✅ CONFIRMAR"):
                pdf = criar_pdf_nativo(vend, cli_sel, d_cli, itens.to_dict('records'), total, {'plano':p_pag,'forma':f_pag,'venc':venc}, "PEDIDO")
                st.session_state['pdf_gerado'] = pdf; st.session_state['name'] = "Pedido.pdf"
                if origem == "METAL QUÍMICA":
                    for _,r in itens.iterrows():
                        idx = st.session_state['estoque'][st.session_state['estoque']['Cod']==r['Cod']].index[0]
                        st.session_state['estoque'].at[idx,'Saldo'] -= r['Qtd']
                        st.session_state['log_vendas'].append({
                            'Data': datetime.now().strftime("%d/%m/%Y %H:%M"),
                            'Cliente': cli_sel,
                            'Cod': r['Cod'],
                            'Produto': r['Produto'],
                            'Qtd': r['Qtd']
                        })
                    salvar_dados()
                    st.success("Baixado!")
                else: st.success("Venda Independente Registrada (Sem baixa no estoque Metal Química).")
        if st.session_state['pdf_gerado']:
            st.download_button("📥 PDF", st.session_state['pdf_gerado'], st.session_state.get('name', 'doc.pdf'), "application/pdf")








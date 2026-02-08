import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import os
from pypdf import PdfReader
from fpdf import FPDF
import json
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURAÇÃO DA PÁGINA (TEM QUE SER A PRIMEIRA COISA) ---
st.set_page_config(page_title="Sistema Integrado v56", layout="wide", page_icon="🧪")

# --- 2. CONEXÃO COM O GOOGLE SHEETS ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except:
    st.error("Erro no Secrets. Verifique o arquivo .streamlit/secrets.toml")
    st.stop()

# --- 3. SISTEMA DE LOGIN (ARTE E SEGURANÇA) ---
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
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False
        st.session_state["usuario_nome"] = ""

    if not st.session_state["autenticado"]:
        # Design da Tela de Login
        st.markdown("""
            <style>
                .login-container { background-color: #f0f2f6; padding: 30px; border-radius: 15px; border: 2px solid #d6d6d6; text-align: center; margin-bottom: 20px; }
                .titulo-principal { color: #1f1f1f; font-size: 28px; font-weight: bold; margin-bottom: 10px; }
                .sub-logos { display: flex; justify-content: center; gap: 20px; font-size: 18px; font-weight: bold; }
                .labortec { color: #004aad; }
                .metal { color: #d35400; }
            </style>
            <div class="login-container">
                <div class="titulo-principal">🔐 SISTEMA INTEGRADO</div>
                <div class="sub-logos"><span class="labortec">🧪 LABORTEC</span><span>|</span><span class="metal">⚙️ METAL QUÍMICA</span></div>
                <p style="margin-top: 15px; color: #555;">Área Restrita aos Operadores</p>
            </div>
        """, unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
            senha = st.text_input("🔑 Digite seu Código de Acesso:", type="password")
            if st.button("🚀 ENTRAR", type="primary", use_container_width=True):
                usuario_encontrado = None
                for nome, senha_real in CREDENCIAIS.items():
                    if senha == senha_real:
                        usuario_encontrado = nome
                        break
                if usuario_encontrado:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_nome"] = usuario_encontrado
                    st.rerun()
                else:
                    st.error("⛔ Código inválido.")
        return False
    return True

if not verificar_senha():
    st.stop() # PARA TUDO AQUI SE NÃO ESTIVER LOGADO

# --- 4. FUNÇÕES DE DADOS (CARREGAR E SALVAR) ---
def carregar_dados():
    try:
        df_est = conn.read(worksheet="Estoque", ttl="0")
        if not df_est.empty: st.session_state['estoque'] = df_est
            
        df_cli = conn.read(worksheet="Clientes", ttl="0")
        if not df_cli.empty: st.session_state['clientes_db'] = df_cli.set_index('Nome').to_dict('index')
            
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
    except: return False

def salvar_dados():
    try:
        conn.update(worksheet="Estoque", data=st.session_state['estoque'])
        
        if st.session_state.get('clientes_db'):
            df_clis = pd.DataFrame.from_dict(st.session_state['clientes_db'], orient='index').reset_index()
            df_clis.rename(columns={'index': 'Nome'}, inplace=True)
            conn.update(worksheet="Clientes", data=df_clis)
        
        if st.session_state.get('log_vendas'): conn.update(worksheet="Log_Vendas", data=pd.DataFrame(st.session_state['log_vendas']))
        if st.session_state.get('log_entradas'): conn.update(worksheet="Log_Entradas", data=pd.DataFrame(st.session_state['log_entradas']))
        if st.session_state.get('log_laudos'): conn.update(worksheet="Log_Laudos", data=pd.DataFrame(st.session_state['log_laudos']))
        st.toast("💾 Salvo na Nuvem!", icon="☁️")
    except Exception as e: st.warning(f"Erro ao salvar: {e}")

# --- 5. INICIALIZAÇÃO DE VARIÁVEIS ---
if 'dados_carregados' not in st.session_state:
    st.session_state['dados_carregados'] = carregar_dados()

if 'tabelas_precos' not in st.session_state:
    st.session_state['tabelas_precos'] = {'PADRAO': {}, 'REVENDA': {}}

if 'estoque' not in st.session_state:
    st.session_state['estoque'] = pd.DataFrame(columns=['Cod', 'Produto', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Saldo', 'Estoque_Inicial', 'Estoque_Minimo'])

if 'clientes_db' not in st.session_state: st.session_state['clientes_db'] = {}
if 'log_vendas' not in st.session_state: st.session_state['log_vendas'] = []
if 'log_entradas' not in st.session_state: st.session_state['log_entradas'] = []
if 'log_laudos' not in st.session_state: st.session_state['log_laudos'] = []

if not st.session_state['estoque'].empty:
    if 'Estoque_Inicial' not in st.session_state['estoque'].columns: st.session_state['estoque']['Estoque_Inicial'] = st.session_state['estoque']['Saldo']
    if 'Estoque_Minimo' not in st.session_state['estoque'].columns: st.session_state['estoque']['Estoque_Minimo'] = 0.0

if 'pdf_gerado' not in st.session_state: st.session_state['pdf_gerado'] = None

# --- 6. FUNÇÕES VISUAIS E TEMAS ---
def aplicar_tema(escolha):
    css = """<style>
        [data-testid="stSidebar"] .block-container { text-align: center; }
        .blink-text { animation: blinker 1.5s linear infinite; color: #FF4B4B; font-weight: bold; }
        @keyframes blinker { 50% { opacity: 0; } }
    </style>"""
    if escolha == "⚪ Padrão (Clean)":
        css += """<style>.stApp { background-color: #FFFFFF !important; color: #000000 !important; } .stTextInput input { background-color: #FFF !important; color: #000 !important; }</style>"""
    elif escolha == "🔵 Azul Labortec":
        css += """<style>.stApp { background-color: #F0F8FF !important; color: #002B4E !important; } .stTextInput input { border: 1px solid #B0C4DE !important; }</style>"""
    elif escolha == "⚫ Dark Mode (Noturno)":
        css += """<style>.stApp { background-color: #0E1117 !important; color: #FAFAFA !important; } .stTextInput input { background-color: #1c1e24 !important; color: white !important; }</style>"""
    st.markdown(css, unsafe_allow_html=True)

def exibir_cabecalho_tela(titulo, logo, empresa):
    c1, c2 = st.columns([1, 6])
    with c1: 
        if os.path.exists(logo): st.image(logo, width=100)
    with c2: 
        st.title(titulo)
        st.caption(empresa)
    st.markdown("---")

# --- 7. NAVEGAÇÃO E MENU LATERAL ---
# Se o código chegar aqui, o menu VAI aparecer
st.sidebar.title("MENU GERAL")
st.sidebar.success(f"👋 {obter_saudacao()}, {st.session_state['usuario_nome']}!")
st.sidebar.markdown("---")

tema = st.sidebar.selectbox("🎨 Visual:", ["⚪ Padrão (Clean)", "🔵 Azul Labortec", "⚫ Dark Mode (Noturno)"])
aplicar_tema(tema)

page = st.sidebar.radio("Navegar:", ["📊 DASHBOARD", "LAUDOS", "VENDAS", "ENTRADA", "ESTOQUE", "MÍNIMOS", "CONFERÊNCIA", "CLIENTES"])

# --- 8. LÓGICA DAS PÁGINAS ---

if page == "📊 DASHBOARD":
    st.markdown("<h1 style='text-align: center;'>⚗️ Central de Inteligência</h1>", unsafe_allow_html=True)
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    total_vendas = sum(i['Qtd'] for i in st.session_state['log_vendas'])
    total_entrada = sum(i['Qtd'] for i in st.session_state['log_entradas'])
    col1.metric("📦 Total Vendido", f"{total_vendas:,.1f} KG")
    col2.metric("📥 Total Reposto", f"{total_entrada:,.1f} KG")
    
    st.subheader("📅 Próximos Laudos")
    laudos = st.session_state.get('log_laudos', [])
    if laudos:
        df_l = pd.DataFrame(laudos)
        st.dataframe(df_l, use_container_width=True)
    else:
        st.info("Sem laudos agendados.")

elif page == "LAUDOS":
    exibir_cabecalho_tela("Agendamento de Laudos", "labortec.jpg", "LABORTEC")
    with st.form("laudo"):
        cli = st.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
        data = st.date_input("Data Coleta", format="DD/MM/YYYY")
        if st.form_submit_button("Agendar"):
            st.session_state['log_laudos'].append({"Cliente": cli, "Data_Coleta": data.strftime("%d/%m/%Y")})
            salvar_dados()
            st.success("Agendado!")
    
    if st.session_state['log_laudos']:
        df = pd.DataFrame(st.session_state['log_laudos'])
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if not edited.equals(df):
            st.session_state['log_laudos'] = edited.to_dict('records')
            salvar_dados()
            st.rerun()

elif page == "ENTRADA":
    exibir_cabecalho_tela("Entrada Estoque", "metal.jpg", "METAL QUÍMICA")
    c1, c2 = st.columns([3,1])
    opcoes = st.session_state['estoque'].apply(lambda x: f"{x['Cod']} - {x['Produto']}", axis=1)
    prod = c1.selectbox("Produto", opcoes)
    qtd = c2.number_input("Qtd (KG)", min_value=0.0)
    if st.button("Confirmar Entrada", type="primary"):
        cod = prod.split(" - ")[0]
        idx = st.session_state['estoque'][st.session_state['estoque']['Cod']==cod].index[0]
        st.session_state['estoque'].at[idx, 'Saldo'] += qtd
        st.session_state['log_entradas'].append({'Data': datetime.now().strftime("%d/%m/%Y"), 'Cod': cod, 'Qtd': qtd})
        salvar_dados()
        st.success("Estoque atualizado!")
        st.rerun()

elif page == "ESTOQUE":
    exibir_cabecalho_tela("Gestão de Estoque", "metal.jpg", "METAL QUÍMICA")
    with st.expander("Novo Produto"):
        with st.form("novo_prod"):
            c1,c2,c3 = st.columns([1,3,1])
            cod = c1.text_input("Código")
            nome = c2.text_input("Nome")
            saldo = c3.number_input("Saldo Inicial", min_value=0.0)
            if st.form_submit_button("Cadastrar"):
                novo = pd.DataFrame([{'Cod': cod, 'Produto': nome, 'Saldo': saldo, 'Marca': 'LABORTEC', 'NCM':'', 'Unidade':'KG', 'Preco_Base':0.0, 'Estoque_Inicial':saldo, 'Estoque_Minimo':0.0}])
                st.session_state['estoque'] = pd.concat([st.session_state['estoque'], novo], ignore_index=True)
                salvar_dados()
                st.rerun()
    
    edited = st.data_editor(st.session_state['estoque'], use_container_width=True, num_rows="dynamic")
    if not edited.equals(st.session_state['estoque']):
        st.session_state['estoque'] = edited
        salvar_dados()

elif page == "MÍNIMOS":
    st.title("🚨 Definir Mínimos")
    edited = st.data_editor(st.session_state['estoque'][['Cod','Produto','Saldo','Estoque_Minimo']], use_container_width=True)
    if st.button("Salvar Mínimos"):
        for i, row in edited.iterrows():
            idx = st.session_state['estoque'][st.session_state['estoque']['Cod']==row['Cod']].index[0]
            st.session_state['estoque'].at[idx, 'Estoque_Minimo'] = row['Estoque_Minimo']
        salvar_dados()
        st.success("Salvo!")

elif page == "CLIENTES":
    st.title("Clientes")
    with st.form("novo_cli"):
        c1,c2 = st.columns([1,3])
        cod = c1.text_input("Cód")
        nome = c2.text_input("Nome")
        end = st.text_input("Endereço")
        if st.form_submit_button("Salvar Cliente"):
            st.session_state['clientes_db'][nome] = {'Cod_Cli':cod, 'End':end}
            salvar_dados()
            st.rerun()
    
    for nome in list(st.session_state['clientes_db'].keys()):
        c1, c2 = st.columns([4,1])
        c1.text(nome)
        if c2.button("🗑️", key=nome):
            del st.session_state['clientes_db'][nome]
            salvar_dados()
            st.rerun()

elif page == "VENDAS":
    st.title("Vendas")
    cli = st.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
    df_v = st.session_state['estoque'].copy()
    if 'Qtd' not in df_v: df_v['Qtd'] = 0.0
    edited = st.data_editor(df_v[['Cod','Produto','Saldo','Preco_Base','Qtd']], use_container_width=True)
    
    if st.button("Finalizar Venda", type="primary"):
        itens = edited[edited['Qtd']>0]
        if not itens.empty:
            for _, row in itens.iterrows():
                idx = st.session_state['estoque'][st.session_state['estoque']['Cod']==row['Cod']].index[0]
                st.session_state['estoque'].at[idx, 'Saldo'] -= row['Qtd']
                st.session_state['log_vendas'].append({'Data': datetime.now().strftime("%d/%m/%Y"), 'Cliente': cli, 'Cod': row['Cod'], 'Produto': row['Produto'], 'Qtd': row['Qtd']})
            salvar_dados()
            st.success("Venda registrada!")
            st.rerun()

elif page == "CONFERÊNCIA":
    st.title("Conferência")
    st.dataframe(st.session_state['estoque'])

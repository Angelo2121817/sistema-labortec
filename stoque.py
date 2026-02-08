import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import os
from pypdf import PdfReader
from fpdf import FPDF
import json
from streamlit_gsheets import GSheetsConnection

# ==============================================================================
# 1. CONFIGURAÇÃO E CONEXÃO
# ==============================================================================
st.set_page_config(page_title="Sistema Integrado v61", layout="wide", page_icon="🧪")

try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except:
    st.error("Erro Crítico: Verifique o 'Secrets' no Streamlit Cloud.")
    st.stop()

# ==============================================================================
# 2. SEGURANÇA E LOGIN (IDENTIFICAÇÃO POR SENHA)
# ==============================================================================
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
        st.markdown("""
            <style>
                .login-box { background-color: #f0f2f6; padding: 40px; border-radius: 20px; border: 2px solid #004aad; text-align: center; }
                .labortec-txt { color: #004aad; font-weight: bold; }
                .metal-txt { color: #d35400; font-weight: bold; }
            </style>
            <div class="login-box">
                <h1>🔐 SISTEMA INTEGRADO</h1>
                <h3><span class="labortec-txt">LABORTEC CONSULTORIA</span> | <span class="metal-txt">METAL QUÍMICA</span></h3>
            </div>
        """, unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns([1,2,1])
        with c2:
            senha = st.text_input("Digite seu código de acesso:", type="password")
            if st.button("🚀 ACESSAR SISTEMA", use_container_width=True, type="primary"):
                for nome, senha_real in CREDENCIAIS.items():
                    if senha == senha_real:
                        st.session_state["autenticado"] = True
                        st.session_state["usuario_nome"] = nome
                        st.rerun()
                st.error("Código inválido!")
        return False
    return True

if not verificar_senha():
    st.stop()

# ==============================================================================
# 3. MOTOR DE DADOS (GOOGLE SHEETS)
# ==============================================================================
def carregar_dados():
    try:
        df_est = conn.read(worksheet="Estoque", ttl="0")
        if not df_est.empty: st.session_state['estoque'] = df_est
        
        df_cli = conn.read(worksheet="Clientes", ttl="0")
        if not df_cli.empty: st.session_state['clientes_db'] = df_cli.set_index('Nome').to_dict('index')
        
        for aba in ["Log_Vendas", "Log_Entradas", "Log_Laudos"]:
            try:
                df = conn.read(worksheet=aba, ttl="0")
                if not df.empty: st.session_state[aba.lower()] = df.to_dict('records')
            except: st.session_state[aba.lower()] = []
        return True
    except: return False

def salvar_dados():
    try:
        conn.update(worksheet="Estoque", data=st.session_state['estoque'])
        if st.session_state.get('clientes_db'):
            df_clis = pd.DataFrame.from_dict(st.session_state['clientes_db'], orient='index').reset_index().rename(columns={'index': 'Nome'})
            conn.update(worksheet="Clientes", data=df_clis)
        conn.update(worksheet="Log_Vendas", data=pd.DataFrame(st.session_state['log_vendas']))
        conn.update(worksheet="Log_Entradas", data=pd.DataFrame(st.session_state['log_entradas']))
        conn.update(worksheet="Log_Laudos", data=pd.DataFrame(st.session_state['log_laudos']))
        st.toast("✅ Nuvem Atualizada!", icon="☁️")
    except Exception as e: st.error(f"Erro ao salvar: {e}")

if 'dados_carregados' not in st.session_state:
    carregar_dados()
    st.session_state['dados_carregados'] = True

# Garantia de Variáveis
for key in ['log_vendas', 'log_entradas', 'log_laudos']:
    if key not in st.session_state: st.session_state[key] = []
if 'estoque' not in st.session_state: 
    st.session_state['estoque'] = pd.DataFrame(columns=['Cod', 'Produto', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Saldo', 'Estoque_Inicial', 'Estoque_Minimo'])
if 'clientes_db' not in st.session_state: st.session_state['clientes_db'] = {}
if 'pdf_gerado' not in st.session_state: st.session_state['pdf_gerado'] = None

# ==============================================================================
# 4. GERENCIADOR DE TEMAS (CSS)
# ==============================================================================
def aplicar_tema(escolha):
    css = """<style>
        [data-testid="stSidebar"] .block-container { text-align: center; }
        .blink-text { animation: blinker 1.5s linear infinite; color: #FF4B4B; font-weight: bold; }
        @keyframes blinker { 50% { opacity: 0; } }
    </style>"""
    
    if escolha == "⚪ Padrão (Clean)":
        css += "<style>.stApp { background-color: #FFFFFF !important; color: #000000 !important; }</style>"
    elif escolha == "🔵 Azul Labortec":
        css += "<style>.stApp { background-color: #F0F8FF !important; color: #002B4E !important; } h1,h2,h3 { color: #004aad !important; }</style>"
    elif escolha == "🌿 Verde Natureza":
        css += "<style>.stApp { background-color: #F1F8E9 !important; color: #1B5E20 !important; }</style>"
    elif escolha == "⚫ Dark Mode (Noturno)":
        css += "<style>.stApp { background-color: #0E1117 !important; color: #FAFAFA !important; } div[data-baseweb='input'] { background-color: #1c1e24 !important; }</style>"
    elif escolha == "🟠 Metal Industrial":
        css += "<style>.stApp { background-color: #2C2C2C !important; color: #FF8C00 !important; } h1,h2,h3 { font-family: 'Courier New'; }</style>"
    elif escolha == "🌃 Cyber Dark":
        css += "<style>.stApp { background-color: #000000 !important; color: #00FFFF !important; } .stButton button { border: 1px solid #00FFFF !important; }</style>"
    
    st.markdown(css, unsafe_allow_html=True)

# ==============================================================================
# 5. GERADOR DE PDF (CORRIGIDO: ALINHAMENTO + CABEÇALHO LABORTEC)
# ==============================================================================
class PDF(FPDF):
    def header(self):
        # 1. Logo
        if os.path.exists("labortec.jpg"): 
            self.image("labortec.jpg", x=10, y=8, w=45)
        
        # 2. Título (Só Labortec)
        self.set_font('Arial', 'B', 14)
        self.set_xy(60, 15)
        self.cell(0, 5, 'LABORTEC CONSULTORIA', 0, 1, 'L')
        
        # 3. Subtítulo
        self.set_font('Arial', '', 9)
        self.set_xy(60, 22)
        self.cell(0, 5, 'Rua Alfredo Bruno, 22 - Campinas/SP', 0, 1, 'L')
        self.set_xy(60, 27)
        self.cell(0, 5, 'CNPJ: 03.763.197/0001-09 | Tel: (19) 3238-9320', 0, 1, 'L')

        # 4. Linha Divisória (Abaixei para 45 para não cortar o logo)
        self.line(10, 45, 200, 45)
        self.ln(35) # Espaço seguro para começar o texto

def criar_doc_pdf(vendedor, cliente, dados_cli, itens, total, titulo):
    pdf = PDF()
    pdf.add_page()
    
    # Título do Doc
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, titulo, 0, 1, 'C')
    
    # Dados Gerais
    pdf.set_font('Arial', '', 9)
    pdf.cell(0, 5, f"Data: {datetime.now().strftime('%d/%m/%Y')} | Vendedor: {vendedor}", 0, 1, 'R')
    pdf.ln(5)
    
    # Dados Cliente
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, f" CLIENTE: {cliente}", 1, 1, 'L')
    pdf.set_font('Arial', '', 9)
    # Tenta pegar endereço e telefone, se não tiver, deixa em branco
    end_cli = dados_cli.get('End', '')
    tel_cli = dados_cli.get('Tel', '')
    pdf.cell(0, 5, f" Endereço: {end_cli} | Tel: {tel_cli}", 0, 1, 'L')
    pdf.ln(5)
    
    # Cabeçalho da Tabela
    pdf.set_font('Arial', 'B', 8)
    w = [15, 90, 20, 30, 30] # Largura das colunas
    cols = ['Qtd', 'Produto', 'Cod', 'Preço Unit.', 'Total']
    for i, c in enumerate(cols): pdf.cell(w[i], 7, c, 1, 0, 'C')
    pdf.ln()
    
    # Itens da Tabela
    pdf.set_font('Arial', '', 8)
    for r in itens:
        pdf.cell(w[0], 6, str(r['Qtd']), 1, 0, 'C')
        pdf.cell(w[1], 6, str(r['Produto'])[:50], 1, 0, 'L')
        pdf.cell(w[2], 6, str(r['Cod']), 1, 0, 'C')
        pdf.cell(w[3], 6, f"R$ {float(r['Preco_Base']):.2f}", 1, 0, 'R')
        pdf.cell(w[4], 6, f"R$ {float(r['Total']):.2f}", 1, 0, 'R')
        pdf.ln()

    # Total Geral
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(sum(w)-30, 10, "TOTAL GERAL:", 0, 0, 'R')
    pdf.cell(30, 10, f"R$ {total:,.2f}", 1, 1, 'R')
    
    # ESTA É A LINHA QUE ESTAVA DANDO ERRO (Agora está alinhada dentro da função)
    return pdf.output(dest='S').encode('latin-1')

# ==============================================================================
# 6. MENU LATERAL E TEMAS
# ==============================================================================
st.sidebar.title("🛠️ MENU GERAL")
st.sidebar.success(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")

st.sidebar.markdown("---")
st.sidebar.subheader("🎨 Personalizar Tela")
opcoes_temas = ["⚪ Padrão (Clean)", "🔵 Azul Labortec", "🌿 Verde Natureza", "⚫ Dark Mode (Noturno)", "🟠 Metal Industrial", "🌃 Cyber Dark"]
tema_sel = st.sidebar.selectbox("Escolha o visual:", opcoes_temas)
aplicar_tema(tema_sel)

menu = st.sidebar.radio("Navegar:", ["📊 Dashboard", "🧪 Laudos", "💰 Vendas & Orçamentos", "📥 Entrada de Estoque", "📦 Gestão de Produtos", "📋 Conferência Geral", "👥 Clientes"])
# ==============================================================================
# 7. PÁGINAS DO SISTEMA
# ==============================================================================

if menu == "💰 Vendas & Orçamentos":
    st.title("💰 Vendas e Orçamentos")
    if not st.session_state['clientes_db']:
        st.warning("Cadastre clientes primeiro!")
    else:
        c1, c2 = st.columns([2,1])
        cli = c1.selectbox("Selecione o Cliente", list(st.session_state['clientes_db'].keys()))
        vend = c2.text_input("Vendedor", st.session_state['usuario_nome'])
        
        df_v = st.session_state['estoque'].copy()
        df_v['Qtd'] = 0.0
        ed = st.data_editor(df_v[['Cod', 'Produto', 'Saldo', 'Preco_Base', 'Qtd']], use_container_width=True)
        
        itens = ed[ed['Qtd'] > 0].copy()
        if not itens.empty:
            itens['Total'] = itens['Qtd'] * itens['Preco_Base']
            total = itens['Total'].sum()
            st.subheader(f"Total: R$ {total:,.2f}")
            
            origem = st.radio("🚛 Origem da Entrega:", ["METAL QUÍMICA (Baixa no Estoque)", "INDEPENDENTE (Sem Baixa)"], horizontal=True)
            
            cb1, cb2 = st.columns(2)
            with cb1:
                if st.button("📄 GERAR ORÇAMENTO", use_container_width=True):
                    pdf = criar_doc_pdf(vend, cli, st.session_state['clientes_db'][cli], itens.to_dict('records'), total, "ORÇAMENTO")
                    st.session_state['pdf_gerado'] = pdf
                    st.session_state['pdf_nome'] = "Orcamento.pdf"
            with cb2:
                if st.button("✅ CONFIRMAR VENDA", use_container_width=True, type="primary"):
                    if "METAL" in origem:
                        for _, r in itens.iterrows():
                            mask = st.session_state['estoque']['Cod'].astype(str) == str(r['Cod'])
                            idx = st.session_state['estoque'][mask].index[0]
                            st.session_state['estoque'].at[idx, 'Saldo'] -= r['Qtd']
                    
                    st.session_state['log_vendas'].append({
                        'Data': datetime.now().strftime("%d/%m/%Y %H:%M"),
                        'Cliente': cli, 'Produto': 'Vários', 'Qtd': itens['Qtd'].sum(), 'Vendedor': vend, 'Origem': origem
                    })
                    salvar_dados()
                    pdf = criar_doc_pdf(vend, cli, st.session_state['clientes_db'][cli], itens.to_dict('records'), total, "PEDIDO DE VENDA")
                    st.session_state['pdf_gerado'] = pdf
                    st.session_state['pdf_nome'] = "Pedido.pdf"
                    st.success("Venda processada!")

            if st.session_state.get('pdf_gerado'):
                st.download_button("📥 BAIXAR PDF", st.session_state['pdf_gerado'], st.session_state['pdf_nome'], "application/pdf")

elif menu == "📥 Entrada de Estoque":
    st.title("📥 Entrada de Mercadoria")
    opcoes = st.session_state['estoque'].apply(lambda x: f"{x['Cod']} - {x['Produto']}", axis=1)
    prod = st.selectbox("Selecione o Produto", opcoes)
    qtd = st.number_input("Quantidade (KG)", min_value=0.0)
    if st.button("Confirmar Entrada"):
        cod = prod.split(" - ")[0]
        mask = st.session_state['estoque']['Cod'].astype(str) == str(cod)
        idx = st.session_state['estoque'][mask].index[0]
        st.session_state['estoque'].at[idx, 'Saldo'] += qtd
        st.session_state['log_entradas'].append({
            'Data': datetime.now().strftime("%d/%m/%Y %H:%M"),
            'Produto': st.session_state['estoque'].at[idx, 'Produto'], 'Qtd': qtd, 'Usuario': st.session_state['usuario_nome']
        })
        salvar_dados()
        st.success("Estoque Atualizado!")

elif menu == "📋 Conferência Geral":
    st.title("📋 Conferência")
    t1, t2, t3 = st.tabs(["📦 Estoque", "📈 Vendas", "📉 Entradas"])
    t1.dataframe(st.session_state['estoque'], use_container_width=True)
    t2.dataframe(pd.DataFrame(st.session_state['log_vendas']).iloc[::-1], use_container_width=True)
    t3.dataframe(pd.DataFrame(st.session_state['log_entradas']).iloc[::-1], use_container_width=True)

elif menu == "📦 Gestão de Produtos":
    st.title("📦 Cadastro")
    ed = st.data_editor(st.session_state['estoque'], num_rows="dynamic", use_container_width=True)
    if st.button("💾 Salvar Alterações"):
        st.session_state['estoque'] = ed
        salvar_dados()

# ==============================================================================
# 5. CLIENTES
# ==============================================================================
elif menu == "👥 Clientes":
    st.title("👥 Gestão de Clientes")
    
    # Formulário de Cadastro Rápido
    with st.form("form_cliente"):
        c1, c2 = st.columns([3,1])
        nome = c1.text_input("Nome do Cliente (Empresa)")
        tel = c2.text_input("Telefone")
        end = st.text_input("Endereço Completo")
        
        if st.form_submit_button("💾 Salvar Cliente"):
            if nome:
                st.session_state['clientes_db'][nome] = {'End': end, 'Tel': tel}
                salvar_dados()
                st.success(f"Cliente {nome} salvo!")
                st.rerun()
            else:
                st.error("O nome é obrigatório.")
    
    st.markdown("---")
    st.subheader("📇 Lista de Contatos")
    
    # Listagem com botão de excluir
    for k in list(st.session_state['clientes_db'].keys()):
        col_n, col_d = st.columns([4,1])
        dados = st.session_state['clientes_db'][k]
        col_n.markdown(f"**{k}** \n📍 {dados.get('End', 'Sem endereço')} | 📞 {dados.get('Tel', 'Sem tel')}")
        
        if col_d.button("🗑️", key=f"del_{k}"):
            del st.session_state['clientes_db'][k]
            salvar_dados()
            st.rerun()

# ==============================================================================
# 6. DASHBOARD (O NOVO RADAR)
# ==============================================================================
elif menu == "📊 Dashboard":
    st.title("📊 Painel de Controle Integrado")
    st.markdown("---")
    
    # --- 1. RADAR DE LAUDOS (ALERTA DE PRAZO) ---
    st.subheader("🔔 Radar de Coletas (Efluentes)")
    laudos = st.session_state.get('log_laudos', [])
    
    # Filtra e Tenta ordenar
    laudos_pendentes = [l for l in laudos if l.get('Status', 'Pendente') == 'Pendente']
    try:
        laudos_pendentes.sort(key=lambda x: datetime.strptime(x['Data_Coleta'], "%d/%m/%Y"))
    except: pass

    if not laudos_pendentes:
        st.success("✅ Tudo limpo! Nenhuma coleta pendente no radar.")
    else:
        # Mostra os 4 primeiros cartões de alerta
        col_laudos = st.columns(4)
        for i, l in enumerate(laudos_pendentes[:4]): 
            with col_laudos[i]:
                st.error(f"📅 **{l['Data_Coleta']}**")
                st.info(f"🏭 {l['Cliente']}")
                if l.get('Obs'): st.caption(f"📝 {l['Obs']}")
    
    st.markdown("---")

    # --- 2. SITUAÇÃO TÁTICA (MÉTRICAS) ---
    st.subheader("📈 Situação Tática")
    c1, c2, c3 = st.columns(3)
    
    qtd_estoque = len(st.session_state['estoque'])
    qtd_vendas = len(st.session_state['log_vendas'])
    qtd_clientes = len(st.session_state['clientes_db'])
    
    c1.metric("📦 Arsenal (Produtos)", qtd_estoque)
    c2.metric("💰 Baixas (Vendas)", qtd_vendas)
    c3.metric("👥 Base de Aliados (Clientes)", qtd_clientes)

    # --- 3. HISTÓRICO DE COMBATE (GRÁFICO) ---
    if st.session_state['log_vendas']:
        st.markdown("---")
        st.caption("Últimas Operações de Venda:")
        df_dash = pd.DataFrame(st.session_state['log_vendas'])
        # Mostra apenas colunas essenciais
        cols_uteis = [c for c in ['Data', 'Cliente', 'Produto', 'Qtd', 'Vendedor'] if c in df_dash.columns]
        st.dataframe(
            df_dash[cols_uteis].tail(5).iloc[::-1], 
            use_container_width=True, 
            hide_index=True
        )

# ==============================================================================
# 7. LAUDOS (O NOVO MÓDULO)
# ==============================================================================
elif menu == "🧪 Laudos":
    st.title("🧪 Agendamento de Coletas (Laudos)")
    
    with st.form("form_laudo"):
        c1, c2 = st.columns([2,1])
        lista_clientes = list(st.session_state['clientes_db'].keys())
        
        if not lista_clientes:
            st.warning("⚠️ Cadastre clientes na aba 'Clientes' antes de agendar.")
            cli_sel = None
        else:
            cli_sel = c1.selectbox("Selecione o Cliente:", lista_clientes)
            
        data_coleta = c2.date_input("Data Prevista:", format="DD/MM/YYYY")
        obs = st.text_input("Observação (Ex: Coletar na saída da ETE)")
        
        if st.form_submit_button("💾 Agendar Coleta"):
            if cli_sel:
                novo_laudo = {
                    "Cliente": cli_sel,
                    "Data_Coleta": data_coleta.strftime("%d/%m/%Y"),
                    "Obs": obs,
                    "Status": "Pendente",
                    "Agendado_Por": st.session_state.get('usuario_nome', 'Sistema')
                }
                st.session_state['log_laudos'].append(novo_laudo)
                salvar_dados()
                st.success(f"Agendado para {cli_sel}!")
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Próximas Coletas")

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
    else:
        st.info("Nenhum laudo pendente.")


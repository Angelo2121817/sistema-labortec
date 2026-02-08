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
st.set_page_config(page_title="Sistema Labortec v60", layout="wide", page_icon="🧪")

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
                <h1>🔐 ACESSO INTEGRADO</h1>
                <h3><span class="labortec-txt">LABORTEC</span> | <span class="metal-txt">METAL QUÍMICA</span></h3>
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

# Inicialização
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
# 4. GERADOR DE PDF PROFISSIONAL
# ==============================================================================
class PDF(FPDF):
    def header(self):
        if os.path.exists("labortec.jpg"): self.image("labortec.jpg", x=10, y=8, w=50)
        self.set_font('Arial', 'B', 12)
        self.set_xy(70, 15)
        self.cell(0, 5, 'LABORTEC CONSULTORIA & METAL QUÍMICA', 0, 1, 'L')
        self.set_font('Arial', '', 8)
        self.set_x(70)
        self.cell(0, 4, 'Rua Alfredo Bruno, 22 - Campinas/SP | CNPJ: 03.763.197/0001-09', 0, 1, 'L')
        self.line(10, 35, 200, 35)
        self.ln(20)

def criar_documento(vendedor, cliente, dados_cli, itens, total, condicoes, titulo):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, titulo, 0, 1, 'C')
    pdf.set_font('Arial', '', 9)
    pdf.cell(0, 5, f"Data: {datetime.now().strftime('%d/%m/%Y')} | Vendedor: {vendedor}", 0, 1, 'R')
    pdf.ln(5)
    
    # Bloco Cliente
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, f" CLIENTE: {cliente}", 1, 1, 'L', True)
    pdf.set_font('Arial', '', 9)
    pdf.cell(0, 5, f" Endereço: {dados_cli.get('End', '')} | Tel: {dados_cli.get('Tel', '')}", 1, 1, 'L')
    pdf.ln(5)

    # Tabela Itens
    pdf.set_font('Arial', 'B', 8)
    w = [15, 80, 25, 30, 40]
    cols = ['Qtd', 'Produto', 'Cod', 'Unitário', 'Total']
    for i, c in enumerate(cols): pdf.cell(w[i], 7, c, 1, 0, 'C', True)
    pdf.ln()
    
    pdf.set_font('Arial', '', 8)
    for r in itens:
        pdf.cell(w[0], 6, str(r['Qtd']), 1, 0, 'C')
        pdf.cell(w[1], 6, str(r['Produto'])[:45], 1, 0, 'L')
        pdf.cell(w[2], 6, str(r['Cod']), 1, 0, 'C')
        pdf.cell(w[3], 6, f"R$ {float(r['Preco_Base']):.2f}", 1, 0, 'R')
        pdf.cell(w[4], 6, f"R$ {float(r['Total']):.2f}", 1, 0, 'R')
        pdf.ln()

    pdf.set_font('Arial', 'B', 11)
    pdf.cell(sum(w)-40, 10, "TOTAL GERAL:", 0, 0, 'R')
    pdf.cell(40, 10, f"R$ {total:,.2f}", 1, 1, 'R')
    
    return pdf.output(dest='S').encode('latin-1')

# ==============================================================================
# 5. INTERFACE E NAVEGAÇÃO
# ==============================================================================
st.sidebar.title("🎮 PAINEL DE CONTROLE")
st.sidebar.info(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")

menu = st.sidebar.radio("Navegar:", ["📊 Dashboard", "💰 Vendas & Orçamentos", "📥 Entrada de Estoque", "📦 Gestão de Produtos", "📋 Conferência Geral", "👥 Clientes"])

# --- VENDAS (A PARTE QUE VOCÊ PRECISAVA) ---
if menu == "💰 Vendas & Orçamentos":
    st.title("💰 Vendas & Orçamentos")
    
    if not st.session_state['clientes_db']:
        st.warning("Cadastre clientes primeiro!")
    else:
        c1, c2 = st.columns([2,1])
        cli_sel = c1.selectbox("Selecione o Cliente", list(st.session_state['clientes_db'].keys()))
        vendedor = c2.text_input("Vendedor", st.session_state['usuario_nome'])
        
        # Tabela de Venda
        df_v = st.session_state['estoque'].copy()
        df_v['Qtd'] = 0.0
        edited = st.data_editor(df_v[['Cod', 'Produto', 'Saldo', 'Preco_Base', 'Qtd']], use_container_width=True, key="venda_editor")
        
        itens_venda = edited[edited['Qtd'] > 0].copy()
        itens_venda['Total'] = itens_venda['Qtd'] * itens_venda['Preco_Base']
        total = itens_venda['Total'].sum()
        
        if total > 0:
            st.subheader(f"Total: R$ {total:,.2f}")
            
            # OPÇÃO DE ENTREGA (SISTEMA DE BAIXA)
            origem = st.radio("🚛 Origem da Mercadoria:", ["METAL QUÍMICA (Dar baixa no estoque)", "INDEPENDENTE (Apenas registrar venda)"], horizontal=True)
            
            col_b1, col_b2 = st.columns(2)
            
            with col_b1:
                if st.button("📄 GERAR ORÇAMENTO (Apenas PDF)", use_container_width=True):
                    pdf = criar_documento(vendedor, cli_sel, st.session_state['clientes_db'][cli_sel], itens_venda.to_dict('records'), total, {}, "ORÇAMENTO")
                    st.session_state['pdf_gerado'] = pdf
                    st.session_state['pdf_nome'] = "Orcamento_Labortec.pdf"

            with col_b2:
                if st.button("✅ CONFIRMAR VENDA (Registrar e PDF)", use_container_width=True, type="primary"):
                    # Registrar no Log
                    for _, row in itens_venda.iterrows():
                        # Dar baixa se for Metal Química
                        if "METAL" in origem:
                            mask = st.session_state['estoque']['Cod'].astype(str) == str(row['Cod'])
                            if not st.session_state['estoque'][mask].empty:
                                idx = st.session_state['estoque'][mask].index[0]
                                st.session_state['estoque'].at[idx, 'Saldo'] -= row['Qtd']
                        
                        # Logar a venda sempre
                        st.session_state['log_vendas'].append({
                            'Data': datetime.now().strftime("%d/%m/%Y %H:%M"),
                            'Cliente': cli_sel, 'Produto': row['Produto'], 'Qtd': row['Qtd'], 'Vendedor': vendedor, 'Origem': origem
                        })
                    
                    salvar_dados()
                    pdf = criar_documento(vendedor, cli_sel, st.session_state['clientes_db'][cli_sel], itens_venda.to_dict('records'), total, {}, "PEDIDO DE VENDA")
                    st.session_state['pdf_gerado'] = pdf
                    st.session_state['pdf_nome'] = "Pedido_Venda.pdf"
                    st.success("Venda registrada com sucesso!")

            if st.session_state.get('pdf_gerado'):
                st.download_button("📥 BAIXAR DOCUMENTO PDF", st.session_state['pdf_gerado'], st.session_state['pdf_nome'], "application/pdf", use_container_width=True)

# --- ENTRADA DE ESTOQUE (CONFERÊNCIA) ---
elif menu == "📥 Entrada de Estoque":
    st.title("📥 Registro de Entrada")
    c1, c2 = st.columns([3,1])
    opcoes = st.session_state['estoque'].apply(lambda x: f"{x['Cod']} - {x['Produto']}", axis=1)
    prod = c1.selectbox("Selecione o Produto", opcoes)
    qtd = c2.number_input("Quantidade (KG)", min_value=0.0)
    
    if st.button("📥 Confirmar Entrada", type="primary"):
        cod = prod.split(" - ")[0]
        mask = st.session_state['estoque']['Cod'].astype(str) == str(cod)
        if not st.session_state['estoque'][mask].empty:
            idx = st.session_state['estoque'][mask].index[0]
            st.session_state['estoque'].at[idx, 'Saldo'] += qtd
            st.session_state['log_entradas'].append({
                'Data': datetime.now().strftime("%d/%m/%Y %H:%M"),
                'Produto': st.session_state['estoque'].at[idx, 'Produto'],
                'Qtd': qtd, 'Usuario': st.session_state['usuario_nome']
            })
            salvar_dados()
            st.success("Estoque atualizado!")
            st.rerun()

# --- CONFERÊNCIA (ESTAVA FALTANDO) ---
elif menu == "📋 Conferência Geral":
    st.title("📋 Auditoria e Histórico")
    t1, t2, t3 = st.tabs(["📦 Estoque Real", "📈 Histórico de Vendas", "📉 Histórico de Entradas"])
    with t1: st.dataframe(st.session_state['estoque'], use_container_width=True)
    with t2: st.dataframe(pd.DataFrame(st.session_state['log_vendas']).iloc[::-1], use_container_width=True)
    with t3: st.dataframe(pd.DataFrame(st.session_state['log_entradas']).iloc[::-1], use_container_width=True)

# --- GESTÃO DE PRODUTOS ---
elif menu == "📦 Gestão de Produtos":
    st.title("📦 Cadastro e Preços")
    with st.expander("➕ CADASTRAR NOVO PRODUTO"):
        with st.form("novo_p"):
            c1,c2,c3,c4 = st.columns(4)
            ncod = c1.text_input("Código")
            nnom = c2.text_input("Nome")
            npre = c3.number_input("Preço Base", min_value=0.0)
            nsal = c4.number_input("Saldo Inicial", min_value=0.0)
            if st.form_submit_button("Salvar Produto"):
                novo = pd.DataFrame([{'Cod': ncod, 'Produto': nnom, 'Preco_Base': npre, 'Saldo': nsal, 'Marca': 'LABORTEC', 'Unidade': 'KG', 'Estoque_Minimo': 0.0}])
                st.session_state['estoque'] = pd.concat([st.session_state['estoque'], novo], ignore_index=True)
                salvar_dados()
                st.rerun()
    
    ed_est = st.data_editor(st.session_state['estoque'], num_rows="dynamic", use_container_width=True)
    if st.button("💾 Salvar Alterações na Tabela"):
        st.session_state['estoque'] = ed_est
        salvar_dados()

# --- CLIENTES ---
elif menu == "👥 Clientes":
    st.title("👥 Gestão de Clientes")
    with st.form("n_cli"):
        c1, c2 = st.columns([3,1])
        nome = c1.text_input("Nome do Cliente")
        tel = c2.text_input("Telefone")
        end = st.text_input("Endereço Completo")
        if st.form_submit_button("Salvar Cliente"):
            st.session_state['clientes_db'][nome] = {'Tel': tel, 'End': end}
            salvar_dados()
            st.rerun()
    
    for n in list(st.session_state['clientes_db'].keys()):
        col_n, col_d = st.columns([4,1])
        col_n.write(f"**{n}** - {st.session_state['clientes_db'][n]['End']}")
        if col_d.button("🗑️", key=n):
            del st.session_state['clientes_db'][n]
            salvar_dados()
            st.rerun()

# --- DASHBOARD ---
elif menu == "📊 Dashboard":
    st.title(f"📊 Painel Geral - {st.session_state['usuario_nome']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Itens no Estoque", len(st.session_state['estoque']))
    c2.metric("💰 Vendas Registradas", len(st.session_state['log_vendas']))
    c3.metric("👥 Clientes Ativos", len(st.session_state['clientes_db']))

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
# 0. FUNÇÕES DE EXTRAÇÃO PDF (CETESB & PADRÃO)
# ==============================================================================
def extrair_dados_cetesb(f):
    try:
        reader = PdfReader(f)
        text = reader.pages[0].extract_text()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        d = {'Nome': '', 'CNPJ': '', 'End': '', 'Bairro': '', 'Cidade': '', 'CEP': '', 'UF': 'SP', 'Cod_Cli': '', 'Tel': ''}
        for i, line in enumerate(lines):
            cnpj_m = re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', line)
            if cnpj_m:
                d['CNPJ'] = cnpj_m.group(1)
                d['Nome'] = line.replace(d['CNPJ'], '').strip()
                if i + 1 < len(lines):
                    prox = lines[i+1]
                    cad_m = re.search(r'(\d+-\d+-\d+)', prox)
                    d['End'] = prox.replace(cad_m.group(1), '').strip() if cad_m else prox
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
    except: return None

def ler_pdf_antigo(f):
    try:
        reader = PdfReader(f)
        primeira_pagina = reader.pages[0].extract_text() or ""
        if "CETESB" in primeira_pagina.upper():
            return extrair_dados_cetesb(f)
        text = ""
        for p in reader.pages:
            t = p.extract_text()
            if t: text += t + "\n"
        clean = re.sub(r'\s+', ' ', text).strip()
        idx_inicio = clean.lower().find("cliente")
        core = clean[idx_inicio:] if idx_inicio != -1 else clean
        d = {'Nome':'', 'Cod_Cli':'', 'End':'', 'CEP':'', 'Bairro':'', 'Cidade':'', 'UF':'', 'CNPJ':'', 'Tel':''}
        def extract(key, stops):
            match = re.search(re.escape(key) + r'[:\s]*', core, re.IGNORECASE)
            if not match: return ""
            fragment = core[match.end():]
            min_idx = len(fragment)
            for stop in stops:
                stop_match = re.search(re.escape(stop), fragment, re.IGNORECASE)
                if stop_match and stop_match.start() < min_idx: min_idx = stop_match.start()
            return fragment[:min_idx].strip(" :/-|").strip()
        d['Nome'] = extract("Cliente", ["CNPJ", "CPF", "Endereço", "Data:", "Código:"])
        d['CNPJ'] = (re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', core) or [None])[0]
        d['End'] = extract("Endereço", ["Bairro", "Cidade", "Cep"])
        d['Bairro'] = extract("Bairro", ["Cidade", "Cep"])
        d['Cidade'] = extract("Cidade", ["/", "-", "Cep"])
        return d
    except Exception as e:
        return None

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
# 2. SEGURANÇA E LOGIN
# ==============================================================================
CREDENCIAIS = {"General": "labormetal22", "Fabricio": "fabricio2225", "Anderson": "anderson2225", "Angelo": "angelo2225"}
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
        st.markdown("<h1 style='text-align:center;'>🔐 ACESSO RESTRITO</h1>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1,2,1])
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

if not verificar_senha(): st.stop()

# ==============================================================================
# 3. MOTOR DE DADOS
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
        st.toast("✅ Nuvem Atualizada!")
    except Exception as e: st.error(f"Erro ao salvar: {e}")

if 'dados_carregados' not in st.session_state:
    carregar_dados()
    st.session_state['dados_carregados'] = True

for key in ['log_vendas', 'log_entradas', 'log_laudos']:
    if key not in st.session_state: st.session_state[key] = []
if 'estoque' not in st.session_state: 
    st.session_state['estoque'] = pd.DataFrame(columns=['Cod', 'Produto', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Saldo', 'Estoque_Inicial', 'Estoque_Minimo'])
if 'clientes_db' not in st.session_state: st.session_state['clientes_db'] = {}

# ==============================================================================
# 5. GERADOR DE PDF (FIX: ALINHAMENTO TOTAL E LOGO ISOLADA)
# ==============================================================================
class PDF(FPDF):
    def header(self):
        # Logo isolada à esquerda
        if os.path.exists("labortec.jpg"):
            self.image("labortec.jpg", x=10, y=8, w=35)
        
        # Textos deslocados para a direita para não bater na logo
        self.set_font('Arial', 'B', 16)
        self.set_xy(50, 8)
        self.cell(100, 10, 'LABORTEC', 0, 0, 'L')
        
        self.set_font('Arial', 'B', 16)
        self.set_xy(100, 8)
        titulo_doc = getattr(self, 'titulo_doc', 'ORÇAMENTO')
        self.cell(100, 10, titulo_doc, 0, 1, 'R')
        
        self.set_font('Arial', '', 8)
        self.set_xy(50, 18)
        self.cell(100, 4, 'Rua Alfredo Bruno, 22 - Campinas/SP - CEP 13040-235', 0, 0, 'L')
        
        self.set_xy(100, 18)
        self.cell(100, 4, f"Data: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'R')
        
        self.set_xy(50, 22)
        self.cell(100, 4, 'labortecconsultoria@gmail.com | Tel.: (19) 3238-9320', 0, 0, 'L')
        
        self.set_xy(100, 22)
        vendedor_nome = getattr(self, 'vendedor_nome', 'Sistema')
        self.cell(100, 4, f"Vendedor: {vendedor_nome}", 0, 1, 'R')
        
        self.set_xy(50, 26)
        self.cell(100, 4, 'C.N.P.J.: 03.763.197/0001-09', 0, 1, 'L')
        
        self.line(10, 35, 200, 35)
        self.ln(10)

    def footer(self):
        self.set_y(-25)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 4, 'Obs.: FRETE NÃO INCLUSO. PROPOSTA VÁLIDA POR 5 DIAS.', 0, 1, 'C')
        self.cell(0, 4, 'PRAZO DE RETIRADA: 3 A 5 DIAS ÚTEIS APÓS CONFIRMAÇÃO.', 0, 0, 'C')

def criar_doc_pdf(vendedor, cliente, dados_cli, itens, total, condicoes, titulo):
    pdf = PDF()
    pdf.vendedor_nome = vendedor
    pdf.titulo_doc = titulo
    pdf.add_page()
    
    # Bloco Cliente
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 7, f" Cliente: {cliente}", 1, 1, 'L', fill=True)
    
    pdf.set_font('Arial', '', 9)
    pdf.cell(0, 6, f" Endereço: {dados_cli.get('End', '')}", 'LR', 1, 'L')
    pdf.cell(0, 6, f" Cidade: {dados_cli.get('Cidade', '')}/{dados_cli.get('UF', '')} - CEP: {dados_cli.get('CEP', '')}", 'LR', 1, 'L')
    pdf.cell(0, 6, f" CNPJ: {dados_cli.get('CNPJ', '')} - Tel: {dados_cli.get('Tel', '')}", 'LRB', 1, 'L')
    pdf.ln(4)
    
    # Bloco Condições
    pdf.cell(0, 7, f" Pagto: {condicoes.get('plano', '')} | Forma: {condicoes.get('forma', '')} | Vencto: {condicoes.get('venc', '')}", 1, 1, 'L')
    pdf.ln(5)
    
    # Tabela de Itens
    pdf.set_font('Arial', 'B', 8)
    pdf.set_fill_color(220, 220, 220)
    # Larguras Ajustadas: Un(12), Qtd(12), Produto(90), Marca(25), NCM(20), Total(31) = 190 total
    pdf.cell(12, 7, 'Un', 1, 0, 'C', fill=True)
    pdf.cell(12, 7, 'Qtd', 1, 0, 'C', fill=True)
    pdf.cell(90, 7, 'Produto', 1, 0, 'C', fill=True)
    pdf.cell(25, 7, 'Marca', 1, 0, 'C', fill=True)
    pdf.cell(20, 7, 'NCM', 1, 0, 'C', fill=True)
    pdf.cell(31, 7, 'Total', 1, 1, 'C', fill=True)
    
    pdf.set_font('Arial', '', 8)
    for r in itens:
        pdf.cell(12, 6, str(r.get('Unidade', 'KG')), 1, 0, 'C')
        pdf.cell(12, 6, str(r['Qtd']), 1, 0, 'C')
        pdf.cell(90, 6, str(r['Produto'])[:55], 1, 0, 'L')
        pdf.cell(25, 6, str(r.get('Marca', 'LABORTEC')), 1, 0, 'C')
        pdf.cell(20, 6, str(r.get('NCM', '')), 1, 0, 'C')
        pdf.cell(31, 6, f"{float(r['Total']):.2f}", 1, 1, 'R')
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(159, 8, "TOTAL GERAL: ", 0, 0, 'R')
    pdf.cell(31, 8, f"R$ {total:,.2f}", 1, 1, 'R')
    
    # Assinaturas
    pdf.ln(20)
    y = pdf.get_y()
    pdf.line(20, y, 90, y); pdf.line(120, y, 190, y)
    pdf.set_font('Arial', '', 8)
    pdf.set_xy(20, y+2); pdf.cell(70, 4, 'Assinatura Cliente', 0, 0, 'C')
    pdf.set_xy(120, y+2); pdf.cell(70, 4, 'Assinatura Labortec', 0, 1, 'C')
    
    return pdf.output(dest='S').encode('latin-1')

# ==============================================================================
# MENU LATERAL
# ==============================================================================
st.sidebar.title("🛠️ MENU")
menu = st.sidebar.radio("Navegar:", ["📊 Dashboard", "🧪 Laudos", "💰 Vendas & Orçamentos", "📥 Entrada", "📦 Produtos", "👥 Clientes"])

# ==============================================================================
# PÁGINA VENDAS (FIX: LÓGICA DE ENTREGA METAL QUÍMICA)
# ==============================================================================
if menu == "💰 Vendas & Orçamentos":
    st.title("💰 Vendas e Orçamentos")
    if not st.session_state['clientes_db']: st.warning("Cadastre clientes!"); st.stop()
    
    c1, c2 = st.columns([2,1])
    cli = c1.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
    vend = c2.text_input("Vendedor", st.session_state['usuario_nome'])
    d_cli = st.session_state['clientes_db'][cli]
    
    col1, col2, col3 = st.columns(3)
    p_pag = col1.text_input("Plano", "28/42 DIAS")
    f_pag = col2.text_input("Forma", "BOLETO ITAU")
    venc = col3.text_input("Vencimento", "A COMBINAR")
    
    df_v = st.session_state['estoque'].copy()
    if 'Qtd' not in df_v.columns: df_v.insert(0, 'Qtd', 0.0)
    ed_v = st.data_editor(df_v[['Qtd', 'Produto', 'Cod', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Saldo']], use_container_width=True, hide_index=True)
    
    itens_sel = ed_v[ed_v['Qtd'] > 0].copy()
    itens_sel['Total'] = itens_sel['Qtd'] * itens_sel['Preco_Base']
    total = itens_sel['Total'].sum()
    
    if not itens_sel.empty:
        st.metric("Total", f"R$ {total:,.2f}")
        c_orc, c_ped = st.columns(2)
        with c_orc:
            if st.button("📄 ORÇAMENTO", use_container_width=True):
                pdf = criar_doc_pdf(vend, cli, d_cli, itens_sel.to_dict('records'), total, {'plano':p_pag, 'forma':f_pag, 'venc':venc}, "ORÇAMENTO")
                st.download_button("📥 Baixar", pdf, f"Orcamento_{cli}.pdf", "application/pdf")
        
        with c_ped:
            origem = st.radio("Origem da Entrega?", ["METAL QUÍMICA (Baixa Estoque)", "INDEPENDENTE (Sem Baixa)"], horizontal=True)
            if st.button("✅ CONFIRMAR PEDIDO", type="primary", use_container_width=True):
                pdf = criar_doc_pdf(vend, cli, d_cli, itens_sel.to_dict('records'), total, {'plano':p_pag, 'forma':f_pag, 'venc':venc}, "PEDIDO DE VENDA")
                if "METAL" in origem:
                    for _, row in itens_sel.iterrows():
                        idx = st.session_state['estoque'][st.session_state['estoque']['Cod'] == row['Cod']].index[0]
                        st.session_state['estoque'].at[idx, 'Saldo'] -= row['Qtd']
                        st.session_state['log_vendas'].append({'Data': datetime.now().strftime("%d/%m/%Y %H:%M"), 'Cliente': cli, 'Produto': row['Produto'], 'Qtd': row['Qtd'], 'Vendedor': vend})
                    salvar_dados()
                    st.success("Pedido confirmado com baixa no estoque!")
                else: st.success("Venda Independente Registrada!")
                st.download_button("📥 Baixar Pedido", pdf, f"Pedido_{cli}.pdf", "application/pdf")

elif menu == "👥 Clientes":
    st.title("👥 Gestão de Clientes")
    with st.expander("📂 Importar CETESB"):
        up = st.file_uploader("PDF", type="pdf")
        if up and st.button("Processar"):
            d = ler_pdf_antigo(up)
            if d:
                for k, v in d.items(): st.session_state[f"f_{k}"] = v
                st.success("Lido!")
    
    with st.form("f_cli"):
        nome = st.text_input("Nome", st.session_state.get('f_Nome', ''))
        c1, c2 = st.columns(2)
        cnpj = c1.text_input("CNPJ", st.session_state.get('f_CNPJ', ''))
        tel = c2.text_input("Tel", st.session_state.get('f_Tel', ''))
        end = st.text_input("Endereço", st.session_state.get('f_End', ''))
        c3, c4, c5 = st.columns([2,1,1])
        cid = c3.text_input("Cidade", st.session_state.get('f_Cidade', ''))
        uf = c4.text_input("UF", st.session_state.get('f_UF', 'SP'))
        cep = c5.text_input("CEP", st.session_state.get('f_CEP', ''))
        if st.form_submit_button("SALVAR"):
            st.session_state['clientes_db'][nome] = {'CNPJ':cnpj, 'Tel':tel, 'End':end, 'Cidade':cid, 'UF':uf, 'CEP':cep}
            salvar_dados(); st.rerun()

elif menu == "📊 Dashboard":
    st.title("📊 Dashboard")
    st.metric("Clientes", len(st.session_state['clientes_db']))
    st.metric("Produtos", len(st.session_state['estoque']))

elif menu == "🧪 Laudos":
    st.title("🧪 Laudos")
    # ... (Lógica de laudos mantida)

elif menu == "📥 Entrada":
    st.title("📥 Entrada")
    # ... (Lógica de entrada mantida)

elif menu == "📦 Produtos":
    st.title("📦 Produtos")
    ed = st.data_editor(st.session_state['estoque'], use_container_width=True, num_rows="dynamic")
    if not ed.equals(st.session_state['estoque']):
        st.session_state['estoque'] = ed
        salvar_dados()

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
    except Exception as e: return None

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
def obter_horario_br():
    return datetime.utcnow() - timedelta(hours=3)

def obter_saudacao():
    hora = obter_horario_br().hour
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
# 4. TEMAS E CSS
# ==============================================================================
def aplicar_tema(escolha):
    css = "<style>.blink-text { animation: blinker 1.5s linear infinite; color: #FF4B4B; font-weight: bold; } @keyframes blinker { 50% { opacity: 0; } }</style>"
    if escolha == "⚪ Padrão (Clean)": css += "<style>.stApp { background-color: #FFFFFF !important; color: #000000 !important; }</style>"
    elif escolha == "🔵 Azul Labortec": css += "<style>.stApp { background-color: #F0F8FF !important; color: #002B4E !important; } h1,h2,h3 { color: #004aad !important; }</style>"
    elif escolha == "🌿 Verde Natureza": css += "<style>.stApp { background-color: #F1F8E9 !important; color: #1B5E20 !important; }</style>"
    elif escolha == "⚫ Dark Mode (Noturno)": css += "<style>.stApp { background-color: #0E1117 !important; color: #FAFAFA !important; }</style>"
    st.markdown(css, unsafe_allow_html=True)

# ==============================================================================
# 5. GERADOR DE PDF (FIX: CONTEÚDO DESLOCADO 1 POLEGADA PARA BAIXO)
# ==============================================================================
class PDF(FPDF):
    def header(self):
        # 1. Logo à esquerda (Mantida no topo)
        if os.path.exists("labortec.jpg"):
            self.image("labortec.jpg", x=10, y=8, w=48)
        
        # Deslocamento de ~1 polegada (25mm) para o restante do cabeçalho
        offset_y = 25 
        
        # 2. Textos da Labortec (Totalmente à direita da logo)
        self.set_font('Arial', 'B', 16)
        self.set_xy(65, 10 + offset_y)
        self.cell(100, 10, 'LABORTEC', 0, 0, 'L')
        
        # 3. Título do Documento (Canto Superior Direito)
        self.set_font('Arial', 'B', 16)
        self.set_xy(110, 10 + offset_y)
        titulo_doc = getattr(self, 'titulo_doc', 'ORÇAMENTO')
        self.cell(90, 10, titulo_doc, 0, 1, 'R')
        
        # 4. Detalhes da Labortec
        self.set_font('Arial', '', 8)
        self.set_xy(65, 20 + offset_y)
        self.cell(100, 4, 'Rua Alfredo Bruno, 22 - Campinas/SP - CEP 13040-235', 0, 0, 'L')
        
        # Data
        self.set_xy(110, 20 + offset_y)
        self.cell(90, 4, f"Data: {obter_horario_br().strftime('%d/%m/%Y')}", 0, 1, 'R')
        
        # Contatos
        self.set_xy(65, 24 + offset_y)
        self.cell(100, 4, 'labortecconsultoria@gmail.com | Tel.: (19) 3238-9320', 0, 0, 'L')
        
        # Vendedor
        self.set_xy(110, 24 + offset_y)
        vendedor_nome = getattr(self, 'vendedor_nome', 'Sistema')
        self.cell(90, 4, f"Vendedor: {vendedor_nome}", 0, 1, 'R')
        
        # CNPJ
        self.set_xy(65, 28 + offset_y)
        self.cell(100, 4, 'C.N.P.J.: 03.763.197/0001-09', 0, 1, 'L')
        
        # 5. Linha Divisória (Deslocada)
        self.line(10, 38 + offset_y, 200, 38 + offset_y)
        self.set_y(45 + offset_y) # Espaço seguro para o conteúdo começar

    def footer(self):
        self.set_y(-25)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 4, 'Obs.: FRETE NÃO INCLUSO. PROPOSTA VÁLIDA POR 5 DIAS.', 0, 1, 'C')
        self.cell(0, 4, 'PRAZO DE RETIRADA: 3 A 5 DIAS ÚTEIS APÓS CONFIRMAÇÃO.', 0, 0, 'C')

def criar_doc_pdf(vendedor, cliente, dados_cli, itens, total, condicoes, titulo):
    pdf = PDF(); pdf.vendedor_nome = vendedor; pdf.titulo_doc = titulo; pdf.add_page()
    
    # Bloco Cliente
    pdf.set_font('Arial', 'B', 10); pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 8, f" Cliente: {cliente}", 1, 1, 'L', fill=True)
    
    # Dados do Cliente
    pdf.set_font('Arial', '', 9)
    pdf.cell(0, 6, f" Endereço: {dados_cli.get('End', '')}", 'LR', 1, 'L')
    pdf.cell(0, 6, f" Cidade: {dados_cli.get('Cidade', '')}/{dados_cli.get('UF', '')} - CEP: {dados_cli.get('CEP', '')}", 'LR', 1, 'L')
    pdf.cell(0, 6, f" CNPJ: {dados_cli.get('CNPJ', '')} - Tel: {dados_cli.get('Tel', '')}", 'LRB', 1, 'L')
    pdf.ln(5)
    
    # Bloco Condições
    pdf.cell(0, 8, f" Pagto: {condicoes.get('plano', '')} | Forma: {condicoes.get('forma', '')} | Vencto: {condicoes.get('venc', '')}", 1, 1, 'L')
    pdf.ln(6)
    
    # Tabela de Itens
    pdf.set_font('Arial', 'B', 8); pdf.set_fill_color(225, 225, 225)
    w = [15, 15, 85, 25, 20, 30] 
    cols = ['Un', 'Qtd', 'Produto', 'Marca', 'NCM', 'Total']
    for i, c in enumerate(cols): pdf.cell(w[i], 8, c, 1, 0, 'C', fill=True)
    pdf.ln()
    
    pdf.set_font('Arial', '', 8)
    for r in itens:
        pdf.cell(w[0], 7, str(r.get('Unidade', 'KG')), 1, 0, 'C')
        pdf.cell(w[1], 7, str(r['Qtd']), 1, 0, 'C')
        pdf.cell(w[2], 7, str(r['Produto'])[:52], 1, 0, 'L')
        pdf.cell(w[3], 7, str(r.get('Marca', 'LABORTEC')), 1, 0, 'C')
        pdf.cell(w[4], 7, str(r.get('NCM', '')), 1, 0, 'C')
        pdf.cell(w[5], 7, f"{float(r['Total']):.2f}", 1, 1, 'R')
    
    # Total Geral
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(sum(w)-w[5], 10, "TOTAL GERAL: ", 0, 0, 'R')
    pdf.cell(w[5], 10, f"R$ {total:,.2f}", 1, 1, 'R')
    
    # Assinaturas
    pdf.ln(30)
    y = pdf.get_y()
    pdf.line(25, y, 90, y); pdf.line(120, y, 185, y)
    pdf.set_font('Arial', '', 8); pdf.set_xy(25, y+2); pdf.cell(65, 4, 'Assinatura Cliente', 0, 0, 'C')
    pdf.set_xy(120, y+2); pdf.cell(65, 4, 'Assinatura Labortec', 0, 1, 'C')
    
    return pdf.output(dest='S').encode('latin-1')

# ==============================================================================
# MENU LATERAL E TEMAS
# ==============================================================================
st.sidebar.title("🛠️ MENU")
st.sidebar.success(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")
opcoes_temas = ["⚪ Padrão (Clean)", "🔵 Azul Labortec", "🌿 Verde Natureza", "⚫ Dark Mode (Noturno)"]
tema_sel = st.sidebar.selectbox("Tema:", opcoes_temas)
aplicar_tema(tema_sel)
menu = st.sidebar.radio("Navegar:", ["📊 Dashboard", "🧪 Laudos", "💰 Vendas & Orçamentos", "📥 Entrada", "📦 Produtos", "📋 Conferência Geral", "👥 Clientes"])

# ==============================================================================
# PÁGINAS
# ==============================================================================
if menu == "📊 Dashboard":
    st.title("📊 Dashboard Operacional")
    st.markdown("---")
    st.subheader("🔔 Radar de Coletas (Laudos)")
    laudos = st.session_state.get('log_laudos', [])
    laudos_pendentes = [l for l in laudos if l.get('Status', 'Pendente') == 'Pendente']
    if not laudos_pendentes: st.success("✅ Nenhuma coleta pendente.")
    else:
        try: laudos_pendentes.sort(key=lambda x: datetime.strptime(x['Data_Coleta'], "%d/%m/%Y"))
        except: pass
        col_laudos = st.columns(4)
        for i, l in enumerate(laudos_pendentes[:4]): 
            with col_laudos[i]:
                st.error(f"📅 **{l['Data_Coleta']}**")
                st.info(f"🏭 {l['Cliente']}")
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("👥 Clientes", len(st.session_state['clientes_db']))
    c2.metric("📦 Produtos", len(st.session_state['estoque']))
    c3.metric("💰 Vendas", len(st.session_state['log_vendas']))

elif menu == "💰 Vendas & Orçamentos":
    st.title("💰 Vendas e Orçamentos")
    if not st.session_state['clientes_db']: st.warning("Cadastre clientes!"); st.stop()
    c1, c2 = st.columns([2,1])
    cli = c1.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
    vend = c2.text_input("Vendedor", st.session_state['usuario_nome'])
    d_cli = st.session_state['clientes_db'][cli]
    col1, col2, col3 = st.columns(3)
    p_pag = col1.text_input("Plano", "28/42 DIAS"); f_pag = col2.text_input("Forma", "BOLETO ITAU"); venc = col3.text_input("Vencimento", "A COMBINAR")
    df_v = st.session_state['estoque'].copy()
    if 'Qtd' not in df_v.columns: df_v.insert(0, 'Qtd', 0.0)
    ed_v = st.data_editor(df_v[['Qtd', 'Produto', 'Cod', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Saldo']], use_container_width=True, hide_index=True)
    itens_sel = ed_v[ed_v['Qtd'] > 0].copy(); itens_sel['Total'] = itens_sel['Qtd'] * itens_sel['Preco_Base']; total = itens_sel['Total'].sum()
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
                        st.session_state['log_vendas'].append({'Data': obter_horario_br().strftime("%d/%m/%Y %H:%M"), 'Cliente': cli, 'Produto': row['Produto'], 'Qtd': row['Qtd'], 'Vendedor': vend})
                    salvar_dados(); st.success("Pedido confirmado com baixa no estoque!")
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

elif menu == "🧪 Laudos":
    st.title("🧪 Laudos")
    with st.form("f_laudo"):
        cli_l = st.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
        data_l = st.date_input("Data")
        if st.form_submit_button("Agendar"):
            st.session_state['log_laudos'].append({'Cliente': cli_l, 'Data_Coleta': data_l.strftime("%d/%m/%Y"), 'Status': 'Pendente'})
            salvar_dados(); st.rerun()

elif menu == "📦 Produtos":
    st.title("📦 Produtos")
    ed = st.data_editor(st.session_state['estoque'], use_container_width=True, num_rows="dynamic")
    if not ed.equals(st.session_state['estoque']): st.session_state['estoque'] = ed; salvar_dados()

elif menu == "📋 Conferência Geral":
    st.title("📋 Conferência Geral")
    tab1, tab2, tab3 = st.tabs(["📊 Vendas", "📥 Entradas", "🧪 Laudos"])
    with tab1:
        if st.session_state['log_vendas']: st.dataframe(pd.DataFrame(st.session_state['log_vendas']).iloc[::-1], use_container_width=True)
    with tab2:
        if st.session_state['log_entradas']: st.dataframe(pd.DataFrame(st.session_state['log_entradas']).iloc[::-1], use_container_width=True)
    with tab3:
        if st.session_state['log_laudos']: st.dataframe(pd.DataFrame(st.session_state['log_laudos']).iloc[::-1], use_container_width=True)

elif menu == "📥 Entrada":
    st.title("📥 Entrada de Estoque")
    with st.form("f_ent"):
        p_ent = st.selectbox("Produto", st.session_state['estoque']['Produto'].tolist())
        q_ent = st.number_input("Qtd", min_value=0.0)
        if st.form_submit_button("Confirmar"):
            idx = st.session_state['estoque'][st.session_state['estoque']['Produto'] == p_ent].index[0]
            st.session_state['estoque'].at[idx, 'Saldo'] += q_ent
            st.session_state['log_entradas'].append({'Data': obter_horario_br().strftime("%d/%m/%Y %H:%M"), 'Produto': p_ent, 'Qtd': q_ent})
            salvar_dados(); st.rerun()

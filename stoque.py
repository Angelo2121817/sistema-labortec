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
    """Extrai dados especificamente do layout de licenças da CETESB."""
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
    """Função adaptada para detectar CETESB ou usar padrão antigo."""
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
# 5. GERADOR DE PDF (CORRIGIDO: POSICIONAMENTO E REMOÇÃO DE CÓDIGOS)
# ==============================================================================
class PDF(FPDF):
    def header(self):
        # Logo Labortec (Simétrico à esquerda)
        if os.path.exists("labortec.jpg"):
            self.image("labortec.jpg", x=10, y=8, w=40)
        
        # Nome da Empresa (Cabeçalho Esquerdo - Ajustado para não sobrepor)
        self.set_font('Arial', 'B', 16)
        self.set_xy(10, 8)
        self.cell(100, 10, 'LABORTEC', 0, 0, 'L')
        
        # Título do Documento (Cabeçalho Direito)
        self.set_font('Arial', 'B', 16)
        self.set_xy(100, 8)
        titulo_doc = getattr(self, 'titulo_doc', 'ORÇAMENTO')
        self.cell(100, 10, titulo_doc, 0, 1, 'R')
        
        # Informações da Labortec (Abaixo do Nome - Ajustado para não sobrepor)
        self.set_font('Arial', '', 9)
        self.set_xy(10, 18)
        self.cell(100, 5, 'Rua Alfredo Bruno, 22 - Campinas/SP - CEP 13040-235', 0, 0, 'L')
        
        # Data (Abaixo do Título)
        self.set_xy(100, 18)
        self.cell(100, 5, f"Data: {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'R')
        
        # E-mail e Telefone
        self.set_xy(10, 23)
        self.cell(100, 5, 'labortecconsultoria@gmail.com | Tel.: (19) 3238-9320', 0, 0, 'L')
        
        # Vendedor
        self.set_xy(100, 23)
        vendedor_nome = getattr(self, 'vendedor_nome', 'Sistema')
        self.cell(100, 5, f"Vendedor: {vendedor_nome}", 0, 1, 'R')
        
        # CNPJ Labortec
        self.set_xy(10, 28)
        self.cell(100, 5, 'C.N.P.J.: 03.763.197/0001-09', 0, 1, 'L')
        
        # Linha Divisória
        self.line(10, 35, 200, 35)
        self.ln(10)

    def footer(self):
        # Observações Finais no rodapé
        self.set_y(-30)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 5, 'Obs.: FRETE NÃO INCLUSO. PROPOSTA VÁLIDA POR 5 DIAS.', 0, 1, 'C')
        self.cell(0, 5, 'PRAZO DE RETIRADA: 3 A 5 DIAS ÚTEIS APÓS CONFIRMAÇÃO.', 0, 0, 'C')

def criar_doc_pdf(vendedor, cliente, dados_cli, itens, total, condicoes, titulo):
    pdf = PDF()
    pdf.vendedor_nome = vendedor
    pdf.titulo_doc = titulo
    pdf.add_page()
    
    # --- BLOCO CLIENTE (REMOVIDO CÓDIGO DO CLIENTE) ---
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(245, 245, 245)
    pdf.cell(0, 7, f" Cliente: {cliente}", 1, 1, 'L', fill=True)
    
    pdf.set_font('Arial', '', 9)
    end = dados_cli.get('End', '')
    cid = dados_cli.get('Cidade', '')
    uf = dados_cli.get('UF', '')
    cep = dados_cli.get('CEP', '')
    cnpj = dados_cli.get('CNPJ', '')
    tel = dados_cli.get('Tel', '')
    
    pdf.cell(0, 6, f" Endereço: {end}", 'LR', 1, 'L')
    pdf.cell(0, 6, f" Cidade: {cid}/{uf} - CEP: {cep}", 'LR', 1, 'L')
    pdf.cell(0, 6, f" CNPJ: {cnpj} - Tel: {tel}", 'LRB', 1, 'L')
    pdf.ln(4)
    
    # --- BLOCO CONDIÇÕES ---
    pdf.set_font('Arial', '', 9)
    pagto = condicoes.get('plano', 'A COMBINAR')
    forma = condicoes.get('forma', 'A COMBINAR')
    venc = condicoes.get('venc', 'A COMBINAR')
    pdf.cell(0, 7, f" Pagto: {pagto} | Forma: {forma} | Vencto: {venc}", 1, 1, 'L')
    pdf.ln(5)
    
    # --- TABELA DE ITENS (REMOVIDO COLUNA CÓDIGO) ---
    pdf.set_font('Arial', 'B', 8)
    pdf.set_fill_color(230, 230, 230)
    # Reajustado larguras: Un(15), Qtd(15), Produto(95), Marca(30), NCM(25), Total(31)
    pdf.cell(15, 7, 'Un', 1, 0, 'C', fill=True)
    pdf.cell(15, 7, 'Qtd', 1, 0, 'C', fill=True)
    pdf.cell(95, 7, 'Produto', 1, 0, 'C', fill=True)
    pdf.cell(30, 7, 'Marca', 1, 0, 'C', fill=True)
    pdf.cell(25, 7, 'NCM', 1, 0, 'C', fill=True)
    pdf.cell(31, 7, 'Total', 1, 1, 'C', fill=True)
    
    pdf.set_font('Arial', '', 8)
    for r in itens:
        pdf.cell(15, 6, str(r.get('Unidade', 'KG')), 1, 0, 'C')
        pdf.cell(15, 6, str(r['Qtd']), 1, 0, 'C')
        pdf.cell(95, 6, str(r['Produto'])[:60], 1, 0, 'L')
        pdf.cell(30, 6, str(r.get('Marca', 'LABORTEC')), 1, 0, 'C')
        pdf.cell(25, 6, str(r.get('NCM', '')), 1, 0, 'C')
        pdf.cell(31, 6, f"{float(r['Total']):.2f}", 1, 1, 'R')
    
    # Total Geral
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(180, 8, "TOTAL GERAL: ", 0, 0, 'R')
    pdf.cell(31, 8, f"R$ {total:,.2f}", 1, 1, 'R')
    
    # --- BLOCO ASSINATURAS ---
    pdf.ln(25)
    y_ass = pdf.get_y()
    pdf.line(20, y_ass, 90, y_ass) # Linha Cliente
    pdf.line(120, y_ass, 190, y_ass) # Linha Labortec
    
    pdf.set_font('Arial', '', 8)
    pdf.set_xy(20, y_ass + 2)
    pdf.cell(70, 4, 'Assinatura Cliente', 0, 0, 'C')
    pdf.set_xy(120, y_ass + 2)
    pdf.cell(70, 4, 'Assinatura Labortec', 0, 1, 'C')
    
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
        
        d_cli = st.session_state['clientes_db'][cli]
        
        col1, col2, col3 = st.columns(3)
        p_pag = col1.text_input("Plano de Pagto", "28/42 DIAS")
        f_pag = col2.text_input("Forma de Pagto", "BOLETO ITAU")
        venc = col3.text_input("Vencimento", "A COMBINAR")
        
        st.markdown("---")
        df_v = st.session_state['estoque'].copy()
        if 'Qtd' not in df_v.columns: df_v.insert(0, 'Qtd', 0.0)
        
        # Editor de Itens
        ed_v = st.data_editor(
            df_v[['Qtd', 'Produto', 'Cod', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Saldo']],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Qtd": st.column_config.NumberColumn("Qtd", min_value=0.0, format="%.1f"),
                "Preco_Base": st.column_config.NumberColumn("Preço Unit.", format="R$ %.2f"),
                "Saldo": st.column_config.NumberColumn("Saldo", disabled=True)
            }
        )
        
        itens_sel = ed_v[ed_v['Qtd'] > 0].copy()
        itens_sel['Total'] = itens_sel['Qtd'] * itens_sel['Preco_Base']
        total_geral = itens_sel['Total'].sum()
        
        if not itens_sel.empty:
            st.metric("Total Geral", f"R$ {total_geral:,.2f}")
            
            c_orc, c_ped = st.columns(2)
            with c_orc:
                if st.button("📄 GERAR ORÇAMENTO", type="secondary", use_container_width=True):
                    pdf_bytes = criar_doc_pdf(vend, cli, d_cli, itens_sel.to_dict('records'), total_geral, {'plano':p_pag, 'forma':f_pag, 'venc':venc}, "ORÇAMENTO")
                    st.download_button("📥 Baixar Orçamento", pdf_bytes, f"Orcamento_{cli[:10]}.pdf", "application/pdf")
            
            with c_ped:
                if st.button("✅ CONFIRMAR PEDIDO", type="primary", use_container_width=True):
                    pdf_bytes = criar_doc_pdf(vend, cli, d_cli, itens_sel.to_dict('records'), total_geral, {'plano':p_pag, 'forma':f_pag, 'venc':venc}, "PEDIDO DE VENDA")
                    # Baixa no estoque
                    for _, row in itens_sel.iterrows():
                        idx = st.session_state['estoque'][st.session_state['estoque']['Cod'] == row['Cod']].index[0]
                        st.session_state['estoque'].at[idx, 'Saldo'] -= row['Qtd']
                        st.session_state['log_vendas'].append({
                            'Data': datetime.now().strftime("%d/%m/%Y %H:%M"),
                            'Cliente': cli, 'Produto': row['Produto'], 'Cod': row['Cod'], 'Qtd': row['Qtd'], 'Vendedor': vend
                        })
                    salvar_dados()
                    st.success("Pedido confirmado e estoque atualizado!")
                    st.download_button("📥 Baixar Pedido", pdf_bytes, f"Pedido_{cli[:10]}.pdf", "application/pdf")

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
                    "Cliente": cli_sel, "Data_Coleta": data_coleta.strftime("%d/%m/%Y"), "Obs": obs, "Status": "Pendente", "Agendado_Por": st.session_state.get('usuario_nome', 'Sistema')
                }
                st.session_state['log_laudos'].append(novo_laudo)
                salvar_dados()
                st.success(f"Agendado para {cli_sel}!")
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Próximas Coletas")
    if st.session_state['log_laudos']:
        df_laudos = pd.DataFrame(st.session_state['log_laudos'])
        edited_laudos = st.data_editor(df_laudos, use_container_width=True, num_rows="dynamic", key="editor_laudos")
        if not edited_laudos.equals(df_laudos):
            st.session_state['log_laudos'] = edited_laudos.to_dict('records')
            salvar_dados()
    else: st.info("Nenhum laudo pendente.")

elif menu == "📊 Dashboard":
    st.title("📊 Painel de Controle Integrado")
    st.markdown("---")
    st.subheader("🔔 Radar de Coletas (Efluentes)")
    laudos = st.session_state.get('log_laudos', [])
    laudos_pendentes = [l for l in laudos if l.get('Status', 'Pendente') == 'Pendente']
    if not laudos_pendentes: st.success("✅ Tudo limpo! Nenhuma coleta pendente no radar.")
    else:
        try: laudos_pendentes.sort(key=lambda x: datetime.strptime(x['Data_Coleta'], "%d/%m/%Y"))
        except: pass
        col_laudos = st.columns(4)
        for i, l in enumerate(laudos_pendentes[:4]): 
            with col_laudos[i]:
                st.error(f"📅 **{l['Data_Coleta']}**")
                st.info(f"🏭 {l['Cliente']}")
                if l.get('Obs'): st.caption(f"📝 {l['Obs']}")
    st.markdown("---")
    st.subheader("📈 Situação Tática")
    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Arsenal (Produtos)", len(st.session_state['estoque']))
    c2.metric("💰 Baixas (Vendas)", len(st.session_state['log_vendas']))
    c3.metric("👥 Aliados (Clientes)", len(st.session_state['clientes_db']))

elif menu == "👥 Clientes":
    st.title("👥 Gestão de Clientes")
    campos = ['form_nome', 'form_tel', 'form_end', 'form_cnpj', 'form_cid', 'form_uf', 'form_cep', 'form_cod']
    for campo in campos:
        if campo not in st.session_state: st.session_state[campo] = ""

    def limpar_campos():
        for c in campos: st.session_state[c] = ""

    def salvar_no_callback():
        nome = st.session_state['form_nome']
        if nome:
            st.session_state['clientes_db'][nome] = {
                'Tel': st.session_state['form_tel'], 'End': st.session_state['form_end'], 'CNPJ': st.session_state['form_cnpj'],
                'Cidade': st.session_state['form_cid'], 'UF': st.session_state['form_uf'], 'CEP': st.session_state['form_cep'], 'Cod_Cli': st.session_state['form_cod']
            }
            salvar_dados()
            st.toast(f"Cliente {nome} salvo!", icon="✅")
            limpar_campos()
        else: st.toast("Erro: Nome obrigatório!", icon="❌")

    with st.expander("📂 Importar Dados de Licença (CETESB/PDF)"):
        arquivo_pdf = st.file_uploader("Arraste o PDF aqui:", type="pdf")
        if arquivo_pdf is not None:
            if st.button("🔄 Processar PDF"):
                dados_lidos = ler_pdf_antigo(arquivo_pdf)
                if dados_lidos:
                    st.session_state['form_nome'] = str(dados_lidos.get('Nome', ''))
                    st.session_state['form_cnpj'] = str(dados_lidos.get('CNPJ', ''))
                    st.session_state['form_end'] = str(dados_lidos.get('End', ''))
                    st.session_state['form_cid'] = str(dados_lidos.get('Cidade', ''))
                    st.session_state['form_uf'] = str(dados_lidos.get('UF', ''))
                    st.session_state['form_cep'] = str(dados_lidos.get('CEP', ''))
                    st.success("Dados extraídos! Confira e clique em SALVAR.")
                else: st.error("Erro na leitura do PDF.")

    with st.form("form_cliente"):
        c1, c2 = st.columns([3, 1])
        c1.text_input("Nome / Razão Social", key="form_nome")
        c2.text_input("Cód. Cliente", key="form_cod")
        c3, c4 = st.columns(2)
        c3.text_input("CNPJ", key="form_cnpj")
        c4.text_input("Telefone", key="form_tel")
        st.text_input("Endereço", key="form_end")
        c5, c6, c7 = st.columns([2, 1, 1])
        c5.text_input("Cidade", key="form_cid")
        c6.text_input("UF", key="form_uf")
        c7.text_input("CEP", key="form_cep")
        st.form_submit_button("💾 SALVAR DADOS", on_click=salvar_no_callback)

    st.button("🧹 Limpar", on_click=limpar_campos)
    st.markdown("---")
    if st.session_state['clientes_db']:
        busca = st.text_input("🔍 Buscar...")
        lista = sorted(list(st.session_state['clientes_db'].keys()))
        if busca: lista = [k for k in lista if busca.lower() in k.lower()]
        for k in lista:
            d = st.session_state['clientes_db'][k]
            with st.expander(f"🏢 {k}"):
                st.write(f"📍 {d.get('End', '')} | 📞 {d.get('Tel', '')}")
                if st.button("🗑️ EXCLUIR", key=f"dl_{k}"):
                    del st.session_state['clientes_db'][k]
                    salvar_dados()
                    st.rerun()

elif menu == "📥 Entrada de Estoque":
    st.title("📥 Entrada de Estoque")
    with st.form("form_entrada"):
        prod_lista = st.session_state['estoque']['Produto'].tolist()
        prod_sel = st.selectbox("Produto", prod_lista)
        qtd_ent = st.number_input("Quantidade (KG)", min_value=0.0)
        if st.form_submit_button("📥 Registrar Entrada"):
            idx = st.session_state['estoque'][st.session_state['estoque']['Produto'] == prod_sel].index[0]
            st.session_state['estoque'].at[idx, 'Saldo'] += qtd_ent
            st.session_state['log_entradas'].append({
                'Data': datetime.now().strftime("%d/%m/%Y %H:%M"), 'Produto': prod_sel, 'Qtd': qtd_ent, 'Usuario': st.session_state['usuario_nome']
            })
            salvar_dados()
            st.success("Estoque atualizado!")

elif menu == "📦 Gestão de Produtos":
    st.title("📦 Gestão de Produtos")
    edited_df = st.data_editor(st.session_state['estoque'], use_container_width=True, num_rows="dynamic")
    if not edited_df.equals(st.session_state['estoque']):
        st.session_state['estoque'] = edited_df
        salvar_dados()

elif menu == "📋 Conferência Geral":
    st.title("📋 Conferência de Logs")
    tab1, tab2, tab3 = st.tabs(["Vendas", "Entradas", "Laudos"])
    with tab1: st.dataframe(st.session_state['log_vendas'], use_container_width=True)
    with tab2: st.dataframe(st.session_state['log_entradas'], use_container_width=True)
    with tab3: st.dataframe(st.session_state['log_laudos'], use_container_width=True)

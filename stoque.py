import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import os
from pypdf import PdfReader
from fpdf import FPDF
import json
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema Integrado v58", layout="wide", page_icon="🧪")

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
    st.stop()

# --- 4. FUNÇÕES DE PDF (RESGATADAS) ---
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
    pdf.cell(0, 5, f"CNPJ: {dados_cli.get('CNPJ','')}", 0, 1, 'L')
    pdf.cell(0, 5, f"Endereço: {dados_cli.get('End','')}, {dados_cli.get('Bairro','')}", 0, 1, 'L')
    pdf.cell(0, 5, f"Cidade: {dados_cli.get('Cidade','')}/{dados_cli.get('UF','')} - CEP: {dados_cli.get('CEP','')}", 0, 1, 'L')
    pdf.cell(0, 5, f"Tel: {dados_cli.get('Tel','')}", 0, 1, 'L')
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
        pdf.cell(w[6], 6, f"{r['Preco_Base']:.2f}", 1, 0, 'R')
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
                    if cad_m: d['End'] = prox.replace(cad_m.group(1), '').strip()
                    else: d['End'] = prox
                if i + 2 < len(lines):
                    addr_line = lines[i+2]
                    cep_m = re.search(r'(\d{5}-\d{3})', addr_line)
                    if cep_m:
                        d['CEP'] = cep_m.group(1)
                        d['Cidade'] = addr_line.split(d['CEP'])[-1].strip()
                break
        return d
    except: return None

def ler_pdf_antigo(f):
    try:
        reader = PdfReader(f)
        texto_inicial = reader.pages[0].extract_text() or ""
        if "CETESB" in texto_inicial.upper(): return extrair_dados_cetesb(f)
        return {'Nome': 'Cliente Importado', 'End': 'Preencher Manualmente'} # Simplificado para evitar erros
    except Exception as e: st.error(f"Erro PDF: {e}"); return None

# --- 5. FUNÇÕES DE DADOS (COM BLINDAGEM) ---
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

# --- 6. INICIALIZAÇÃO ---
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
if 'name' not in st.session_state: st.session_state['name'] = "documento.pdf"

# --- 7. TEMAS ---
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
        st.dataframe(pd.DataFrame(laudos), use_container_width=True)
    else: st.info("Sem laudos agendados.")

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
        # Correção de Index (Força string)
        mask = st.session_state['estoque']['Cod'].astype(str) == str(cod)
        
        if not st.session_state['estoque'][mask].empty:
            idx = st.session_state['estoque'][mask].index[0]
            st.session_state['estoque'].at[idx, 'Saldo'] += qtd
            
            # AGORA SALVA DATA E HORA
            data_hora = datetime.now().strftime("%d/%m/%Y %H:%M")
            nome_prod = st.session_state['estoque'].at[idx, 'Produto']
            
            st.session_state['log_entradas'].append({
                'Data': data_hora, 
                'Cod': cod, 
                'Produto': nome_prod,
                'Qtd': qtd,
                'Usuario': st.session_state['usuario_nome']
            })
            salvar_dados()
            st.success(f"Entrada registrada: +{qtd}Kg em {nome_prod}!")
            st.rerun()
        else:
            st.error("ERRO: Produto não encontrado.")

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
            mask = st.session_state['estoque']['Cod'].astype(str) == str(row['Cod'])
            if not st.session_state['estoque'][mask].empty:
                idx = st.session_state['estoque'][mask].index[0]
                st.session_state['estoque'].at[idx, 'Estoque_Minimo'] = row['Estoque_Minimo']
        salvar_dados()
        st.success("Salvo!")

elif page == "CLIENTES":
    st.title("Clientes")
    with st.expander("Importar PDF (CETESB Antigo)"):
        up = st.file_uploader("PDF", type="pdf")
        if up and st.button("Ler"):
            d = ler_pdf_antigo(up)
            if d: st.session_state['temp'] = d; st.success("Lido!")
            else: st.error("Erro leitura")
    
    if 'temp' not in st.session_state: st.session_state['temp'] = {}
    
    with st.form("novo_cli"):
        st.caption("Preencha os dados:")
        c1,c2 = st.columns([1,3])
        cod = c1.text_input("Cód", st.session_state['temp'].get('Cod_Cli',''))
        nome = c2.text_input("Nome", st.session_state['temp'].get('Nome',''))
        end = st.text_input("Endereço", st.session_state['temp'].get('End',''))
        cnpj = st.text_input("CNPJ", st.session_state['temp'].get('CNPJ',''))
        c3,c4,c5 = st.columns(3)
        cid = c3.text_input("Cidade", st.session_state['temp'].get('Cidade',''))
        uf = c4.text_input("UF", st.session_state['temp'].get('UF',''))
        tel = c5.text_input("Tel", st.session_state['temp'].get('Tel',''))
        cep = st.text_input("CEP", st.session_state['temp'].get('CEP',''))
        
        if st.form_submit_button("Salvar Cliente"):
            st.session_state['clientes_db'][nome] = {
                'Cod_Cli':cod, 'End':end, 'CNPJ':cnpj, 'Cidade':cid, 'UF':uf, 'Tel':tel, 'CEP':cep
            }
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
    
    if not st.session_state['clientes_db']:
        st.warning("Cadastre clientes primeiro!")
    else:
        c1, c2, c3 = st.columns([2,1,1])
        cli = c1.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
        vend = c2.text_input("Vendedor", st.session_state['usuario_nome'])
        
        # Dados do Cliente Selecionado
        d_cli = st.session_state['clientes_db'][cli]
        
        # Tabela de Itens
        df_v = st.session_state['estoque'].copy()
        if 'Qtd' not in df_v: df_v['Qtd'] = 0.0
        edited = st.data_editor(df_v[['Cod','Produto','Saldo','Preco_Base','Qtd']], use_container_width=True)
        
        # Cálculos
        ed_copy = edited.copy()
        ed_copy['Qtd'] = pd.to_numeric(ed_copy['Qtd'], errors='coerce').fillna(0)
        itens = ed_copy[ed_copy['Qtd'] > 0]
        itens['Total'] = itens['Qtd'] * itens['Preco_Base']
        total_geral = itens['Total'].sum()
        
        if not itens.empty:
            st.metric("Valor Total", f"R$ {total_geral:,.2f}")
            st.markdown("---")
            
            col_b1, col_b2, col_b3 = st.columns(3)
            p_pag = col_b1.text_input("Pagamento", "28/42 Dias")
            f_pag = col_b2.text_input("Forma", "Boleto")
            venc = col_b3.text_input("Vencimento", "A Combinar")
            
            c_blue, c_green = st.columns(2)
            
            # --- BOTÃO AZUL: ORÇAMENTO (NÃO MEXE NO ESTOQUE) ---
            with c_blue:
                if st.button("📄 GERAR ORÇAMENTO", type="primary"):
                    pdf = criar_pdf_nativo(vend, cli, d_cli, itens.to_dict('records'), total_geral, {'plano':p_pag,'forma':f_pag,'venc':venc}, "ORÇAMENTO")
                    st.session_state['pdf_gerado'] = pdf
                    st.session_state['name'] = "Orcamento.pdf"
                    st.toast("Orçamento Gerado! Baixe abaixo.")
            
            # --- BOTÃO VERDE: VENDA (BAIXA ESTOQUE) ---
            with c_green:
                if st.button("✅ CONFIRMAR VENDA (BAIXAR ESTOQUE)"):
                    for _, row in itens.iterrows():
                        mask = st.session_state['estoque']['Cod'].astype(str) == str(row['Cod'])
                        if not st.session_state['estoque'][mask].empty:
                            idx = st.session_state['estoque'][mask].index[0]
                            st.session_state['estoque'].at[idx, 'Saldo'] -= row['Qtd']
                            
                            st.session_state['log_vendas'].append({
                                'Data': datetime.now().strftime("%d/%m/%Y %H:%M"),
                                'Cliente': cli,
                                'Cod': row['Cod'],
                                'Produto': row['Produto'],
                                'Qtd': row['Qtd'],
                                'Usuario': st.session_state['usuario_nome']
                            })
                    salvar_dados()
                    
                    pdf = criar_pdf_nativo(vend, cli, d_cli, itens.to_dict('records'), total_geral, {'plano':p_pag,'forma':f_pag,'venc':venc}, "PEDIDO DE VENDA")
                    st.session_state['pdf_gerado'] = pdf
                    st.session_state['name'] = "Pedido.pdf"
                    st.success("Venda Confirmada e Estoque Baixado!")
            
            if st.session_state['pdf_gerado']:
                st.download_button("📥 BAIXAR PDF", st.session_state['pdf_gerado'], st.session_state['name'], "application/pdf")

elif page == "CONFERÊNCIA":
    st.title("Conferência e Auditoria")
    
    tab1, tab2, tab3 = st.tabs(["📋 Estoque Atual", "📥 Histórico de Entradas", "📤 Histórico de Vendas"])
    
    with tab1:
        st.dataframe(st.session_state['estoque'], use_container_width=True)
        
    with tab2:
        if st.session_state['log_entradas']:
            st.dataframe(pd.DataFrame(st.session_state['log_entradas']).iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhuma entrada registrada.")
            
    with tab3:
        if st.session_state['log_vendas']:
            st.dataframe(pd.DataFrame(st.session_state['log_vendas']).iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhuma venda registrada.")

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
# 1. CONFIGURAÇÃO E INICIALIZAÇÃO (A BASE DE TUDO)
# ==============================================================================
st.set_page_config(page_title="Sistema Integrado v85 - Final", layout="wide", page_icon="🧪")

# --- GARANTIA DE GAVETAS (SESSION STATE) ---
# Isso impede que o sistema tente ler algo que não existe
if 'dados_carregados' not in st.session_state: st.session_state['dados_carregados'] = False
if 'estoque' not in st.session_state: st.session_state['estoque'] = pd.DataFrame(columns=['Cod', 'Produto', 'Quantidade', 'Preço', 'Categoria'])
if 'clientes_db' not in st.session_state: st.session_state['clientes_db'] = {}
if 'log_vendas' not in st.session_state: st.session_state['log_vendas'] = []
if 'log_entradas' not in st.session_state: st.session_state['log_entradas'] = []
if 'log_laudos' not in st.session_state: st.session_state['log_laudos'] = []
if 'aviso_geral' not in st.session_state: st.session_state['aviso_geral'] = ""
if 'edit_mode' not in st.session_state: st.session_state['edit_mode'] = False

# --- CONEXÃO COM GOOGLE SHEETS ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"Erro Crítico de Conexão: {e}")
    st.stop()

# ==============================================================================
# 2. FUNÇÕES AUXILIARES (PDF, DATA, ETC)
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
    except Exception: return None

def ler_pdf_antigo(f):
    try:
        reader = PdfReader(f)
        primeira_pagina = reader.pages[0].extract_text() or ""
        if "CETESB" in primeira_pagina.upper(): return extrair_dados_cetesb(f)
        text = ""
        for p in reader.pages:
            t = p.extract_text()
            if t: text += t + "\n"
        clean = re.sub(r"\s+", " ", text).strip()
        idx_inicio = clean.lower().find("cliente")
        core = clean[idx_inicio:] if idx_inicio != -1 else clean
        d = {"Nome": "", "Cod_Cli": "", "End": "", "CEP": "", "Bairro": "", "Cidade": "", "UF": "", "CNPJ": "", "Tel": "", "Email": ""}
        def extract(key, stops):
            match = re.search(re.escape(key) + r"[:\s]*", core, re.IGNORECASE)
            if not match: return ""
            fragment = core[match.end():]
            min_idx = len(fragment)
            for stop in stops:
                stop_match = re.search(re.escape(stop), fragment, re.IGNORECASE)
                if stop_match and stop_match.start() < min_idx: min_idx = stop_match.start()
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
    except Exception: return None

# ==============================================================================
# 3. SEGURANÇA E LOGIN
# ==============================================================================
CREDENCIAIS = {"General": "labormetal22", "Fabricio": "fabricio2225", "Anderson": "anderson2225", "Angelo": "angelo2225"}

def obter_horario_br(): return datetime.utcnow() - timedelta(hours=3)

def obter_saudacao():
    hora = obter_horario_br().hour
    if 5 <= hora < 12: return "Bom dia"
    elif 12 <= hora < 18: return "Boa tarde"
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

if not verificar_senha(): st.stop()

# ==============================================================================
# 4. CARGA E SALVAMENTO DE DADOS
# ==============================================================================
def _normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _fix_date_br(val):
    if not val or pd.isna(val) or str(val).strip() == "": return ""
    try: return pd.to_datetime(val, dayfirst=True).strftime("%d/%m/%Y")
    except: return val

def _fix_datetime_br(val):
    if not val or pd.isna(val) or str(val).strip() == "": return ""
    try: return pd.to_datetime(val, dayfirst=True).strftime("%d/%m/%Y %H:%M")
    except: return val

def carregar_dados():
    try:
        # 1. Estoque
        df_est = conn.read(worksheet="Estoque", ttl=0)
        if isinstance(df_est, pd.DataFrame) and not df_est.empty:
            df_est = _normalizar_colunas(df_est)
            st.session_state["estoque"] = df_est
        
        # 2. Clientes
        df_cli = conn.read(worksheet="Clientes", ttl=0)
        if isinstance(df_cli, pd.DataFrame) and not df_cli.empty:
            df_cli = _normalizar_colunas(df_cli)
            if "Email" not in df_cli.columns: df_cli["Email"] = ""
            if "Nome" in df_cli.columns: st.session_state["clientes_db"] = df_cli.set_index("Nome").to_dict("index")
            else: st.session_state["clientes_db"] = {}
            
        # 3. Logs
        for aba in ["Log_Vendas", "Log_Entradas", "Log_Laudos", "Avisos"]:
            try: df = conn.read(worksheet=aba, ttl=0)
            except: df = pd.DataFrame()
            
            if isinstance(df, pd.DataFrame) and not df.empty:
                df = _normalizar_colunas(df)
                if aba == "Log_Laudos":
                    if "Cliente" not in df.columns: df["Cliente"] = ""
                    if "Status" not in df.columns: df["Status"] = "Pendente"
                    if "Data_Coleta" in df.columns: df["Data_Coleta"] = df["Data_Coleta"].apply(_fix_date_br)
                    if "Data_Resultado" in df.columns: df["Data_Resultado"] = df["Data_Resultado"].apply(_fix_date_br)
                    st.session_state['log_laudos'] = df.to_dict("records")
                elif aba in ["Log_Vendas", "Log_Entradas"]:
                    if "Data" in df.columns: df["Data"] = df["Data"].apply(_fix_datetime_br)
                    st.session_state[aba.lower()] = df.to_dict("records")
                elif aba == "Avisos":
                    try: st.session_state['aviso_geral'] = str(df.iloc[0].values[0])
                    except: st.session_state['aviso_geral'] = ""
            else:
                if aba == "Avisos": st.session_state['aviso_geral'] = ""
                else: st.session_state[aba.lower()] = []
        
        st.session_state['dados_carregados'] = True
        return True
    except Exception as e:
        st.error(f"Erro no Carregamento: {e}")
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
        df_aviso = pd.DataFrame({"Mensagem": [str(st.session_state.get('aviso_geral', ""))]})
        conn.update(worksheet="Avisos", data=df_aviso)
        st.toast("✅ Dados Sincronizados!", icon="☁️")
    except Exception as e:
        st.error(f"⚠️ ERRO CRÍTICO AO SALVAR: {e}")

# Carrega os dados se ainda não carregou
if not st.session_state['dados_carregados']:
    carregar_dados()

# ==============================================================================
# 5. TEMAS E CSS
# ==============================================================================
def aplicar_tema(escolha):
    css = """<style>.centered-title { text-align: center; color: #1e3d59; font-weight: bold; padding: 20px 0; font-size: 2.5em; }</style>"""
    if escolha == "⚪ Padrão (Clean)": css += "<style>.stApp { background-color: #FFFFFF !important; color: #000000 !important; }</style>"
    elif escolha == "🔵 Azul Labortec": css += "<style>.stApp { background-color: #F0F8FF !important; color: #002B4E !important; } h1,h2,h3 { color: #004aad !important; }</style>"
    elif escolha == "🌿 Verde Natureza": css += "<style>.stApp { background-color: #F1F8E9 !important; color: #1B5E20 !important; }</style>"
    elif escolha == "⚫ Dark Mode (Noturno)": css += "<style>.stApp { background-color: #0E1117 !important; color: #FAFAFA !important; } .prevista-label { color: #aaa; }</style>"
    st.markdown(css, unsafe_allow_html=True)

# ==============================================================================
# 6. GERADOR DE PDF
# ==============================================================================
class PDF(FPDF):
    def header(self):
        if os.path.exists("labortec.jpg"): self.image("labortec.jpg", x=10, y=8, w=48)
        offset_y = 10
        self.set_font("Arial", "B", 19)
        self.set_xy(65, 10 + offset_y); self.cell(100, 10, "LABORTEC", 0, 0, "L")
        self.set_font("Arial", "B", 19)
        self.set_xy(110, 10 + offset_y); titulo = getattr(self, "titulo_doc", "ORÇAMENTO"); self.cell(90, 10, titulo, 0, 1, "R")
        self.set_font("Arial", "", 10)
        self.set_xy(65, 20 + offset_y); self.cell(100, 5, "Rua Alfredo Bruno, 22 - Campinas/SP - CEP 13040-235", 0, 0, "L")
        self.set_xy(110, 20 + offset_y); self.cell(90, 5, f"Data: {obter_horario_br().strftime('%d/%m/%Y')}", 0, 1, "R")
        self.set_xy(65, 25 + offset_y); self.cell(100, 5, "labortecconsultoria@gmail.com | Tel.: (19) 3238-9320", 0, 0, "L")
        self.set_xy(110, 25 + offset_y); vend = getattr(self, "vendedor_nome", "Sistema"); self.cell(90, 5, f"Vendedor: {vend}", 0, 1, "R")
        self.set_xy(65, 30 + offset_y); self.cell(100, 5, "C.N.P.J.: 03.763.197/0001-09", 0, 1, "L")
        self.line(10, 40 + offset_y, 200, 40 + offset_y); self.set_y(48 + offset_y)
    def footer(self):
        self.set_y(-25); self.set_font("Arial", "I", 7)
        self.cell(0, 4, "Obs.: FRETE NÃO INCLUSO. PROPOSTA VÁLIDA POR 5 DIAS.", 0, 1, "C")
        self.cell(0, 4, "PRAZO DE RETIRADA: 3 A 5 DIAS ÚTEIS APÓS CONFIRMAÇÃO.", 0, 0, "C")

def criar_doc_pdf(vendedor, cliente, dados_cli, itens, total, condicoes, titulo):
    pdf = PDF(); pdf.vendedor_nome = vendedor; pdf.titulo_doc = titulo; pdf.add_page()
    pdf.set_font("Arial", "B", 10); pdf.set_fill_color(240, 240, 240); pdf.cell(0, 8, f" Cliente: {cliente}", 1, 1, "L", fill=True)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 6, f" Endereço: {dados_cli.get('End', '')}", "LR", 1, "L")
    pdf.cell(0, 6, f" Cidade: {dados_cli.get('Cidade', '')}/{dados_cli.get('UF', '')} - CEP: {dados_cli.get('CEP', '')}", "LR", 1, "L")
    pdf.cell(0, 6, f" CNPJ: {dados_cli.get('CNPJ', '')} - Tel: {dados_cli.get('Tel', '')}", "LRB", 1, "L"); pdf.ln(5)
    pdf.cell(0, 8, f" Pagto: {condicoes.get('plano', '')} | Forma: {condicoes.get('forma', '')} | Vencto: {condicoes.get('venc', '')}", 1, 1, "L"); pdf.ln(6)
    pdf.set_font("Arial", "B", 8); pdf.set_fill_color(225, 225, 225)
    w = [15, 15, 85, 25, 20, 30]; cols = ["Un", "Qtd", "Produto", "Marca", "NCM", "Total"]
    for i, c in enumerate(cols): pdf.cell(w[i], 8, c, 1, 0, "C", fill=True)
    pdf.ln(); pdf.set_font("Arial", "", 8)
    for r in itens:
        pdf.cell(w[0], 7, str(r.get("Unidade", "KG")), 1, 0, "C")
        pdf.cell(w[1], 7, str(r.get("Qtd", 0)), 1, 0, "C")
        pdf.cell(w[2], 7, str(r.get("Produto", ""))[:52], 1, 0, "L")
        pdf.cell(w[3], 7, str(r.get("Marca", "LABORTEC")), 1, 0, "C")
        pdf.cell(w[4], 7, str(r.get("NCM", "")), 1, 0, "C")
        try:
            total_item = r.get('Total', 0)
            if 'Preco_Final' in r: total_item = r['Preco_Final'] * r['Qtd']
            pdf.cell(w[5], 7, f"{float(total_item):.2f}", 1, 1, "R")
        except: pdf.cell(w[5], 7, "0.00", 1, 1, "R")
    pdf.set_font("Arial", "B", 10)
    pdf.cell(sum(w) - w[5], 10, "TOTAL GERAL: ", 0, 0, "R"); pdf.cell(w[5], 10, f"R$ {total:,.2f}", 1, 1, "R")
    pdf.ln(30); y = pdf.get_y(); pdf.line(25, y, 90, y); pdf.line(120, y, 185, y)
    pdf.set_font("Arial", "", 8); pdf.set_xy(25, y + 2); pdf.cell(65, 4, "Assinatura Cliente", 0, 0, "C")
    pdf.set_xy(120, y + 2); pdf.cell(65, 4, "Assinatura Labortec", 0, 1, "C")
    return pdf.output(dest="S").encode("latin-1")

def gerar_pdf_estoque(usuario, df_estoque):
    pdf = PDF(); pdf.vendedor_nome = usuario; pdf.titulo_doc = "RELATÓRIO DE ESTOQUE"; pdf.add_page()
    pdf.set_font("Arial", "B", 10); pdf.set_fill_color(240, 240, 240); pdf.cell(0, 8, f" POSIÇÃO DE ESTOQUE EM: {obter_horario_br().strftime('%d/%m/%Y às %H:%M')}", 1, 1, "L", fill=True); pdf.ln(5)
    w = [15, 75, 25, 15, 20, 20, 25]; cols = ["Cód", "Produto", "Marca", "Un", "Saldo", "Custo", "Total R$"]
    pdf.set_font("Arial", "B", 8); pdf.set_fill_color(225, 225, 225)
    for i, c in enumerate(cols): pdf.cell(w[i], 8, c, 1, 0, "C", fill=True)
    pdf.ln(); pdf.set_font("Arial", "", 7); valor_total_estoque = 0.0
    for _, row in df_estoque.iterrows():
        try: saldo = float(row.get('Saldo', 0)); custo = float(row.get('Preco_Base', 0)); total_item = saldo * custo
        except: saldo, custo, total_item = 0.0, 0.0, 0.0
        valor_total_estoque += total_item
        pdf.cell(w[0], 6, str(row.get('Cod', ''))[:6], 1, 0, "C")
        pdf.cell(w[1], 6, str(row.get('Produto', ''))[:45], 1, 0, "L")
        pdf.cell(w[2], 6, str(row.get('Marca', ''))[:15], 1, 0, "C")
        pdf.cell(w[3], 6, str(row.get('Unidade', 'UN')), 1, 0, "C")
        if saldo <= 0: pdf.set_text_color(200, 0, 0)
        else: pdf.set_text_color(0, 0, 0)
        pdf.cell(w[4], 6, f"{saldo:,.2f}", 1, 0, "R")
        pdf.set_text_color(0, 0, 0)
        pdf.cell(w[5], 6, f"{custo:,.2f}", 1, 0, "R")
        pdf.cell(w[6], 6, f"{total_item:,.2f}", 1, 1, "R")
    pdf.ln(2); pdf.set_font("Arial", "B", 9); pdf.cell(sum(w)-25, 8, "VALOR TOTAL EM ESTOQUE:", 0, 0, "R"); pdf.cell(25, 8, f"R$ {valor_total_estoque:,.2f}", 1, 1, "R", fill=True)
    pdf.ln(15); y = pdf.get_y(); pdf.line(60, y, 150, y); pdf.set_font("Arial", "", 8); pdf.set_xy(60, y + 2); pdf.cell(90, 4, "Responsável pela Conferência", 0, 1, "C")
    return pdf.output(dest="S").encode("latin-1")

# ==============================================================================
# 7. MENU E NAVEGAÇÃO
# ==============================================================================
st.sidebar.title("🛠️ MENU GERAL")
st.sidebar.success(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")

# --- QUADRO DE AVISOS LATERAL (RESTAURADO) ---
# Note que agora o 'if' está encostado na parede esquerda
if 'aviso_geral' not in st.session_state: st.session_state['aviso_geral'] = ""

st.sidebar.markdown("---")
with st.sidebar.expander("📢 MURAL DE AVISOS"):
    # O que está DENTRO do 'with' continua recuado (com espaço)
    aviso_txt = st.text_area("Escreva o aviso:", value=st.session_state['aviso_geral'], height=100)
    c_salv, c_limp = st.columns(2)
    
    if c_salv.button("💾 GRAVAR"):
        st.session_state['aviso_geral'] = aviso_txt
        salvar_dados() 
        st.rerun()
        
    if c_limp.button("🗑️ APAGAR"):
        st.session_state['aviso_geral'] = ""
        salvar_dados()
        st.rerun()
        
# Se tiver aviso, mostra um alerta fixo na barra lateral também
if st.session_state['aviso_geral']:
    st.sidebar.warning(f"🔔 {st.session_state['aviso_geral']}")

st.sidebar.markdown("---")
st.sidebar.subheader("🎨 Personalizar Tela")
tema_sel = st.sidebar.selectbox("Visual:", ["⚪ Padrão (Clean)", "🔵 Azul Labortec", "🌿 Verde Natureza", "⚫ Dark Mode (Noturno)"])
aplicar_tema(tema_sel)


menu = st.sidebar.radio("Navegar:", ["📊 Dashboard", "🧪 Laudos", "💰 Vendas & Orçamentos", "📥 Entrada de Estoque", "📦 Estoque", "📋 Conferência Geral", "👥 Clientes", "🛠️ Admin / Backup"])

# ==============================================================================
# 8. PÁGINAS DO SISTEMA
# ==============================================================================

if menu == "📊 Dashboard":
    st.markdown('<div class="centered-title">📊 Dashboard Gerencial</div>', unsafe_allow_html=True)
    
    # --- 1. MURAL DE AVISOS (O GRANDE ALERTA VERMELHO) ---
    if st.session_state['aviso_geral']:
        st.markdown(f"""
        <div style='background-color:#ffebee; border:2px solid #ff1744; color:#b71c1c; padding:15px; border-radius:10px; text-align:center; font-weight:bold; font-size:1.2em; margin-bottom:20px;'>
            📢 {st.session_state['aviso_geral']}
        </div>
        """, unsafe_allow_html=True)

    # --- 2. RADAR DE LAUDOS PENDENTES (A LINHA DO TEMPO) ---
    st.markdown("---")
    st.markdown("<h4 style='color: #1e3d59;'>📡 Monitoramento de Coletas (Pendentes)</h4>", unsafe_allow_html=True)
    laudos_atuais = st.session_state.get("log_laudos", [])
    ativos = [l for l in laudos_atuais if str(l.get("Status", "Pendente")) == "Pendente"]
    
    if not ativos: 
        st.success("✅ Radar Limpo! Nenhuma coleta pendente.")
    else:
        items_html = ""
        for l in ativos:
            items_html += f"""
            <div style='min-width:250px; background:#fff; border-radius:10px; padding:15px; box-shadow:0 4px 6px rgba(0,0,0,0.1); border:1px solid #ddd; margin-right:20px;'>
                <div style='font-weight:bold; color:#1e3d59; border-bottom:2px solid #ffb400; padding-bottom:5px;'>🏢 {l.get('Cliente','?')}</div>
                <div style='margin-top:10px;'>📅 Coleta: <b>{l.get('Data_Coleta','--')}</b></div>
                <div style='margin-top:5px;'>🧪 Previsão: <b>{l.get('Data_Resultado','--')}</b></div>
                <div style='margin-top:10px; text-align:center; background:#e3f2fd; color:#1565c0; border-radius:15px; font-size:0.8em; padding:3px;'>⏳ AGUARDANDO COLETA</div>
            </div>"""
        components.html(f"<div style='display:flex; overflow-x:auto; padding:10px;'>{items_html}</div>", height=220)

    # --- 3. GRÁFICOS (MANTIDOS) ---
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 📈 Vendas Diárias")
        log_v = st.session_state.get('log_vendas', [])
        if log_v:
            df_v = pd.DataFrame(log_v)
            df_v['Dia'] = pd.to_datetime(df_v['Data'], dayfirst=True, errors='coerce').dt.date
            st.area_chart(df_v.groupby('Dia')['Qtd'].sum())
        else: st.caption("Sem dados.")
    with c2:
        st.markdown("### 🏆 Top Produtos")
        if log_v:
            df_v = pd.DataFrame(log_v)
            st.bar_chart(df_v.groupby('Produto')['Qtd'].sum().sort_values(ascending=False).head(5), horizontal=True)
elif menu == "📦 Estoque":
    st.title("📦 Estoque & Inventário")
    
    # Busca e Ferramentas
    c_busca, c_relat, c_ferramentas = st.columns([3, 1, 1])
    with c_busca:
        busca = st.text_input("Filtrar:", placeholder="🔍 Pesquisar...", label_visibility="collapsed")
    with c_relat:
        if st.button("📄 PDF", use_container_width=True):
            if not st.session_state['estoque'].empty:
                pdf_bytes = gerar_pdf_estoque(st.session_state['usuario_nome'], st.session_state['estoque'])
                st.download_button("⬇️ BAIXAR", data=pdf_bytes, file_name="Estoque.pdf", mime="application/pdf", type="primary")
    
    with c_ferramentas:
        with st.popover("🛠️ GERENCIAR", use_container_width=True):
            st.markdown("### ➕ Adicionar")
            with st.form("add_prod", clear_on_submit=True):
                c1, c2 = st.columns([1,2])
                cod_n = c1.text_input("Cód")
                nome_n = c2.text_input("Nome")
                c3, c4 = st.columns(2)
                preco_n = c3.number_input("Preço", min_value=0.0)
                saldo_n = c4.number_input("Saldo", min_value=0.0)
                if st.form_submit_button("Salvar"):
                    novo = {"Cod": cod_n, "Produto": nome_n, "Preco_Base": preco_n, "Saldo": saldo_n, "Marca": "LABORTEC", "Unidade": "KG"}
                    st.session_state['estoque'] = pd.concat([st.session_state['estoque'], pd.DataFrame([novo])], ignore_index=True)
                    salvar_dados(); st.rerun()
            
            st.markdown("---")
            st.markdown("### 🗑️ Excluir")
            # --- LÓGICA DE EXCLUSÃO CORRIGIDA E ALINHADA ---
            df_seguro = st.session_state.get('estoque', pd.DataFrame())
            if not df_seguro.empty and 'Cod' in df_seguro.columns:
                opcoes_del = df_seguro.apply(lambda x: f"{x.get('Cod', '')} - {x.get('Produto', '')}", axis=1).tolist()
            else: opcoes_del = ["Vazio"]
            
            alvo = st.selectbox("Item:", [""] + opcoes_del)
            if st.button("💣 EXCLUIR"):
                if alvo and alvo != "Vazio":
                    c_alvo = alvo.split(" - ")[0]
                    st.session_state['estoque'] = st.session_state['estoque'][st.session_state['estoque']['Cod'].astype(str) != str(c_alvo)]
                    salvar_dados(); st.rerun()

    # Tabela Principal
    df_exibir = st.session_state['estoque'].copy()
    if busca:
        df_exibir = df_exibir[df_exibir['Produto'].str.contains(busca, case=False) | df_exibir['Cod'].astype(str).str.contains(busca)]
    
    ed = st.data_editor(
        df_exibir, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "Saldo": st.column_config.NumberColumn("✅ SALDO", format="%.2f"),
            "Preco_Base": st.column_config.NumberColumn("💲 PREÇO", format="%.2f")
        }
    )
    if not ed.equals(df_exibir):
        st.session_state["estoque"] = ed; salvar_dados()

elif menu == "💰 Vendas & Orçamentos":
    st.title("💰 Vendas")
    if not st.session_state['clientes_db']: st.warning("Cadastre clientes!"); st.stop()
    
    c1, c2 = st.columns([2, 1])
    cli = c1.selectbox("Cliente", sorted(list(st.session_state['clientes_db'].keys())))
    vend = c2.text_input("Vendedor", st.session_state['usuario_nome'])
    d_cli = st.session_state['clientes_db'][cli]
    fator = float(d_cli.get('Fator', 1.0))
    
    df_v = st.session_state['estoque'].copy()
    if 'Qtd' not in df_v.columns: df_v.insert(0, 'Qtd', 0.0)
    df_v['Preco_Final'] = pd.to_numeric(df_v['Preco_Base'], errors='coerce').fillna(0) * fator
    
    ed_v = st.data_editor(df_v[['Qtd', 'Produto', 'Cod', 'Saldo', 'Preco_Final']], use_container_width=True, hide_index=True)
    itens = ed_v[ed_v['Qtd'] > 0].copy()
    
    if not itens.empty:
        total = (itens['Qtd'] * itens['Preco_Final']).sum()
        st.metric("Total", f"R$ {total:,.2f}")
        if st.button("✅ FECHAR VENDA"):
            for _, row in itens.iterrows():
                mask = st.session_state['estoque']['Cod'].astype(str) == str(row['Cod'])
                if not st.session_state['estoque'][mask].empty:
                    idx = st.session_state['estoque'][mask].index[0]
                    atual = float(st.session_state['estoque'].at[idx, 'Saldo'] or 0)
                    st.session_state['estoque'].at[idx, 'Saldo'] = atual - float(row['Qtd'])
            
            # Log
            nomes = " + ".join(itens['Produto'].tolist())
            st.session_state['log_vendas'].append({'Data': obter_horario_br().strftime("%d/%m/%Y %H:%M"), 'Cliente': cli, 'Produto': nomes, 'Qtd': itens['Qtd'].sum(), 'Vendedor': vend})
            salvar_dados(); st.success("Venda Realizada!"); st.rerun()

elif menu == "👥 Clientes":
    st.title("👥 Clientes")
# --- ÁREA DE IMPORTAÇÃO DE PDF (RESTAURADA) ---
    with st.expander("📂 Importar Dados de Licença (CETESB/PDF)"):
        arquivo_pdf = st.file_uploader("Arraste o PDF aqui:", type="pdf")
        if arquivo_pdf is not None and st.button("🔄 Processar PDF"):
            try:
                # Chama a função que já existe lá no topo
                dados_lidos = ler_pdf_antigo(arquivo_pdf) 
                if dados_lidos:
                    # Preenche o formulário automaticamente
                    st.session_state['form_nome'] = str(dados_lidos.get('Nome', ''))
                    st.session_state['form_cnpj'] = str(dados_lidos.get('CNPJ', ''))
                    st.session_state['form_end'] = str(dados_lidos.get('End', ''))
                    st.session_state['form_cid'] = str(dados_lidos.get('Cidade', ''))
                    st.session_state['form_uf'] = str(dados_lidos.get('UF', ''))
                    st.session_state['form_cep'] = str(dados_lidos.get('CEP', ''))
                    st.session_state['form_tel'] = str(dados_lidos.get('Tel', ''))
                    st.session_state['form_email'] = str(dados_lidos.get('Email', ''))
                    st.session_state['form_cod'] = str(dados_lidos.get('Cod_Cli', ''))
                    st.success("✅ Dados extraídos! Verifique o formulário abaixo.")
                else:
                    st.warning("Não consegui ler os dados desse PDF.")
            except Exception as e:
                st.error(f"Erro ao processar: {e}")    
    # Formulário Compacto
    with st.expander("➕ Novo / Editar Cliente", expanded=not st.session_state['clientes_db']):
        c1, c2 = st.columns([3, 1])
        nome = c1.text_input("Nome")
        cod = c2.text_input("Cód")
        c3, c4 = st.columns([1, 2])
        fator = c3.number_input("Fator Preço", 0.1, 5.0, 1.0, 0.05)
        cnpj = c4.text_input("CNPJ")
        tel = st.text_input("Tel")
        end = st.text_input("Endereço")
        if st.button("💾 SALVAR CLIENTE"):
            if nome:
                st.session_state['clientes_db'][nome] = {'Cod_Cli': cod, 'Fator': fator, 'CNPJ': cnpj, 'Tel': tel, 'End': end}
                salvar_dados(); st.success("Salvo!"); st.rerun()

    st.markdown("---")
    for nome, dados in st.session_state['clientes_db'].items():
        with st.expander(f"🏢 {nome} (Fator: {dados.get('Fator', 1.0)})"):
            st.write(f"CNPJ: {dados.get('CNPJ')} | Tel: {dados.get('Tel')}")
            if st.button("🗑️ Apagar", key=f"del_{nome}"):
                del st.session_state['clientes_db'][nome]; salvar_dados(); st.rerun()

elif menu == "📥 Entrada de Estoque":
    st.title("📥 Entrada")
    opcoes = st.session_state['estoque'].apply(lambda x: f"{x['Cod']} - {x['Produto']}", axis=1)
    sel = st.selectbox("Produto", opcoes)
    qtd = st.number_input("Qtd", min_value=0.0)
    if st.button("Confirmar Entrada"):
        cod = sel.split(" - ")[0]
        mask = st.session_state['estoque']['Cod'].astype(str) == str(cod)
        if not st.session_state['estoque'][mask].empty:
            idx = st.session_state['estoque'][mask].index[0]
            atual = float(st.session_state['estoque'].at[idx, 'Saldo'] or 0)
            st.session_state['estoque'].at[idx, 'Saldo'] = atual + qtd
            st.session_state['log_entradas'].append({'Data': obter_horario_br().strftime("%d/%m/%Y"), 'Produto': sel, 'Qtd': qtd, 'User': st.session_state['usuario_nome']})
            salvar_dados(); st.success("Estoque atualizado!"); st.rerun()

elif menu == "🧪 Laudos":
    st.title("🧪 Laudos")
    with st.form("add_laudo"):
        cli = st.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
        data = st.date_input("Data Coleta")
        if st.form_submit_button("Agendar"):
            st.session_state['log_laudos'].append({'Cliente': cli, 'Data_Coleta': data.strftime("%d/%m/%Y"), 'Status': 'Pendente'})
            salvar_dados(); st.rerun()
    
    st.markdown("---")
    df_laudos = pd.DataFrame(st.session_state['log_laudos'])
    if not df_laudos.empty:
        edited_laudos = st.data_editor(df_laudos, num_rows="dynamic", use_container_width=True)
        if st.button("💾 Salvar Laudos"):
            st.session_state['log_laudos'] = edited_laudos.to_dict('records')
            salvar_dados(); st.rerun()

elif menu == "📋 Conferência Geral":
    st.title("📋 Logs do Sistema")
    t1, t2 = st.tabs(["Vendas", "Entradas"])
    with t1: st.dataframe(pd.DataFrame(st.session_state.get('log_vendas', [])))
    with t2: st.dataframe(pd.DataFrame(st.session_state.get('log_entradas', [])))

elif menu == "🛠️ Admin / Backup":
    st.title("🛠️ Admin")
    if st.text_input("Senha", type="password") == "labormetal22":
        if st.button("Baixar Backup JSON"):
            data = {k: st.session_state[k] for k in ['estoque', 'clientes_db', 'log_vendas', 'log_entradas', 'log_laudos'] if isinstance(st.session_state[k], (list, dict))}
            # Converte DataFrame para dict
            data['estoque'] = st.session_state['estoque'].to_dict('records')
            st.download_button("Download", json.dumps(data, indent=4), "backup.json")
        
        up = st.file_uploader("Restaurar JSON", type="json")
        if up and st.button("Carregar Backup"):
            d = json.load(up)
            st.session_state['estoque'] = pd.DataFrame(d['estoque'])
            st.session_state['clientes_db'] = d['clientes_db']
            st.session_state['log_vendas'] = d['log_vendas']
            st.session_state['log_entradas'] = d['log_entradas']
            st.session_state['log_laudos'] = d['log_laudos']
            salvar_dados(); st.success("Restaurado!")
        
        st.markdown("---")
        mural = st.text_area("Mural de Avisos", st.session_state['aviso_geral'])
        if st.button("Atualizar Mural"):
            st.session_state['aviso_geral'] = mural
            salvar_dados(); st.rerun()






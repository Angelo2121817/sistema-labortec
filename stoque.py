import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import os
import html
from pypdf import PdfReader
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components

# ==============================================================================
# 0. FUNÇÕES DE EXTRAÇÃO PDF (CETESB & PADRÃO)
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
    except Exception:
        return None


def ler_pdf_antigo(f):
    try:
        reader = PdfReader(f)
        primeira_pagina = reader.pages[0].extract_text() or ""
        if "CETESB" in primeira_pagina.upper():
            return extrair_dados_cetesb(f)

        text = ""
        for p in reader.pages:
            t = p.extract_text()
            if t:
                text += t + "\n"

        clean = re.sub(r"\s+", " ", text).strip()
        idx_inicio = clean.lower().find("cliente")
        core = clean[idx_inicio:] if idx_inicio != -1 else clean

        d = {"Nome": "", "Cod_Cli": "", "End": "", "CEP": "", "Bairro": "", "Cidade": "", "UF": "", "CNPJ": "", "Tel": "", "Email": ""}

        def extract(key, stops):
            match = re.search(re.escape(key) + r"[:\s]*", core, re.IGNORECASE)
            if not match:
                return ""
            fragment = core[match.end():]
            min_idx = len(fragment)
            for stop in stops:
                stop_match = re.search(re.escape(stop), fragment, re.IGNORECASE)
                if stop_match and stop_match.start() < min_idx:
                    min_idx = stop_match.start()
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
    except Exception:
        return None


# ==============================================================================
# 1. CONFIGURAÇÃO E CONEXÃO
# ==============================================================================
st.set_page_config(page_title="Sistema Integrado v61", layout="wide", page_icon="🧪")
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception:
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
    if 5 <= hora < 12:
        return "Bom dia"
    elif 12 <= hora < 18:
        return "Boa tarde"
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


if not verificar_senha():
    st.stop()


# ==============================================================================
# 3. MOTOR DE DADOS
# ==============================================================================
def _normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _fix_date_br(val):
    if not val or pd.isna(val) or str(val).strip() == "":
        return ""
    try:
        return pd.to_datetime(val, dayfirst=True).strftime("%d/%m/%Y")
    except:
        return val

def _fix_datetime_br(val):
    if not val or pd.isna(val) or str(val).strip() == "":
        return ""
    try:
        return pd.to_datetime(val, dayfirst=True).strftime("%d/%m/%Y %H:%M")
    except:
        return val

def carregar_dados():
    try:
        df_est = conn.read(worksheet="Estoque", ttl=0)
        if isinstance(df_est, pd.DataFrame) and not df_est.empty:
            df_est = _normalizar_colunas(df_est)
            st.session_state["estoque"] = df_est

        df_cli = conn.read(worksheet="Clientes", ttl=0)
        if isinstance(df_cli, pd.DataFrame) and not df_cli.empty:
            df_cli = _normalizar_colunas(df_cli)
            if "Email" not in df_cli.columns:
                df_cli["Email"] = ""
            if "Nome" in df_cli.columns:
                st.session_state["clientes_db"] = df_cli.set_index("Nome").to_dict("index")
            else:
                st.session_state["clientes_db"] = {}

        for aba in ["Log_Vendas", "Log_Entradas", "Log_Laudos"]:
            df = conn.read(worksheet=aba, ttl=0)
            if isinstance(df, pd.DataFrame) and not df.empty:
                df = _normalizar_colunas(df)
                
                if aba == "Log_Laudos":
                    if "Cliente" not in df.columns: df["Cliente"] = ""
                    if "Status" not in df.columns: df["Status"] = "Pendente"
                    if "Data_Coleta" not in df.columns: df["Data_Coleta"] = ""
                    if "Data_Resultado" not in df.columns: df["Data_Resultado"] = "Não definida"

                    if "Data_Coleta" in df.columns:
                        df["Data_Coleta"] = df["Data_Coleta"].apply(_fix_date_br)
                    if "Data_Resultado" in df.columns:
                        df["Data_Resultado"] = df["Data_Resultado"].apply(_fix_date_br)
                    
                    for c in ["Cliente", "Status"]:
                        df[c] = df[c].fillna("").astype(str)

                elif aba in ["Log_Vendas", "Log_Entradas"]:
                    if "Data" in df.columns:
                        df["Data"] = df["Data"].apply(_fix_datetime_br)
                    
                st.session_state[aba.lower()] = df.to_dict("records")
            else:
                st.session_state[aba.lower()] = []
        return True
    except Exception:
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
        st.toast("✅ Sincronizado!")
    except Exception:
        st.error("Erro ao salvar")


if "dados_carregados" not in st.session_state:
    carregar_dados()
    st.session_state["dados_carregados"] = True

for key in ["log_vendas", "log_entradas", "log_laudos"]:
    if key not in st.session_state:
        st.session_state[key] = []
if "estoque" not in st.session_state:
    st.session_state["estoque"] = pd.DataFrame(columns=["Cod", "Produto", "Marca", "NCM", "Unidade", "Preco_Base", "Saldo", "Estoque_Inicial", "Estoque_Minimo"])
if "clientes_db" not in st.session_state:
    st.session_state["clientes_db"] = {}


# ==============================================================================
# 4. TEMAS E CSS
# ==============================================================================
def aplicar_tema(escolha):
    css = """
    <style>
        .centered-title { text-align: center; color: #1e3d59; font-weight: bold; padding: 20px 0; font-size: 2.5em; }
    </style>
    """
    if escolha == "⚪ Padrão (Clean)":
        css += "<style>.stApp { background-color: #FFFFFF !important; color: #000000 !important; }</style>"
    elif escolha == "🔵 Azul Labortec":
        css += "<style>.stApp { background-color: #F0F8FF !important; color: #002B4E !important; } h1,h2,h3 { color: #004aad !important; }</style>"
    elif escolha == "🌿 Verde Natureza":
        css += "<style>.stApp { background-color: #F1F8E9 !important; color: #1B5E20 !important; }</style>"
    elif escolha == "⚫ Dark Mode (Noturno)":
        css += "<style>.stApp { background-color: #0E1117 !important; color: #FAFAFA !important; } .prevista-label { color: #aaa; }</style>"
    st.markdown(css, unsafe_allow_html=True)


# ==============================================================================
# 5. GERADOR DE PDF
# ==============================================================================
class PDF(FPDF):
    def header(self):
        if os.path.exists("labortec.jpg"):
            self.image("labortec.jpg", x=10, y=8, w=48)
        offset_y = 10
        self.set_font("Arial", "B", 19)
        self.set_xy(65, 10 + offset_y)
        self.cell(100, 10, "LABORTEC", 0, 0, "L")

        self.set_font("Arial", "B", 19)
        self.set_xy(110, 10 + offset_y)
        titulo_doc = getattr(self, "titulo_doc", "ORÇAMENTO")
        self.cell(90, 10, titulo_doc, 0, 1, "R")

        self.set_font("Arial", "", 10)
        self.set_xy(65, 20 + offset_y)
        self.cell(100, 5, "Rua Alfredo Bruno, 22 - Campinas/SP - CEP 13040-235", 0, 0, "L")
        self.set_xy(110, 20 + offset_y)
        self.cell(90, 5, f"Data: {obter_horario_br().strftime('%d/%m/%Y')}", 0, 1, "R")

        self.set_xy(65, 25 + offset_y)
        self.cell(100, 5, "labortecconsultoria@gmail.com | Tel.: (19) 3238-9320", 0, 0, "L")
        self.set_xy(110, 25 + offset_y)
        vendedor_nome = getattr(self, "vendedor_nome", "Sistema")
        self.cell(90, 5, f"Vendedor: {vendedor_nome}", 0, 1, "R")

        self.set_xy(65, 30 + offset_y)
        self.cell(100, 5, "C.N.P.J.: 03.763.197/0001-09", 0, 1, "L")

        self.line(10, 40 + offset_y, 200, 40 + offset_y)
        self.set_y(48 + offset_y)

    def footer(self):
        self.set_y(-25)
        self.set_font("Arial", "I", 7)
        self.cell(0, 4, "Obs.: FRETE NÃO INCLUSO. PROPOSTA VÁLIDA POR 5 DIAS.", 0, 1, "C")
        self.cell(0, 4, "PRAZO DE RETIRADA: 3 A 5 DIAS ÚTEIS APÓS CONFIRMAÇÃO.", 0, 0, "C")


def criar_doc_pdf(vendedor, cliente, dados_cli, itens, total, condicoes, titulo):
    pdf = PDF()
    pdf.vendedor_nome = vendedor
    pdf.titulo_doc = titulo
    pdf.add_page()

    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 8, f" Cliente: {cliente}", 1, 1, "L", fill=True)

    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 6, f" Endereço: {dados_cli.get('End', '')}", "LR", 1, "L")
    pdf.cell(0, 6, f" Cidade: {dados_cli.get('Cidade', '')}/{dados_cli.get('UF', '')} - CEP: {dados_cli.get('CEP', '')}", "LR", 1, "L")
    pdf.cell(0, 6, f" CNPJ: {dados_cli.get('CNPJ', '')} - Tel: {dados_cli.get('Tel', '')}", "LRB", 1, "L")
    pdf.ln(5)

    pdf.cell(0, 8, f" Pagto: {condicoes.get('plano', '')} | Forma: {condicoes.get('forma', '')} | Vencto: {condicoes.get('venc', '')}", 1, 1, "L")
    pdf.ln(6)

    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(225, 225, 225)
    w = [15, 15, 85, 25, 20, 30]
    cols = ["Un", "Qtd", "Produto", "Marca", "NCM", "Total"]
    for i, c in enumerate(cols):
        pdf.cell(w[i], 8, c, 1, 0, "C", fill=True)

    pdf.ln()
    pdf.set_font("Arial", "", 8)

    for r in itens:
        pdf.cell(w[0], 7, str(r.get("Unidade", "KG")), 1, 0, "C")
        pdf.cell(w[1], 7, str(r.get("Qtd", 0)), 1, 0, "C")
        pdf.cell(w[2], 7, str(r.get("Produto", ""))[:52], 1, 0, "L")
        pdf.cell(w[3], 7, str(r.get("Marca", "LABORTEC")), 1, 0, "C")
        pdf.cell(w[4], 7, str(r.get("NCM", "")), 1, 0, "C")
        try:
            pdf.cell(w[5], 7, f"{float(r.get('Total', 0)):.2f}", 1, 1, "R")
        except Exception:
            pdf.cell(w[5], 7, "0.00", 1, 1, "R")

    pdf.set_font("Arial", "B", 10)
    pdf.cell(sum(w) - w[5], 10, "TOTAL GERAL: ", 0, 0, "R")
    pdf.cell(w[5], 10, f"R$ {total:,.2f}", 1, 1, "R")

    pdf.ln(30)
    y = pdf.get_y()
    pdf.line(25, y, 90, y)
    pdf.line(120, y, 185, y)

    pdf.set_font("Arial", "", 8)
    pdf.set_xy(25, y + 2)
    pdf.cell(65, 4, "Assinatura Cliente", 0, 0, "C")
    pdf.set_xy(120, y + 2)
    pdf.cell(65, 4, "Assinatura Labortec", 0, 1, "C")

    return pdf.output(dest="S").encode("latin-1")


# ==============================================================================
# 6. MENU LATERAL E TEMAS
# ==============================================================================
st.sidebar.title("🛠️ MENU GERAL")
st.sidebar.success(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")

# --- SISTEMA DE AVISOS (NOVO) ---
if 'aviso_geral' not in st.session_state: st.session_state['aviso_geral'] = ""
st.sidebar.markdown("---")
with st.sidebar.expander("📢 DEFINIR AVISO GERAL"):
    aviso_txt = st.text_area("Mensagem para a Tropa:", 
                             value=st.session_state['aviso_geral'], 
                             height=100)
    c_salv, c_limp = st.columns(2)
    if c_salv.button("💾 Gravar"):
        st.session_state['aviso_geral'] = aviso_txt
        st.rerun()
    if c_limp.button("🗑️ Apagar"):
        st.session_state['aviso_geral'] = ""
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🎨 Personalizar Tela")
opcoes_temas = ["⚪ Padrão (Clean)", "🔵 Azul Labortec", "🌿 Verde Natureza", "⚫ Dark Mode (Noturno)", "🟠 Metal Industrial", "🌃 Cyber Dark"]
tema_sel = st.sidebar.selectbox("Escolha o visual:", opcoes_temas)
aplicar_tema(tema_sel)

menu = st.sidebar.radio("Navegar:", ["📊 Dashboard", "🧪 Laudos", "💰 Vendas & Orçamentos", "📥 Entrada de Estoque", "📦 Estoque", "📋 Conferência Geral", "👥 Clientes"])

# ==============================================================================
# 7. PÁGINAS DO SISTEMA
# ==============================================================================

if menu == "📊 Dashboard":
    st.markdown('<div class="centered-title">📊 Dashboard Operacional</div>', unsafe_allow_html=True)
    
    # --- ALERTA GERAL (O ALTO-FALANTE) ---
    if st.session_state['aviso_geral']:
        st.markdown(f"""
        <div style="background-color: #ffebee; border: 2px solid #ff1744; border-radius: 10px; padding: 15px; margin-bottom: 20px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <h3 style="color: #d50000; margin: 0;">📢 COMUNICADO DO COMANDO</h3>
            <p style="font-size: 1.3em; font-weight: bold; color: #b71c1c; margin-top: 10px;">{st.session_state['aviso_geral']}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("<h3 style='text-align: center; color: #1e3d59;'>📡 Radar de Coletas e Resultados</h3>", unsafe_allow_html=True)

    laudos_atuais = st.session_state.get("log_laudos", [])
    ativos = [l for l in laudos_atuais if str(l.get("Status", "Pendente")) == "Pendente"]

    if not ativos:
        st.success("✅ Tudo em dia! Nenhuma pendência no radar.")
    else:
        items_html = ""
        # Multiplica itens se forem poucos para o carrossel não quebrar visualmente
        lista_loop = ativos * (4 if len(ativos) < 4 else 1)
        
        for l in lista_loop:
            cliente = html.escape(str(l.get("Cliente", "") or "Cliente não informado"))
            coleta = html.escape(str(l.get("Data_Coleta", "") or "Data não informada"))
            resultado = html.escape(str(l.get("Data_Resultado", "") or "Não definida"))

            items_html += f"""
            <div class="carousel-item">
                <div class="coleta-cliente">🏢 {cliente}</div>
                <div class="prevista-label">Coleta:</div>
                <div class="neon-date">📅 {coleta}</div>
                <div style="margin-top: 8px;">
                    <div class="prevista-label">Resultado:</div>
                    <div class="neon-result">🧪 {resultado}</div>
                </div>
            </div>
            """

        carousel_component = f"""
        <style>
            .carousel-wrapper {{ overflow: hidden; width: 100%; position: relative; padding: 10px 0; }}
            .carousel-track {{ display: flex; width: max-content; animation: scroll {max(20, len(ativos)*5)}s linear infinite; }}
            .carousel-track:hover {{ animation-play-state: paused; }}
            @keyframes scroll {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-50%); }} }}
            .carousel-item {{ width: 280px; flex-shrink: 0; margin-right: 20px; background: white; padding: 15px; border-radius: 12px; border-left: 6px solid #ff4b4b; box-shadow: 0 4px 10px rgba(0,0,0,0.08); height: 170px; display: flex; flex-direction: column; justify-content: center; font-family: sans-serif; }}
            .coleta-cliente {{ font-weight: bold; color: #1e3d59; margin-bottom: 8px; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
            .prevista-label {{ font-size: 13px; color: #666; font-weight: 600; margin-bottom: 2px; text-transform: uppercase; letter-spacing: 0.5px; }}
            .neon-date {{ font-weight: bold; color: #d32f2f; font-size: 15px; }}
            .neon-result {{ font-weight: bold; color: #1e7e34; font-size: 16px; }}
        </style>
        <div class="carousel-wrapper"><div class="carousel-track">{items_html}</div></div>
        """
        components.html(carousel_component, height=200)

elif menu == "🧪 Laudos":
    st.title("🧪 Gestão de Laudos")
    
    with st.expander("📅 Agendar Nova Coleta", expanded=True):
        with st.form("f_laudo"):
            cli_l = st.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
            c1, c2 = st.columns(2)
            data_l = c1.date_input("Data da Coleta")
            data_r = c2.date_input("Previsão do Resultado", value=data_l + timedelta(days=7))
            
            if st.form_submit_button("Agendar"):
                novo = {
                    'Cliente': cli_l, 
                    'Data_Coleta': data_l.strftime("%d/%m/%Y"), 
                    'Data_Resultado': data_r.strftime("%d/%m/%Y"), 
                    'Status': 'Pendente'
                }
                st.session_state['log_laudos'].append(novo)
                salvar_dados()
                st.success("Agendado!")
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Editar Previsões e Status")
    
    laudos = st.session_state.get('log_laudos', [])
    if not laudos:
        st.info("Sem laudos registrados.")
    else:
        df_p = pd.DataFrame(laudos)
        df_p['ID'] = range(len(laudos))
        
        ed_p = st.data_editor(
            df_p[['ID', 'Cliente', 'Data_Coleta', 'Data_Resultado', 'Status']],
            use_container_width=True, 
            hide_index=True,
            disabled=['ID', 'Cliente'],
            column_config={
                "Data_Coleta": st.column_config.TextColumn("Data Coleta (dd/mm/aaaa)"),
                "Data_Resultado": st.column_config.TextColumn("Prev. Resultado (dd/mm/aaaa)"),
                "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "Em Análise", "Concluído", "Cancelado"])
            }
        )

        if st.button("💾 SALVAR ALTERAÇÕES"):
            for _, row in ed_p.iterrows():
                idx = int(row['ID'])
                st.session_state['log_laudos'][idx]['Data_Coleta'] = str(row['Data_Coleta'])
                st.session_state['log_laudos'][idx]['Data_Resultado'] = str(row['Data_Resultado'])
                st.session_state['log_laudos'][idx]['Status'] = row['Status']
            
            salvar_dados()
            st.success("Dados atualizados!")
            st.rerun()

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
            origem = st.radio("Origem?", ["METAL QUÍMICA", "INDEPENDENTE"], horizontal=True)
            if st.button("✅ CONFIRMAR", type="primary", use_container_width=True):
                pdf = criar_doc_pdf(vend, cli, d_cli, itens_sel.to_dict('records'), total, {'plano':p_pag, 'forma':f_pag, 'venc':venc}, "PEDIDO")
                if "METAL" in origem:
                    for _, row in itens_sel.iterrows():
                        idxs = st.session_state['estoque'][st.session_state['estoque']['Cod'] == row['Cod']].index
                        if len(idxs) > 0: st.session_state['estoque'].at[idxs[0], 'Saldo'] -= row['Qtd']
                    st.session_state['log_vendas'].append({'Data': obter_horario_br().strftime("%d/%m/%Y %H:%M"), 'Cliente': cli, 'Produto': 'Vários', 'Qtd': itens_sel['Qtd'].sum(), 'Vendedor': vend})
                    salvar_dados(); st.success("Venda Registrada!")
                else: st.success("Venda Registrada!")
                st.download_button("📥 Baixar Pedido", pdf, f"Pedido_{cli}.pdf", "application/pdf")

elif menu == "👥 Clientes":
    st.title("👥 Gestão de Clientes")
    
    campos = ['form_nome', 'form_tel', 'form_end', 'form_cnpj', 'form_cid', 'form_uf', 'form_cep', 'form_cod']
    for c in campos: 
        if c not in st.session_state: st.session_state[c] = ""

    def limpar_campos():
        for c in campos: st.session_state[c] = ""

    def salvar_no_callback():
        nome = st.session_state['form_nome']
        if nome:
            st.session_state['clientes_db'][nome] = {
                'Tel': st.session_state['form_tel'], 'End': st.session_state['form_end'],
                'CNPJ': st.session_state['form_cnpj'], 'Cidade': st.session_state['form_cid'],
                'UF': st.session_state['form_uf'], 'CEP': st.session_state['form_cep'], 'Cod_Cli': st.session_state['form_cod']
            }
            salvar_dados(); st.toast(f"Cliente {nome} salvo!", icon="✅"); limpar_campos()
        else: st.toast("Erro: Nome obrigatório!", icon="❌")

    def excluir_cliente(nome):
        if nome in st.session_state['clientes_db']: del st.session_state['clientes_db'][nome]; salvar_dados(); st.toast("Removido.", icon="🗑️")

    def preparar_edicao(k, d):
        st.session_state['form_nome'] = str(k)
        st.session_state['form_tel'] = str(d.get('Tel', ''))
        st.session_state['form_end'] = str(d.get('End', ''))
        st.session_state['form_cnpj'] = str(d.get('CNPJ', ''))
        st.session_state['form_cid'] = str(d.get('Cidade', ''))
        st.session_state['form_uf'] = str(d.get('UF', ''))
        st.session_state['form_cep'] = str(d.get('CEP', ''))
        st.session_state['form_cod'] = str(d.get('Cod_Cli', ''))

    with st.expander("📂 Importar Dados de Licença (CETESB/PDF)"):
        arquivo_pdf = st.file_uploader("Arraste o PDF aqui:", type="pdf")
        if arquivo_pdf is not None and st.button("🔄 Processar PDF"):
            try:
                dados_lidos = ler_pdf_antigo(arquivo_pdf)
                if dados_lidos:
                    st.session_state['form_nome'] = str(dados_lidos.get('Nome', ''))
                    st.session_state['form_cnpj'] = str(dados_lidos.get('CNPJ', ''))
                    st.session_state['form_end'] = str(dados_lidos.get('End', ''))
                    st.session_state['form_cid'] = str(dados_lidos.get('Cidade', ''))
                    st.session_state['form_uf'] = str(dados_lidos.get('UF', ''))
                    st.session_state['form_cep'] = str(dados_lidos.get('CEP', ''))
                    st.session_state['form_tel'] = str(dados_lidos.get('Tel', ''))
                    st.session_state['form_cod'] = str(dados_lidos.get('Cod_Cli', ''))
                    st.success("Dados extraídos!")
            except NameError: st.error("Erro na função de leitura.")

    with st.form("form_cliente"):
        st.write("📝 **Dados Cadastrais**")
        c1, c2 = st.columns([3, 1])
        c1.text_input("Nome / Razão Social", key="form_nome")
        c2.text_input("Cód. Cliente", key="form_cod")
        c3, c4 = st.columns([1, 1])
        c3.text_input("CNPJ", key="form_cnpj")
        c4.text_input("Telefone", key="form_tel")
        st.text_input("Endereço", key="form_end")
        c5, c6, c7 = st.columns([2, 1, 1])
        c5.text_input("Cidade", key="form_cid"); c6.text_input("UF", key="form_uf"); c7.text_input("CEP", key="form_cep")
        st.form_submit_button("💾 SALVAR DADOS", on_click=salvar_no_callback)

    st.button("🧹 Limpar / Cancelar", on_click=limpar_campos)
    st.markdown("---"); st.subheader("📇 Carteira de Clientes")
    
    if st.session_state['clientes_db']:
        busca = st.text_input("🔍 Buscar...", placeholder="Nome da empresa...")
        lista = sorted(list(st.session_state['clientes_db'].keys()))
        if busca: lista = [k for k in lista if busca.lower() in k.lower()]
        for k in lista:
            d = st.session_state['clientes_db'][k]
            with st.expander(f"🏢 {k}"):
                col_a, col_b = st.columns(2)
                col_a.write(f"📍 {d.get('End', '')}"); col_b.write(f"📞 {d.get('Tel', '')} | CNPJ: {d.get('CNPJ', '')}")
                c_edit, c_del = st.columns([1, 1])
                c_edit.button("✏️ EDITAR", key=f"ed_{k}", on_click=preparar_edicao, args=(k, d))
                c_del.button("🗑️ EXCLUIR", key=f"dl_{k}", on_click=excluir_cliente, args=(k,))
    else: st.info("Nenhum cliente cadastrado.")

# ==============================================================================
# 5. ESTOQUE (COM BLINDAGEM DE DADOS + MÍNIMO EDITÁVEL)
# ==============================================================================
elif menu == "📦 Estoque":
    st.title("📦 Estoque Geral")
    
    # 1. BLINDAGEM: Garante que as colunas existem e são números
    if not st.session_state["estoque"].empty:
        # Se a coluna Mínimo não existir, cria ela agora com 0.0
        if "Estoque_Minimo" not in st.session_state["estoque"].columns:
            st.session_state["estoque"]["Estoque_Minimo"] = 0.0
            
        # Força conversão para número (evita erro de digitação antiga)
        cols_numericas = ["Saldo", "Estoque_Minimo", "Preco_Base"]
        for col in cols_numericas:
            if col in st.session_state["estoque"].columns:
                st.session_state["estoque"][col] = pd.to_numeric(
                    st.session_state["estoque"][col], errors='coerce'
                ).fillna(0.0)
elif menu == "📥 Entrada de Estoque":
    st.title("📥 Entrada de Mercadoria")
    
    if st.session_state['estoque'].empty:
        st.warning("Cadastre produtos no estoque primeiro!")
        st.stop()

    with st.form("f_ent"):
        # Cria lista de opções segura
        opcoes = st.session_state['estoque'].apply(lambda x: f"{x['Cod']} - {x['Produto']}", axis=1)
        prod_sel = st.selectbox("Selecione o Produto", opcoes)
        qtd_ent = st.number_input("Quantidade (KG)", min_value=0.0, step=1.0)
        
        if st.form_submit_button("✅ Confirmar Entrada"):
            # Pega o código separado do nome
            cod = prod_sel.split(" - ")[0]
            
            # Localiza o produto no DataFrame
            mask = st.session_state['estoque']['Cod'].astype(str) == str(cod)
            
            if not st.session_state['estoque'][mask].empty:
                idx = st.session_state['estoque'][mask].index[0]
                
                # --- AQUI ESTAVA O ERRO (CORRIGIDO) ---
                # Pega o saldo atual e converte para float (número) na marra
                saldo_atual = float(st.session_state['estoque'].at[idx, 'Saldo'] or 0.0)
                novo_saldo = saldo_atual + float(qtd_ent)
                
                # Atualiza o estoque
                st.session_state['estoque'].at[idx, 'Saldo'] = novo_saldo
                
                # Registra no Log
                nome_prod = st.session_state['estoque'].at[idx, 'Produto']
                st.session_state['log_entradas'].append({
                    'Data': datetime.now().strftime("%d/%m/%Y %H:%M"),
                    'Produto': nome_prod,
                    'Qtd': qtd_ent,
                    'Usuario': st.session_state['usuario_nome']
                })
                
                salvar_dados()
                st.success(f"Entrada de +{qtd_ent}Kg em {nome_prod} realizada!")
                st.rerun()
            else:
                st.error("Erro crítico: Produto não encontrado no índice.")
    with tab1:
        if st.session_state['log_vendas']:
            # Cria o DataFrame e inverte a ordem (iloc[::-1]) para o mais recente aparecer em cima
            df_vendas = pd.DataFrame(st.session_state['log_vendas'])
            st.dataframe(df_vendas.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhuma venda registrada ainda.")

    with tab2:
        if st.session_state['log_entradas']:
            df_entradas = pd.DataFrame(st.session_state['log_entradas'])
            st.dataframe(df_entradas.iloc[::-1], use_container_width=True)
        else:
            st.info("Nenhuma entrada de estoque registrada.")

    # 2. ESTILO: Verde Tático
    def estilo_saldo(val):
        return 'background-color: #d4edda; color: #155724; font-weight: 900; border: 1px solid #c3e6cb'

    try:
        df_styled = st.session_state["estoque"].style.map(estilo_saldo, subset=["Saldo"])
    except:
        df_styled = st.session_state["estoque"]

    st.caption("📝 Defina o **Mínimo** (🚨) para controle. O **Saldo** (✅) também é ajustável.")

    # 3. EDITOR (Mínimo visível e editável)
    ed = st.data_editor(
        df_styled, 
        use_container_width=True, 
        num_rows="dynamic",
        key="editor_estoque_v6", # Key nova para resetar qualquer erro visual
        column_config={
            "Saldo": st.column_config.NumberColumn(
                "✅ SALDO", 
                help="Quantidade física atual",
                format="%.2f",
                step=1,
            ),
            "Estoque_Minimo": st.column_config.NumberColumn(
                "🚨 Mínimo", # Coluna recuperada!
                help="Abaixo disso é necessário repor",
                format="%.0f", # Número inteiro fica mais limpo
                step=1
            ),
            # Ocultando o que você não quer ver, mas mantendo no sistema
            "Preco_Base": None, 
            "Estoque_Inicial": None 
        }
    )
    
    # Salvar
    if not ed.equals(st.session_state["estoque"]):
        st.session_state["estoque"] = ed
        salvar_dados()



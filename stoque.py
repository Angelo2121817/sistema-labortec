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
st.set_page_config(page_title="Sistema Integrado v80", layout="wide", page_icon="🧪")
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
# 3. MOTOR DE DADOS
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
        df_est = conn.read(worksheet="Estoque", ttl=0)
        if isinstance(df_est, pd.DataFrame) and not df_est.empty:
            df_est = _normalizar_colunas(df_est)
            st.session_state["estoque"] = df_est

        df_cli = conn.read(worksheet="Clientes", ttl=0)
        if isinstance(df_cli, pd.DataFrame) and not df_cli.empty:
            df_cli = _normalizar_colunas(df_cli)
            if "Email" not in df_cli.columns: df_cli["Email"] = ""
            if "Nome" in df_cli.columns: st.session_state["clientes_db"] = df_cli.set_index("Nome").to_dict("index")
            else: st.session_state["clientes_db"] = {}

        for aba in ["Log_Vendas", "Log_Entradas", "Log_Laudos"]:
            df = conn.read(worksheet=aba, ttl=0)
            if isinstance(df, pd.DataFrame) and not df.empty:
                df = _normalizar_colunas(df)
                if aba == "Log_Laudos":
                    if "Cliente" not in df.columns: df["Cliente"] = ""
                    if "Status" not in df.columns: df["Status"] = "Pendente"
                    if "Data_Coleta" not in df.columns: df["Data_Coleta"] = ""
                    if "Data_Resultado" not in df.columns: df["Data_Resultado"] = "Não definida"
                    if "Data_Coleta" in df.columns: df["Data_Coleta"] = df["Data_Coleta"].apply(_fix_date_br)
                    if "Data_Resultado" in df.columns: df["Data_Resultado"] = df["Data_Resultado"].apply(_fix_date_br)
                    for c in ["Cliente", "Status"]: df[c] = df[c].fillna("").astype(str)
                elif aba in ["Log_Vendas", "Log_Entradas"]:
                    if "Data" in df.columns: df["Data"] = df["Data"].apply(_fix_datetime_br)
                st.session_state[aba.lower()] = df.to_dict("records")
            else:
                st.session_state[aba.lower()] = []
        return True
    except Exception: return False

def salvar_dados():
    try:
        conn.update(worksheet="Estoque", data=st.session_state["estoque"])
        if st.session_state.get("clientes_db"):
            df_clis = pd.DataFrame.from_dict(st.session_state["clientes_db"], orient="index").reset_index().rename(columns={"index": "Nome"})
            conn.update(worksheet="Clientes", data=df_clis)
        conn.update(worksheet="Log_Vendas", data=pd.DataFrame(st.session_state.get("log_vendas", [])))
        conn.update(worksheet="Log_Entradas", data=pd.DataFrame(st.session_state.get("log_entradas", [])))
        conn.update(worksheet="Log_Laudos", data=pd.DataFrame(st.session_state.get("log_laudos", [])))
        st.toast("✅ Sincronizado!", icon="☁️")
    except Exception as e:
        print(f"Erro silencioso ao salvar: {e}")
        pass

if "dados_carregados" not in st.session_state:
    carregar_dados()
    st.session_state["dados_carregados"] = True

for key in ["log_vendas", "log_entradas", "log_laudos"]:
    if key not in st.session_state: st.session_state[key] = []
if "estoque" not in st.session_state:
    st.session_state["estoque"] = pd.DataFrame(columns=["Cod", "Produto", "Marca", "NCM", "Unidade", "Preco_Base", "Saldo", "Estoque_Inicial", "Estoque_Minimo"])
if "clientes_db" not in st.session_state: st.session_state["clientes_db"] = {}

# ==============================================================================
# 4. TEMAS E CSS
# ==============================================================================
def aplicar_tema(escolha):
    css = """<style>.centered-title { text-align: center; color: #1e3d59; font-weight: bold; padding: 20px 0; font-size: 2.5em; }</style>"""
    if escolha == "⚪ Padrão (Clean)": css += "<style>.stApp { background-color: #FFFFFF !important; color: #000000 !important; }</style>"
    elif escolha == "🔵 Azul Labortec": css += "<style>.stApp { background-color: #F0F8FF !important; color: #002B4E !important; } h1,h2,h3 { color: #004aad !important; }</style>"
    elif escolha == "🌿 Verde Natureza": css += "<style>.stApp { background-color: #F1F8E9 !important; color: #1B5E20 !important; }</style>"
    elif escolha == "⚫ Dark Mode (Noturno)": css += "<style>.stApp { background-color: #0E1117 !important; color: #FAFAFA !important; } .prevista-label { color: #aaa; }</style>"
    st.markdown(css, unsafe_allow_html=True)

# ==============================================================================
# 5. GERADOR DE PDF
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

# ==============================================================================
# 6. MENU LATERAL E TEMAS
# ==============================================================================
st.sidebar.title("🛠️ MENU GERAL")
st.sidebar.success(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")

if 'aviso_geral' not in st.session_state: st.session_state['aviso_geral'] = ""
st.sidebar.markdown("---")
with st.sidebar.expander("📢 DEFINIR AVISO"):
    aviso_txt = st.text_area("Mensagem do Mural:", value=st.session_state['aviso_geral'], height=100)
    c1, c2 = st.columns(2)
    if c1.button("💾 Gravar"): st.session_state['aviso_geral'] = aviso_txt; st.rerun()
    if c2.button("🗑️ Apagar"): st.session_state['aviso_geral'] = ""; st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🎨 Personalizar Tela")
opcoes_temas = ["⚪ Padrão (Clean)", "🔵 Azul Labortec", "🌿 Verde Natureza", "⚫ Dark Mode (Noturno)", "🟠 Metal Industrial", "🌃 Cyber Dark"]
tema_sel = st.sidebar.selectbox("Escolha o visual:", opcoes_temas)
aplicar_tema(tema_sel)

menu = st.sidebar.radio("Navegar:", [
    "📊 Dashboard", "🧪 Laudos", "💰 Vendas & Orçamentos", "📥 Entrada de Estoque", 
    "📦 Estoque", "📋 Conferência Geral", "👥 Clientes", "🛠️ Admin / Backup"
])

# ==============================================================================
# 7. PÁGINAS DO SISTEMA
# ==============================================================================

if menu == "📊 Dashboard":
    st.markdown('<div class="centered-title">📊 Dashboard Gerencial</div>', unsafe_allow_html=True)
    if st.session_state['aviso_geral']:
        st.markdown(f"""<div style='background-color:#ffebee; border:2px solid #ff1744; color:#b71c1c; padding:10px; border-radius:10px; text-align:center; font-weight:bold;'>📢 {st.session_state['aviso_geral']}</div>""", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("<h4 style='color: #1e3d59;'>📡 Monitoramento de Coletas (Pendentes)</h4>", unsafe_allow_html=True)
    laudos_atuais = st.session_state.get("log_laudos", [])
    ativos = [l for l in laudos_atuais if str(l.get("Status", "Pendente")) == "Pendente"]
    
    if not ativos: st.success("✅ Radar Limpo!")
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
        components.html(f"<div style='display:flex; overflow-x:auto; padding:10px;'>{items_html}</div>", height=200)

    st.markdown("---")
    st.markdown("<h4 style='color: #d32f2f;'>🚨 Estoque Crítico</h4>", unsafe_allow_html=True)
    df_est = st.session_state.get('estoque')
    if df_est is not None and not df_est.empty:
        try:
            criticos = df_est[ (pd.to_numeric(df_est['Saldo'], errors='coerce').fillna(0) < pd.to_numeric(df_est['Estoque_Minimo'], errors='coerce').fillna(0)) ].copy()
            if not criticos.empty: st.dataframe(criticos[['Cod', 'Produto', 'Saldo', 'Estoque_Minimo']], use_container_width=True, hide_index=True)
            else: st.info("👍 Estoque OK.")
        except: st.info("Erro ao calcular estoque.")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 📈 Vendas Diárias")
        log_v = st.session_state.get('log_vendas', [])
        if log_v:
            df_v = pd.DataFrame(log_v)
            df_v['Dia'] = pd.to_datetime(df_v['Data'], dayfirst=True, errors='coerce').dt.date
            st.area_chart(df_v.groupby('Dia')['Qtd'].sum(), color="#004aad")
        else: st.caption("Sem dados.")
    with c2:
        st.markdown("### 🏆 Top Produtos")
        if log_v:
            df_v = pd.DataFrame(log_v)
            st.bar_chart(df_v.groupby('Produto')['Qtd'].sum().sort_values(ascending=False).head(5), color="#ffb400", horizontal=True)
        else: st.caption("Sem dados.")

elif menu == "🧪 Laudos":
    st.title("🧪 Gestão de Laudos")
    with st.expander("📅 Agendar Nova Coleta", expanded=True):
        with st.form("f_laudo"):
            cli_l = st.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
            c1, c2 = st.columns(2)
            data_l = c1.date_input("Data da Coleta", format="DD/MM/YYYY")
            data_r = c2.date_input("Previsão do Resultado", value=data_l + timedelta(days=7), format="DD/MM/YYYY")
            if st.form_submit_button("Agendar"):
                st.session_state['log_laudos'].append({
                    'Cliente': cli_l, 'Data_Coleta': data_l.strftime("%d/%m/%Y"), 
                    'Data_Resultado': data_r.strftime("%d/%m/%Y"), 'Status': 'Pendente'
                })
                salvar_dados(); st.success("Agendado!"); st.rerun()

    st.markdown("---"); st.subheader("📋 Editar Previsões")
    laudos = st.session_state.get('log_laudos', [])
    laudos_ativos = [l for l in laudos if l.get('Status') != 'Arquivado']
    if not laudos_ativos: st.info("Sem laudos ativos.")
    else:
        df_view = pd.DataFrame(laudos)
        df_view['ID_Real'] = range(len(laudos))
        df_view = df_view[df_view['Status'] != 'Arquivado']
        df_view['Data_Coleta'] = pd.to_datetime(df_view['Data_Coleta'], dayfirst=True, errors='coerce')
        df_view['Data_Resultado'] = pd.to_datetime(df_view['Data_Resultado'], dayfirst=True, errors='coerce')
        
        ed_p = st.data_editor(
            df_view[['ID_Real', 'Cliente', 'Data_Coleta', 'Data_Resultado', 'Status']], 
            use_container_width=True, hide_index=True, disabled=['ID_Real', 'Cliente'],
            column_config={
                "Data_Coleta": st.column_config.DateColumn("Coleta", format="DD/MM/YYYY"),
                "Data_Resultado": st.column_config.DateColumn("Previsão", format="DD/MM/YYYY"),
                "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "Em Análise", "Concluído", "Cancelado"])
            }
        )
        if st.button("💾 SALVAR ALTERAÇÕES"):
            for _, row in ed_p.iterrows():
                idx = int(row['ID_Real'])
                c = row['Data_Coleta'].strftime("%d/%m/%Y") if hasattr(row['Data_Coleta'], 'strftime') else str(row['Data_Coleta'])
                r = row['Data_Resultado'].strftime("%d/%m/%Y") if hasattr(row['Data_Resultado'], 'strftime') else str(row['Data_Resultado'])
                st.session_state['log_laudos'][idx].update({'Data_Coleta': c, 'Data_Resultado': r, 'Status': row['Status']})
            salvar_dados(); st.success("Salvo!"); st.rerun()

elif menu == "💰 Vendas & Orçamentos":
    st.title("💰 Vendas Inteligentes")
    if not st.session_state['clientes_db']: st.warning("Cadastre clientes!"); st.stop()
    
    c1, c2 = st.columns([2,1])
    cli = c1.selectbox("Cliente", list(st.session_state['clientes_db'].keys()))
    vend = c2.text_input("Vendedor", st.session_state['usuario_nome'])
    d_cli = st.session_state['clientes_db'][cli]
    
    try: fator = float(d_cli.get('Fator', 1.0) or 1.0)
    except: fator = 1.0
    
    if fator == 1.0: st.info(f"Tabela Normal (Fator 1.0)")
    elif fator < 1.0: st.success(f"Desconto de {int((1-fator)*100)}%")
    else: st.warning(f"Acréscimo de {int((fator-1)*100)}%")
    
    c3, c4, c5 = st.columns(3)
    p_pag = c3.text_input("Plano", "28/42 DIAS"); f_pag = c4.text_input("Forma", "BOLETO"); venc = c5.text_input("Vencimento", "A COMBINAR")
    
    df_v = st.session_state['estoque'].copy()
    if 'Qtd' not in df_v.columns: df_v.insert(0, 'Qtd', 0.0)
    df_v['Preco_Base'] = pd.to_numeric(df_v['Preco_Base'], errors='coerce').fillna(0.0)
    df_v['Preco_Final'] = df_v['Preco_Base'] * fator
    
    ed_v = st.data_editor(
        df_v[['Qtd', 'Produto', 'Cod', 'Marca', 'NCM', 'Unidade', 'Preco_Base', 'Preco_Final', 'Saldo']], 
        use_container_width=True, hide_index=True,
        column_config={
            "Preco_Base": st.column_config.NumberColumn("Base", format="%.2f", disabled=True),
            "Preco_Final": st.column_config.NumberColumn("Final", format="%.2f"),
            "Qtd": st.column_config.NumberColumn("Qtd", step=1.0)
        }
    )
    
    itens = ed_v[ed_v['Qtd'] > 0].copy()
    itens['Total'] = itens['Qtd'] * itens['Preco_Final']
    total = itens['Total'].sum()
    
    if not itens.empty:
        st.divider(); st.metric("Total", f"R$ {total:,.2f}")
        b1, b2 = st.columns(2)
        if b1.button("📄 ORÇAMENTO"):
            pdf = criar_doc_pdf(vend, cli, d_cli, itens.to_dict('records'), total, {'plano':p_pag, 'forma':f_pag, 'venc':venc}, "ORÇAMENTO")
            st.download_button("📥 Baixar PDF", pdf, f"Orcamento_{cli}.pdf", "application/pdf")
        
        with b2:
            tipo = st.radio("Baixa?", ["Sim (Estoque)", "Não (Apenas Pedido)"], horizontal=True)
            if st.button("✅ FECHAR VENDA", type="primary"):
                pdf = criar_doc_pdf(vend, cli, d_cli, itens.to_dict('records'), total, {'plano':p_pag, 'forma':f_pag, 'venc':venc}, "PEDIDO")
                if "Sim" in tipo:
                    for _, r in itens.iterrows():
                        mask = st.session_state['estoque']['Cod'].astype(str) == str(r['Cod'])
                        if not st.session_state['estoque'][mask].empty:
                            idx = st.session_state['estoque'][mask].index[0]
                            try: atual = float(st.session_state['estoque'].at[idx, 'Saldo'])
                            except: atual = 0.0
                            st.session_state['estoque'].at[idx, 'Saldo'] = atual - r['Qtd']
                st.session_state['log_vendas'].append({'Data': obter_horario_br().strftime("%d/%m/%Y %H:%M"), 'Cliente': cli, 'Produto': 'Vários', 'Qtd': itens['Qtd'].sum(), 'Vendedor': vend})
                salvar_dados(); st.success("Venda Realizada!")
                st.download_button("📥 Baixar Pedido", pdf, f"Pedido_{cli}.pdf", "application/pdf")

elif menu == "📥 Entrada de Estoque":
    st.title("📥 Entrada de Mercadoria")
    if st.session_state['estoque'].empty: st.warning("Cadastre produtos!"); st.stop()
    
    with st.form("f_ent"):
        opcoes = st.session_state['estoque'].apply(lambda x: f"{x['Cod']} - {x['Produto']}", axis=1)
        sel = st.selectbox("Produto", opcoes)
        qtd = st.number_input("Qtd (KG)", min_value=0.0)
        if st.form_submit_button("Confirmar"):
            cod = sel.split(" - ")[0]
            mask = st.session_state['estoque']['Cod'].astype(str) == str(cod)
            if not st.session_state['estoque'][mask].empty:
                idx = st.session_state['estoque'][mask].index[0]
                try: atual = float(st.session_state['estoque'].at[idx, 'Saldo'])
                except: atual = 0.0
                st.session_state['estoque'].at[idx, 'Saldo'] = atual + qtd
                st.session_state['log_entradas'].append({'Data': obter_horario_br().strftime("%d/%m/%Y"), 'Produto': sel, 'Qtd': qtd, 'Usuario': st.session_state['usuario_nome']})
                salvar_dados(); st.success("Entrada Realizada!"); st.rerun()

elif menu == "📦 Estoque":
    st.title("📦 Estoque Geral")
    
    # --- 1. CADASTRO ---
    with st.expander("➕ NOVO PRODUTO", expanded=False):
        with st.form("novo_prod"):
            c1, c2 = st.columns([1, 4])
            cod = c1.text_input("Código")
            nome = c2.text_input("Nome do Produto")
            c3, c4, c5 = st.columns(3)
            marca = c3.text_input("Marca", "LABORTEC"); ncm = c4.text_input("NCM"); unid = c5.selectbox("Un", ["KG", "L", "UN"])
            c6, c7, c8 = st.columns(3)
            preco = c6.number_input("Preço Base", 0.0); saldo = c7.number_input("Saldo Inicial", 0.0); min_est = c8.number_input("Mínimo", 0.0)
            
            if st.form_submit_button("CADASTRAR"):
                if cod and nome:
                    existentes = st.session_state['estoque']['Cod'].astype(str).values
                    if str(cod) in existentes: st.error("Código já existe!")
                    else:
                        novo = {"Cod": cod, "Produto": nome, "Marca": marca, "NCM": ncm, "Unidade": unid, "Preco_Base": preco, "Saldo": saldo, "Estoque_Minimo": min_est}
                        st.session_state['estoque'] = pd.concat([st.session_state['estoque'], pd.DataFrame([novo])], ignore_index=True)
                        salvar_dados(); st.success("Cadastrado!"); st.rerun()
                else: st.warning("Código e Nome obrigatórios.")

    # --- 2. TABELA ---
    st.markdown("---")
    if not st.session_state['estoque'].empty:
        for c in ['Saldo', 'Preco_Base', 'Estoque_Minimo']:
            st.session_state['estoque'][c] = pd.to_numeric(st.session_state['estoque'][c], errors='coerce').fillna(0.0)
            
    def style_saldo(v): return 'background-color: #d4edda; color: #155724; font-weight: bold'
    try: df_style = st.session_state['estoque'].style.map(style_saldo, subset=['Saldo'])
    except: df_style = st.session_state['estoque']
    
    ed = st.data_editor(df_style, use_container_width=True, num_rows="dynamic", key="ed_estoque", column_config={
        "Saldo": st.column_config.NumberColumn("Saldo", format="%.2f"),
        "Preco_Base": st.column_config.NumberColumn("Preço", format="%.2f")
    })
    if not ed.equals(st.session_state['estoque']):
        st.session_state['estoque'] = ed; salvar_dados()

elif menu == "📋 Conferência Geral":
    st.title("📋 Conferência")
    t1, t2, t3 = st.tabs(["Vendas", "Entradas", "Laudos"])
    with t1:
        if st.session_state['log_vendas']:
            ed = st.data_editor(pd.DataFrame(st.session_state['log_vendas']), num_rows="dynamic", use_container_width=True)
            if st.button("Salvar Vendas"): st.session_state['log_vendas'] = ed.to_dict('records'); salvar_dados(); st.rerun()
    with t2:
        if st.session_state['log_entradas']:
            ed = st.data_editor(pd.DataFrame(st.session_state['log_entradas']), num_rows="dynamic", use_container_width=True)
            if st.button("Salvar Entradas"): st.session_state['log_entradas'] = ed.to_dict('records'); salvar_dados(); st.rerun()
    with t3:
        laudos = st.session_state.get('log_laudos', [])
        for i, l in enumerate(laudos):
            if l.get('Status') != 'Arquivado':
                with st.expander(f"{l['Cliente']} - {l['Data_Coleta']}"):
                    if st.button("Arquivar", key=f"arq_{i}"):
                        st.session_state['log_laudos'][i]['Status'] = 'Arquivado'; salvar_dados(); st.rerun()

elif menu == "👥 Clientes":
    st.title("👥 Gestão de Clientes & Precificação")
    
    # --- 1. CONFIGURAÇÃO INICIAL E ESTADO ---
    if 'edit_mode' not in st.session_state: 
        st.session_state['edit_mode'] = False

    # Define os campos padrão para não dar erro de chave
    campos_padrao = ['form_nome', 'form_tel', 'form_email', 'form_end', 'form_cnpj', 
                     'form_cid', 'form_uf', 'form_cep', 'form_cod', 'form_fator']
    
    for campo in campos_padrao:
        if campo not in st.session_state:
            st.session_state[campo] = 1.0 if campo == 'form_fator' else ""

    # --- 2. FUNÇÕES DE COMANDO ---
    def limpar_campos():
        for campo in campos_padrao:
            st.session_state[campo] = 1.0 if campo == 'form_fator' else ""
        st.session_state['edit_mode'] = False

    def salvar_cliente():
        # Limpeza básica dos dados
        nome = str(st.session_state.get('form_nome', '')).strip()
        
        if not nome:
            st.toast("Erro: O nome é obrigatório!", icon="❌")
            return

        # Bloqueio de duplicidade (apenas se for novo cadastro)
        if not st.session_state['edit_mode'] and nome in st.session_state['clientes_db']:
            st.error(f"⛔ O cliente '{nome}' já existe. Use a busca para editar.")
            return
        
        # Tratamento do Fator para garantir que é número
        try:
            fator_seguro = float(st.session_state.get('form_fator', 1.0))
        except:
            fator_seguro = 1.0

        # Gravação no Banco de Dados
        st.session_state['clientes_db'][nome] = {
            'Tel': st.session_state.get('form_tel', ''),
            'Email': st.session_state.get('form_email', ''),
            'End': st.session_state.get('form_end', ''),
            'CNPJ': st.session_state.get('form_cnpj', ''),
            'Cidade': st.session_state.get('form_cid', ''),
            'UF': st.session_state.get('form_uf', ''),
            'CEP': st.session_state.get('form_cep', ''),
            'Cod_Cli': st.session_state.get('form_cod', ''),
            'Fator': fator_seguro
        }
        
        salvar_dados()
        tipo_acao = "atualizado" if st.session_state['edit_mode'] else "cadastrado"
        st.toast(f"Cliente {nome} {tipo_acao} com sucesso!", icon="✅")
        limpar_campos()

    def excluir_cliente(nome_alvo):
        if nome_alvo in st.session_state['clientes_db']:
            del st.session_state['clientes_db'][nome_alvo]
            salvar_dados()
            st.toast("Cliente removido.", icon="🗑️")
            st.rerun()

    def preparar_edicao(chave, dados):
        st.session_state['form_nome'] = str(chave)
        st.session_state['form_tel'] = str(dados.get('Tel', ''))
        st.session_state['form_email'] = str(dados.get('Email', ''))
        st.session_state['form_end'] = str(dados.get('End', ''))
        st.session_state['form_cnpj'] = str(dados.get('CNPJ', ''))
        st.session_state['form_cid'] = str(dados.get('Cidade', ''))
        st.session_state['form_uf'] = str(dados.get('UF', ''))
        st.session_state['form_cep'] = str(dados.get('CEP', ''))
        st.session_state['form_cod'] = str(dados.get('Cod_Cli', ''))
        
        try:
            st.session_state['form_fator'] = float(dados.get('Fator', 1.0))
        except:
            st.session_state['form_fator'] = 1.0
            
        st.session_state['edit_mode'] = True
        st.toast(f"Editando: {chave}", icon="✏️")

    # --- 3. ÁREA DE IMPORTAÇÃO (PDF) ---
    with st.expander("📂 Importar Dados de Licença (CETESB/PDF)"):
        arquivo_pdf = st.file_uploader("Arraste o PDF aqui:", type="pdf")
        if arquivo_pdf is not None and st.button("🔄 Processar PDF"):
            try:
                # Chama a função que já existe no seu código lá em cima
                dados_lidos = ler_pdf_antigo(arquivo_pdf) 
                if dados_lidos:
                    st.session_state['form_nome'] = str(dados_lidos.get('Nome', ''))
                    st.session_state['form_cnpj'] = str(dados_lidos.get('CNPJ', ''))
                    st.session_state['form_end'] = str(dados_lidos.get('End', ''))
                    st.session_state['form_cid'] = str(dados_lidos.get('Cidade', ''))
                    st.session_state['form_uf'] = str(dados_lidos.get('UF', ''))
                    st.session_state['form_cep'] = str(dados_lidos.get('CEP', ''))
                    st.session_state['form_tel'] = str(dados_lidos.get('Tel', ''))
                    st.session_state['form_email'] = str(dados_lidos.get('Email', ''))
                    st.session_state['form_cod'] = str(dados_lidos.get('Cod_Cli', ''))
                    st.success("Dados extraídos com sucesso!")
            except NameError: 
                st.error("Erro: Função de leitura não encontrada. Verifique o início do código.")
            except Exception as e:
                st.error(f"Erro ao processar: {e}")

    # --- 4. FORMULÁRIO DE CADASTRO ---
    with st.form("form_cliente_principal"):
        st.markdown(f"#### {'✏️ Editando Cliente' if st.session_state['edit_mode'] else '➕ Novo Cliente'}")
        
        c1, c2 = st.columns([3, 1])
        c1.text_input("Nome / Razão Social", key="form_nome", disabled=st.session_state['edit_mode']) 
        c2.text_input("Cód. Cliente", key="form_cod")
        
        c3, c4 = st.columns([1, 2])
        c3.number_input("💲 Fator Preço (1.0 = Normal)", min_value=0.1, max_value=5.0, step=0.05, key="form_fator")
        c4.text_input("CNPJ", key="form_cnpj")
        
        c5, c6 = st.columns([1, 2])
        c5.text_input("Telefone", key="form_tel")
        c6.text_input("E-mail", key="form_email", placeholder="email@empresa.com")
        
        st.text_input("Endereço", key="form_end")
        
        c7, c8, c9 = st.columns([2, 1, 1])
        c7.text_input("Cidade", key="form_cid")
        c8.text_input("UF", key="form_uf")
        c9.text_input("CEP", key="form_cep")
        
        st.form_submit_button("💾 SALVAR DADOS", on_click=salvar_cliente)

    # Botão de Cancelar fora do form para não submeter
    if st.session_state['edit_mode']:
        st.button("❌ Cancelar Edição", on_click=limpar_campos)
    else:
        st.button("🧹 Limpar Campos", on_click=limpar_campos)
    
    # --- 5. LISTAGEM DE CLIENTES (ÁREA DO ERRO CORRIGIDA) ---
    st.markdown("---")
    st.subheader("📇 Carteira de Clientes")
    
    if st.session_state['clientes_db']:
        busca = st.text_input("🔍 Buscar Cliente...", placeholder="Digite o nome...")
        
        # Ordena a lista
        lista_clientes = sorted(list(st.session_state['clientes_db'].keys()))
        
        # Filtra se tiver busca
        if busca: 
            lista_clientes = [k for k in lista_clientes if busca.lower() in k.lower()]
        
        # Cabeçalho Visual
        h1, h2 = st.columns([5, 1])
        h1.caption("DADOS DO CLIENTE")
        h2.caption("AÇÕES")

        for nome in lista_clientes:
            dados = st.session_state['clientes_db'][nome]
            
            # --- BLINDAGEM MATEMÁTICA DA LISTA (AQUI ESTAVA O ERRO) ---
            try:
                raw_fator = dados.get('Fator', 1.0)
                # Força conversão para float, se falhar, usa 1.0
                fator = float(raw_fator) if raw_fator else 1.0
            except (ValueError, TypeError):
                fator = 1.0

            # Lógica de Exibição do Texto (Blindada com try/except e round)
            try:
                if fator == 1.0:
                    txt_fator = "NORMAL"
                    cor_fator = "blue"
                elif fator < 1.0:
                    # round resolve problemas de dizima periodica
                    desc = int(round((1.0 - fator) * 100))
                    txt_fator = f"DESC. {desc}%"
                    cor_fator = "green"
                else:
                    acres = int(round((fator - 1.0) * 100))
                    txt_fator = f"ACRÉSC. {acres}%"
                    cor_fator = "red"
            except:
                txt_fator = "NORMAL"
                cor_fator = "blue"
            
            email = dados.get('Email', '')

            # Layout da Linha
            col_info, col_btn = st.columns([5, 1])
            
            with col_info:
                with st.expander(f"🏢 {nome} [{txt_fator}]"):
                    st.write(f"📍 {dados.get('End', '-')}")
                    st.write(f"📞 {dados.get('Tel', '-')} | CNPJ: {dados.get('CNPJ', '-')}")
                    st.markdown(f"**Tabela:** :{cor_fator}[{fator:.2f}]")
                    
                    b1, b2 = st.columns([1, 1])
                    b1.button("✏️ EDITAR", key=f"ed_{nome}", on_click=preparar_edicao, args=(nome, dados))
                    b2.button("🗑️ EXCLUIR", key=f"del_{nome}", on_click=excluir_cliente, args=(nome,))
            
            with col_btn:
                if email:
                    # Popover Discreto
                    with st.popover("📋", help="Copiar Email"):
                        st.code(email, language="text")
                else:
                    st.caption("-")
            
    else:
        st.info("Nenhum cliente cadastrado no sistema.")

elif menu == "🛠️ Admin / Backup":
    st.title("🛠️ Admin")
    if st.text_input("Senha", type="password") == "labormetal22":
        t1, t2, t3 = st.tabs(["Backup", "Restaurar", "Reset"])
        with t1:
            if st.button("Gerar Backup"):
                data = {
                    "estoque": st.session_state['estoque'].to_dict('records'),
                    "clientes": st.session_state['clientes_db'],
                    "vendas": st.session_state['log_vendas'],
                    "entradas": st.session_state['log_entradas'],
                    "laudos": st.session_state['log_laudos']
                }
                st.download_button("Baixar JSON", json.dumps(data, indent=4), f"Backup_{datetime.now().date()}.json", "application/json")
        with t2:
            up = st.file_uploader("Upload JSON", type="json")
            if up and st.button("Carregar"):
                d = json.load(up)
                st.session_state['estoque'] = pd.DataFrame(d['estoque'])
                st.session_state['clientes_db'] = d['clientes']
                st.session_state['log_vendas'] = d['vendas']
                st.session_state['log_entradas'] = d['entradas']
                st.session_state['log_laudos'] = d['laudos']
                salvar_dados(); st.success("Restaurado!")
        with t3:
            if st.button("ZERAR TUDO") and st.text_input("Confirma?") == "SIM":
                st.session_state['clientes_db'] = {}
                st.session_state['log_vendas'] = []
                # ... limpar o resto
                salvar_dados()


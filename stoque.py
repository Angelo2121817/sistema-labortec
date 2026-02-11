import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import os
import html
import json
import time
from pypdf import PdfReader
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection
import streamlit.components.v1 as components

# ==============================================================================
# CACHE E OTIMIZAÇÃO PARA EVITAR RATE LIMIT 429
# ==============================================================================

@st.cache_resource
def get_connection():
    """Cria conexão UMA VEZ e reutiliza"""
    try:
        return st.connection("gsheets", type=GSheetsConnection)
    except Exception as e:
        st.error(f"Erro na conexão: {e}")
        return None

def realizar_backup_local():
    """Salva backup local para fallback"""
    try:
        dados_backup = {
            "estoque": st.session_state.get("estoque", pd.DataFrame()).to_dict("records"),
            "clientes": st.session_state.get("clientes_db", {}),
            "log_vendas": st.session_state.get("log_vendas", []),
            "log_entradas": st.session_state.get("log_entradas", []),
            "log_laudos": st.session_state.get("log_laudos", []),
            "aviso": st.session_state.get("aviso_geral", "")
        }
        with open("backup_seguranca.json", "w", encoding="utf-8") as f:
            json.dump(dados_backup, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Erro ao criar backup local: {e}")

def carregar_backup_local():
    """Carrega dados do backup local se API falhar"""
    try:
        if os.path.exists("backup_seguranca.json"):
            with open("backup_seguranca.json", "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Erro ao carregar backup: {e}")
    return None

# --- BLOCO DE SEGURANÇA INICIAL ---
if 'estoque' not in st.session_state:
    st.session_state['estoque'] = pd.DataFrame(columns=['Cod', 'Produto', 'Quantidade', 'Preço', 'Categoria'])
if 'clientes_db' not in st.session_state: st.session_state['clientes_db'] = {}
if 'log_vendas' not in st.session_state: st.session_state['log_vendas'] = []
if 'log_entradas' not in st.session_state: st.session_state['log_entradas'] = []
if 'log_laudos' not in st.session_state: st.session_state['log_laudos'] = []
if 'aviso_geral' not in st.session_state: st.session_state['aviso_geral'] = ""
if 'dados_carregados' not in st.session_state: st.session_state['dados_carregados'] = False
if 'ultima_sincronizacao' not in st.session_state: st.session_state['ultima_sincronizacao'] = None

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

conn = get_connection()
if conn is None:
    st.error("Falha na conexão com Google Sheets. Usando dados locais.")

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
# 3. MOTOR DE DADOS (OTIMIZADO)
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
    """Carrega dados UMA VEZ com fallback para backup local"""
    
    # Se já foi carregado nesta sessão, não carrega novamente
    if st.session_state.get('dados_carregados'):
        return True
    
    try:
        if conn is None:
            raise Exception("Conexão não disponível")
        
        # Adiciona delay para evitar rate limit
        time.sleep(2)
        
        # 1. Carrega Estoque
        try:
            df_est = conn.read(worksheet="Estoque", ttl=3600)  # Cache de 1 hora
            if isinstance(df_est, pd.DataFrame) and not df_est.empty:
                df_est = _normalizar_colunas(df_est)
                st.session_state["estoque"] = df_est
        except Exception as e:
            st.warning(f"Erro ao carregar Estoque: {e}")

        time.sleep(1)

        # 2. Carrega Clientes
        try:
            df_cli = conn.read(worksheet="Clientes", ttl=3600)
            if isinstance(df_cli, pd.DataFrame) and not df_cli.empty:
                df_cli = _normalizar_colunas(df_cli)
                if "Email" not in df_cli.columns: df_cli["Email"] = ""
                if "Nome" in df_cli.columns: 
                    st.session_state["clientes_db"] = df_cli.set_index("Nome").to_dict("index")
        except Exception as e:
            st.warning(f"Erro ao carregar Clientes: {e}")

        time.sleep(1)

        # 3. Carrega Logs (com delay entre cada um)
        for aba in ["Log_Vendas", "Log_Entradas", "Log_Laudos", "Avisos"]:
            try:
                df = conn.read(worksheet=aba, ttl=3600)
                
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
                        st.session_state['log_laudos'] = df.to_dict("records")

                    elif aba in ["Log_Vendas", "Log_Entradas"]:
                        if "Data" in df.columns: df["Data"] = df["Data"].apply(_fix_datetime_br)
                        st.session_state[aba.lower()] = df.to_dict("records")
                    
                    elif aba == "Avisos":
                        try:
                            val = str(df.iloc[0].values[0])
                            st.session_state['aviso_geral'] = val
                        except:
                            st.session_state['aviso_geral'] = ""
                else:
                    if aba == "Avisos": st.session_state['aviso_geral'] = ""
                    else: st.session_state[aba.lower()] = []
                
                time.sleep(1)  # Delay entre requisições
                
            except Exception as e:
                st.warning(f"Erro ao carregar {aba}: {e}")
        
        st.session_state['dados_carregados'] = True
        st.session_state['ultima_sincronizacao'] = obter_horario_br()
        realizar_backup_local()
        return True
        
    except Exception as e:
        st.error(f"⚠️ Erro crítico ao carregar dados: {e}")
        
        # Tenta carregar backup local
        backup = carregar_backup_local()
        if backup:
            st.session_state["estoque"] = pd.DataFrame(backup.get("estoque", []))
            st.session_state["clientes_db"] = backup.get("clientes", {})
            st.session_state["log_vendas"] = backup.get("log_vendas", [])
            st.session_state["log_entradas"] = backup.get("log_entradas", [])
            st.session_state["log_laudos"] = backup.get("log_laudos", [])
            st.session_state['aviso_geral'] = backup.get("aviso", "")
            st.session_state['dados_carregados'] = True
            st.warning("✅ Dados carregados do backup local!")
            return True
        
        return False

def salvar_dados():
    """Salva com retry e fallback"""
    try:
        if conn is None:
            raise Exception("Conexão não disponível")
        
        time.sleep(1)
        
        # Salva na Nuvem (Google Sheets)
        conn.update(worksheet="Estoque", data=st.session_state["estoque"])
        
        time.sleep(1)
        
        if st.session_state.get("clientes_db"):
            df_clis = pd.DataFrame.from_dict(st.session_state["clientes_db"], orient="index").reset_index().rename(columns={"index": "Nome"})
            conn.update(worksheet="Clientes", data=df_clis)
        
        time.sleep(1)
            
        conn.update(worksheet="Log_Vendas", data=pd.DataFrame(st.session_state.get("log_vendas", [])))
        
        time.sleep(1)
        
        conn.update(worksheet="Log_Entradas", data=pd.DataFrame(st.session_state.get("log_entradas", [])))
        
        time.sleep(1)
        
        conn.update(worksheet="Log_Laudos", data=pd.DataFrame(st.session_state.get("log_laudos", [])))
        
        time.sleep(1)
        
        df_aviso = pd.DataFrame({"Mensagem": [str(st.session_state.get('aviso_geral', ""))]})
        conn.update(worksheet="Avisos", data=df_aviso)
        
        st.toast("✅ Dados Sincronizados!", icon="☁️")
        realizar_backup_local()
        
    except Exception as e:
        st.warning(f"⚠️ Erro ao salvar na nuvem: {e}. Dados salvos localmente.")
        realizar_backup_local()

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

def gerar_pdf_estoque(usuario, df_estoque):
    pdf = PDF()
    pdf.vendedor_nome = usuario
    pdf.titulo_doc = "RELATÓRIO DE ESTOQUE"
    pdf.add_page()
    
    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(0, 8, f" POSIÇÃO DE ESTOQUE EM: {obter_horario_br().strftime('%d/%m/%Y às %H:%M')}", 1, 1, "L", fill=True)
    pdf.ln(5)
    
    w = [15, 75, 25, 15, 20, 20, 25] 
    cols = ["Cód", "Produto", "Marca", "Un", "Saldo", "Custo", "Total R$"]
    
    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(225, 225, 225)
    
    for i, c in enumerate(cols):
        pdf.cell(w[i], 8, c, 1, 0, "C", fill=True)
    pdf.ln()
    
    pdf.set_font("Arial", "", 7)
    valor_total_estoque = 0.0
    
    for _, row in df_estoque.iterrows():
        try:
            saldo = float(row.get('Saldo', 0))
            custo = float(row.get('Preco_Base', 0))
            total_item = saldo * custo
        except:
            saldo, custo, total_item = 0.0, 0.0, 0.0
            
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
        
    pdf.ln(2)
    pdf.set_font("Arial", "B", 9)
    pdf.cell(sum(w)-25, 8, "VALOR TOTAL EM ESTOQUE:", 0, 0, "R")
    pdf.cell(25, 8, f"R$ {valor_total_estoque:,.2f}", 1, 1, "R", fill=True)
    
    pdf.ln(15)
    y = pdf.get_y()
    
    pdf.line(60, y, 150, y)
    pdf.set_font("Arial", "", 8)
    pdf.set_xy(60, y + 2)
    pdf.cell(90, 4, "Responsável pela Conferência", 0, 1, "C")
    
    return pdf.output(dest="S").encode("latin-1")

# ==============================================================================
# 6. MENU LATERAL E TEMAS
# ==============================================================================
st.sidebar.title("🛠️ MENU GERAL")
st.sidebar.success(f"👤 {obter_saudacao()}, {st.session_state['usuario_nome']}!")

st.sidebar.markdown("---")
with st.sidebar.expander("📢 DEFINIR AVISO"):
    aviso_txt = st.text_area("Mensagem do Mural:", value=st.session_state['aviso_geral'], height=100)
    c1, c2 = st.columns(2)
    if c1.button("💾 Gravar"): 
        st.session_state['aviso_geral'] = aviso_txt
        salvar_dados()
        st.rerun()
    if c2.button("🗑️ Apagar"): 
        st.session_state['aviso_geral'] = ""
        salvar_dados()
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🎨 Personalizar Tela")
opcoes_temas = ["⚪ Padrão (Clean)", "🔵 Azul Labortec", "🌿 Verde Natureza", "⚫ Dark Mode (Noturno)"]
tema_sel = st.sidebar.selectbox("Escolha o visual:", opcoes_temas)
aplicar_tema(tema_sel)

# Mostra status de sincronização
if st.session_state.get('ultima_sincronizacao'):
    st.sidebar.caption(f"✅ Última sync: {st.session_state['ultima_sincronizacao'].strftime('%H:%M:%S')}")
else:
    st.sidebar.caption("⏳ Carregando dados...")

menu = st.sidebar.radio("Navegar:", [
    "📊 Dashboard", "🧪 Laudos", "💰 Vendas & Orçamentos", "📥 Entrada de Estoque", 
    "📦 Estoque", "📋 Conferência Geral", "👥 Clientes", "🛠️ Admin / Backup"
])

# CARREGA DADOS APENAS UMA VEZ
if not st.session_state.get('dados_carregados'):
    with st.spinner("⏳ Carregando dados..."):
        carregar_dados()

# ==============================================================================
# 7. PÁGINAS DO SISTEMA (RESTO DO CÓDIGO IGUAL AO ANTERIOR)
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

# [RESTO DO CÓDIGO IGUAL AO ANTERIOR - COPIE AS OUTRAS SEÇÕES DO MENU]
# Laudos, Vendas, Entrada, Estoque, Conferência, Clientes, Admin...

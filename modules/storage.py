import sqlite3
import os
import datetime
import io
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "plano_sc_estudo.db")

DEFAULT_SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1Um65rCo3IEcC2fdkgey-TkP_DIT3qqlajp3h3Um1QSY/edit"
WORKSHEET_NAME = "Dados"

# -----------------------------------------------------------------------------
# Utilitários de Conexão com Google Sheets
# -----------------------------------------------------------------------------
def _get_secrets_safe():
    """Recupera st.secrets defensivamente sem quebrar em ambientes sem Streamlit."""
    try:
        import streamlit as st
        return st.secrets
    except Exception:
        return {}

def _get_spreadsheet_url() -> str:
    secrets = _get_secrets_safe()
    if "connections" in secrets and "gsheets" in secrets["connections"]:
        return secrets["connections"]["gsheets"].get("spreadsheet", DEFAULT_SPREADSHEET_URL)
    if "GSHEETS_URL" in secrets:
        return str(secrets["GSHEETS_URL"])
    return DEFAULT_SPREADSHEET_URL

def _get_service_account_dict():
    secrets = _get_secrets_safe()
    creds = None
    if "connections" in secrets and "gsheets" in secrets["connections"]:
        conn = dict(secrets["connections"]["gsheets"])
        if "client_email" in conn and "private_key" in conn:
            creds = conn
    elif "gcp_service_account" in secrets:
        creds = dict(secrets["gcp_service_account"])
        
    if creds and "private_key" in creds:
        # Corrige quebras de linha escapadas que costumam ocorrer em TOML / Cloud Secrets
        if "\\n" in creds["private_key"]:
            creds["private_key"] = creds["private_key"].replace("\\n", "\n")
        expected_keys = [
            "type", "project_id", "private_key_id", "private_key",
            "client_email", "client_id", "auth_uri", "token_uri",
            "auth_provider_x509_cert_url", "client_x509_cert_url"
        ]
        return {k: creds[k] for k in expected_keys if k in creds}
    return None

def _get_gspread_client():
    creds = _get_service_account_dict()
    if not creds:
        return None
    try:
        import gspread
        return gspread.service_account_from_dict(creds)
    except Exception as e:
        print(f"[Aviso] Falha ao instanciar gspread com credenciais: {e}")
        return None

def montar_linhas_caso(caso_info: dict, itens: list[dict], data_envio: str) -> list[list]:
    """Prepara a matriz de dados exatamente nas 16 colunas da aba Dados (A a P)."""
    rows = []
    for it in itens:
        rows.append([
            caso_info.get("codigo_caso", ""),
            caso_info.get("uf", "BR"),
            caso_info.get("cidade", ""),
            caso_info.get("hospital_prestador", "Não informado"),
            caso_info.get("tipo_atendimento", "Não especificado"),
            caso_info.get("natureza_inconsistencia", ""),
            caso_info.get("data_evento", ""),
            data_envio,
            caso_info.get("identificacao_opcional", ""),
            caso_info.get("relato_observacoes", ""),
            it.get("descricao", "Sem descrição"),
            it.get("categoria", "Outros"),
            float(it.get("quantidade", 1.0) or 1.0),
            float(it.get("coparticipacao", 0.0) or 0.0),
            float(it.get("faturado_credenciado", 0.0) or 0.0),
            it.get("observacao_estatistica", "")
        ])
    return rows

def salvar_no_google_sheets(caso_info: dict, itens: list[dict], data_envio: str) -> tuple[bool, str]:
    """Salva as linhas do caso diretamente no Google Sheets via gspread ou Webhook."""
    rows = montar_linhas_caso(caso_info, itens, data_envio)
    secrets = _get_secrets_safe()
    
    # 1. Tentativa via Webhook Google Apps Script (se configurado)
    webhook_url = secrets.get("GSHEETS_WEBHOOK_URL")
    if webhook_url:
        try:
            import requests
            resp = requests.post(webhook_url, json={"rows": rows}, timeout=10)
            if resp.status_code == 200:
                return True, "Sincronizado com Google Sheets via Apps Script Webhook."
        except Exception as e:
            print(f"[Erro Webhook Google Sheets] {e}")

    # 2. Tentativa via Service Account / gspread (Padrão st-gsheets-connection)
    client = _get_gspread_client()
    if client:
        try:
            spreadsheet_url = _get_spreadsheet_url()
            sh = client.open_by_url(spreadsheet_url)
            wks = sh.worksheet(WORKSHEET_NAME)
            wks.append_rows(rows, value_input_option="USER_ENTERED")
            return True, "Sincronizado com Google Sheets via Conta de Serviço."
        except Exception as e:
            msg_erro = f"Falha ao gravar no Google Sheets: {e}"
            print(f"[Erro Google Sheets] {msg_erro}")
            return False, msg_erro

    return False, "Google Sheets não configurado (salvo apenas no banco local)."

def obter_dados_gsheets() -> pd.DataFrame | None:
    """Tenta ler os dados da aba Dados do Google Sheets."""
    # 1. Ler via gspread
    client = _get_gspread_client()
    if client:
        try:
            spreadsheet_url = _get_spreadsheet_url()
            sh = client.open_by_url(spreadsheet_url)
            wks = sh.worksheet(WORKSHEET_NAME)
            records = wks.get_all_records()
            if records:
                return pd.DataFrame(records)
        except Exception as e:
            print(f"[Aviso] Falha ao ler Google Sheets via gspread: {e}")

    # 2. Ler via st.connection("gsheets") se configurado
    try:
        import streamlit as st
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        url = _get_spreadsheet_url()
        df = conn.read(spreadsheet=url, worksheet=WORKSHEET_NAME, ttl=60)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass

    return None

# -----------------------------------------------------------------------------
# Persistência Relacional SQLite Local
# -----------------------------------------------------------------------------
def init_db():
    """Inicializa as tabelas do banco de dados relacional local."""
    os.makedirs(DB_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS casos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_caso TEXT UNIQUE NOT NULL,
            uf TEXT,
            cidade TEXT,
            hospital_prestador TEXT,
            tipo_atendimento TEXT,
            data_evento TEXT,
            data_envio TEXT,
            total_itens INTEGER,
            soma_coparticipacao REAL,
            soma_faturado REAL
        )
        """)
        
        # Migração defensiva de colunas opcionais
        try:
            cursor.execute("ALTER TABLE casos ADD COLUMN identificacao_opcional TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE casos ADD COLUMN relato_observacoes TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE casos ADD COLUMN natureza_inconsistencia TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_caso TEXT NOT NULL,
            descricao TEXT NOT NULL,
            categoria TEXT,
            quantidade REAL DEFAULT 1.0,
            coparticipacao REAL DEFAULT 0.0,
            faturado_credenciado REAL DEFAULT 0.0,
            observacao_estatistica TEXT,
            FOREIGN KEY (codigo_caso) REFERENCES casos(codigo_caso)
        )
        """)
        
        conn.commit()

def salvar_caso(caso_info: dict, itens: list[dict]) -> dict:
    """Salva um caso e seus itens no SQLite local e no Google Sheets (se configurado)."""
    init_db()
    codigo_caso = caso_info["codigo_caso"]
    data_envio = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    total_itens = len(itens)
    soma_copart = sum(float(it.get("coparticipacao", 0.0) or 0.0) for it in itens)
    soma_fat = sum(float(it.get("faturado_credenciado", 0.0) or 0.0) for it in itens)
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
        INSERT INTO casos (
            codigo_caso, uf, cidade, hospital_prestador, tipo_atendimento,
            data_evento, data_envio, total_itens, soma_coparticipacao, soma_faturado, identificacao_opcional, relato_observacoes, natureza_inconsistencia
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            codigo_caso,
            caso_info.get("uf", "BR"),
            caso_info.get("cidade", ""),
            caso_info.get("hospital_prestador", "Não informado"),
            caso_info.get("tipo_atendimento", "Não especificado"),
            caso_info.get("data_evento", ""),
            data_envio,
            total_itens,
            soma_copart,
            soma_fat,
            caso_info.get("identificacao_opcional", ""),
            caso_info.get("relato_observacoes", ""),
            caso_info.get("natureza_inconsistencia", "")
        ))
        
        for it in itens:
            cursor.execute("""
            INSERT INTO itens (
                codigo_caso, descricao, categoria, quantidade,
                coparticipacao, faturado_credenciado, observacao_estatistica
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                codigo_caso,
                it.get("descricao", "Sem descrição"),
                it.get("categoria", "Outros"),
                float(it.get("quantidade", 1.0) or 1.0),
                float(it.get("coparticipacao", 0.0) or 0.0),
                float(it.get("faturado_credenciado", 0.0) or 0.0),
                it.get("observacao_estatistica", "")
            ))
            
        conn.commit()
        
    # Gravar em nuvem no Google Sheets
    gs_ok, gs_msg = salvar_no_google_sheets(caso_info, itens, data_envio)
    
    return {
        "codigo_caso": codigo_caso,
        "gsheets_sincronizado": gs_ok,
        "gsheets_mensagem": gs_msg
    }

def obter_todos_itens_df() -> pd.DataFrame:
    """Retorna um DataFrame completo com todos os itens, priorizando Google Sheets e caindo para SQLite."""
    # 1. Tentar ler do Google Sheets
    df_gs = obter_dados_gsheets()
    if df_gs is not None and not df_gs.empty:
        return df_gs
        
    # 2. Fallback para SQLite
    init_db()
    query = """
    SELECT 
        c.codigo_caso as "Código do Caso",
        c.uf as "UF",
        c.cidade as "Cidade",
        c.hospital_prestador as "Hospital / Prestador",
        c.tipo_atendimento as "Tipo de Atendimento",
        c.natureza_inconsistencia as "Classificação / Natureza",
        c.data_evento as "Data do Evento",
        c.data_envio as "Data de Envio",
        c.identificacao_opcional as "Matrícula / Contato (Opcional)",
        c.relato_observacoes as "Relato / Observações",
        i.descricao as "Descrição do Item",
        i.categoria as "Categoria",
        i.quantidade as "Quantidade",
        i.coparticipacao as "Coparticipação (R$)",
        i.faturado_credenciado as "Faturado Credenciado (R$)",
        i.observacao_estatistica as "Observação Estatística"
    FROM itens i
    JOIN casos c ON i.codigo_caso = c.codigo_caso
    ORDER BY c.id DESC, i.id ASC
    """
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(query, conn)

def obter_resumo_estatistico() -> dict:
    """Retorna métricas agregadas da base de evidências, calculadas sobre a fonte ativa."""
    df = obter_todos_itens_df()
    if df is not None and not df.empty:
        col_caso = "Código do Caso" if "Código do Caso" in df.columns else df.columns[0]
        col_copart = "Coparticipação (R$)" if "Coparticipação (R$)" in df.columns else "coparticipacao"
        col_fat = "Faturado Credenciado (R$)" if "Faturado Credenciado (R$)" in df.columns else "faturado_credenciado"
        col_uf = "UF" if "UF" in df.columns else "uf"
        col_cat = "Categoria" if "Categoria" in df.columns else "categoria"
        
        # Converte valores numéricos caso venham formatados em texto
        copart_series = pd.to_numeric(
            df[col_copart].astype(str).str.replace("R$", "", regex=False).str.replace(".", "", regex=False).str.replace(",", ".", regex=False).str.strip(),
            errors="coerce"
        ).fillna(0.0) if col_copart in df.columns else pd.Series([0.0] * len(df))
        
        fat_series = pd.to_numeric(
            df[col_fat].astype(str).str.replace("R$", "", regex=False).str.replace(".", "", regex=False).str.replace(",", ".", regex=False).str.strip(),
            errors="coerce"
        ).fillna(0.0) if col_fat in df.columns else pd.Series([0.0] * len(df))
        
        total_casos = int(df[col_caso].nunique())
        total_itens = len(df)
        soma_copart = float(copart_series.sum())
        soma_fat = float(fat_series.sum())
        
        # Agrupamento UF
        if col_uf in df.columns:
            df_temp = df.copy()
            df_temp["copart_num"] = copart_series
            df_uf = df_temp.groupby(col_uf).agg(
                total_casos=(col_caso, "nunique"),
                total_itens=(col_caso, "count")
            ).reset_index().rename(columns={col_uf: "uf"}).sort_values("total_casos", ascending=False)
        else:
            df_uf = pd.DataFrame(columns=["uf", "total_casos", "total_itens"])
            
        # Agrupamento Categoria
        if col_cat in df.columns:
            df_temp = df.copy()
            df_temp["copart_num"] = copart_series
            df_temp["fat_num"] = fat_series
            df_cat = df_temp.groupby(col_cat).agg(
                qtd=(col_cat, "count"),
                soma_copart=("copart_num", "sum"),
                soma_fat=("fat_num", "sum")
            ).reset_index().rename(columns={col_cat: "categoria"}).sort_values("qtd", ascending=False)
        else:
            df_cat = pd.DataFrame(columns=["categoria", "qtd", "soma_copart", "soma_fat"])
            
        return {
            "total_casos": total_casos,
            "total_itens": total_itens,
            "soma_coparticipacao": soma_copart,
            "soma_faturado": soma_fat,
            "df_uf": df_uf,
            "df_categoria": df_cat,
            "fonte": "Google Sheets" if _get_service_account_dict() or _get_secrets_safe().get("GSHEETS_WEBHOOK_URL") else "SQLite Local"
        }

    return {
        "total_casos": 0,
        "total_itens": 0,
        "soma_coparticipacao": 0.0,
        "soma_faturado": 0.0,
        "df_uf": pd.DataFrame(columns=["uf", "total_casos", "total_itens"]),
        "df_categoria": pd.DataFrame(columns=["categoria", "qtd", "soma_copart", "soma_fat"]),
        "fonte": "Vazia"
    }

def exportar_para_excel() -> bytes:
    """Gera um arquivo Excel formatado pericialmente em memória a partir da base completa."""
    df = obter_todos_itens_df()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Itens Coletados - Plano SC"
    
    header_fill = PatternFill(start_color="1B4965", end_color="1B4965", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    cell_font = Font(name="Calibri", size=10)
    thin_border = Border(
        left=Side(style='thin', color="DDDDDD"),
        right=Side(style='thin', color="DDDDDD"),
        top=Side(style='thin', color="DDDDDD"),
        bottom=Side(style='thin', color="DDDDDD")
    )
    
    headers = list(df.columns)
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
    for row_data in df.itertuples(index=False):
        ws.append(list(row_data))
        
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=len(headers)):
        for cell in row:
            cell.font = cell_font
            cell.border = thin_border
            if cell.column in [14, 15]:  # Coparticipação e Faturado
                cell.number_format = "R$ #,##0.00"
                cell.alignment = Alignment(horizontal="right")
            elif cell.column in [1, 2, 5, 6, 7, 8]:
                cell.alignment = Alignment(horizontal="center")
                
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)
        
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()

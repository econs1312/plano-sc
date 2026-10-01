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

def salvar_caso(caso_info: dict, itens: list[dict]) -> str:
    """Salva um caso com seus itens associados."""
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
            data_evento, data_envio, total_itens, soma_coparticipacao, soma_faturado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            soma_fat
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
        
    return codigo_caso

def obter_resumo_estatistico() -> dict:
    """Retorna métricas agregadas da base de evidências."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        c_casos = conn.cursor()
        c_casos.execute("SELECT COUNT(*), COALESCE(SUM(total_itens), 0), COALESCE(SUM(soma_coparticipacao), 0), COALESCE(SUM(soma_faturado), 0) FROM casos")
        row = c_casos.fetchone()
        
        total_casos = row[0]
        total_itens = row[1]
        soma_copart = row[2]
        soma_fat = row[3]
        
        # Casos por UF
        df_uf = pd.read_sql_query("SELECT uf, COUNT(*) as total_casos, SUM(total_itens) as total_itens FROM casos GROUP BY uf ORDER BY total_casos DESC", conn)
        
        # Itens por categoria
        df_cat = pd.read_sql_query("SELECT categoria, COUNT(*) as qtd, SUM(coparticipacao) as soma_copart, SUM(faturado_credenciado) as soma_fat FROM itens GROUP BY categoria ORDER BY qtd DESC", conn)
        
    return {
        "total_casos": total_casos,
        "total_itens": total_itens,
        "soma_coparticipacao": soma_copart,
        "soma_faturado": soma_fat,
        "df_uf": df_uf,
        "df_categoria": df_cat
    }

def obter_todos_itens_df() -> pd.DataFrame:
    """Retorna um DataFrame completo com todos os itens e contexto do caso."""
    init_db()
    query = """
    SELECT 
        c.codigo_caso as "Código do Caso",
        c.uf as "UF",
        c.cidade as "Cidade",
        c.hospital_prestador as "Hospital / Prestador",
        c.tipo_atendimento as "Tipo de Atendimento",
        c.data_evento as "Data do Evento",
        c.data_envio as "Data de Envio",
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

def exportar_para_excel() -> bytes:
    """Gera um arquivo Excel formatado pericialmente em memória para download."""
    df = obter_todos_itens_df()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Itens Coletados - Plano SC"
    
    # Estilos
    header_fill = PatternFill(start_color="1B4965", end_color="1B4965", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    cell_font = Font(name="Calibri", size=10)
    thin_border = Border(
        left=Side(style='thin', color="DDDDDD"),
        right=Side(style='thin', color="DDDDDD"),
        top=Side(style='thin', color="DDDDDD"),
        bottom=Side(style='thin', color="DDDDDD")
    )
    
    # Cabeçalhos
    headers = list(df.columns)
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
    # Dados
    for row_data in df.itertuples(index=False):
        ws.append(list(row_data))
        
    # Formatação numérica e larguras
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=len(headers)):
        for cell in row:
            cell.font = cell_font
            cell.border = thin_border
            # Coparticipação e Faturado (colunas 11 e 12)
            if cell.column in [11, 12]:
                cell.number_format = "R$ #,##0.00"
                cell.alignment = Alignment(horizontal="right")
            elif cell.column in [1, 2, 5, 6, 7, 10]:
                cell.alignment = Alignment(horizontal="center")
                
    # Auto-ajuste de colunas
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)
        
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()

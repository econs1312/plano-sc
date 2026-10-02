import re
import uuid
import datetime

def gerar_codigo_caso(uf: str = "BR") -> str:
    """Gera um identificador anônimo para o caso (ex: CASO-SC-SP-8F2A)."""
    uf_clean = re.sub(r'[^A-Z]', '', uf.upper())[:2] or "BR"
    short_hash = uuid.uuid4().hex[:4].upper()
    ano = datetime.datetime.now().year
    return f"CASO-SC-{uf_clean}-{ano}-{short_hash}"

def sanitizar_texto(texto: str) -> str:
    """
    Remove padrões de dados sensíveis (LGPD) como CPF, matrículas,
    telefones e e-mails que possam ter sido capturados acidentalmente.
    """
    if not texto:
        return ""
    
    # Mascarar CPF (formatado ou puro)
    texto = re.sub(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b', '[CPF REMOVIDO]', texto)
    texto = re.sub(r'\b\d{11}\b', '[DOCUMENTO REMOVIDO]', texto)
    
    # Mascarar e-mails
    texto = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL REMOVIDO]', texto)
    
    # Mascarar telefones
    texto = re.sub(r'\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\d{4}|\d{4})[-\s]?\d{4}\b', '[TELEFONE REMOVIDO]', texto)
    
    # Mascarar padrões de matrícula (letras C/F seguidas de números ou 6 a 8 dígitos isolados)
    texto = re.sub(r'\b[cCfF]\d{6,8}\b', '[MATRÍCULA REMOVIDA]', texto)
    
    # Limpar excesso de espaços
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def higienizar_item(item: dict) -> dict:
    """Higieniza todos os campos de texto de um item extraído."""
    item_clean = item.copy()
    if "descricao" in item_clean:
        item_clean["descricao"] = sanitizar_texto(item_clean["descricao"])
    if "prestador" in item_clean:
        item_clean["prestador"] = sanitizar_texto(item_clean["prestador"])
    if "categoria" in item_clean:
        item_clean["categoria"] = sanitizar_texto(item_clean["categoria"])
    return item_clean

def formatar_data_inteligente(valor: str) -> tuple[str, bool]:
    """
    Formata automaticamente qualquer entrada de data para o padrão DD/MM/AAAA (ou MM/AAAA).
    Exemplos aceitos:
      - 01102026 -> 01/10/2026
      - 1102026 -> 01/10/2026
      - 011026 -> 01/10/2026
      - 102026 -> 10/2026
      - 01.10.2026 / 01-10-2026 -> 01/10/2026
      - 2026-10-01 -> 01/10/2026
    Retorna: (data_formatada, eh_valido)
    """
    if not valor:
        return "", False
    
    val = str(valor).strip()
    if val.lower() in ["não informado", "nao informado", "null", "none", "não identificado", "nao identificado"]:
        return "", False
        
    # 1. Se já está no formato ISO AAAA-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
        try:
            dt = datetime.datetime.strptime(val, "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y"), True
        except ValueError:
            return val, False

    # 2. Se contém separadores como barra, ponto, traço ou espaço
    val_limpo = re.sub(r"[.\- ]", "/", val)
    partes = val_limpo.split("/")
    
    if len(partes) == 3:
        p1, p2, p3 = partes
        if p1.isdigit() and p2.isdigit() and p3.isdigit():
            dia = int(p1)
            mes = int(p2)
            ano = int(p3)
            if ano < 100:
                ano += 2000
            if 1 <= dia <= 31 and 1 <= mes <= 12 and 1990 <= ano <= 2050:
                return f"{dia:02d}/{mes:02d}/{ano:04d}", True
            return val, False

    if len(partes) == 2:
        p1, p2 = partes
        if p1.isdigit() and p2.isdigit():
            mes = int(p1)
            ano = int(p2)
            if ano < 100:
                ano += 2000
            if 1 <= mes <= 12 and 1990 <= ano <= 2050:
                return f"{mes:02d}/{ano:04d}", True
            return val, False

    # 3. Apenas números consecutivos
    digitos = re.sub(r"\D", "", val)
    
    # 8 dígitos: DDMMAAAA
    if len(digitos) == 8:
        dia = int(digitos[:2])
        mes = int(digitos[2:4])
        ano = int(digitos[4:])
        if 1 <= dia <= 31 and 1 <= mes <= 12 and 1990 <= ano <= 2050:
            return f"{dia:02d}/{mes:02d}/{ano:04d}", True
        return val, False

    # 7 dígitos: D-MM-AAAA (ex: 1102026 -> 01/10/2026)
    if len(digitos) == 7:
        dia = int(digitos[0])
        mes = int(digitos[1:3])
        ano = int(digitos[3:])
        if 1 <= dia <= 9 and 1 <= mes <= 12 and 1990 <= ano <= 2050:
            return f"{dia:02d}/{mes:02d}/{ano:04d}", True

    # 6 dígitos: MMAAAA ou DDMMAA
    if len(digitos) == 6:
        ano_candidato = int(digitos[2:])
        mes_candidato = int(digitos[:2])
        if 1990 <= ano_candidato <= 2050 and 1 <= mes_candidato <= 12:
            return f"{mes_candidato:02d}/{ano_candidato:04d}", True
        
        dia = int(digitos[:2])
        mes = int(digitos[2:4])
        ano = int(digitos[4:]) + 2000
        if 1 <= dia <= 31 and 1 <= mes <= 12 and 1990 <= ano <= 2050:
            return f"{dia:02d}/{mes:02d}/{ano:04d}", True

    return val, False


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

import json
import re
import google.generativeai as genai
from modules.anonymizer import sanitizar_texto, higienizar_item

MODELOS_DISPONIVEIS = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-pro"
]

PROMPT_SISTEMA = """
Você é um especialista em análise estatística de faturamentos médicos e demonstrativos de coparticipação do Plano SC.
Sua missão é extrair com rigor pericial as informações dos itens faturados contidos no documento/imagem enviado, preparando os dados para um estudo amostral amplo.

DIRETRIZES FUNDAMENTAIS:
1. ANONIMIZAÇÃO E PRIVACIDADE (LGPD):
   - NUNCA extraia nomes de pessoas físicas, CPFs, números de matrícula, carteirinha ou dados de contato.
   - Extraia apenas dados técnicos do faturamento: hospital/prestador, data, descrição do item, quantidade e valores.

2. ESTRUTURA DOS DADOS:
   Retorne EXCLUSIVAMENTE um objeto JSON válido, sem texto explicativo adicional, com o seguinte formato:
{
  "hospital_ou_prestador": "Nome do hospital, laboratório ou prestador (ou 'Não informado')",
  "data_evento": "DD/MM/AAAA ou MM/AAAA",
  "tipo_atendimento": "Pronto-Socorro / Internação / Ambulatorial / Exame / Consulta / Outro",
  "itens": [
    {
      "descricao": "Nome exato e padronizado do item, insumo, medicamento ou procedimento",
      "quantidade": 1.0,
      "coparticipacao": 0.00,
      "faturado_credenciado": 0.00,
      "categoria": "Dispositivos / Insumos Especiais | Materiais de Consumo Básico | Medicamentos / Soluções | Exames e Diagnósticos | Consultas / Pronto-Socorro | Taxas e Diárias | Outros",
      "observacao_estatistica": "Breve nota descritiva se for caso relevante para estudo de custos (ex: insumo básico avulso, equipo, exame de alta coparticipação)"
    }
  ]
}

3. VALORES MONETÁRIOS:
   - Forneça valores em formato numérico float (ex: 125.50), sem o símbolo R$.
   - Se o valor não estiver legível ou for zero, registre 0.00.
   - Em telas do app onde há 'Coparticipação' e 'Recebido pelo credenciado' (ou 'Valor faturado'), associe corretamente cada coluna.
"""

def extrair_evidencia_com_gemini(arquivo_bytes: bytes, mime_type: str, api_key: str) -> dict:
    """
    Envia a imagem ou PDF para o modelo Gemini e retorna o dicionário estruturado.
    """
    if not api_key:
        raise ValueError("Chave da API Gemini não informada.")

    genai.configure(api_key=api_key)
    
    ultimo_erro = None
    for modelo_nome in MODELOS_DISPONIVEIS:
        try:
            model = genai.GenerativeModel(modelo_nome)
            
            # Preparar payload multimodal
            partes = [
                {"mime_type": mime_type, "data": arquivo_bytes},
                PROMPT_SISTEMA
            ]
            
            response = model.generate_content(
                partes,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json"
                }
            )
            
            texto_resposta = response.text.strip()
            
            # Limpar eventuais blocos markdown `json ... `
            texto_limpo = re.sub(r'^`(?:json)?\s*', '', texto_resposta, flags=re.MULTILINE)
            texto_limpo = re.sub(r'\s*`$', '', texto_limpo, flags=re.MULTILINE).strip()
            
            dados = json.loads(texto_limpo)
            
            # Higienização de segurança pós-extração
            dados["hospital_ou_prestador"] = sanitizar_texto(dados.get("hospital_ou_prestador", "Não informado"))
            dados["data_evento"] = sanitizar_texto(dados.get("data_evento", ""))
            dados["tipo_atendimento"] = sanitizar_texto(dados.get("tipo_atendimento", "Não especificado"))
            
            itens_tratados = []
            for item in dados.get("itens", []):
                itens_tratados.append(higienizar_item(item))
            dados["itens"] = itens_tratados
            
            return {
                "sucesso": True,
                "modelo_usado": modelo_nome,
                "dados": dados
            }
            
        except Exception as e:
            ultimo_erro = e
            continue

    return {
        "sucesso": False,
        "erro": f"Não foi possível processar o documento com os modelos Gemini disponíveis: {str(ultimo_erro)}"
    }

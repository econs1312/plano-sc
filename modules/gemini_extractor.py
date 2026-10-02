import json
import re
import base64
import urllib.request
import urllib.error
from modules.anonymizer import sanitizar_texto, higienizar_item, formatar_data_inteligente

# Modelos ativos compatíveis com a chave da API Gemini (v1beta)
MODELOS_DISPONIVEIS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-flash-latest"
]

PROMPT_SISTEMA = """
Você é um assistente de extração e estruturação de demonstrativos de despesas médicas e coparticipação do Plano SC.
Sua missão é extrair com precisão e fidelidade as informações dos itens faturados contidos no documento/imagem enviado, organizando procedimentos e valores.

DIRETRIZES FUNDAMENTAIS:
1. ANONIMIZAÇÃO E PRIVACIDADE (LGPD):
   - NUNCA extraia nomes de pessoas físicas, CPFs, números de matrícula, carteirinha ou dados de contato.
   - Extraia apenas dados técnicos do faturamento: hospital/prestador, data, descrição do item, quantidade e valores.

2. ESTRUTURA DOS DADOS:
   Retorne EXCLUSIVAMENTE um objeto JSON válido, sem texto explicativo adicional, com o seguinte formato:
{
  "hospital_ou_prestador": "Nome do hospital, laboratório ou prestador visível (se não estiver explícito na imagem, retorne string vazia \"\")",
  "data_evento": "Data do evento no formato DD/MM/AAAA ou MM/AAAA (verifique cabeçalhos, títulos ou detalhes; se nenhuma data estiver visível no print, retorne string vazia \"\")",
  "tipo_atendimento": "Pronto-Socorro / Internação / Ambulatorial / Exame / Consulta / Outro",
  "itens": [
    {
      "descricao": "Nome exato e padronizado do item, insumo, medicamento ou procedimento",
      "quantidade": 1.0,
      "coparticipacao": 0.00,
      "faturado_credenciado": 0.00,
      "categoria": "Dispositivos / Insumos Especiais | Materiais de Consumo Básico | Medicamentos / Soluções | Exames e Diagnósticos | Consultas / Pronto-Socorro | Taxas e Diárias | Outros",
      "observacao_estatistica": "Breve nota descritiva se houver alguma particularidade visível no documento"
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
    Envia a imagem ou PDF diretamente para a API Gemini (REST v1beta) com structured JSON.
    """
    if not api_key:
        raise ValueError("Chave da API Gemini não informada.")

    # Codificar arquivo em Base64
    b64_data = base64.b64encode(arquivo_bytes).decode("ascii")

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    },
                    {
                        "text": PROMPT_SISTEMA
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
    }
    
    json_bytes = json.dumps(payload).encode("utf-8")
    ultimo_erro = None

    for modelo_nome in MODELOS_DISPONIVEIS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo_nome}:generateContent?key={api_key.strip()}"
        req = urllib.request.Request(
            url,
            data=json_bytes,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                resposta_api = json.loads(resp.read().decode("utf-8"))
                
                candidatos = resposta_api.get("candidates", [])
                if not candidatos:
                    continue
                    
                partes = candidatos[0].get("content", {}).get("parts", [])
                if not partes:
                    continue
                    
                texto_resposta = partes[0].get("text", "").strip()
                
                # Limpar eventuais blocos markdown `json ... `
                texto_limpo = re.sub(r"^`(?:json)?\s*", "", texto_resposta, flags=re.MULTILINE)
                texto_limpo = re.sub(r"\s*`$", "", texto_limpo, flags=re.MULTILINE).strip()
                
                dados = json.loads(texto_limpo)
                
                # Higienização de segurança pós-extração
                raw_hosp = sanitizar_texto(dados.get("hospital_ou_prestador", ""))
                if raw_hosp.lower() in ["não informado", "nao informado", "null", "none", "não identificado", "nao identificado"]:
                    raw_hosp = ""
                dados["hospital_ou_prestador"] = raw_hosp

                raw_data = sanitizar_texto(dados.get("data_evento", ""))
                fmt_data, eh_valida = formatar_data_inteligente(raw_data)
                dados["data_evento"] = fmt_data if eh_valida else ""

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
                
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")
                ultimo_erro = f"HTTP {e.code}: {err_body}"
            except Exception:
                ultimo_erro = f"HTTP {e.code}: {e.reason}"
            continue
        except Exception as e:
            ultimo_erro = str(e)
            continue

    return {
        "sucesso": False,
        "erro": f"Não foi possível processar o documento com os modelos Gemini disponíveis: {ultimo_erro}"
    }

def transcrever_audio_com_gemini(audio_bytes: bytes, mime_type: str, api_key: str) -> str:
    """
    Transcreve com IA o relato falado do colega via Gemini REST v1beta.
    """
    if not api_key:
        return ""

    b64_audio = base64.b64encode(audio_bytes).decode("ascii")
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_audio
                        }
                    },
                    {
                        "text": "Transcreva fielmente o conteúdo deste áudio em português. Retorne apenas o texto transcrito, sem comentários, introduções ou aspas."
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1
        }
    }
    json_bytes = json.dumps(payload).encode("utf-8")

    for modelo_nome in MODELOS_DISPONIVEIS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo_nome}:generateContent?key={api_key.strip()}"
        req = urllib.request.Request(
            url,
            data=json_bytes,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resposta_api = json.loads(resp.read().decode("utf-8"))
                candidatos = resposta_api.get("candidates", [])
                if candidatos:
                    texto = candidatos[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    return sanitizar_texto(texto.strip())
        except Exception:
            continue
            
    return ""

# 📊 Observatório Amostral de Faturamentos — Plano SC

Plataforma web colaborativa e segura, desenhada para coletar, anonimizar e consolidar comprovantes de despesas médicas e demonstrativos de coparticipação de usuários do **Plano SC**.

O objetivo desta iniciativa é **estritamente estatístico, atuarial e pericial**, fornecendo uma base amostral robusta para o estudo detalhado da composição de custos hospitalares, sem conotação alarmista ou punitiva.

---

## 🚀 Principais Funcionalidades

1. **Intake Inteligente com IA Multimodal (Google Gemini):**
   - Extrai automaticamente tabelas de itens de saúde a partir de capturas de tela do aplicativo do Plano SC (ou arquivos PDF).
   - Identifica hospital, data, descrição do item, quantidade, coparticipação retida e valor faturado pelo credenciado.
2. **Anonimização Estrita e Conformidade com a LGPD:**
   - Supressão imediata de nomes de beneficiários, CPFs, e-mails, telefones e matrículas antes de qualquer persistência.
   - Geração de protocolos anônimos por unidade da federação (ex: CASO-SC-SP-2026-X8F2).
3. **Validação Humana Interativa:**
   - O colega revisa os valores extraídos pela inteligência artificial antes de confirmar a submissão.
4. **Painel do Estudo & Exportação Direta:**
   - Gráficos agregados por estado e categoria de despesa.
   - Exportação em um clique da base consolidada em Excel (.xlsx), pronta para plugar nos pipelines de auditoria e benchmarking de mercado (CMED, SIMPRO, distribuidores).

---

## 🛠️ Como Executar Localmente

### 1. Pré-requisitos
- Python 3.10 ou superior instalado.

### 2. Instalação das Dependências
`ash
pip install -r requirements.txt
`

### 3. Configuração dos Segredos (.streamlit/secrets.toml)
Crie o arquivo .streamlit/secrets.toml a partir do modelo de exemplo:
`	oml
GEMINI_API_KEY = "sua_chave_gemini_aqui"
`

### 4. Inicialização do Servidor Web
`ash
streamlit run app.py
`
Acesse http://localhost:8501 no seu navegador.

---

## ☁️ Como Publicar Gratuitamente no Streamlit Community Cloud

A aplicação foi projetada para rodar com **custo financeiro zero (R$ 0,00)** no Streamlit Community Cloud:

1. Faça o commit e push dos arquivos deste repositório para o seu GitHub:
   `ash
   git add .
   git commit -m "feat: estrutura inicial da plataforma de levantamento amostral"
   git push origin main
   `
2. Acesse [share.streamlit.io](https://share.streamlit.io) e faça login com sua conta do GitHub.
3. Clique em **"New app"** e selecione:
   - **Repository:** econs1312/plano-sc
   - **Branch:** main
   - **Main file path:** pp.py
4. Em **Advanced Settings** -> **Secrets**, cole a sua chave da API Gemini:
   `	oml
   GEMINI_API_KEY = "sua_chave_gemini_aqui"
   `
5. Clique em **"Deploy"**. Em cerca de 2 minutos você terá uma URL pública gratuita (com HTTPS) pronta para compartilhar com os colegas.

---

## 🔒 Governança e Diretrizes de Privacidade

- **Denominação Exclusiva:** Refere-se estritamente ao termo "Plano SC".
- **Proteção de Segredos:** O arquivo .streamlit/secrets.toml e o banco de dados data/ estão listados no .gitignore para garantir que nenhuma chave ou dado não-anonimizado seja sincronizado no GitHub público.
